"""MoA 评审模块的确定性测试；全部使用注入的模拟 CLI，不发起真实模型调用。"""
import json
from pathlib import Path

import pytest

from refractrouter.moa_review import (MOA_POLICY, REVIEW_SCHEMA, aggregate,
    MOA_MATERIAL_CRITERIA, calibration_review, claude_command, codex_command, final_quality_status, judge,
    material_review, output_messages, output_review, preflight_envelope, purpose_review,
    summarize_calibration,
    run_review_target)
from refractrouter.quality_study import digest, load_study

STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


def review_json(verdict, criteria, *, suffix=''):
    return json.dumps({'verdict': verdict, 'rationale': f'模拟依据{suffix}',
                       'criteria': [{'criterion': c, 'verdict': verdict,
                                     'rationale': f'模拟依据{suffix}'} for c in criteria]},
                      ensure_ascii=False)


def fake_invoke(responses):
    calls = []

    def invoke(reviewer, messages, schema=None):
        calls.append({'reviewer_id': reviewer['reviewer_id'], 'messages': messages})
        return 0, responses[reviewer['reviewer_id']], '', 120.0, 'test-version'

    return invoke, calls


def test_both_primary_pass_no_escalation():
    criteria = ['甲', '乙']
    responses = {r['reviewer_id']: review_json('pass', criteria) for r in MOA_POLICY['primary']}
    responses.update({r['reviewer_id']: review_json('pending', criteria) for r in MOA_POLICY['escalation']})
    invoke, calls = fake_invoke(responses)
    record = run_review_target([{'role': 'user', 'content': '{}'}], criteria, invoke)
    assert record['consensus']['overall'] == 'pass'
    assert record['consensus']['escalated_criteria'] == 0
    assert record['escalation'] == []
    assert [c['reviewer_id'] for c in calls] == [r['reviewer_id'] for r in MOA_POLICY['primary']]


def test_disagreement_escalates_and_escalation_wins():
    criteria = ['甲', '乙']
    responses = {
        MOA_POLICY['primary'][0]['reviewer_id']: review_json('pass', criteria),
        MOA_POLICY['primary'][1]['reviewer_id']: review_json('fail', criteria),
        MOA_POLICY['escalation'][0]['reviewer_id']: review_json('fail', criteria),
        MOA_POLICY['escalation'][1]['reviewer_id']: review_json('fail', criteria),
    }
    invoke, calls = fake_invoke(responses)
    record = run_review_target([{'role': 'user', 'content': '{}'}], criteria, invoke)
    assert record['consensus']['overall'] == 'fail'
    assert record['consensus']['escalated_criteria'] == 2
    assert len(record['escalation']) == 2
    assert [c['reviewer_id'] for c in calls] == [r['reviewer_id'] for r in
                                                 MOA_POLICY['primary'] + MOA_POLICY['escalation']]
    for row in record['consensus']['criteria']:
        assert row['verdict'] == 'fail' and row['escalated'] is True


def test_escalation_disagreement_stays_pending():
    criteria = ['甲']
    responses = {
        MOA_POLICY['primary'][0]['reviewer_id']: review_json('pass', criteria),
        MOA_POLICY['primary'][1]['reviewer_id']: review_json('fail', criteria),
        MOA_POLICY['escalation'][0]['reviewer_id']: review_json('pass', criteria),
        MOA_POLICY['escalation'][1]['reviewer_id']: review_json('fail', criteria),
    }
    invoke, _ = fake_invoke(responses)
    record = run_review_target([{'role': 'user', 'content': '{}'}], criteria, invoke)
    assert record['consensus']['overall'] == 'pending'
    assert record['consensus']['criteria'][0]['verdict'] == 'pending'


def test_primary_partial_failure_escalates_and_missing_escalation_pending():
    criteria = ['甲']
    responses = {
        MOA_POLICY['primary'][0]['reviewer_id']: review_json('pass', criteria),
        MOA_POLICY['primary'][1]['reviewer_id']: review_json('fail', criteria),
        MOA_POLICY['escalation'][0]['reviewer_id']: review_json('fail', criteria),
        MOA_POLICY['escalation'][1]['reviewer_id']: review_json('pass', criteria),
    }
    invoke, _ = fake_invoke(responses)
    record = run_review_target([{'role': 'user', 'content': '{}'}], criteria, invoke)
    assert record['consensus']['overall'] == 'pending'


def test_invalid_review_is_failed_and_pending():
    criteria = ['甲']
    responses = {r['reviewer_id']: '不是 JSON' for r in MOA_POLICY['primary']}
    responses.update({r['reviewer_id']: '不是 JSON' for r in MOA_POLICY['escalation']})
    invoke, _ = fake_invoke(responses)
    record = run_review_target([{'role': 'user', 'content': '{}'}], criteria, invoke)
    assert all(r['status'] == 'failed' for r in record['primary'])
    assert record['consensus']['overall'] == 'pending'
    assert record['consensus']['failed_records'] == 2


def test_code_fenced_json_is_parsed():
    """模型把 JSON 包在 Markdown 代码围栏中时，剥离围栏后仍应正常解析。"""
    criteria = ['甲', '乙']
    def fenced(verdict):
        return '```json\n' + review_json(verdict, criteria) + '\n```'
    responses = {r['reviewer_id']: fenced('pass') for r in MOA_POLICY['primary']}
    invoke, _ = fake_invoke(responses)
    record = run_review_target([{'role': 'user', 'content': '{}'}], criteria, invoke)
    assert all(p['status'] == 'reviewed' for p in record['primary'])
    assert record['consensus']['overall'] == 'pass'


def test_cli_commands_include_model_and_effort():
    primary_codex = MOA_POLICY['primary'][0]
    primary_claude = MOA_POLICY['primary'][1]
    schema = Path('/tmp/schema.json'); out = Path('/tmp/last.txt')
    schema_json = json.dumps(REVIEW_SCHEMA, ensure_ascii=False, separators=(',', ':'))
    codex_args = codex_command(primary_codex, out, schema)
    assert codex_args[:2] == ['codex', 'exec']
    assert '--ignore-user-config' not in codex_args
    assert primary_codex['model'] in codex_args
    assert f'model_reasoning_effort={primary_codex["thinking_effort"]}' in codex_args
    assert 'request_max_retries=0' in codex_args
    assert 'stream_max_retries=0' in codex_args
    assert str(out) in codex_args
    assert '--output-schema' not in codex_args
    assert MOA_POLICY['primary'][0]['output_schema'] is False
    assert MOA_POLICY['codex_cli']['ignore_user_config'] is False
    assert MOA_POLICY['codex_cli']['request_max_retries'] == 0
    assert MOA_POLICY['codex_cli']['stream_max_retries'] == 0
    claude_args = claude_command(primary_claude, schema_json)
    assert claude_args[:2] == ['claude', '-p']
    assert primary_claude['model'] in claude_args
    assert f'--effort' in claude_args and primary_claude['thinking_effort'] in claude_args
    assert '--tools' in claude_args and '' in claude_args
    assert '--json-schema' in claude_args
    assert claude_args[claude_args.index('--json-schema') + 1] == schema_json
    assert MOA_POLICY['claude_cli']['json_schema'] == 'inline-json'


def test_codex_output_schema_is_reviewer_capability():
    schema = Path('/tmp/schema.json'); out = Path('/tmp/last.txt')
    primary_codex = MOA_POLICY['primary'][0]
    escalation_codex = MOA_POLICY['escalation'][0]
    gpt_style = {'reviewer_id': 'probe-gpt', 'cli': 'codex', 'model': 'gpt-x',
                 'thinking_effort': 'high', 'output_schema': True}
    assert '--output-schema' not in codex_command(primary_codex, out, schema)
    assert '--output-schema' not in codex_command(escalation_codex, out, schema)
    assert '--output-schema' in codex_command(gpt_style, out, schema)


def test_judge_records_binding_and_policy():
    criteria = ['甲']
    messages = [{'role': 'user', 'content': 'payload'}]
    invoke, _ = fake_invoke({MOA_POLICY['primary'][0]['reviewer_id']: review_json('pass', criteria)})
    record = judge(MOA_POLICY['primary'][0], messages, criteria, invoke)
    assert record['status'] == 'reviewed'
    assert record['origin'] == 'model'
    assert record['prompt_sha256'] == digest(messages)
    assert record['response_sha256'] == digest(review_json('pass', criteria))


def test_deterministic_fail_overrides_consensus():
    assert final_quality_status('fail', 'pass') == 'fail'
    assert final_quality_status('pass', 'fail') == 'fail'
    assert final_quality_status('unverified', 'pass') == 'pass'
    assert final_quality_status('pass', 'pending') == 'pending'


def test_material_and_output_review_bindings_with_mock():
    _, tasks, refs, *_ = load_study(STUDY)
    selected = tasks[:2]
    criteria_material = list(MOA_MATERIAL_CRITERIA)
    responses = {}
    for reviewer in MOA_POLICY['primary'] + MOA_POLICY['escalation']:
        responses[reviewer['reviewer_id']] = review_json('pass', criteria_material)
    invoke, calls = fake_invoke(responses)
    records = material_review(selected, refs, invoke)
    assert len(records) == 2
    for record, task in zip(records, selected):
        assert record['task_sha256'] == task['task_sha256']
        assert record['reference_sha256'] == digest(refs[task['task_id']])
        assert record['consensus']['overall'] == 'pass'
        assert record['policy_sha256'] == digest(MOA_POLICY)
    assert len(calls) == 2 * 2  # 两位初审，无分歧所以不升级

    rows = [{'run_id': 'r1', 'task_id': selected[0]['task_id'],
             'output': refs[selected[0]['task_id']]['author_reference']}]
    _, criteria_output = output_messages(selected[0], rows[0]['output'])
    responses = {}
    for reviewer in MOA_POLICY['primary'] + MOA_POLICY['escalation']:
        responses[reviewer['reviewer_id']] = review_json('pass', criteria_output)
    invoke, calls = fake_invoke(responses)
    records = output_review(selected, refs, rows, invoke)
    assert len(records) == 1
    assert records[0]['output_sha256'] == digest(rows[0]['output'])
    assert records[0]['task_sha256'] == selected[0]['task_sha256']
    assert records[0]['consensus']['overall'] == 'pass'


def test_calibration_review_reports_moa_and_final_gate_metrics():
    _, tasks, refs, controls, *_ = load_study(STUDY)
    criteria_by_case = {}
    responses = {}
    for case in controls:
        task = next(t for t in tasks if t['task_id'] == case['task_id'])
        _, criteria = output_messages(task, case['output'])
        criteria_by_case[case['case_id']] = criteria
    for reviewer in MOA_POLICY['primary'] + MOA_POLICY['escalation']:
        # 初审一致 pass，因此不会升级；用于验证指标结构而不模拟真实模型判断。
        if reviewer in MOA_POLICY['primary']:
            responses[reviewer['reviewer_id']] = {
                case_id: review_json('pass', criteria)
                for case_id, criteria in criteria_by_case.items()
            }

    calls = []
    def invoke(reviewer, messages, schema=None):
        payload = json.loads(messages[1]['content'])
        case_id = payload['candidate_output']['case_id_for_test']
        calls.append(reviewer['reviewer_id'])
        return (0, responses[reviewer['reviewer_id']][case_id], '', 10.0, 'test')

    # output_messages 不接受额外字段；这里用内存副本注入测试用 case_id。
    original_controls = [dict(case, output=dict(case['output'],
                                                 case_id_for_test=case['case_id']))
                         for case in controls]
    records = calibration_review(tasks, refs, original_controls, invoke)
    summary = summarize_calibration(records)
    assert len(records) == 19
    assert summary['author_label_counts'] == {'acceptable': 12, 'unacceptable': 7}
    assert summary['deterministic_status_counts']['fail'] == 5
    assert summary['deterministic_expectation_mismatches'] == []
    assert summary['moa_false_accepts'] == 7
    assert summary['final_false_accepts'] == 2
    assert summary['final_false_rejects'] == 0
    assert summary['actual_calls'] == 38
    assert len(calls) == 38
    for record in records:
        assert record['policy_sha256'] == digest(MOA_POLICY)
        assert record['output_sha256'] == digest(next(
            c['output'] for c in original_controls if c['case_id'] == record['case_id']))


def test_purpose_review_binds_policy():
    policy_sha = 'abc'; bindings = {'t1': 'hash1'}
    responses = {}
    for reviewer in MOA_POLICY['primary'] + MOA_POLICY['escalation']:
        responses[reviewer['reviewer_id']] = review_json('pass', ['研究用途与质量、非劣、样本量和失败标准相符'])
    invoke, _ = fake_invoke(responses)
    record = purpose_review(policy_sha, bindings, invoke=invoke)
    assert record['consensus']['overall'] == 'pass'
    assert record['policy_sha256'] == digest(MOA_POLICY)
    assert record['statistics_policy_sha256'] == policy_sha
    assert record['task_bindings'] == bindings


def test_preflight_envelope_is_zero_call_and_frozen():
    envelope = preflight_envelope('material', list(range(18)))
    assert envelope['real_model_calls'] == 0
    assert envelope['maximum_calls'] == 18 * 4
    assert envelope['timeout_sum_seconds'] == 18 * 4 * MOA_POLICY['timeout_seconds']
    assert envelope['policy_sha256'] == digest(MOA_POLICY)


def test_cli_preflight_is_zero_call(tmp_path):
    from experiments.run_moa_review import main
    output = tmp_path / 'moa-preflight'
    main(['--kind', 'material', '--study-dir', str(STUDY), '--output-dir', str(output), '--preflight'])
    preflight = json.loads((output / 'preflight.json').read_text())
    assert preflight['envelope']['real_model_calls'] == 0
    assert preflight['envelope']['targets'] == 18
    assert preflight['envelope']['maximum_calls'] == 18 * 4
    assert preflight['policy']['schema_version'] == 'moa-review-policy-v1'
    assert preflight['policy']['primary'][0]['thinking_effort'] == 'max'
    assert preflight['policy']['primary'][1]['thinking_effort'] == 'high'
    assert preflight['policy']['escalation'][0]['thinking_effort'] == 'high'
    assert preflight['policy']['escalation'][1]['thinking_effort'] == 'max'


def test_calibration_cli_preflight_is_zero_call(tmp_path):
    from experiments.run_moa_review import main
    output = tmp_path / 'moa-calibration-preflight'
    main(['--kind', 'calibration', '--study-dir', str(STUDY),
          '--output-dir', str(output), '--preflight'])
    preflight = json.loads((output / 'preflight.json').read_text())
    assert preflight['envelope']['kind'] == 'calibration'
    assert preflight['envelope']['real_model_calls'] == 0
    assert preflight['envelope']['targets'] == 19
    assert preflight['envelope']['maximum_calls'] == 19 * 4
    assert len(preflight['targets']) == 19
    assert len({row['case_id'] for row in preflight['targets']}) == 19


def test_calibration_cli_live_reuses_preflight_directory(tmp_path, monkeypatch):
    from experiments import run_moa_review
    output = tmp_path / 'moa-calibration-live'
    run_moa_review.main(['--kind', 'calibration', '--study-dir', str(STUDY),
                         '--output-dir', str(output), '--preflight'])
    record = {
        'case_id': 'analysis-01-positive', 'author_semantic_label': 'acceptable',
        'deterministic_status': 'pass', 'expected_check_status': 'pass',
        'final_status': 'pass',
        'consensus': {'overall': 'pass', 'failed_records': 0,
                      'escalated_criteria': 0},
        'primary': [], 'escalation': [],
    }
    monkeypatch.setattr(run_moa_review, 'calibration_review',
                        lambda *args, **kwargs: [record])
    run_moa_review.main(['--kind', 'calibration', '--study-dir', str(STUDY),
                         '--output-dir', str(output), '--live'])
    result = json.loads((output / 'moa-results.json').read_text())
    assert result['kind'] == 'calibration'
    assert result['records'] == [record]
    assert result['summary']['cases'] == 1
    assert result['summary']['final_status_counts'] == {'pass': 1, 'fail': 0, 'pending': 0}
