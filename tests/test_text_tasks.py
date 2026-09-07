from dataclasses import replace
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from experiments.build_node_routing_profile import build_profile
from refractrouter.manifest import load_model_manifest
from refractrouter.model_selection import Weights
from refractrouter.node_routing import NodeProfile, load_profile, route_nodes
from refractrouter.openai_compatible import ChatResponse
from refractrouter.task_plan import PLANNER_SYSTEM, preview_plan, validate_plan
from refractrouter.task_runtime import run_task, TaskCallBudget, validate_models

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = load_model_manifest(ROOT / 'data/model-manifests/openai-gpt-5.4.json')
PROFILE = json.loads((ROOT / 'data/routing/demo-usd-v1.json').read_text())
REQUEST = {'task': '比较两个方案，给出成本和风险分析。', 'mode': 'run', 'method': 'B',
           'qualityMin': 80, 'costMax': 10, 'latencyMaxMs': 300000,
           'weights': {'quality': .5, 'cost': .25, 'latency': .25}}


def branched_plan():
    return {'nodes': [
        {'node_id': 'cost', 'node_type': 'synthesis', 'parents': [], 'prompt_template': 'Analyze costs'},
        {'node_id': 'risk', 'node_type': 'synthesis', 'parents': [], 'prompt_template': 'Analyze risks'},
        {'node_id': 'answer', 'node_type': 'generation', 'parents': ['cost', 'risk'], 'prompt_template': 'Compare and conclude'},
    ], 'final_node_id': 'answer', 'acceptance_criteria': ['Compare costs and risks']}


class Client:
    def __init__(self, plan=None, fail_at=None, bad_judge=False):
        self.plan = plan if plan is not None else json.loads((ROOT / 'data/task-plans/parallel-analysis-v2.json').read_text())
        self.calls = []
        self.fail_at = fail_at
        self.bad_judge = bad_judge

    def complete(self, model, messages, *, json_mode=False):
        self.calls.append((model, messages))
        if len(self.calls) == self.fail_at:
            raise RuntimeError('provider secret must not leak')
        payload = messages[-1]['content']
        if messages[0]['content'] == PLANNER_SYSTEM:
            content = json.dumps(self.plan)
        elif model.role == 'judge':
            criteria = json.loads(payload)['criteria']
            content = json.dumps({'score': 92, 'passed': True, 'rationale': 'meets task',
                'criteria': [] if self.bad_judge else [{'criterion': c, 'passed': True, 'rationale': 'covered'} for c in criteria]})
        elif json_mode:
            content = json.dumps({key: '模拟的 ' + key for key in json.loads(payload)['contract']['output']['fields']})
        else:
            content = 'Answer from ' + model.model_id
        return ChatResponse(content, 100, 80, 0, 0, 10, 1, 'stop', 'mock-request')


def live(client, **overrides):
    return run_task({**REQUEST, **overrides}, MANIFEST, {**PROFILE, 'kind': 'empirical'},
                    client=client, production_limit=100, evaluation_limit=100)


@pytest.mark.parametrize('mutate', [
    lambda p: p['nodes'].append(p['nodes'][0]),
    lambda p: p['nodes'][0].update(parents=['missing']),
    lambda p: p['nodes'][0].update(parents=['answer']),
    lambda p: p.update(final_node_id='risk'),
    lambda p: p['nodes'][0].update(node_type='shell'),
    lambda p: p['nodes'][2].update(parents=['cost', 'cost']),
    lambda p: p.update(acceptance_criteria=[]),
    lambda p: p['nodes'][0].update(command='rm -rf'),
])
def test_invalid_plans_stop_before_node_execution(mutate):
    plan = Client().plan
    mutate(plan)
    client = Client(plan)
    result = live(client)
    assert result['status'] == 'failed'
    assert len(client.calls) == 1
    assert result['plan'] is None
    assert result['charged']['production'] > 0


def test_plan_preserves_branching_and_roundtrips():
    plan = validate_plan(branched_plan())
    assert plan.order() == ('cost', 'risk', 'answer')
    assert validate_plan(plan.to_dict()) == plan


def test_global_constraints_can_require_mixed_assignment():
    plan = validate_plan(branched_plan())
    profiles = tuple(NodeProfile(mid, kind, quality, cost, latency, 3)
        for kind in ('synthesis', 'generation')
        for mid, quality, cost, latency in [('cheap', 90, 1, 10), ('fast', 89, 3, 1)])
    result = route_nodes(plan, profiles, method='A', quality_min=88, cost_max=5, latency_max_ms=21)
    assert result['status'] == 'selected'
    assert sorted(result['assignments'].values()) == ['cheap', 'cheap', 'fast']
    assert result['prediction']['cost'] == 5
    assert route_nodes(plan, profiles, method='A', quality_min=88, cost_max=4, latency_max_ms=21)['status'] == 'no-feasible-route'
    assert route_nodes(plan, profiles, method='B', quality_min=88, cost_max=9, latency_max_ms=30,
                       weights=Weights(0, 0, 1))['assignments'] == {'cost': 'fast', 'risk': 'fast', 'answer': 'fast'}


def test_missing_profile_never_silently_falls_back():
    plan = preview_plan('write an answer')
    assert route_nodes(plan, (), method='A', quality_min=0, cost_max=100, latency_max_ms=100)['status'] == 'no-feasible-route'
    with pytest.raises(ValueError, match='bindings'):
        load_profile({**PROFILE, 'model_bindings': {}}, MANIFEST)
    with pytest.raises(ValueError, match='synthetic'):
        run_task(REQUEST, MANIFEST, PROFILE, client=Client(), production_limit=100, evaluation_limit=100)


def test_live_task_plans_routes_executes_and_independently_judges():
    client = Client()
    result = live(client)
    assert result['status'] == 'completed'
    assert result['plan_origin'] == 'model'
    assert len(client.calls) == 5  # planner + 3 nodes + independent judge
    assert client.calls[-1][0].role == 'judge'
    assert result['evaluation']['score'] == 92
    assert result['critical_path_latency_ms'] == 20  # branches execute serially but graph path is shorter
    assert result['charged']['production'] > 0 and result['charged']['evaluation'] > 0
    upstream = [json.loads(messages[-1]['content'])['upstream'] for _, messages in client.calls[1:-1]]
    assert upstream[0] == upstream[1] == {}
    assert set(upstream[2]) == {'cost', 'risk'}


def test_provided_plan_and_plan_only_modes():
    client = Client()
    result = live(client, mode='plan')
    assert result['status'] == 'planned' and len(client.calls) == 1
    result = live(Client(), plan=branched_plan())
    assert result['status'] == 'completed' and result['plan_origin'] == 'provided'
    assert len(result['calls']) == 4


def test_zero_call_preview_and_demo_are_not_real_quality():
    with patch('socket.socket', side_effect=AssertionError('network forbidden')):
        for mode, status in [('preflight', 'preview'), ('demo', 'simulated')]:
            result = run_task({**REQUEST, 'mode': mode}, MANIFEST, PROFILE)
            assert result['status'] == status
            assert result['evaluation'] is None
            assert result['plan_origin'] == 'template-preview'
        assert result['final_output'].startswith('[SIMULATED]')


def test_budget_exhaustion_and_unknown_provider_usage_stop_calls():
    client = Client()
    result = run_task(REQUEST, MANIFEST, {**PROFILE, 'kind': 'empirical'},
                      client=client, production_limit=.0000001, evaluation_limit=100)
    assert result['status'] == 'failed' and not client.calls
    client = Client(fail_at=2)
    result = live(client)
    assert len(client.calls) == 2 and result['status'] == 'failed'
    assert result['calls'][-1]['status'] == 'unknown-usage'
    assert result['calls'][-1]['charged'] == result['calls'][-1]['reserved'] > 0
    assert 'secret' not in str(result['issues'])


def test_judge_failure_preserves_answer_and_billed_usage():
    result = live(Client(bad_judge=True))
    assert result['status'] == 'failed' and result['final_output']
    assert result['evaluation'] is None and result['charged']['evaluation'] > 0


def test_empirical_profile_rebuild_and_invalid_cohort_exclusion():
    rebuilt = build_profile(ROOT / 'reports/v0.3-contract-recovery/repeated-agent-plan')
    assert rebuilt == json.loads((ROOT / 'data/routing/report-transfer-v1.json').read_text())
    assert any(r['node_type'] == 'synthesis' and r['model_id'] == 'cheap' for r in rebuilt['exclusions'])


def test_ark_endpoint_and_payload_override_rejected_before_calls():
    ark = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    for model in [replace(ark.models[0], base_url='https://ark.cn-beijing.volces.com/api/v3'),
                  replace(ark.models[0], request_options={'max_completion_tokens': 99999})]:
        with pytest.raises(ValueError):
            validate_models(replace(ark, models=(model, *ark.models[1:])))


def test_cli_preflight_and_fresh_paths(tmp_path):
    req = tmp_path / 'request.json'
    req.write_text(json.dumps({**REQUEST, 'mode': 'preflight'}))
    command = ['uv', 'run', '--offline', 'python', 'validation/dsh/task_runner.py',
               '--request-file', str(req), '--profile', 'data/routing/demo-usd-v1.json',
               '--manifest', 'data/model-manifests/openai-gpt-5.4.json',
               '--output-dir', str(tmp_path / 'output'), '--evidence', str(tmp_path / 'evidence.json')]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr + result.stdout
    evidence = json.loads((tmp_path / 'evidence.json').read_text())
    assert evidence['task']['status'] == 'preview' and evidence['task']['qualityScore'] is None
    assert evidence['task']['productionCost'] == 0
    assert {'plan.json', 'routing.json', 'task-result.json'} <= set(evidence['artifacts'])
    assert subprocess.run(command, cwd=ROOT, capture_output=True).returncode != 0


def test_no_feasible_route_stops_after_planner():
    client = Client()
    result = live(client, qualityMin=100)
    assert result['status'] == 'no-feasible-route' and len(client.calls) == 1
    assert not result['nodes'] and result['evaluation'] is None


def test_evaluation_budget_failure_does_not_invent_a_quality_score():
    client = Client()
    result = run_task(REQUEST, MANIFEST, {**PROFILE, 'kind': 'empirical'}, client=client,
                      production_limit=100, evaluation_limit=.000001)
    assert result['status'] == 'failed' and len(client.calls) == 4
    assert result['final_output'] and result['evaluation'] is None
    assert result['charged']['evaluation'] == 0


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf')])
def test_profile_numeric_inputs_reject_invalid_values(value):
    with pytest.raises(ValueError):
        NodeProfile('cheap', 'planning', value, 1, 1, 1)


def test_search_limit_and_duplicate_profiles_are_explicit():
    plan = validate_plan({'nodes': [{'node_id': f'n{i}', 'node_type': 'synthesis',
        'parents': [] if i == 0 else [f'n{i-1}'], 'prompt_template': 'Analyze'} for i in range(8)],
        'final_node_id': 'n7', 'acceptance_criteria': ['Answer']})
    profiles = tuple(NodeProfile(f'm{i}', 'synthesis', 90, 1, 1, 1) for i in range(5))
    with pytest.raises(ValueError, match='100000'):
        route_nodes(plan, profiles, method='A', quality_min=80, cost_max=100, latency_max_ms=100)
    with pytest.raises(ValueError, match='duplicate'):
        route_nodes(plan, (profiles[0], profiles[0]), method='A', quality_min=80, cost_max=100, latency_max_ms=100)
