"""Issue #32：验证拆分结构与交接，所有模型响应均为模拟。"""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from refractrouter.task_contracts import PLAN_VERSION, decode_output
from refractrouter.task_plan import preview_plan, validate_plan
from refractrouter.task_runtime import run_task, validate_request
from tests.test_text_tasks import Client, MANIFEST, PROFILE, REQUEST, live, branched_plan

ROOT = Path(__file__).resolve().parents[1]


def example(name='parallel-analysis'):
    return json.loads((ROOT / f'data/task-plans/{name}-v2.json').read_text())


@pytest.mark.parametrize(('name', 'waves'), [
    ('parallel-analysis', [['cost', 'risk'], ['answer']]),
    ('serial-analysis', [['cost'], ['risk'], ['answer']]),
    ('single-answer', [['answer']]),
])
def test_dependency_structures_and_versioned_roundtrip(name, waves):
    plan = validate_plan(example(name), require_v2=True)
    assert plan.ready_waves() == waves
    assert validate_plan(plan.to_dict()) == plan
    analysis = plan.diagnostics()
    assert analysis['execution_mode'] == 'serial'
    assert analysis['semantic_dependencies_verified'] is False
    assert all(analysis['criterion_owners'].values())
    assert analysis['dependency_depth'] == len(waves)
    if name == 'parallel-analysis':
        assert analysis['downstream_counts'] == {'cost': 1, 'risk': 1, 'answer': 0}
        assert analysis['join_nodes'] == ['answer']
        assert 'review-join-context-and-conflict-handling' in analysis['warnings']


@pytest.mark.parametrize('mutate', [
    lambda p: p.update(schema_version='unknown'),
    lambda p: p.update(schema_version=None),
    lambda p: p.pop('decomposition_reason'),
    lambda p: p['nodes'][0]['contract'].update(execution='shell'),
    lambda p: p['nodes'][0]['contract'].update(failure_policy='retry'),
    lambda p: p['nodes'][0]['contract'].update(model_id='cheap'),
    lambda p: p['nodes'][0]['contract']['capability'].update(risk='critical'),
    lambda p: p['nodes'][0]['contract']['capability'].update(input_budget_tokens=True),
    lambda p: p['nodes'][0]['contract']['capability'].update(expected_output_tokens=8193),
    lambda p: p['nodes'][2]['contract']['inputs'].pop('cost'),
    lambda p: p['nodes'][2]['contract']['inputs']['cost'].update(fields=['missing']),
    lambda p: p['nodes'][2]['contract']['inputs']['cost'].update(reason=''),
    lambda p: p['nodes'][0]['contract'].update(covers=[True]),
    lambda p: p['nodes'][0]['contract'].update(covers=[2]),
    lambda p: p['nodes'][0]['contract'].update(checks=[]),
    lambda p: p['nodes'][2]['contract']['output'].update(format='json'),
])
def test_malformed_contracts_stop_before_any_model_call(mutate):
    plan = example()
    mutate(plan)
    client = Client()
    with pytest.raises(ValueError):
        live(client, plan=plan)
    assert not client.calls


def test_coverage_and_user_criteria_cannot_be_silently_weakened():
    plan = example()
    for node in plan['nodes']:
        node['contract']['covers'] = [0]
    with pytest.raises(ValueError, match='owning node'):
        validate_plan(plan)
    client = Client()
    result = live(client, acceptanceCriteria=['保持原始要求，不得替换'])
    assert result['status'] == 'failed'
    assert 'preserve' in result['issues'][0]
    assert len(client.calls) == 1  # 只有规划调用已计费。
    result = live(Client(), acceptanceCriteria=example()['acceptance_criteria'])
    assert result['status'] == 'completed'


@pytest.mark.parametrize('criteria', [[], [''], [1], ['重复', '重复'], '不是数组'])
def test_bad_request_criteria(criteria):
    with pytest.raises(ValueError):
        validate_request({**REQUEST, 'acceptanceCriteria': criteria})


def test_legacy_plan_is_explicit_and_model_planner_cannot_downgrade():
    plan = validate_plan(branched_plan())
    assert plan.to_dict() == branched_plan()
    assert 'legacy-plan-without-handoff-contracts' in plan.diagnostics()['warnings']
    assert live(Client(), plan=branched_plan())['status'] == 'completed'
    result = live(Client(branched_plan()))
    assert result['status'] == 'failed' and len(result['calls']) == 1
    assert 'text-task-plan-v2' in result['issues'][0]
    assert json.loads(result['planner_output']) == branched_plan()
    assert len(result['planner_prompt_sha256']) == 64


def test_zero_call_preview_never_invents_a_semantic_decomposition():
    plan = preview_plan('改写一句话', required_criteria=['保留原意'])
    assert plan.schema_version == PLAN_VERSION and len(plan.nodes) == 1
    assert plan.acceptance_criteria == ('保留原意',)
    assert plan.diagnostics()['parallel_opportunities'] == []


def test_duplicate_work_is_reviewed_without_deleting_required_edges():
    raw = example()
    raw['nodes'][1]['prompt_template'] = raw['nodes'][0]['prompt_template']
    plan = validate_plan(raw)
    assert 'review-duplicate-work-for-possible-merge' in plan.diagnostics()['warnings']
    assert len(plan.nodes) == 3
    assert plan.to_dict() == raw


def test_context_is_projected_to_declared_fields_and_contract_is_supplied():
    raw = example()
    raw['nodes'][2]['contract']['inputs']['cost']['fields'] = ['result', 'evidence']
    client = Client()
    result = live(client, plan=raw)
    assert result['status'] == 'completed'
    payloads = [json.loads(messages[-1]['content']) for model, messages in client.calls if model.role != 'judge']
    assert payloads[0]['upstream'] == payloads[1]['upstream'] == {}
    assert set(payloads[2]['upstream']['cost']) == {'result', 'evidence'}
    assert 'assumptions' in payloads[2]['upstream']['risk']
    assert payloads[2]['contract'] == raw['nodes'][2]['contract']
    assert all(n['contract_status'] == 'structure-valid' and n['semantic_status'] == 'not-evaluated'
               for n in result['nodes'])
    assert result['plan_analysis']['parallel_opportunities'] == [['cost', 'risk']]


def test_invalid_handoff_preserves_output_and_cost_and_blocks_descendants():
    class BadOutput(Client):
        def complete(self, model, messages, *, json_mode=False):
            response = super().complete(model, messages, json_mode=json_mode)
            return replace(response, content='{"result":"缺少证据字段"}')
    client = BadOutput()
    result = live(client, plan=example())
    assert result['status'] == 'failed' and len(client.calls) == 1
    assert result['nodes'][0]['status'] == 'invalid-output'
    assert '缺少证据字段' in result['nodes'][0]['output']
    assert result['charged']['production'] > 0
    assert result['calls'][0]['status'] == 'billed'
    assert not result['final_output'] and result['evaluation'] is None


@pytest.mark.parametrize('content', ['[]', '{}', '{"text": ""}', '{"result": {}}', '非 JSON'])
def test_nonempty_flat_output_schema_is_enforced(content):
    with pytest.raises(ValueError, match='node-output-contract-invalid'):
        decode_output(content, example()['nodes'][0]['contract'])


def test_input_and_model_capacity_constraints_are_applied_before_node_calls():
    raw = example()
    raw['nodes'][0]['contract']['capability']['input_budget_tokens'] = 256
    client = Client()
    result = live(client, plan=raw)
    assert result['status'] == 'failed' and not client.calls
    assert 'node-input-budget-exceeded' in result['issues'][0]
    raw = example()
    small_models = tuple(replace(m, context_window=9000) if m.role != 'judge' else m for m in MANIFEST.models)
    client = Client()
    result = run_task({**REQUEST, 'plan': raw}, replace(MANIFEST, models=small_models),
                      {**PROFILE, 'kind': 'empirical'}, client=client, production_limit=100, evaluation_limit=100)
    assert result['status'] == 'no-feasible-route' and not client.calls
    assert result['routing']['eligible_models'] == {'cost': [], 'risk': [], 'answer': []}


def test_contracts_are_snapshotted_and_branched_demo_is_offline():
    raw = example()
    plan = validate_plan(raw)
    exported = plan.to_dict()
    exported['nodes'][0]['contract']['objective'] = '外部修改'
    assert plan.to_dict() == raw
    result = run_task({**REQUEST, 'mode': 'demo', 'plan': raw}, MANIFEST, PROFILE)
    assert result['status'] == 'simulated' and result['evaluation'] is None
    assert result['final_output'].startswith('[SIMULATED]')
    assert all('[SIMULATED]' in n['output'] for n in result['nodes'])


def test_join_context_overflow_preserves_branch_costs_and_blocks_merge():
    """独立分支均成功，不代表汇总请求必定能容纳交接内容。"""
    class LargeBranchOutput(Client):
        def complete(self, model, messages, *, json_mode=False):
            response = super().complete(model, messages, json_mode=json_mode)
            if json_mode and model.role != 'judge':
                fields = json.loads(messages[-1]['content'])['contract']['output']['fields']
                return replace(response, content=json.dumps({key: 'x' * 2500 for key in fields}))
            return response

    raw = example()
    raw['nodes'][2]['contract']['capability']['input_budget_tokens'] = 4000
    client = LargeBranchOutput()
    result = live(client, plan=raw)
    assert result['status'] == 'failed'
    assert result['issues'] == ['node-input-budget-exceeded before answer']
    assert [row['label'] for row in result['calls']] == ['cost', 'risk']
    assert [row['node_id'] for row in result['nodes']] == ['cost', 'risk']
    assert all(row['status'] == 'ok' for row in result['nodes'])
    assert result['charged']['production'] > 0 and result['charged']['evaluation'] == 0
    assert result['evaluation'] is None and not result['final_output']


@pytest.mark.parametrize('name', ['parallel-analysis', 'single-answer'])
@pytest.mark.parametrize('method', ['A', 'B'])
def test_single_model_and_unsplit_task_remain_valid_options(name, method):
    from refractrouter.model_selection import Weights
    from refractrouter.node_routing import NodeProfile, route_nodes

    plan = validate_plan(example(name))
    profiles = tuple(NodeProfile(mid, kind, quality, cost, latency, 3)
        for kind in ('synthesis', 'generation')
        for mid, quality, cost, latency in [('cheap', 90, 1, 10), ('strong', 95, 2, 20)])
    result = route_nodes(plan, profiles, method=method, quality_min=80, cost_max=10,
                         latency_max_ms=100, weights=Weights(0, 1, 0) if method == 'B' else None)
    assert result['status'] == 'selected'
    assert set(result['assignments'].values()) == {'cheap'}
    assert len(result['assignments']) == len(plan.nodes)
