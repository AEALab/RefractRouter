"""本地 MoA 判例重判的确定性回归；评审用假 invoke，不发起任何 CLI 或網路呼叫。"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.replay_judge_moa import (MOA_POLICY, case_criteria, effective_policy, load_cases,
                                          override_codex_reviewer, repair_criterion_labels,
                                          replay_case, review_target, run, summarize)
from refractrouter.quality_calibration import parse_review
from refractrouter.quality_study import digest

THRESHOLDS = {'verdict_agreement_min': 0.925234, 'criterion_agreement_min': 0.950935,
              'risk_direction_max': 0.037383}
MOA_POLICY_DIGEST = 'b591b0f80635a0d771e7c0360581dba3f97b7638c6c7e1ef26494be2fc3d0d92'


def _messages(case_id, criteria):
    payload = {'mode': '交付结果评审', 'task': {'task_id': 't1'},
               'candidate_output': case_id, 'criteria': list(criteria)}
    return [{'role': 'system', 'content': '你是辅助研究评审模型。'},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]


def _case(case_id, *, delivery, research, criteria=('c1', 'c2'), arm='direct-strong', repeat=1):
    messages = _messages(case_id, criteria)
    recorded = {}
    for stage, verdict in (('delivery-judge', delivery), ('research-judge', research)):
        recorded[stage] = {'verdict': verdict, 'charged_afp': 1.5,
                           'criteria': {name: verdict for name in criteria}}
    return {'case_id': case_id, 'run_id': case_id, 'task_id': 't1', 'arm': arm, 'repeat': repeat,
            'request': {'messages': messages, 'payload_sha256': 'sha-' + case_id,
                        'identical_between_judges': True},
            'recorded': recorded}


def _write_cases(tmp_path, cases):
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps({'schema_version': 'judge-replay-v1', 'cases': cases},
                               ensure_ascii=False))
    return path


def _invoke(verdict_for, calls, *, exit_code=0):
    """假 invoke：verdict_for(candidate_output, criterion) 決定每個 criterion 的判定。"""
    def invoke(reviewer, messages, schema=None):
        calls.append(reviewer['reviewer_id'])
        if exit_code != 0:
            return exit_code, '', '合成失敗', 1.0, None
        payload = json.loads(messages[-1]['content'])
        rows = [{'criterion': name,
                 'verdict': verdict_for(payload['candidate_output'], name),
                 'rationale': '合成理由'} for name in payload['criteria']]
        verdicts = {row['verdict'] for row in rows}
        overall = 'fail' if 'fail' in verdicts else 'pending' if 'pending' in verdicts else 'pass'
        body = {'verdict': overall, 'rationale': '合成理由', 'criteria': rows}
        return 0, json.dumps(body, ensure_ascii=False), '', 1.0, None
    return invoke


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.socket', side_effect=AssertionError('本测试不得发起付费调用')):
        yield


def test_agreement_with_both_references_yields_replace_decision(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass'),
             _case('case-2', delivery='fail', research='fail')]
    cases_path = _write_cases(tmp_path, cases)
    calls = []
    decided = {'case-1': 'pass', 'case-2': 'fail'}
    records = run(cases_path, tmp_path / 'out',
                  invoke=_invoke(lambda case_id, name: decided[case_id], calls))
    summary = summarize(records, THRESHOLDS)

    assert len(calls) == 4
    assert summary['case_count'] == 2
    assert summary['decision'] == 'replace'
    assert summary['checks']['delivery-judge']['all_ok'] is True
    assert summary['primary']['research-judge']['verdict_agreement'] == 1.0
    assert summary['moa_review_cost']['ark_afp'] == 0


def test_ark_fail_candidate_pass_blocks_replacement(tmp_path):
    cases = [_case('case-1', delivery='fail', research='fail', criteria=('c1',))]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out',
                  invoke=_invoke(lambda case_id, name: 'pass', []))
    summary = summarize(records, THRESHOLDS)

    assert summary['primary']['delivery-judge']['ark_fail_candidate_pass'] == 1
    assert summary['primary']['delivery-judge']['risk_direction'] == 1.0
    assert summary['checks']['delivery-judge']['risk_direction_ok'] is False
    assert summary['decision'] == 'keep'


def test_reference_disagreement_cases_are_reported_separately(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass'),
             _case('case-2', delivery='fail', research='pass', criteria=('c1',))]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out',
                  invoke=_invoke(lambda case_id, name: 'pass', []))
    summary = summarize(records, THRESHOLDS)

    assert summary['excluding_reference_disagreements'] == 1
    assert summary['reference_disagreement_cases'] == ['case-2']
    assert summary['primary']['delivery-judge']['verdict_agreement'] == 1.0
    # 全量統計仍保留矛盾判例，避免用剔除掩蓋不一致
    assert summary['by_reference_all_cases']['delivery-judge']['verdict_pairs'] == {
        'fail -> pass': 1, 'pass -> pass': 1}


def test_limit_and_resume_do_not_repeat_work(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass'),
             _case('case-2', delivery='pass', research='pass')]
    cases_path = _write_cases(tmp_path, cases)
    out = tmp_path / 'out'
    first_calls = []
    run(cases_path, out, limit=1, invoke=_invoke(lambda case_id, name: 'pass', first_calls))
    assert len(first_calls) == 2

    second_calls = []
    records = run(cases_path, out, invoke=_invoke(lambda case_id, name: 'pass', second_calls))
    assert len(second_calls) == 2        # 只重跑尚未完成的第二例
    assert [record['case_id'] for record in records] == ['case-1', 'case-2']

    stored = json.loads((out / 'records.json').read_text())
    assert stored['schema_version'] == 'judge-moa-replay-v1'
    assert len(stored['records']) == 2


def test_force_reruns_completed_cases(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass')]
    cases_path = _write_cases(tmp_path, cases)
    out = tmp_path / 'out'
    run(cases_path, out, invoke=_invoke(lambda case_id, name: 'pass', []))
    calls = []
    run(cases_path, out, force=True, invoke=_invoke(lambda case_id, name: 'pass', calls))
    assert len(calls) == 2


def test_failed_cli_records_pending_and_stays_in_denominator(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass', criteria=('c1',))]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out',
                  invoke=_invoke(lambda case_id, name: 'pass', [], exit_code=1))
    summary = summarize(records, THRESHOLDS)

    assert records[0]['moa']['consensus']['overall'] == 'pending'
    assert summary['moa_review_cost']['failed_records'] == 2
    assert summary['primary']['delivery-judge']['verdict_pairs'] == {'pass -> pending': 1}


def test_missing_criteria_and_unknown_case_ids_are_rejected(tmp_path):
    broken = _case('case-1', delivery='pass', research='pass')
    payload = json.loads(broken['request']['messages'][-1]['content'])
    payload.pop('criteria')
    broken['request']['messages'][-1]['content'] = json.dumps(payload, ensure_ascii=False)
    cases_path = _write_cases(tmp_path, [broken])
    with pytest.raises(ValueError, match='criteria'):
        case_criteria(load_cases(cases_path)[0])

    good = _write_cases(tmp_path, [_case('case-1', delivery='pass', research='pass')])
    with pytest.raises(ValueError, match='找不到判例'):
        run(good, tmp_path / 'out', case_ids=['case-404'],
            invoke=_invoke(lambda case_id, name: 'pass', []))


def test_unknown_schema_is_rejected(tmp_path):
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps({'schema_version': 'other', 'cases': []}))
    with pytest.raises(ValueError, match='schema'):
        load_cases(path)


def test_parallel_reviewers_match_sequential_consensus():
    criteria = ['c1', 'c2']
    messages = _messages('case-1', criteria)
    sequential = review_target(messages, criteria,
                               _invoke(lambda case_id, name: 'pass', []), reviewer_workers=1)
    parallel_calls = []
    parallel = review_target(messages, criteria,
                             _invoke(lambda case_id, name: 'pass', parallel_calls),
                             reviewer_workers=2)

    assert len(parallel_calls) == 2
    assert [rec['reviewer_id'] for rec in parallel['primary']] == [
        rec['reviewer_id'] for rec in sequential['primary']]
    assert parallel['consensus']['overall'] == sequential['consensus']['overall'] == 'pass'
    assert parallel['consensus']['criteria'] == sequential['consensus']['criteria']


def test_escalation_runs_only_after_primary_disagreement():
    criteria = ['c1']
    messages = _messages('case-1', criteria)

    def reviewer_verdicts(verdicts, calls):
        def invoke(reviewer, messages, schema=None):
            calls.append(reviewer['reviewer_id'])
            verdict = verdicts[reviewer['reviewer_id']]
            rows = [{'criterion': 'c1', 'verdict': verdict, 'rationale': '合成理由'}]
            body = {'verdict': verdict, 'rationale': '合成理由', 'criteria': rows}
            return 0, json.dumps(body, ensure_ascii=False), '', 1.0, None
        return invoke

    split_escalation = []
    result = review_target(messages, criteria, reviewer_verdicts(
        {'ds-deepseek-v4-pro': 'pass', 'claude-opus': 'fail',
         'codex-kimi-k3': 'pass', 'claude-opus-max': 'fail'}, split_escalation),
        reviewer_workers=2)

    assert len(split_escalation) == 4        # 兩位初審加兩位升級
    assert result['consensus']['escalated_criteria'] == 1
    assert result['consensus']['overall'] == 'pending'

    agreeing_escalation = []
    settled = review_target(messages, criteria, reviewer_verdicts(
        {'ds-deepseek-v4-pro': 'pass', 'claude-opus': 'fail',
         'codex-kimi-k3': 'fail', 'claude-opus-max': 'fail'}, agreeing_escalation),
        reviewer_workers=2)

    assert len(agreeing_escalation) == 4
    assert settled['consensus']['overall'] == 'fail'


def test_records_keep_case_order_with_parallel_cases(tmp_path):
    cases = [_case(name, delivery='pass', research='pass')
             for name in ['case-1', 'case-2', 'case-3']]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out', case_workers=3,
                  invoke=_invoke(lambda case_id, name: 'pass', []))
    stored = json.loads((tmp_path / 'out' / 'records.json').read_text())['records']

    assert [record['case_id'] for record in records] == ['case-1', 'case-2', 'case-3']
    assert [record['case_id'] for record in stored] == ['case-1', 'case-2', 'case-3']


def test_summary_reports_reviewer_latency_against_gate_cap(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass')]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out',
                  invoke=_invoke(lambda case_id, name: 'pass', []))
    summary = summarize(records, THRESHOLDS)

    assert summary['online_gate_cap_seconds'] == 45
    latency = summary['reviewer_latency']
    assert latency['ds-deepseek-v4-pro'] == {'calls': 1, 'timed_calls': 1,
                                            'unavailable_calls': 0,
                                            'median_ms': 1.0, 'p90_ms': 1.0,
                                            'max_ms': 1.0, 'at_or_over_45s': 0}
    assert latency['claude-opus']['calls'] == 1
    assert 'claude-opus-max' not in latency      # 未升級就沒有升級位紀錄


def test_reviewer_unavailability_is_separated_from_disagreement(tmp_path):
    """額度或認證失敗的案例不該稀釋一致率，也不該被當成候選評審的反對證據。"""
    cases = [_case('case-1', delivery='pass', research='pass', criteria=('c1',)),
             _case('case-2', delivery='pass', research='pass', criteria=('c1',))]
    out = tmp_path / 'out'

    def invoke(reviewer, messages, schema=None):
        if json.loads(messages[-1]['content'])['candidate_output'] == 'case-1':
            return 1, '', 'session limit', 4.0, None
        return 0, _review_body([_row('c1')]), '', 12.0, None

    records = run(_write_cases(tmp_path, cases), out, invoke=invoke, reviewer_workers=1)
    summary = summarize(records, THRESHOLDS)

    assert summary['reviewer_unavailable_case_ids'] == ['case-1']
    assert summary['primary']['delivery-judge']['verdict_agreement'] == 0.5
    assert summary['primary_reviewers_available_only']['delivery-judge']['verdict_agreement'] == 1.0
    assert summary['decision'] == 'replace-pending-coverage'
    assert summary['decision_all_cases'] == 'keep'
    assert summary['decision_basis'] == {'case_count_used': 1,
                                         'excluded_reviewer_unavailable': 1,
                                         'excluded_reference_disagreements': 0,
                                         'coverage_complete': False}
    assert summary['parse_recovery']['reviewer_unavailable_cases'] == 1
    assert summary['reviewer_latency']['claude-opus'] == {'calls': 2, 'timed_calls': 1,
                                                          'unavailable_calls': 1,
                                                          'median_ms': 12.0, 'p90_ms': 12.0,
                                                          'max_ms': 12.0, 'at_or_over_45s': 0}


def test_only_unavailable_cases_yield_insufficient_decision(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass', criteria=('c1',))]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out',
                  invoke=_invoke(lambda case_id, name: 'pass', [], exit_code=1),
                  reviewer_workers=1)
    summary = summarize(records, THRESHOLDS)

    assert summary['decision'] == 'insufficient'
    assert summary['decision_basis']['case_count_used'] == 0
    assert summary['checks_reviewers_available_only']['delivery-judge']['all_ok'] is False
    assert summary['reviewer_latency']['claude-opus'] == {'calls': 1, 'timed_calls': 0,
                                                          'unavailable_calls': 1}


def test_by_reviewer_agreement_uses_only_completed_rows(tmp_path):
    """單一評審者對照只用該評審者真的跑完的案例，未跑完的一律不列入。"""
    cases = [_case('case-1', delivery='pass', research='pass', criteria=('c1',)),
             _case('case-2', delivery='fail', research='fail', criteria=('c1',))]

    def invoke(reviewer, messages, schema=None):
        case_id = json.loads(messages[-1]['content'])['candidate_output']
        if reviewer['cli'] == 'claude':
            return 1, '', 'session limit', 4.0, None
        return 0, _review_body([_row('c1', 'pass' if case_id == 'case-1' else 'fail')]), '', 12.0, None

    records = run(_write_cases(tmp_path, cases), tmp_path / 'out', invoke=invoke,
                  reviewer_workers=1)
    summary = summarize(records, THRESHOLDS)

    codex = summary['by_reviewer_agreement']['ds-deepseek-v4-pro']['delivery-judge']
    assert codex['reviewed_cases'] == 2
    assert codex['verdict_agreement'] == 1.0
    assert codex['criterion_agreement'] == 1.0
    assert 'claude-opus' not in summary['by_reviewer_agreement']


CRITERION_A = '正文与结构化结论一致且未反写依赖或扩大证据含义'
CRITERION_B = '必需结论完整、事实正确且各自引用足以支持主张'
CRITERION_A_REWRITTEN = '正文与结构化结论一致且未反写依赖或夸大证据含义'


def _review_body(rows):
    verdicts = {row['verdict'] for row in rows}
    overall = 'fail' if 'fail' in verdicts else 'pending' if 'pending' in verdicts else 'pass'
    return json.dumps({'verdict': overall, 'rationale': '合成理由', 'criteria': rows},
                      ensure_ascii=False)


def _row(criterion, verdict='pass'):
    return {'criterion': criterion, 'verdict': verdict, 'rationale': '合成理由'}


def test_label_repair_maps_near_synonym_back_to_source_criteria():
    body = _review_body([_row(CRITERION_A_REWRITTEN, 'fail'), _row(CRITERION_B)])
    repaired, repair = repair_criterion_labels(body, [CRITERION_A, CRITERION_B])

    assert repair['status'] == 'repaired'
    assert len(repair['repairs']) == 1
    assert repair['repairs'][0]['returned'] == CRITERION_A_REWRITTEN
    assert repair['repairs'][0]['matched'] == CRITERION_A
    assert repair['repairs'][0]['ratio'] >= 0.8
    parsed = parse_review(repaired, [CRITERION_A, CRITERION_B])
    # 修補只改標籤文字，判定方向不得改變
    assert parsed['verdict'] == 'fail'
    assert {row['criterion'] for row in parsed['criteria']} == {CRITERION_A, CRITERION_B}


def test_label_repair_keeps_exact_output_untouched():
    body = _review_body([_row(CRITERION_A), _row(CRITERION_B)])
    repaired, repair = repair_criterion_labels(body, [CRITERION_A, CRITERION_B])

    assert repair == {'status': 'exact', 'repairs': []}
    assert repaired == body


def test_label_repair_refuses_ambiguous_mismatched_or_unparsable_output():
    ambiguous = _review_body([_row('准则甲'), _row('准则乙')])
    text, repair = repair_criterion_labels(ambiguous, ['准则甲', '准则丙'])
    assert repair['status'] == 'unmatched'
    assert text == ambiguous

    short = _review_body([_row('准则甲')])
    text, repair = repair_criterion_labels(short, ['准则甲', '准则乙'])
    assert repair['status'] == 'count-mismatch'
    assert repair['returned_count'] == 1
    assert text == short

    text, repair = repair_criterion_labels('这不是 JSON', ['准则甲'])
    assert repair['status'] == 'unparsed'
    assert text == '这不是 JSON'


def _rewriting_invoke():
    """模擬 codex 側候選評審者把 criterion 標籤寫成近義詞（真實觀測到的行為）。"""
    def invoke(reviewer, messages, schema=None):
        criteria = json.loads(messages[-1]['content'])['criteria']
        rows = [_row(name.replace('扩大', '夸大') if reviewer['cli'] == 'codex' else name)
                for name in criteria]
        return 0, _review_body(rows), '', 1.0, None
    return invoke


def test_strict_mode_marks_paraphrased_labels_pending(tmp_path):
    case = _case('case-1', delivery='pass', research='pass',
                 criteria=(CRITERION_A, CRITERION_B))
    record = replay_case(case, _rewriting_invoke(), reviewer_workers=1)

    assert record['moa']['consensus']['overall'] == 'pending'
    assert record['moa']['primary'][0]['status'] == 'failed'
    assert 'coverage mismatch' in record['moa']['primary'][0]['error']
    assert record['label_repairs'] == {}


def test_label_repair_recovers_case_and_keeps_original_response():
    case = _case('case-1', delivery='pass', research='pass',
                 criteria=(CRITERION_A, CRITERION_B))
    record = replay_case(case, _rewriting_invoke(), reviewer_workers=1, repair_labels=True)

    assert record['moa']['consensus']['overall'] == 'pass'
    row = record['moa']['primary'][0]
    assert CRITERION_A_REWRITTEN in row['raw_response']          # 原始證據保留
    assert CRITERION_A in row['repaired_response']
    assert row['response_sha256'] == digest(row['raw_response'])
    assert record['label_repairs']['ds-deepseek-v4-pro']['status'] == 'repaired'
    # 標籤原文正確的評審者不寫入修補欄位
    assert 'repaired_response' not in record['moa']['primary'][1]
    assert 'claude-opus' not in record['label_repairs']


def test_run_header_and_summary_record_parse_mode(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass')]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out', repair_labels=True,
                  invoke=_invoke(lambda case_id, name: 'pass', []))
    stored = json.loads((tmp_path / 'out' / 'records.json').read_text())
    summary = summarize(records, THRESHOLDS, parse_mode=stored['parse_mode'])

    assert stored['parse_mode'] == 'labels-repaired'
    assert summary['parse_mode'] == 'labels-repaired'
    assert summary['parse_recovery'] == {'cases_with_label_issues': 0,
                                         'by_reviewer_status': {}, 'pending_overall': 0,
                                         'reviewer_unavailable_cases': 0,
                                         'strict_failures_by_repair_status': {},
                                         'strict_failures_unrecoverable_count': 0,
                                         'strict_failures_unrecoverable': []}


def test_summary_counts_ark_escalation_calls(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass', criteria=('c1',))]
    verdicts = {'ds-deepseek-v4-pro': 'pass', 'claude-opus': 'fail',
                'codex-kimi-k3': 'pass', 'claude-opus-max': 'pass'}

    def invoke(reviewer, messages, schema=None):
        return 0, _review_body([_row('c1', verdicts[reviewer['reviewer_id']])]), '', 1.0, None

    records = run(_write_cases(tmp_path, cases), tmp_path / 'out', invoke=invoke)
    summary = summarize(records, THRESHOLDS)

    assert summary['moa_review_cost']['codex_cli_escalation_calls'] == 1
    assert summary['moa_review_cost']['ark_afp'] == 0


def test_codex_reviewer_override_replaces_model_and_keeps_claude_side():
    updated, changed = override_codex_reviewer(MOA_POLICY, 'primary', 'ds/deepseek-flash:high')

    assert updated['primary'][0]['model'] == 'ds/deepseek-flash'
    assert updated['primary'][0]['thinking_effort'] == 'high'
    assert updated['primary'][0]['reviewer_id'] == 'codex-ds-deepseek-flash-high'
    assert updated['primary'][1] == MOA_POLICY['primary'][1]        # claude 側不動
    assert changed[0]['before']['model'] == 'ds/deepseek-v4-pro'
    assert digest(updated) != digest(MOA_POLICY)
    with pytest.raises(ValueError, match='覆寫規格缺少模型'):
        override_codex_reviewer(MOA_POLICY, 'escalation', '')
    claude_only = {'primary': [MOA_POLICY['primary'][1]], 'escalation': []}
    with pytest.raises(ValueError, match='沒有 codex 側評審者'):
        override_codex_reviewer(claude_only, 'primary', 'ds/deepseek-flash:high')


def test_effective_policy_without_override_keeps_frozen_digest():
    policy, overrides = effective_policy()

    assert overrides == []
    assert digest(policy) == digest(MOA_POLICY)
    assert digest(policy) == MOA_POLICY_DIGEST


def test_run_header_records_policy_overrides(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass')]
    policy, overrides = effective_policy('ds/deepseek-flash:high')
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out', policy=policy,
                  policy_overrides=overrides, invoke=_invoke(lambda case_id, name: 'pass', []))
    stored = json.loads((tmp_path / 'out' / 'records.json').read_text())

    assert stored['policy_sha256'] == digest(policy)
    assert stored['frozen_policy_sha256'] == MOA_POLICY_DIGEST
    assert stored['policy_overrides'][0]['after']['model'] == 'ds/deepseek-flash'
    assert records[0]['moa']['policy_sha256'] == digest(policy)
    # 覆寫後 reviewer_id 改變，延遲統計跟著用新身分
    summary = summarize(records, THRESHOLDS, policy=policy)
    assert 'codex-ds-deepseek-flash-high' in summary['reviewer_latency']
    assert 'ds-deepseek-v4-pro' not in summary['reviewer_latency']


def test_summary_reports_clean_subset_apart_from_repaired_cases(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass',
                   criteria=(CRITERION_A, CRITERION_B)),
             _case('case-2', delivery='pass', research='pass',
                   criteria=(CRITERION_A, CRITERION_B))]
    out = tmp_path / 'out'
    records = run(_write_cases(tmp_path, cases), out, repair_labels=True,
                  invoke=_rewriting_invoke(), reviewer_workers=1)
    summary = summarize(records, THRESHOLDS, parse_mode='labels-repaired')

    assert summary['case_count'] == 2
    assert summary['clean_case_count'] == 0            # 兩例都動用了標籤修補
    assert all(record['moa']['primary'][0]['strict_status'] == 'failed' for record in records)
    assert summary['parse_recovery']['by_reviewer_status'] == {
        'ds-deepseek-v4-pro / repaired': 2}


def test_summary_reports_strict_failures_recoverable_by_label_repair(tmp_path):
    """嚴格模式下解析失敗的案例，要用零調用的事後檢查分出可修補與不可修補。"""
    cases = [_case('case-1', delivery='pass', research='pass',
                   criteria=(CRITERION_A, CRITERION_B))]
    records = run(_write_cases(tmp_path, cases), tmp_path / 'out',
                  invoke=_rewriting_invoke(), reviewer_workers=1)
    summary = summarize(records, THRESHOLDS)

    assert records[0]['moa']['consensus']['overall'] == 'pending'
    assert summary['parse_recovery']['strict_failures_by_repair_status'] == {
        'ds-deepseek-v4-pro / repaired': 1}
    assert summary['parse_recovery']['strict_failures_unrecoverable_count'] == 0
    assert summary['parse_recovery']['strict_failures_unrecoverable'] == []


def test_summary_lists_unrecoverable_parse_failures(tmp_path):
    cases = [_case('case-1', delivery='pass', research='pass', criteria=('c1',))]

    def invoke(reviewer, messages, schema=None):
        if reviewer['cli'] == 'claude':
            return 0, 'not-json-at-all', '', 9.0, None
        return 0, _review_body([_row('c1')]), '', 9.0, None

    records = run(_write_cases(tmp_path, cases), tmp_path / 'out', invoke=invoke,
                  reviewer_workers=1)
    summary = summarize(records, THRESHOLDS)

    assert summary['parse_recovery']['strict_failures_by_repair_status'] == {
        'claude-opus / unparsed': 1}
    assert summary['parse_recovery']['strict_failures_unrecoverable_count'] == 1
    listed = summary['parse_recovery']['strict_failures_unrecoverable'][0]
    assert listed['case_id'] == 'case-1'
    assert listed['reviewer_id'] == 'claude-opus'
    assert listed['status'] == 'unparsed'
