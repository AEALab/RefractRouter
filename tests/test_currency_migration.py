"""配置升级不能借金额转换改变策略或取得新提供方权限。"""
from copy import deepcopy
from dataclasses import replace

import pytest

from refractrouter.currency_migration import migrate_planning
from refractrouter.planning_config import compile_config
from refractrouter.openai_compatible import ChatResponse, model_response_cost
from refractrouter.schemas import ModelSpec
from tests.test_planning_routing import advisor_gate_configuration, composite_configuration


def test_cash_upgrade_preserves_advisor_flow_and_existing_cny_limit():
    original = advisor_gate_configuration()
    original['billingUnit'] = 'AFP'
    original['maxProductionCost'] = 5000
    original['maxProductionCostByUnit'] = {'AFP': 5000, 'CNY': 3}
    before = deepcopy(original)
    result = migrate_planning(original, {})
    c = compile_config(result['configuration'])
    assert c['budgets'] == {'CNY': 3}
    assert c['advisor']['flow'] == 'gate-v2'
    assert (c['advisor']['maxReviews'], c['advisor']['maxRedos']) == (2, 1)
    assert result['configuration']['advisor'] == original['advisor']
    assert original == before


def test_no_implicit_afp_conversion_and_zero_budget_is_explicit():
    cfg = advisor_gate_configuration()
    cfg.update(billingUnit='AFP', maxProductionCost=5000, maxProductionCostByUnit={'AFP': 5000})
    with pytest.raises(ValueError, match='明确 CNY'):
        migrate_planning(cfg, {})
    result = migrate_planning(cfg, {}, cny_budget=0)
    assert compile_config(result['configuration'])['budgets'] == {'CNY': 0}


def test_provider_change_clears_old_pair_acceptance_and_requires_data_domain():
    cfg = advisor_gate_configuration()
    cfg['compatiblePairs'] = [['small', 'large'], ['judge', 'large']]
    target = {**cfg['models'][0], 'provider': 'new-cash-provider'}
    target.pop('deployment')
    with pytest.raises(ValueError, match='数据域'):
        migrate_planning(cfg, {'small': target})
    target['deployment'] = 'external-cloud'
    result = migrate_planning(cfg, {'small': target})
    assert result['configuration']['compatiblePairs'] == [['judge', 'large']]
    assert result['historyCompatibilityRequiresValidation'] == ['small']


def test_v7_rejects_afp_models_and_media_even_when_overall_unit_is_cny():
    cfg = advisor_gate_configuration()
    cfg['schemaVersion'] = 'refractagent-planning-v7'
    for key in ('models', 'mediaRoutes'):
        bad = deepcopy(cfg)
        bad.setdefault(key, []).append({'id': 'unconverted', 'billingUnit': 'AFP'})
        with pytest.raises(ValueError, match='AFP 路线'):
            compile_config(bad)


def test_cash_amount_not_rounded_to_zero_and_invalid_cache_is_rejected():
    model = ModelSpec('tiny', 'official', .0000001, .0000001, 1, billing_unit='CNY')
    response = ChatResponse('ok', 1, 1, 0, 0, 1, 1, 'stop', 'mock')
    assert model_response_cost(model, response) == 2e-10
    with pytest.raises(ValueError, match='不能超过'):
        model_response_cost(model, replace(response, cached_input_tokens=2))
    # 冻结 AFP 历史计算口径保留，不以新金额合同重写订阅记录。
    assert model_response_cost(replace(model, billing_unit='AFP'), response) == 0


def test_composite_migration_keeps_task_pool_and_stage_rules():
    cfg = composite_configuration()
    before = compile_config(cfg)
    after = compile_config(migrate_planning(cfg, {})['configuration'])
    assert after['composite'] == before['composite']
    assert after['strategy'] == before['strategy']
    assert after['max_calls'] == before['max_calls']


def test_afp_route_cannot_be_migrated_by_relabeling_currency():
    cfg = advisor_gate_configuration()
    cfg['models'][0]['billingUnit'] = 'AFP'
    relabeled = {**cfg['models'][0], 'billingUnit': 'CNY'}
    with pytest.raises(ValueError, match='AFP 标签'):
        migrate_planning(cfg, {'small': relabeled})


def test_new_automatic_pool_only_compiles_actual_cash_routes():
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.dsh_model_pool import compile_dsh_model_pool
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    pool['schemaVersion'] = 'refractagent-dsh-model-pool-v5'
    pool['cashLimits'] = {'production': 10, 'evaluation': 1}
    cfg, _ = compile_dsh_model_pool(pool, catalog)
    assert cfg['billingUnit'] == 'CNY'
    assert all(model['pricing']['unit'] == 'CNY' for model in cfg['models'])
    pool['billingUnit'] = 'AFP'
    with pytest.raises(ValueError, match='CNY 预算'):
        compile_dsh_model_pool(pool, catalog)
    pool, catalog = fixture('ark', 'glm-5.3', 'CNY')
    pool['schemaVersion'] = 'refractagent-dsh-model-pool-v5'
    pool['cashLimits'] = {'production': 10, 'evaluation': 1}
    with pytest.raises(ValueError, match='matching billing group'):
        compile_dsh_model_pool(pool, catalog)


def test_currency_migration_protocol_and_native_call_use_cash_ledger(tmp_path):
    from refractrouter.planning_runtime import PlanningRuntime
    from tests.test_planning_routing import begin, step, receipt
    runtime = PlanningRuntime(tmp_path)
    assert 'planning-routing-v7' in runtime.handle({'op': 'handshake'})['capabilities']
    migration = runtime.handle({'op': 'currency-migration',
        'config': advisor_gate_configuration(), 'bindings': {}})
    assert not migration['configurationWritten']
    run = begin(runtime, strategy='static', config=migration['configuration'])
    action = step(runtime, run)
    result = receipt(runtime, run, action)
    assert result['action'] == 'release'
    call = result['record']['calls'][0]
    assert call['billing_unit'] == 'CNY'
    assert call['cost_basis'] == 'public-price-calculation'
    assert call['provider_cost_confirmed'] is False


def subscription_config():
    cfg = advisor_gate_configuration()
    cfg.update(schemaVersion='refractagent-planning-v7', maxReferenceCost=100,
               maxProductionCost=.000001, maxProductionCostByUnit={'CNY': .000001})
    for row in cfg['models']:
        row['billingMode'] = 'subscription'
        row['referencePricing'] = {
            'executionEndpoint': 'https://ark.cn-beijing.volces.com/api/plan/v3',
            'price': {'schemaVersion': 'refractrouter-currency-price-v1',
                'provider': 'official', 'model': row['model'], 'endpoint': 'https://example.com/v1',
                'currency': 'CNY', 'rates': {'input': '.00002', 'output': '.0001'},
                'source': 'https://example.com/pricing', 'checkedAt': '2026-10-06',
                'basis': 'route-public-price'},
            'mapping': {'match': 'verified-version', 'source': 'https://example.com/models',
                        'checkedAt': '2026-10-06', 'description': '模拟的版本匹配证据'}}
    return cfg


def test_subscription_config_derives_prices_and_preserves_execution_identity():
    cfg = subscription_config()
    result = compile_config(cfg)
    assert not result['model_issues']
    model = result['models']['small']
    assert model.provider == cfg['models'][0]['provider']
    assert model.input_cost_per_1k == .02
    assert model.billing_mode == 'subscription'
    old = deepcopy(cfg)
    old['schemaVersion'] = 'refractagent-planning-v6'
    old.pop('maxReferenceCost')
    old['models'][0]['billingUnit'] = 'AFP'
    migrated = migrate_planning(old, {'small': cfg['models'][0]}, reference_budget=100)
    assert migrated['changedModelIds'] == []
    assert not compile_config(migrated['configuration'])['model_issues']


@pytest.mark.parametrize('strategy', ['static', 'stage', 'advisor', 'escalation'])
def test_subscription_native_path_does_not_require_cash_for_executor(tmp_path, strategy):
    from refractrouter.planning_runtime import PlanningRuntime
    from tests.test_planning_routing import begin, step, receipt
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, strategy=strategy, config=subscription_config())
    action = step(runtime, run)
    assert action['action'] == 'call'
    result = receipt(runtime, run, action)
    record = runtime.persist(runtime.require(run))
    assert record['costsByUnit']['CNY']['production'] == 0
    assert record['referenceCosts']['occupied'] > 0
    assert record['calls'][0]['cash_cost_cny'] is None
    assert record['calls'][0]['reference_pricing']['executionEndpoint'].endswith('/api/plan/v3')
    # 所有实际执行／审核仍走宿主调用；仅计价依据改变。
    assert result['action'] in ('call', 'release')


def test_advisor_cash_reviewer_still_requires_cash_before_subscription_execution(tmp_path):
    from refractrouter.planning_runtime import PlanningRuntime
    from tests.test_planning_routing import begin, step
    cfg = subscription_config()
    judge_id = cfg['advisor']['judge']['modelId']
    for model in cfg['models']:
        if model['id'] == judge_id:
            model['billingMode'] = 'metered'
            model.pop('referencePricing')
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, strategy='advisor', config=cfg)
    with pytest.raises(ValueError, match='预算不足'):
        step(runtime, run)
    assert runtime.require(run)['budget'].records == []


def test_host_metadata_keeps_subscription_endpoint_and_host_capacity():
    from refractrouter.planning_model_metadata import lookup
    row = subscription_config()['models'][0]
    request = {'provider': 'ark', 'model': 'deepseek-v4-flash', 'billingUnit': 'AUTO',
               'billingMode': 'subscription', 'referencePricing': row['referencePricing'],
               'providerBaseURL': row['referencePricing']['executionEndpoint'],
               'host': {'contextWindow': 64000, 'maxOutputTokens': 1000}}
    info = lookup(request)
    assert info['billingUnit'] == 'CNY'
    assert info['pricingBasis'] == 'reference-price'
    assert info['pricing']['inputPer1k'] == .02
    assert info['capacity']['contextWindow'] == 64000
    assert info['provider'] == 'ark'
    assert not info['issues']
    with pytest.raises(ValueError, match='实际端点不一致'):
        lookup({**request, 'providerBaseURL': 'https://example.com/v1'})


def test_automatic_pool_preserves_subscription_model_with_reference_price():
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.dsh_model_pool import compile_dsh_model_pool
    from refractrouter.application_config import compile_configuration
    pool, catalog = fixture('ark', 'glm-5.3', 'CNY')
    pool.update(schemaVersion='refractagent-dsh-model-pool-v5',
                cashLimits={'production': .01, 'evaluation': .01})
    row = pool['routes'][0]
    row.update(billingMode='subscription', referencePricing=subscription_config()['models'][0]['referencePricing'])
    config, evidence = compile_dsh_model_pool(pool, catalog)
    compiled = compile_configuration(config)
    assert config['schemaVersion'] == 'refractagent-providers-v6'
    assert all(m.billing_mode == 'subscription' for m in compiled.manifest.models)
    assert all(m.billing_unit == 'CNY' for m in compiled.manifest.models)
    assert all(m.provider == 'ark' for m in compiled.manifest.models)


def test_automatic_subscription_run_reports_reference_and_cash_separately():
    import json
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.dsh_model_pool import compile_dsh_model_pool
    from refractrouter.application_config import compile_configuration
    from refractrouter.configured_routing import configured_profile
    from refractrouter.task_plan import preview_plan
    from refractrouter.task_runtime import run_task
    pool, catalog = fixture('ark', 'glm-5.3', 'CNY')
    pool.update(schemaVersion='refractagent-dsh-model-pool-v5', cashLimits={'production': .000001, 'evaluation': .000001})
    pool['routes'][0].update(billingMode='subscription', referencePricing=subscription_config()['models'][0]['referencePricing'])
    cfg, _ = compile_dsh_model_pool(pool, catalog)
    compiled = compile_configuration(cfg)
    plan = preview_plan('简短回答')
    profile = configured_profile(compiled, compiled.manifest, plan.to_dict())
    class Client:
        def complete(self, model, messages, *, json_mode=False):
            payload = json.loads(messages[-1]['content'])
            if 'criteria' in payload:
                answer = {'score': 92, 'passed': True, 'rationale': '模拟验收',
                          'criteria': [{'criterion': c, 'passed': True, 'rationale': '覆盖'} for c in payload['criteria']]}
            else:
                answer = {key: '模拟答案' for key in payload['contract']['output']['fields']}
            return ChatResponse(json.dumps(answer), 100, 80, 0, 0, 10, 1, 'stop', 'mock')
    result = run_task({'task': '简短回答', 'mode': 'run', 'method': 'A', 'qualityMin': 80,
        'costMax': 100, 'latencyMaxMs': 300000, 'plan': plan.to_dict()}, compiled.manifest,
        profile, client=Client(), production_limit=100, evaluation_limit=100,
        configured_application=True, configuration=compiled)
    assert result['status'] == 'completed', result['issues']
    assert result['reference_costs_cny']['production'] > 0
    assert result['cash_costs_cny'] == {'production': 0, 'evaluation': 0}
    assert all(call['billing_mode'] == 'subscription' for call in result['calls'])


def test_ark_migration_populates_packaged_reference_without_replacing_model():
    cfg = advisor_gate_configuration()
    first = cfg['models'][0]
    first.update(provider='ark', model='glm-5.3', billingUnit='AFP')
    migrated = migrate_planning(cfg, {}, reference_budget=100)['configuration']
    row = migrated['models'][0]
    assert (row['provider'], row['model']) == ('ark', 'glm-5.3')
    assert row['billingMode'] == 'subscription'
    assert row['referencePricing']['price']['provider'] == 'openrouter'
    assert row['referencePricing']['mapping']['match'] == 'published-model-name'
    assert not compile_config(migrated)['model_issues']


def test_minimax_reference_uses_official_cny_and_actual_input_tier():
    from refractrouter.subscription_reference import planning_binding
    from refractrouter.currency_pricing import reference_price
    cfg = subscription_config()
    cfg['models'][0] = planning_binding({**cfg['models'][0], 'provider': 'ark', 'model': 'minimax-m3'})
    model = compile_config(cfg)['models']['small']
    reference = model.reference_pricing
    assert reference['price']['currency'] == 'CNY'
    low = reference_price(reference, input_tokens=524288)
    high = reference_price(reference, input_tokens=524289)
    assert dict(high.rates)['input'] == 2 * dict(low.rates)['input']
    response = ChatResponse('ok', 100, 20, 0, 0, 1, 1, 'stop', 'mock')
    assert model_response_cost(model, response) == pytest.approx(.000378)
    assert model.input_cost_per_1k == .0042  # 预留覆盖长输入阶梯


def test_automatic_migration_keeps_roles_and_disabled_unpriced_models():
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.currency_migration import migrate_pool
    pool, catalog = fixture('ark', 'glm-5.3', 'AFP')
    pool['routes'].append({'provider': 'ark', 'model': 'unpriced', 'enabled': False, 'deployment': 'external-cloud'})
    before = deepcopy(pool)
    result = migrate_pool(pool, catalog, production_cash=2, evaluation_cash=.1)
    assert pool == before
    assert result['configuration']['routes'][0]['model'] == 'glm-5.3'
    assert result['configuration']['cashLimits'] == {'production': 2, 'evaluation': .1}
    assert result['configuration']['routes'][1]['enabled'] is False
    assert not result['configurationWritten']


def test_media_migration_preserves_subscription_endpoint_and_acceptance_status():
    from refractrouter.subscription_reference import ARK_ENDPOINT
    cfg = advisor_gate_configuration()
    original = {'id': 'seedream', 'provider': 'ark-plan', 'credentialProvider': 'ark',
        'model': 'doubao-seedream-5.0-lite', 'operations': ['image-generate', 'image-edit'],
        'billingUnit': 'AFP', 'pricing': {'basis': 'image', 'unitCost': 99,
        'source': 'https://docs.volcengine.com/', 'checkedAt': '2026-09-26'},
        'deployment': 'external-cloud', 'verification': 'connected', 'endpoint': ARK_ENDPOINT}
    cfg['mediaRoutes'] = [original]
    draft = migrate_planning(cfg, {}, reference_budget=10)['configuration']
    route = compile_config(draft)['media_routes'][0]
    for key in ('endpoint', 'credentialProvider', 'model', 'verification', 'deployment'):
        assert route[key] == original[key]
    assert route['billingMode'] == 'subscription'
    assert route['billingUnit'] == 'CNY'
    assert route['pricing']['unitCost'] == .22
    assert cfg['mediaRoutes'][0]['billingUnit'] == 'AFP'
    draft['mediaRoutes'][0]['pricing']['unitCost'] = 99
    with pytest.raises(ValueError, match='快照不一致'):
        compile_config(draft)


def test_subscription_media_runtime_uses_reference_ledger(tmp_path):
    from refractrouter.subscription_reference import media_binding, ARK_ENDPOINT
    from refractrouter.planning_runtime import PlanningRuntime
    from tests.test_planning_routing import begin
    cfg = migrate_planning(advisor_gate_configuration(), {}, reference_budget=10)['configuration']
    cfg['mediaRoutes'] = [media_binding({'id': 'image', 'provider': 'ark-plan',
        'model': 'doubao-seedream-5.0-lite', 'operations': ['image-generate'],
        'endpoint': ARK_ENDPOINT, 'verification': 'verified', 'deployment': 'external-cloud'})]
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, 'static', config=cfg)
    op = runtime.handle({'op': 'media-reserve', 'runId': run, 'routeId': 'image',
        'operation': 'image-generate', 'maxUnits': 2, 'input': {'prompt': '公开风景'}})
    runtime.handle({'op': 'media-update', 'runId': run, 'operationId': op['operationId'],
        'status': 'submitted', 'providerTaskId': 'existing-result'})
    runtime.handle({'op': 'media-update', 'runId': run, 'operationId': op['operationId'],
        'status': 'succeeded', 'actualUnits': 1, 'artifacts': [{'attachmentId': 'saved-image'}]})
    budget = runtime.runs[run]['budget']
    assert budget.snapshot()[0]['CNY']['production'] == 0
    assert budget.reference_snapshot()['occupied'] == .22
    assert budget.records[-1]['cash_cost_cny'] is None


def test_gateway_rejects_cash_endpoint_under_subscription_reference(tmp_path):
    from refractrouter.model_gateway import ModelGateway
    cfg = subscription_config()
    providers = {m['provider']: {'baseURL': m['referencePricing']['executionEndpoint']}
                 for m in cfg['models']}
    gateway = ModelGateway({'providers': providers, 'planningRouting': cfg}, tmp_path/'good')
    gateway.close()
    for route in providers.values():
        route['baseURL'] = 'https://ark.cn-beijing.volces.com/api/v3'
    with pytest.raises(ValueError, match='实际调用端点不一致'):
        ModelGateway({'providers': providers, 'planningRouting': cfg}, tmp_path/'bad')


def test_explicit_pool_migration_removes_only_legacy_afp_constraint():
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.currency_migration import migrate_pool
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    pool.setdefault('objective', {}).update(maxAfpCoefficient=2, qualityMin=80,
                                            primary='cost', secondary='latency', dagMode='auto')
    before = deepcopy(pool)
    result = migrate_pool(pool, catalog, production_cash=2, evaluation_cash=1)
    assert result['removedLegacyConstraints'] == ['objective.maxAfpCoefficient']
    assert 'maxAfpCoefficient' not in result['configuration']['objective']
    assert result['configuration']['objective']['qualityMin'] == 80
    assert pool == before


@pytest.mark.parametrize('strategy', ['task', 'composite'])
def test_pool_strategies_settle_subscription_judge_and_execution_without_cash(tmp_path, strategy):
    import json
    from refractrouter.planning_runtime import PlanningRuntime
    from tests.test_planning_routing import task_pool_configuration, begin, step, receipt
    cfg = task_pool_configuration() if strategy == 'task' else composite_configuration()
    cfg.update(schemaVersion='refractagent-planning-v7', maxReferenceCost=100,
               maxProductionCost=.000001, maxProductionCostByUnit={'CNY': .000001})
    references = {row['id']: row['referencePricing'] for row in subscription_config()['models']}
    for model in cfg['models']:
        model.update(billingMode='subscription', referencePricing=references[model['id']])
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, strategy, config=cfg)
    judge = step(runtime, run)
    assert judge['purpose'] == 'task'
    execute = receipt(runtime, run, judge, json.dumps({'answers': {'candidates': {
        'small': {'score': .91, 'missingInformation': .02},
        'large': {'score': .92, 'missingInformation': .01}}}}))
    assert execute['purpose'] == 'execute'
    receipt(runtime, run, execute)
    record = runtime.persist(runtime.require(run))
    assert record['costsByUnit']['CNY']['production'] == 0
    assert record['referenceCosts']['occupied'] > 0
    assert [row['purpose'] for row in record['calls']] == ['task', 'execute']
    assert all(row['cash_cost_cny'] is None for row in record['calls'])
