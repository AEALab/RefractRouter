"""必要拆分的执行边界、合并安全及完整记账；仅使用模拟模型。"""
from copy import deepcopy
import json
from pathlib import Path
from threading import Event

import pytest

from refractrouter.agent import build_request, run_agent
from refractrouter.minimal_planning import MINIMAL_PLANNER_SYSTEM, compile_minimal
from refractrouter.openai_compatible import ChatResponse
from tests.test_automatic_dag import config
from tests.test_fast_dynamic_dag import Client, compact, EXHIBITION
from tests.test_text_tasks import REQUEST
from refractrouter.task_runtime import validate_request


def plan(decision, *jobs, **extra):
    return {**compact(*jobs), 'decision': decision, **extra}


class MinimalClient(Client):
    def complete(self, model, messages, **kwargs):
        if messages[0]['content'] == MINIMAL_PLANNER_SYSTEM:
            self.calls.append((model, json.loads(messages[-1]['content']), 0))
            return ChatResponse(json.dumps(self.plan), 120, 100, 0, 0, 10, 1, 'stop', 'mock')
        return super().complete(model, messages, **kwargs)


def run(tmp_path, client, *, configuration=None, **payload):
    summary = run_agent({'task': '按原始规则分别核对费用和条件，保留所有例外后给出建议。',
        'template': 'auto', 'plannerPolicy': 'minimal-v1', **payload},
        provider_config=configuration or config(), client=client, mode='live', execute_paid_run=True, runs_dir=tmp_path)
    return summary, json.loads(Path(summary['result_path']).read_text())


def test_direct_keeps_planning_and_delivery_judge_costs(tmp_path):
    client = MinimalClient(plan=plan('direct', ('answer', [])))
    summary, raw = run(tmp_path, client, acceptanceCriteria=['核对所有条件', '保留例外'])
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 3
    assert client.calls[0][0].model_id == 'fast'
    assert client.calls[0][1]['acceptance_criteria'] == ['核对所有条件', '保留例外']
    assert summary['planning_decision']['decision'] == 'direct'
    assert summary['planning_decision']['benefit_verified'] is False
    assert summary['planning_policy'] == 'minimal-v1'
    assert raw['plan']['nodes'][0]['contract']['covers'] == [0, 1]
    assert summary['cost_breakdown']['planning'] > 0
    assert summary['cost_breakdown']['evaluation'] > 0
    assert sum(summary['cost_breakdown'].values()) == pytest.approx(sum(summary['costs'].values()))
    assert not raw.get('dynamic_decomposition', {}).get('events')
    judge_payload = next(p for m, p, _ in client.calls if m.role == 'judge')
    assert judge_payload['criteria'] == ['核对所有条件', '保留例外']


def test_explicit_single_has_no_planning_call_or_new_policy(tmp_path):
    client = MinimalClient()
    summary = run_agent({'task': '给出完整建议', 'template': 'single'}, provider_config=config(),
        client=client, mode='live', execute_paid_run=True, runs_dir=tmp_path)
    assert summary['status'] == 'completed'
    assert len(client.calls) == 2 and summary['cost_breakdown']['planning'] == 0
    assert 'planning_policy' not in summary


def test_parallel_branches_overlap_and_join_gets_full_material(tmp_path):
    class Parallel(MinimalClient):
        def __init__(self):
            super().__init__(plan=plan('parallel', ('left', []), ('right', []), ('answer', ['left', 'right'])))
            self.left, self.right = Event(), Event()
        def complete(self, model, messages, **kwargs):
            payload = json.loads(messages[-1]['content'])
            nid = payload.get('node_id')
            if nid == 'left':
                self.left.set()
                assert self.right.wait(2)
            if nid == 'right':
                self.right.set()
                assert self.left.wait(2)
            if nid == 'answer':
                assert set(payload['upstream']) == {'left', 'right'}
                assert '保留所有例外' in payload['task']
            return super().complete(model, messages, **kwargs)
    client = Parallel()
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'completed', summary['issues']
    assert raw['execution']['peak_running_nodes'] == 2
    assert len(client.calls) == 5
    assert summary['planning_decision']['final_node_count'] == 3


def test_merge_removes_rewrite_call_without_dropping_jobs_criteria_or_risk(tmp_path):
    proposed = plan('direct', ('facts', []), ('answer', ['facts']), merge_groups=[['facts', 'answer']])
    proposed['nodes'][0].update(job='核对规则中的例外条款，产出逐条依据', risk='high', difficulty='high')
    proposed['nodes'][1]['job'] = '据全部规则给出最终建议'
    original = deepcopy(proposed)
    client = MinimalClient(plan=proposed)
    summary, raw = run(tmp_path, client, acceptanceCriteria=['逐条核对并给出建议'])
    assert summary['status'] == 'completed', summary['issues']
    assert len(client.calls) == 3 and proposed == original
    row = raw['plan']['nodes'][0]
    assert row['node_id'] == 'answer' and row['parents'] == []
    assert '例外条款' in row['prompt_template'] and '最终建议' in row['prompt_template']
    assert 'facts→answer' in row['prompt_template']
    assert row['contract']['capability']['risk'] == 'high'
    assert row['contract']['capability']['difficulty'] == 'high'
    assert row['contract']['covers'] == [0]
    assert raw['compact_planning']['decision']['proposed_node_count'] == 2
    assert raw['compact_planning']['decision']['final_node_count'] == 1
    assert not any(p.get('node_id') == 'facts' for _, p, _ in client.calls)


def test_merge_preserves_external_dependencies_and_branch_deliverables():
    raw = plan('parallel', ('left', []), ('right', []), ('check', ['left']),
        ('answer', ['check', 'right']), merge_groups=[['left', 'check']])
    compiled, _ = compile_minimal(raw, parallel_capacity=2)
    assert {n.node_id: n.parents for n in compiled.nodes} == {'right': (), 'check': (), 'answer': ('check', 'right')}
    assert compiled.contracts['answer']['inputs'].keys() == {'check', 'right'}
    assert 'left→check' in next(n.prompt_template for n in compiled.nodes if n.node_id == 'check')


@pytest.mark.parametrize('groups', [None, '', [['unknown', 'answer']], [['a', 'a']],
    [['a', 'b'], ['b', 'answer']], [['a', 'answer']]])
def test_invalid_or_cyclic_merges_rejected_before_any_execution(tmp_path, groups):
    client = MinimalClient(plan=plan('isolation', ('a', []), ('b', ['a']), ('answer', ['b']), merge_groups=groups))
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed'
    assert len(client.calls) == 1 and not raw['nodes']
    assert raw['calls'][0]['status'] == 'billed'
    assert summary['planning_policy'] == 'minimal-v1'


@pytest.mark.parametrize('decision,jobs', [
    ('direct', [('a', []), ('answer', ['a'])]),
    ('parallel', [('a', []), ('answer', ['a'])]),
    ('isolation', [('answer', [])]),
    ('tool', [('a', []), ('answer', ['a'])]),
    ('magic', [('answer', [])])])
def test_invalid_decision_never_starts_production_nodes(tmp_path, decision, jobs):
    client = MinimalClient(plan=plan(decision, *jobs))
    summary, raw = run(tmp_path, client)
    assert summary['status'] == 'failed' and len(client.calls) == 1 and not raw['nodes']


def test_serial_isolation_is_allowed_and_recorded_as_unverified(tmp_path):
    client = MinimalClient(plan=plan('isolation', ('rules', []), ('answer', ['rules']),
        reason='先独立整理规则及例外，再依据规则作出决策，保留职责边界供审查。'))
    summary, raw = run(tmp_path, client, maxConcurrency=1)
    assert summary['status'] == 'completed', summary['issues']
    assert summary['planning_decision']['semantic_necessity_verified'] is False
    assert raw['plan_analysis']['parallel_opportunities'] == []


@pytest.mark.parametrize('limits', [{'maxConcurrency': 1}, {'providerConcurrency': {'first': 1}}])
def test_parallel_claim_respects_available_concurrency(tmp_path, limits):
    # 测试配置两个候选模型属于同一个 provider；评审 provider 不提供执行槽位。
    configuration = config()
    for model in configuration['models']:
        if model['role'] == 'candidate':
            model['provider'] = 'first'
    client = MinimalClient(plan=plan('parallel', ('a', []), ('b', []), ('answer', ['a', 'b'])))
    summary, raw = run(tmp_path, client, configuration=configuration, **limits)
    assert summary['status'] == 'failed' and len(client.calls) == 1
    assert 'available concurrency' in raw['compact_planning']['attempts'][0]['error']


def test_dependency_guard_still_blocks_historical_wrong_answer(tmp_path):
    client = MinimalClient(plan=plan('direct', ('answer', [])), output='原始 A→B→D→E；延误 A→C→D→E')
    summary, raw = run(tmp_path, client, task=EXHIBITION)
    assert summary['status'] == 'content-verification-failed'
    assert len(client.calls) == 2
    assert not any(m.role == 'judge' for m, _, _ in client.calls)


@pytest.mark.parametrize('extra', [{'plannerPolicy': 'unknown'}, {'maxPlanRepairs': 1}, {'planningMode': 'full'}])
def test_bad_policy_configuration_rejected_without_calls(tmp_path, extra):
    client = MinimalClient()
    with pytest.raises(ValueError):
        run(tmp_path, client, **extra)
    assert not client.calls


def test_policy_not_silently_applied_to_explicit_plan():
    with pytest.raises(ValueError, match='automatic template'):
        build_request({'task': '给出建议', 'template': 'single', 'plannerPolicy': 'minimal-v1'},
            mode='live', production_budget=40, timeout_ms=300000)
    with pytest.raises(ValueError, match='automatic compact'):
        validate_request({**REQUEST, 'plannerPolicy': 'minimal-v1'})
