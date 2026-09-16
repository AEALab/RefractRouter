"""MoA 评审模块的确定性测试；全部使用注入的模拟 CLI，不发起真实模型调用。"""
import json
from pathlib import Path

import pytest

from refractrouter.moa_review import (MOA_POLICY, REVIEW_SCHEMA, aggregate,
    claude_command, codex_command, final_quality_status, judge, material_review,
    output_messages, output_review, preflight_envelope, purpose_review,
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


def test_cli_commands_include_model_and_effort():
    primary_codex = MOA_POLICY['primary'][0]
    primary_claude = MOA_POLICY['primary'][1]
    schema = Path('/tmp/schema.json'); out = Path('/tmp/last.txt')
    codex_args = codex_command(primary_codex, out, schema)
    assert codex_args[:2] == ['codex', 'exec']
    assert primary_codex['model'] in codex_args
    assert f'model_reasoning_effort={primary_codex["thinking_effort"]}' in codex_args
    assert str(schema) in codex_args and str(out) in codex_args
    claude_args = claude_command(primary_claude, schema)
    assert claude_args[:2] == ['claude', '-p']
    assert primary_claude['model'] in claude_args
    assert f'--effort' in claude_args and primary_claude['thinking_effort'] in claude_args
    assert '--tools' in claude_args and '' in claude_args
    assert '--json-schema' in claude_args and str(schema) in claude_args


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
    criteria_material = ['来源与使用范围可追溯', '材料内部无歧义或已标记未知',
        '参考事实及计算正确', '关键错误和语义验收覆盖交付', '来源及模板族独立',
        '任务形态标注合理', '候选任务难度及代表性适合研究', '公共输入未泄漏参考答案']
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


def test_purpose_review_binds_policy():
    policy_sha = 'abc'; bindings = {'t1': 'hash1'}
    responses = {}
    for reviewer in MOA_POLICY['primary'] + MOA_POLICY['escalation']:
        responses[reviewer['reviewer_id']] = review_json('pass', ['研究用途与质量、非劣、样本量和失败标准相符'])
    invoke, _ = fake_invoke(responses)
    record = purpose_review(policy_sha, bindings, invoke)
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
    assert preflight['policy']['primary'][0]['thinking_effort'] == 'high'
    assert preflight['policy']['primary'][1]['thinking_effort'] == 'high'
    assert preflight['policy']['escalation'][0]['thinking_effort'] == 'high'
    assert preflight['policy']['escalation'][1]['thinking_effort'] == 'high'
