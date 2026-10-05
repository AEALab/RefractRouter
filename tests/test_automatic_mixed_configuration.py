"""v5 配置逐模型保留 AFP/CNY，旧版仍拒绝混算。"""
import json
from pathlib import Path

import pytest

from refractrouter.application_config import compile_configuration
from refractrouter.agent import automatic_cost_trace, run_agent
from refractrouter.configured_routing import configured_profile
from refractrouter.automatic_mixed_assignment import route_nodes_mixed
from refractrouter.node_routing import load_profile
from refractrouter.task_plan import preview_plan, validate_plan
from refractrouter.task_runtime import run_task
from tests.test_text_tasks import Client
from tests.test_live_execution import local_evidence


def config():
    source = Path(__file__).resolve().parents[1] / 'data/schema/refractagent-providers-v4-example.json'
    raw = json.loads(source.read_text())
    raw['schemaVersion'] = 'refractagent-providers-v5'
    raw['billingUnit'] = 'MIXED'
    raw['models'][0]['pricing']['unit'] = 'AFP'
    for model in raw['models'][1:]:
        model['pricing']['unit'] = 'CNY'
    return raw


def test_v5_compiles_actual_units_without_sum_or_conversion():
    compiled = compile_configuration(config())
    assert compiled.manifest.billing_unit == 'MIXED'
    assert {model.model_id: model.billing_unit for model in compiled.manifest.models} == {
        'external-worker': 'AFP', 'local-router': 'CNY', 'local-judge': 'CNY'}
    assert compiled.role_pools['worker'] == ('external-worker', 'local-router')


def test_v5_rejects_unaccounted_unit_and_v4_rejects_mixed_pool():
    raw = config()
    raw['models'][0]['pricing']['unit'] = 'USD'
    with pytest.raises(ValueError, match='AFP or CNY'):
        compile_configuration(raw)
    raw = config()
    raw['schemaVersion'] = 'refractagent-providers-v4'
    with pytest.raises(ValueError, match='requires v5'):
        compile_configuration(raw)


def test_mixed_routing_uses_expected_cost_and_keeps_conservative_request_bound():
    raw = config()
    raw['models'][0]['pricing'].update(inputPer1k=.45, outputPer1k=.45)
    raw['providers'][1].update(deployment='trusted-cloud', trustPolicy='team-cn')
    raw['trustPolicies'] = [{'id': 'team-cn', 'residency': 'CN',
        'auditLogging': True, 'allowsSensitiveData': True}]
    raw['models'][1]['pricing'].update(inputPer1k=.01, outputPer1k=.01)
    compiled = compile_configuration(raw)
    source = Path(__file__).resolve().parents[1] / 'data/task-plans/parallel-analysis-v2.json'
    plan = json.loads(source.read_text())
    for node in plan['nodes']:
        node['contract']['capability']['input_budget_tokens'] = 75000
    ids = {node['node_id'] for node in plan['nodes']}
    expected = configured_profile(compiled, compiled.manifest, plan,
        input_forecasts={nid: 75000 for nid in ids},
        cost_input_forecasts={nid: 18750 for nid in ids})
    conservative = configured_profile(compiled, compiled.manifest, plan,
        input_forecasts={nid: 75000 for nid in ids})
    units = {model.model_id: model.billing_unit for model in compiled.manifest.candidates}
    args = {'model_units': units, 'quality_min': 80, 'budgets': {'AFP': 50, 'CNY': 3}}
    validated = validate_plan(plan)
    selected = route_nodes_mixed(validated,
        load_profile(expected, compiled.manifest), **args)
    old = route_nodes_mixed(validated,
        load_profile(conservative, compiled.manifest), **args)
    assert set(selected['assignments'].values()) == {'external-worker'}
    assert 'local-router' in old['assignments'].values()
    basis = expected['forecast_basis']['cost']['external-worker']
    assert basis['input_tokens'] == 18750
    assert basis['input_forecast_source'] == 'observed-byte-ratio-v1'
    assert basis['conservative_input_bound'] == 75000
    assert basis['output_tokens'] == 1000


def test_mixed_runtime_selects_afp_worker_and_records_cny_judge_separately():
    raw = config()
    raw['providers'][1].update(deployment='trusted-cloud', trustPolicy='team-cn')
    raw['trustPolicies'] = [{'id': 'team-cn', 'residency': 'CN',
        'auditLogging': True, 'allowsSensitiveData': True}]
    for model in raw['models'][1:]:
        model['pricing'].update(inputPer1k=.01, outputPer1k=.02)
    compiled = compile_configuration(raw)
    plan = preview_plan('简短回答')
    profile = configured_profile(compiled, compiled.manifest, plan.to_dict())
    client = Client()
    result = run_task({'task': '简短回答', 'mode': 'run', 'method': 'A',
        'qualityMin': 80, 'costMax': 0, 'costMaxByUnit': {'AFP': 100, 'CNY': 10},
        'latencyMaxMs': 300000, 'plan': plan.to_dict()}, compiled.manifest, profile,
        client=client, production_limit={'AFP': 100, 'CNY': 10},
        evaluation_limit={'AFP': 10, 'CNY': 10},
        configured_application=True, configuration=compiled)
    assert result['status'] == 'completed', result['issues']
    assert result['routing']['prediction']['costs_by_unit']['CNY'] == 0
    assert result['calls'][0]['billing_unit'] == 'AFP'
    assert result['calls'][-1]['billing_unit'] == 'CNY'
    assert result['charged']['AFP']['production'] > 0
    assert result['charged']['CNY']['evaluation'] >= 0
    assert result['review']['protection']['status'] == 'converted-to-call'
    trace = automatic_cost_trace({**result, 'routing_profile': profile}, compiled.manifest)
    assert trace['review_protection']['status'] == 'converted-to-call'
    assert trace['selected_nodes'][0]['unit'] == 'AFP'
    assert trace['calls'][-1]['unit'] == 'CNY'


def test_mixed_runtime_stops_before_execution_when_review_call_slot_is_missing():
    compiled = compile_configuration(config())
    plan = preview_plan('简短回答')
    profile = configured_profile(compiled, compiled.manifest, plan.to_dict())
    client = Client()
    result = run_task({'task': '简短回答', 'mode': 'run', 'method': 'A',
        'qualityMin': 80, 'costMax': 0, 'costMaxByUnit': {'AFP': 100, 'CNY': 10},
        'latencyMaxMs': 300000, 'plan': plan.to_dict()}, compiled.manifest, profile,
        client=client, production_limit={'AFP': 100, 'CNY': 10},
        evaluation_limit={'AFP': 10, 'CNY': 10}, max_model_calls=1,
        configured_application=True, configuration=compiled)
    assert result['status'] == 'no-feasible-route'
    assert 'final-review-call-slot-unavailable' in result['issues'][0]
    assert client.calls == []


def test_mixed_generated_plan_compares_direct_and_dag_without_adding_units():
    raw = config()
    raw['providers'][1].update(deployment='trusted-cloud', trustPolicy='team-cn')
    raw['trustPolicies'] = [{'id': 'team-cn', 'residency': 'CN',
        'auditLogging': True, 'allowsSensitiveData': True}]
    for model in raw['models'][1:]:
        model['pricing'].update(inputPer1k=.01, outputPer1k=.02)
    compiled = compile_configuration(raw)
    direct = preview_plan('比较成本和风险')
    profile = configured_profile(compiled, compiled.manifest, direct.to_dict())
    result = run_task({'task': '比较成本和风险', 'mode': 'run', 'method': 'A',
        'qualityMin': 80, 'costMax': 0, 'costMaxByUnit': {'AFP': 100, 'CNY': 10},
        'latencyMaxMs': 300000}, compiled.manifest, profile, client=Client(),
        production_limit={'AFP': 100, 'CNY': 10}, evaluation_limit={'AFP': 10, 'CNY': 10},
        configured_application=True, configuration=compiled,
        alternative_direct_plan=direct.to_dict())
    assert result['status'] == 'completed', result['issues']
    comparison = result['route_comparison']
    assert comparison['status'] == 'selected'
    assert comparison['route'] in {'direct', 'dag'}
    assert set(comparison['planner_actual_costs_by_unit']) == {'AFP', 'CNY'}
    for name in ('direct', 'dag'):
        if comparison[name]:
            assert set(comparison[name]['total_estimated_by_unit']) == {'AFP', 'CNY'}
    assert result['billing_unit'] == 'MIXED'
    assert {'AFP', 'CNY'} == set(result['charged'])


def test_mixed_application_preflight_binds_both_unit_limits(tmp_path):
    result = run_agent({'task': '简短回答', 'template': 'auto', 'strategy': 'auto',
        'complexityPolicy': 'direct'}, mode='preflight', runs_dir=tmp_path,
        provider_config=config(), production_budget={'AFP': 100, 'CNY': 10},
        evaluation_budget={'AFP': 10, 'CNY': 10})
    assert result['status'] == 'preview' and result['billing_unit'] == 'MIXED'
    preview = result['live_authorization_preview']
    assert preview['ready'] is True
    assert preview['costs']['production_hard_limit_by_unit'] == {'AFP': 100, 'CNY': 10}
    assert preview['costs']['evaluation_hard_limit_by_unit'] == {'AFP': 10, 'CNY': 10}
    assert result['costs']['production'] is None
    assert set(result['costs']['by_unit']) == {'AFP', 'CNY'}


def test_mixed_direct_preflight_rejects_unaffordable_final_judge_before_execution(tmp_path):
    raw = config()
    raw['models'][2]['provider'] = 'external'
    raw['models'][2]['pricing'].update(inputPer1k=.45, outputPer1k=.45)
    raw['providers'][0].update(deployment='trusted-cloud', trustPolicy='team-cn')
    raw['trustPolicies'] = [{'id': 'team-cn', 'residency': 'CN',
        'auditLogging': True, 'allowsSensitiveData': True,
        'acknowledgeExternalTransmission': True}]
    result = run_agent({'task': '只回答数字：8+4 等于多少？', 'template': 'auto',
        'strategy': 'auto', 'complexityPolicy': 'direct', 'reviewPolicy': 'always'},
        mode='preflight', runs_dir=tmp_path, provider_config=raw,
        production_budget={'AFP': 100, 'CNY': 10},
        evaluation_budget={'AFP': 10, 'CNY': 1})
    assert result['status'] == 'no-feasible-route'
    assert result['live_authorization_preview']['ready'] is False
    assert result['review']['cost_upper_bound']['unit'] == 'CNY'
    assert result['review']['cost_upper_bound']['amount'] > 1
    assert any('CNY evaluation budget below required upper bound' in issue
               for issue in result['issues'])
    assert result['usage']['input_tokens'] == 0


def test_mixed_summary_keeps_external_jev_cost_separate_and_reports_known_total(tmp_path):
    task = '简短回答'
    evidence = {**local_evidence(task, '', 'UNKNOWN'), 'backend': 'jev',
        'provider': 'openrouter', 'costCny': .0123, 'callId': 'jev-call-1'}
    result = run_agent({'task': task, 'template': 'auto', 'strategy': 'auto',
        'complexityPolicy': 'direct', 'decompositionDecision': evidence},
        mode='preflight', runs_dir=tmp_path, provider_config=config(),
        production_budget={'AFP': 100, 'CNY': 10},
        evaluation_budget={'AFP': 10, 'CNY': 10})
    assert result['costs']['by_unit']['CNY']['production'] == 0
    assert result['costs']['out_of_band_judge'] == {
        'unit': 'CNY', 'cost': .0123, 'call_id': 'jev-call-1',
        'scope': 'decomposition-decision'}
    assert result['costs']['all_in_known_by_unit'] == {'AFP': 0, 'CNY': .0123}
