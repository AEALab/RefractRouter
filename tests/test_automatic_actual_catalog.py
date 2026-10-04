"""自动路由复用实际路线计价；不同单位与缺失质量证据不能混用。"""
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from refractrouter.application_config import compile_configuration
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.openai_compatible import ChatResponse
from refractrouter.planning_model_metadata import lookup
from refractrouter.task_budget import TaskCallBudget

PLAN = 'https://ark.cn-beijing.volces.com/api/plan/v3'


def fixture(provider, model, unit):
    route = {'provider': provider, 'model': model, 'deployment': 'trusted-cloud', 'trustPolicy': 'team'}
    pool = {'schemaVersion': 'refractagent-dsh-model-pool-v3', 'billingUnit': unit,
        'allowSharedJudge': True, 'routes': [route],
        'trustPolicies': [{'id': 'team', 'residency': 'CN', 'auditLogging': True, 'allowsSensitiveData': True}],
        'security': {'dataMode': 'synthetic', 'sensitiveTerms': [], 'classifier': {'enabled': True}}}
    host = {'provider': provider, 'model': model, 'contextWindow': 1048576,
        'maxOutputTokens': 8192, 'providerBaseURL': PLAN if provider == 'ark' else None}
    return pool, {'schemaVersion': 'refractagent-dsh-catalog-v1', 'routes': [host]}


@pytest.mark.parametrize('model', ['kimi-k3', 'deepseek-v4-pro', 'glm-5.3', 'minimax-m3'])
def test_ark_uses_plan_afp_not_manufacturer_usd(model):
    pool, catalog = fixture('ark', model, 'AFP')
    config, evidence = compile_dsh_model_pool(pool, catalog)
    metadata = lookup({'provider': 'ark', 'model': model, 'billingUnit': 'AUTO',
        'providerBaseURL': PLAN, 'host': catalog['routes'][0]})
    assert config['models'][0]['pricing'] == {'unit': 'AFP', **metadata['pricing']}
    assert evidence['ark/' + model]['price_source_unit'] == 'AFP'
    assert 'currency_conversion' not in evidence['ark/' + model]


def test_actual_endpoint_is_required_and_currency_mixing_is_rejected():
    pool, catalog = fixture('ark', 'kimi-k3', 'CNY')
    with pytest.raises(ValueError, match='matching billing group'):
        compile_dsh_model_pool(pool, catalog)
    catalog['routes'][0]['providerBaseURL'] = 'https://example.invalid'
    with pytest.raises(ValueError, match='实际路线价格'):
        compile_dsh_model_pool(pool, catalog)


def test_moonshot_official_cny_and_default_cache_write_are_not_double_billed():
    pool, catalog = fixture('moonshot', 'kimi-k3', 'CNY')
    catalog['routes'][0]['providerBaseURL'] = 'https://api.moonshot.cn/v1'
    config, evidence = compile_dsh_model_pool(pool, catalog)
    model = compile_configuration(config).manifest.models[0]
    assert model.input_cost_per_1k == .02
    assert model.cached_input_cost_per_1k == .002
    assert model.output_cost_per_1k == .1
    budget = TaskCallBudget(None, 1, 1)
    reservation = budget.reserve(model, [{'role': 'user', 'content': '合成测试'}], label='worker')
    budget.dispatch(reservation)
    # 总输入含 600 个缓存写入、200 个缓存读取、200 个普通输入。
    response = ChatResponse('完成', 1000, 20, 200, 0, 10, 1, 'stop', 'mock',
        raw_usage={'cacheWriteTokens': 600})
    budget.settle(reservation, response)
    assert reservation.row['charged'] == pytest.approx(.0184)
    assert evidence['moonshot/kimi-k3']['price_source_unit'] == 'CNY'
    catalog['routes'][0]['providerBaseURL'] = 'https://example.invalid/v1'
    with pytest.raises(ValueError, match='实际路线价格'):
        compile_dsh_model_pool(pool, catalog)


def test_new_models_have_verified_prices_but_no_invented_quality():
    pool, catalog = fixture('ark', 'deepseek-v4.1-flash', 'AFP')
    info = lookup({'provider': 'ark', 'model': 'deepseek-v4.1-flash', 'billingUnit': 'AUTO',
        'providerBaseURL': PLAN, 'host': catalog['routes'][0]})
    assert info['pricing'] and not info['issues']
    assert info['automaticRouting']['issues']
    with pytest.raises(ValueError, match='quality prior'):
        compile_dsh_model_pool(pool, catalog)


def test_actual_routes_reject_manual_prices_and_simulated_zero_cost():
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    pool['routes'][0]['overrides'] = {'inputPer1k': 0}
    with pytest.raises(ValueError, match='manual prices'):
        compile_dsh_model_pool(pool, catalog)
    pool['routes'][0].pop('overrides')
    pool['routes'][0]['deployment'] = 'simulated-local'
    with pytest.raises(ValueError, match='simulated-local'):
        compile_dsh_model_pool(pool, catalog)


def test_official_cash_reserves_peak_and_settles_dispatch_time_tier():
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    config, evidence = compile_dsh_model_pool(pool, catalog)
    assert config['models'][0]['pricing']['inputPer1k'] == .002
    compiled = compile_configuration(config)
    model = compiled.manifest.models[0]
    budget = TaskCallBudget(None, 1, 1)
    reservation = budget.reserve(model, [{'role': 'user', 'content': '合成测试'}], label='worker')
    budget.dispatch(reservation)
    reservation.row['dispatch_at'] = datetime(2026, 10, 4, tzinfo=timezone.utc).isoformat()
    response = ChatResponse('完成', 100, 20, 0, 0, 10, 1, 'stop', 'mock')
    budget.settle(reservation, response)
    assert reservation.row['charged'] == pytest.approx(100/1000*.001+20/1000*.004)
    assert reservation.row['price_snapshot']['tier'] == 'offpeak'
    assert reservation.row['reserved'] > reservation.row['charged']
    assert evidence['deepseek-official/deepseek-flash']['pricing_materialization']['strategy'] == 'peak-budget-current-tier-settlement'


def test_price_policy_cannot_spoof_provider_or_underreserve():
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    config, _ = compile_dsh_model_pool(pool, catalog)
    wrong = deepcopy(config)
    wrong['models'][0]['pricing']['inputPer1k'] = .001
    with pytest.raises(ValueError, match='pricePolicy'):
        compile_configuration(wrong)
    wrong = deepcopy(config)
    wrong['providers'][0]['dshProvider'] = 'other'
    with pytest.raises(ValueError, match='pricePolicy'):
        compile_configuration(wrong)


def test_explicit_live_cap_also_bounds_compact_planner(tmp_path):
    import json
    from refractrouter.agent import run_agent
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    config, _ = compile_dsh_model_pool(pool, catalog)
    result = run_agent({'task': '合成任务', 'template': 'auto', 'boundedCallOutput': True},
        mode='preflight', runs_dir=tmp_path, provider_config=config, max_output_tokens=2048)
    request = json.loads((__import__('pathlib').Path(result['run_dir'])/'request.json').read_text())
    assert request['runtime_request']['unrestrictedPlanning'] is False
    assert request['runtime_request']['plannerMaxOutputTokens'] == 2048
