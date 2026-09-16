"""MoA 评审接入质量执行与统计管线的确定性测试；模拟 CLI，不发起真实模型调用。"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.run_bound_quality_study import RehearsalClient
from refractrouter.moa_review import material_review, output_review, purpose_review
from refractrouter.quality_runtime import execute, moa_gate, prepare
from refractrouter.quality_statistics import analyze
from refractrouter.quality_study import digest, load_study

STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.socket', side_effect=AssertionError('禁止测试发起网络调用')):
        yield


def review_json(verdict, criteria):
    return json.dumps({'verdict': verdict, 'rationale': '模拟依据',
                       'criteria': [{'criterion': c, 'verdict': verdict,
                                     'rationale': '模拟依据'} for c in criteria]},
                      ensure_ascii=False)


def all_pass_invoke(reviewer, messages, schema=None):
    payload = json.loads(messages[-1]['content'])
    return 0, review_json('pass', payload['criteria']), '', 120.0, 'test-version'


def test_moa_gate_requires_full_consensus_and_bindings():
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    frozen = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    materials = material_review(selected, refs, all_pass_invoke)
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'], all_pass_invoke)
    assert moa_gate(frozen, tasks, refs, materials, purpose)
    for bad in ({'task_sha256': 'old'}, {'reference_sha256': 'old'}, {'policy_sha256': 'old'}):
        assert not moa_gate(frozen, tasks, refs, [{**materials[0], **bad}], purpose)
    tampered = deepcopy(materials[0])
    tampered['consensus']['criteria'][0]['verdict'] = 'pending'
    assert not moa_gate(frozen, tasks, refs, [tampered], purpose)
    assert not moa_gate(frozen, tasks, refs, materials, {**purpose, 'statistics_policy_sha256': 'old'})
    assert not moa_gate(frozen, tasks, refs, materials, {**purpose, 'consensus': {'overall': 'pending'}})


def test_execute_accepts_moa_gate_for_heldout_run(tmp_path):
    plan = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    client = RehearsalClient(STUDY)
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['task_id'] == 'analysis-03']
    materials = material_review(selected, refs, all_pass_invoke)
    purpose = purpose_review(digest(plan['statistics_policy']), plan['task_bindings'], all_pass_invoke)
    result = execute(STUDY, plan, tmp_path / 'held', client=client,
                     moa_material_reviews=materials, moa_purpose_review=purpose)
    assert result['moa_gate_evidence']['reviewer_identity_verified'] is False
    assert result['runs'] and result['status'] == 'completed'


def _development_fixture():
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['split'] == 'development'][:2]
    frozen = prepare(STUDY, task_ids=[t['task_id'] for t in selected], arms=['direct-cheap'], repeats=1)
    rows = []
    for spec in frozen['schedule']:
        rows.append({**spec, 'status': 'delivered-unconfirmed', 'quality_status': 'pass',
                     'output': refs[spec['task_id']]['author_reference'], 'cost_known': True,
                     'online_afp': .5, 'offline_afp': .1, 'online_finished_ms': 500})
    result = {'frozen_sha256': digest(frozen), 'simulated': False, 'runs': rows}
    return tasks, refs, selected, frozen, result


def test_analyze_uses_moa_gate_and_output_consensus():
    tasks, refs, selected, frozen, result = _development_fixture()
    materials = material_review(selected, refs, all_pass_invoke)
    purpose = purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'], all_pass_invoke)
    moa_outputs = output_review(selected, refs, result['runs'], all_pass_invoke)
    report = analyze(frozen, result, tasks, references=refs,
                     moa_material_reviews=materials, moa_output_reviews=moa_outputs,
                     moa_purpose_review=purpose)
    arm = 'direct-cheap'
    assert report['arms'][arm]['run_counts']['pass'] == len(result['runs'])
    assert report['arms'][arm]['quality_pass_rate'] == 1
    metrics = report['arms'][arm]['accepted_task_metrics']
    assert metrics['quality_gate_status'] == 'active'
    assert metrics['afp_per_accepted_task'] == pytest.approx(.6)
    assert report['moa_review']['gate_status'] == 'active'
    assert report['moa_review']['output_review_bound_runs'] == len(result['runs'])
    assert report['moa_review']['reviewer_identity_verified'] is False
    cost = report['moa_review']['cost']
    assert cost['real_model_calls'] == 2 * len(materials) + 2 * len(moa_outputs) + 2
    assert cost['included_in_ark_afp'] is False and cost['external_usage'] == 'unknown'
    assert not report['quality_gate_pending']
    # 缺少输出评审时不能自动放行：仍为 pending，不把门槛通过当作交付通过。
    report = analyze(frozen, result, tasks, references=refs,
                     moa_material_reviews=materials, moa_purpose_review=purpose)
    assert report['arms'][arm]['run_counts']['pending'] == len(result['runs'])
    assert report['quality_gate_pending']


def test_deterministic_fail_vetoes_moa_pass_consensus():
    tasks, refs, selected, frozen, result = _development_fixture()
    corrupted = deepcopy(result['runs'][0]['output'])
    corrupted['findings'][0]['value'] = '__被篡改的错误答案__'
    result['runs'][0]['output'] = corrupted
    moa_outputs = output_review(selected, refs, result['runs'], all_pass_invoke)
    report = analyze(frozen, result, tasks, references=refs, moa_output_reviews=moa_outputs)
    assert report['arms']['direct-cheap']['run_counts']['fail'] == 1
    assert report['arms']['direct-cheap']['run_counts']['pass'] == len(result['runs']) - 1
