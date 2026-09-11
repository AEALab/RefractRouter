"""绑定路线的隔离、共享图消融、容量和失败证据；所有客户端均为模拟。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
import time

import pytest

from experiments.run_bound_quality_study import RehearsalClient
from refractrouter.quality_runtime import (ARMS, CAPS, FINAL_SYSTEM, BoundSession, execute,
                                          prepare, stage_model)
from refractrouter.quality_study import MATERIAL_CRITERIA, digest, load_study

STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


@pytest.fixture(autouse=True)
def offline():
    with patch('socket.socket', side_effect=AssertionError('禁止测试发起网络调用')):
        yield


def test_all_bound_arms_and_shared_graph_comparisons(tmp_path):
    plan = prepare(STUDY, task_ids=['analysis-02'], repeats=1)
    client = RehearsalClient(STUDY)
    result = execute(STUDY, plan, tmp_path / 'run', client=client, simulated=True)
    assert len(result['runs']) == len(ARMS) == 12
    assert result['actual_model_calls'] == result['actual_afp'] == 0
    assert all(r['status'] == 'delivered-unconfirmed' and r['quality_status'] == 'pending' for r in result['runs'])
    rows = {r['arm']: r for r in result['runs']}
    shared = [rows[a] for a in ARMS if a.startswith('shared-')]
    assert len({r['plan_sha256'] for r in shared}) == 1
    assert rows['shared-single-1']['assignments'] == rows['shared-single-2']['assignments']
    assert rows['shared-heterogeneous-1']['assignments'] == rows['shared-heterogeneous-2']['assignments']
    assert len(set(rows['shared-single-1']['assignments'].values())) == 1
    assert len(set(rows['shared-heterogeneous-1']['assignments'].values())) == 2
    assert len(result['setups']) == 1 and result['setups'][0]['offline_afp'] > 0
    for r in result['runs']:
        assert r['plan_ready_ms'] <= r['final_text_ready_ms'] <= r['online_finished_ms']
        assert r['online_afp'] > 0 and r['offline_afp'] > 0 and r['cost_known']
    assert sum(r['online_afp'] for r in result['runs']) == pytest.approx(result['charged_or_reserved']['production'])
    assert sum(r['offline_afp'] for r in result['runs']) + result['setups'][0]['offline_afp'] == pytest.approx(result['charged_or_reserved']['evaluation'])
    assert all(c['response']['attempts'] == 1 for c in result['calls'])
    assert len(result['calls']) <= plan['max_calls']
    final_calls = [c for c in result['calls'] if c['stage'] == 'final']
    assert len(final_calls) == 12
    assert {c['request_messages'][0]['content'] for c in final_calls} == {FINAL_SYSTEM}
    # 参考答案与作者/路线标签没有进入任何执行或模型评审的请求。
    for messages in client.messages:
        payload = json.loads(messages[-1]['content'])
        assert not {'reference_checks', 'author_reference', 'task_sha256', 'arm', 'split'} & payload.keys()
        task = payload['task']
        if isinstance(task, str): task = json.loads(task)
        assert set(task) == {'instruction', 'materials', 'requested_findings', 'semantic_criteria', 'output_contract'}


def test_frozen_selection_and_holdout_paid_gate_precede_client_calls(tmp_path):
    plan = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    client = RehearsalClient(STUDY)
    with pytest.raises(ValueError, match='human material'):
        execute(STUDY, plan, tmp_path / 'held', client=client)
    assert not client.messages and not (tmp_path / 'held').exists()
    changed = deepcopy(plan); changed['caps']['planner']['output'] = 9000
    with pytest.raises(ValueError, match='frozen protocol'):
        execute(STUDY, changed, tmp_path / 'changed', client=client, simulated=True)


def test_unknown_usage_stops_and_keeps_reserved_cost(tmp_path):
    class UnknownClient(RehearsalClient):
        def complete(self, *args, **kwargs):
            return replace(super().complete(*args, **kwargs), usage_available=False)
    plan = prepare(STUDY, task_ids=['analysis-01'], arms=['direct-cheap', 'direct-strong'], repeats=1)
    client = UnknownClient(STUDY)
    with pytest.raises(ValueError, match='usage'):
        execute(STUDY, plan, tmp_path / 'run', client=client)
    raw = json.loads((tmp_path / 'run/session.json').read_text())
    assert raw['actual_afp'] is None and raw['actual_model_calls'] == 1
    assert raw['status'] == 'stopped-infrastructure'
    assert raw['calls'][0]['status'] == 'unknown-usage'
    assert raw['calls'][0]['charged'] > 0


def test_bad_final_output_preserves_cost_and_continues_other_trial(tmp_path):
    class BadOnce(RehearsalClient):
        bad = True
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if self.bad and messages[0]['content'] == FINAL_SYSTEM:
                self.bad = False
                return replace(response, content='not JSON')
            return response
    plan = prepare(STUDY, task_ids=['analysis-01'], arms=['direct-cheap', 'direct-strong'], repeats=1)
    result = execute(STUDY, plan, tmp_path / 'run', client=BadOnce(STUDY), simulated=True)
    assert [r['status'] for r in result['runs']] == ['failed', 'delivered-unconfirmed']
    assert result['runs'][0]['quality_status'] == 'fail'
    assert result['runs'][0]['online_afp'] > 0
    assert len(result['calls']) == 4


def test_capacity_rejection_occurs_before_dispatch_and_zero_retry_enforced(tmp_path):
    manifest = load_study(STUDY)[-1]
    frozen = prepare(STUDY, task_ids=['analysis-01'], arms=['direct-cheap'], repeats=1)
    client = RehearsalClient(STUDY)
    session = BoundSession(frozen, tmp_path / 'run', manifest, client, simulated=True)
    with pytest.raises(ValueError, match='capacity'):
        session.call('selector', {'task': 'x' * 40000}, 'oversized')
    assert not client.messages and not session.budget.records
    client.max_retries = 1
    with pytest.raises(ValueError, match='zero HTTP'):
        BoundSession(frozen, tmp_path / 'bad', manifest, client)


def test_offline_judge_failure_does_not_rewrite_online_delivery(tmp_path):
    class BadResearch(RehearsalClient):
        judges = 0
        def complete(self, model, messages, **kwargs):
            response = super().complete(model, messages, **kwargs)
            if model.role == 'judge':
                self.judges += 1
                if self.judges == 2:
                    return replace(response, content='not JSON')
            return response
    frozen = prepare(STUDY, task_ids=['analysis-01'], arms=['direct-cheap'], repeats=1)
    result = execute(STUDY, frozen, tmp_path / 'run', client=BadResearch(STUDY), simulated=True)
    row = result['runs'][0]
    assert row['status'] == 'delivered-unconfirmed'
    assert row['research_status'] == row['quality_status'] == 'pending'
    assert row['offline_afp'] > 0 and len(result['calls']) == 3


def test_human_gate_requires_real_record_shape_bound_to_material_and_policy():
    from refractrouter.quality_runtime import human_gate
    _, tasks, refs, *_ = load_study(STUDY)
    frozen = prepare(STUDY, task_ids=['analysis-03'], arms=['direct-cheap'], repeats=1)
    review = {'task_id': 'analysis-03', 'origin': 'human', 'reviewer': 'fixture-reviewer',
              'evidence': 'fixture://material-review', 'task_sha256': frozen['task_bindings']['analysis-03'],
              'reference_sha256': digest(refs['analysis-03']), 'checks': {c: 'pass' for c in MATERIAL_CRITERIA}}
    purpose = {'origin': 'human', 'reviewer': 'fixture-purpose-reviewer', 'evidence': 'fixture://purpose',
               'policy_sha256': digest(frozen['statistics_policy']), 'task_bindings': frozen['task_bindings'], 'verdict': 'pass'}
    assert human_gate(frozen, tasks, refs, [review], purpose)
    for bad in [{'origin': 'model'}, {'task_sha256': 'old'}, {'evidence': ''}, {'reviewer': 'Codex'}]:
        assert not human_gate(frozen, tasks, refs, [{**review, **bad}], purpose)
    assert not human_gate(frozen, tasks, refs, [review], {**purpose, 'policy_sha256': 'old'})
def test_delivery_code_fence_normalization_does_not_repair_semantics():
    from refractrouter.quality_runtime import parse_delivery
    value = '{"answer":"保留原始正文。","findings":[]}'
    assert parse_delivery(value) == parse_delivery('```json\n' + value + '\n```')
    for invalid in ('额外说明\n```json\n' + value + '\n```', value + value,
                    '```json\n' + value, '{"answer":"", "findings":[]}'):
        with pytest.raises(ValueError):
            parse_delivery(invalid)
