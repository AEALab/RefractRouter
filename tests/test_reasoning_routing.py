"""节点联合选择模型与 effort；离线验证预测、发送和预算边界。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from refractrouter.agent import resource, run_agent
from refractrouter.agent_cli import example_configuration, main
from refractrouter.application_config import compile_configuration, configured_profile
from refractrouter.node_routing import load_profile, route_nodes
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse
from refractrouter.task_budget import TaskCallBudget
from refractrouter.task_plan import validate_plan
from tests.test_responses_api import configuration, Transport, client
from tests.test_text_tasks import Client


def configuration_and_plan():
    config = configuration()
    low, judge = config['models']
    low.update(id='shared-low', reasoningEffort='low', requestOptions={})
    low['routing'] = {'quality': 60, 'latencyMs': 1000, 'outputTokens': 1000, 'profiles': [
        {'nodeType': 'synthesis', 'difficulty': 'low', 'risk': 'low',
         'quality': 92, 'latencyMs': 1000, 'outputTokens': 1000}]}
    high = deepcopy(low)
    high.update(id='shared-high', reasoningEffort='high')
    high['routing'] = {'quality': 96, 'latencyMs': 8000, 'outputTokens': 10000, 'profiles': [
        {'nodeType': 'synthesis', 'difficulty': 'low', 'risk': 'low',
         'quality': 90, 'latencyMs': 8000, 'outputTokens': 10000}]}
    other = deepcopy(high)
    other.update(id='other-model', model='another-model', provider='other-provider', reasoningEffort='medium')
    other['routing'] = {'quality': 85, 'latencyMs': 4000, 'outputTokens': 2000}
    config['providers'].append({**config['providers'][0], 'id': 'other-provider'})
    config['models'] = [low, high, other, judge]
    config['qualityMin'] = 80
    plan = json.loads(resource('compare-plan.json').read_text())
    for node in plan['nodes']:
        node['contract']['capability']['input_budget_tokens'] = 16000
    plan['nodes'][0]['contract']['capability'].update(difficulty='low', risk='low')
    plan['nodes'][1]['contract']['capability'].update(difficulty='high', risk='high')
    return config, plan


@pytest.mark.parametrize(('strategy', 'complex_action'), [('quality', 'shared-high'), ('economy', 'other-model')])
def test_same_dag_jointly_selects_model_and_effort_and_dispatches_them(tmp_path, strategy, complex_action):
    config, plan = configuration_and_plan()
    transport = Transport()
    result = run_agent({'task': '比较方案的成本与风险', 'plan': plan, 'strategy': strategy},
        provider_config=config, mode='live', execute_paid_run=True, runs_dir=tmp_path,
        max_output_tokens=32768, client=client(transport))
    assert result['status'] == 'completed', result['issues']
    routes = result['model_routes']
    assert {nid: action['id'] for nid, action in routes.items()} == {
        'cost': 'shared-low', 'risk': complex_action, 'answer': complex_action}
    expected_effort = 'high' if strategy == 'quality' else 'medium'
    assert [c[2]['reasoning']['effort'] for c in transport.calls] == ['low', expected_effort, expected_effort, 'medium']
    assert len(transport.calls) == 4
    assert routes['cost']['model'] == 'reasoning-answer'
    if strategy == 'quality':
        assert routes['risk']['model'] == routes['cost']['model']
    else:
        assert routes['risk']['provider'] == 'other-provider'
    result_file = json.loads(Path(result['result_path']).read_text())
    assert result_file['routing']['actions'] == routes
    assert [call['route']['reasoning_effort'] for call in result_file['calls']] == ['low', expected_effort, expected_effort, 'medium']
    # Low expected token use must not reduce the hard reserve or mask real reasoning usage.
    assert all(call['reserved'] > .065 for call in result_file['calls'])
    assert result['usage']['reasoning_tokens'] == 32000
    profile = json.loads((Path(result['run_dir'])/'profile.json').read_text())
    assert profile['forecast_basis']['cost']['shared-low']['output_tokens'] == 1000
    assert profile['forecast_basis']['cost']['shared-low']['source'] == 'profiles[0]'
    assert all(row['samples'] == 0 for row in profile['candidates'])


def test_forecast_cost_and_latency_are_specific_to_effort_and_node():
    raw, plan_raw = configuration_and_plan()
    config = compile_configuration(raw)
    plan = validate_plan(plan_raw)
    profile = configured_profile(config, config.manifest, plan_raw)
    rows = load_profile(profile, config.manifest)
    options = {p.model_id: p for p in rows if p.matches(plan.nodes[0], plan)}
    assert options['shared-low'].cost == pytest.approx(.018)
    assert options['shared-high'].cost == pytest.approx(.036)
    assert options['shared-low'].latency_ms == 1000
    # A tight forecast budget selects only feasible actions; no heuristic effort order.
    routed = route_nodes(plan, rows, method='A', quality_min=80, cost_max=.057, latency_max_ms=100000)
    assert routed['status'] == 'no-feasible-route'
    routed = route_nodes(plan, rows, method='A', quality_min=80, cost_max=.06, latency_max_ms=100000)
    assert routed['assignments'] == {'cost':'shared-low', 'risk':'other-model', 'answer':'other-model'}


@pytest.mark.parametrize('kind', ['openai-responses', 'openai-compatible', 'dsh', 'ark-agent-plan'])
def test_first_class_effort_compiles_to_provider_protocol(kind):
    config = example_configuration(kind)
    config['models'][0]['requestOptions'] = {}
    config['models'][0]['reasoningEffort'] = 'provider-supported-value'
    model = compile_configuration(config).manifest.candidates[0]
    options = model.request_options
    assert (options['reasoning']['effort'] if kind == 'openai-responses' else options['reasoning_effort']) == 'provider-supported-value'


def test_chat_dispatch_includes_selected_effort():
    config = example_configuration('openai-compatible')
    config['models'][0]['reasoningEffort'] = 'low'
    model = compile_configuration(config).manifest.candidates[0]
    class Wire:
        def post(self, url, headers, body, timeout_seconds):
            body = json.loads(body)
            assert body['reasoning_effort'] == 'low' and 'reasoning' not in body
            return TransportResponse(200, {}, b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2}}')
    OpenAICompatibleClient(transport=Wire(), environment={'TEAM_MODEL_KEY':'test'}, max_retries=0).complete(model, [{'role':'user','content':'test'}])


@pytest.mark.parametrize('mutate', [
    lambda c: c['models'][0].update(reasoningEffort=''),
    lambda c: c['models'][0].update(reasoningEffort=True),
    lambda c: c['models'][0].update(requestOptions={'reasoning':{'effort':'high'}}),
    lambda c: c['models'][0]['routing'].update(outputTokens=32769),
    lambda c: c['models'][0]['routing'].update(outputTokens=True),
    lambda c: c['models'][0]['routing']['profiles'].append(deepcopy(c['models'][0]['routing']['profiles'][0])),
    lambda c: c['models'][0]['routing']['profiles'][0].update(nodeType='unsupported'),
    lambda c: c['models'][0]['routing']['profiles'][0].pop('risk'),
    lambda c: c['models'][0]['routing']['profiles'][0].update(inputMinTokens=2000, inputMaxTokens=1000),
    lambda c: c['models'][0]['routing']['profiles'][0].update(quality=float('nan')),
    lambda c: c['models'][0]['routing']['profiles'][0].update(latencyMs=0),
    lambda c: c['models'][0]['routing']['profiles'][0].update(outputTokens=0),
])
def test_invalid_action_or_stratum_fails_before_calls_and_artifacts(tmp_path, mutate):
    config, plan = configuration_and_plan()
    mutate(config)
    transport = Transport()
    with pytest.raises(ValueError):
        run_agent({'task':'invalid', 'plan':plan}, provider_config=config, mode='live',
            execute_paid_run=True, runs_dir=tmp_path, max_output_tokens=32768, client=client(transport))
    assert not transport.calls and not list(tmp_path.iterdir())


def test_effort_forecast_cannot_be_silently_clipped_by_host_output_cap(tmp_path):
    config, plan = configuration_and_plan()
    with pytest.raises(ValueError, match='effective maxOutputTokens'):
        run_agent({'task':'too small cap','plan':plan}, provider_config=config, runs_dir=tmp_path, max_output_tokens=2048)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('change', [
    {'request_options': {'reasoning': {'effort': 'high'}}},
    {'max_output_tokens': 16000}, {'api_model':'changed-model'}, {'provider':'changed-provider'},
    {'output_cost_per_1k': .1},
])
def test_forecast_binding_rejects_changed_execution_settings(change):
    raw, plan = configuration_and_plan()
    config = compile_configuration(raw)
    profile = configured_profile(config, config.manifest, plan)
    models = list(config.manifest.models)
    models[0] = replace(models[0], **change)
    with pytest.raises(ValueError, match='bindings'):
        load_profile(profile, replace(config.manifest, models=tuple(models)))


def test_missing_action_binding_is_rejected():
    raw, plan = configuration_and_plan()
    config = compile_configuration(raw)
    profile = configured_profile(config, config.manifest, plan)
    profile.pop('action_bindings')
    with pytest.raises(ValueError, match='action bindings'): load_profile(profile, config.manifest)


def test_token_interval_and_risk_select_exact_profile_without_leaking_to_other_nodes():
    raw, plan = configuration_and_plan()
    first = raw['models'][0]['routing']['profiles'][0]
    first.update(inputMinTokens=256, inputMaxTokens=16000)
    raw['models'][0]['routing']['profiles'].append({**first, 'inputMinTokens':16000,
        'inputMaxTokens':131073, 'quality':81, 'outputTokens':1200})
    config = compile_configuration(raw)
    profile = configured_profile(config, config.manifest, plan)
    assert profile['forecast_basis']['cost']['shared-low'] == {'input_tokens':16000,'output_tokens':1200,'source':'profiles[1]'}
    assert profile['forecast_basis']['risk']['shared-low']['source'] == 'default'


def test_budget_reserves_full_output_even_when_routing_forecasts_are_small():
    config, _ = configuration_and_plan()
    model = compile_configuration(config).manifest.candidates[0]
    adapter = Client()
    budget = TaskCallBudget(adapter, .01, 1)
    with pytest.raises(ValueError, match='budget-exhausted'):
        budget.complete(model, [{'role':'user','content':'test'}], label='small')
    assert not adapter.calls and not budget.records


def test_model_inventory_and_dsh_overlay_preserve_action_configuration(tmp_path, capsys):
    config, _ = configuration_and_plan()
    source = tmp_path/'providers.json'; source.write_text(json.dumps(config))
    assert main(['models','--provider-config',str(source)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [m['reasoning_effort'] for m in data['available_models']] == ['low','high','medium','medium']
    target = tmp_path/'dsh.json'
    assert main(['dsh-config','--provider-config',str(source),'--max-output-tokens','32768','--output',str(target)]) == 0
    assert json.loads(target.read_text())[0]['config']['providerConfig'] == config
