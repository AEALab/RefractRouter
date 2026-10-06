"""自动节点搜索与实际账本使用独立现金上限，不以参考价替代现金。"""
from dataclasses import replace
import pytest

from refractrouter.node_routing import NodeProfile, route_nodes
from refractrouter.planning_support import admission_diagnostics
from refractrouter.task_budget import TaskCallBudget
from refractrouter.task_plan import preview_plan, validate_plan
from refractrouter.task_runtime import _route_budget_shortfall
from tests.test_text_tasks import branched_plan
from tests.test_subscription_budget import model


def route(*, cash_max, quality=90, reference=100):
    plan = validate_plan(branched_plan())
    profiles = tuple(NodeProfile(mid, kind, q, cost, 1, 3)
        for mid, q, cost in [('cash', 90, 1), ('sub', quality, 4)]
        for kind in ('synthesis', 'generation'))
    return route_nodes(plan, profiles, method='A', quality_min=80,
        cost_max=reference, latency_max_ms=100, cash_max=cash_max,
        model_billing_modes={'cash': 'metered', 'sub': 'subscription'})


def test_exhausted_cash_still_allows_quality_qualified_subscription():
    result = route(cash_max=0)
    assert result['status'] == 'selected'
    assert set(result['assignments'].values()) == {'sub'}
    assert result['prediction']['cash_cost'] == 0
    assert result['diagnostics']['rejected_combinations']['cash'] > 0
    assert result['diagnostics']['remaining_cash'] == 0


def test_no_affordable_cash_must_not_lower_quality_or_ignore_reference_limit():
    assert route(cash_max=0, quality=70)['status'] == 'no-feasible-route'
    assert route(cash_max=0, reference=1)['status'] == 'no-feasible-route'
    assert route(cash_max=None, quality=70)['status'] == 'selected'


@pytest.mark.parametrize('limit', [-1, True, float('nan'), float('inf')])
def test_invalid_cash_constraint_is_rejected(limit):
    with pytest.raises(ValueError, match='cash_max'):
        route(cash_max=limit)


def test_cash_balance_includes_inflight_and_unknown_reservations():
    budget = TaskCallBudget(None, 10, 1, cash_limits={'production': .5, 'evaluation': .1})
    reservation = budget.reserve(model('metered'), [], label='cash')
    assert budget.remaining_cash() == pytest.approx(.5-reservation.row['charged'])
    assert budget.remaining_cash('evaluation') == .1
    budget.dispatch(reservation)
    budget.stop()
    assert budget.remaining_cash() == pytest.approx(.5-reservation.row['charged'])
    assert reservation.row['charged'] > 0


def test_zero_configuration_is_unlimited_but_exhausted_balance_is_zero():
    assert TaskCallBudget(None, 10, 1, cash_limits={'production': 0, 'evaluation': 0}).remaining_cash() is None
    probe = TaskCallBudget(None, 10, 1)
    exact_limit = probe.reserve(model('metered'), [], label='probe').row['reserved']
    budget = TaskCallBudget(None, 10, 1, cash_limits={'production': exact_limit, 'evaluation': .1})
    reservation = budget.reserve(model('metered'), [], label='cash')
    assert budget.remaining_cash() == pytest.approx(0)
    budget.stop()
    assert budget.remaining_cash() == exact_limit
    assert reservation.row['status'] == 'cancelled-before-dispatch'


def test_runtime_blocks_unaffordable_route_before_any_model_dispatch():
    from tests.test_automatic_actual_catalog import fixture
    from refractrouter.dsh_model_pool import compile_dsh_model_pool
    from refractrouter.application_config import compile_configuration
    from refractrouter.configured_routing import configured_profile
    from refractrouter.task_plan import preview_plan
    from refractrouter.task_runtime import run_task
    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    pool.update(schemaVersion='refractagent-dsh-model-pool-v5',
                cashLimits={'production': .000000001, 'evaluation': 1})
    config, _ = compile_dsh_model_pool(pool, catalog)
    compiled = compile_configuration(config)
    plan = preview_plan('简短回答')
    profile = configured_profile(compiled, compiled.manifest, plan.to_dict())
    class Client:
        def complete(self, *args, **kwargs):
            raise AssertionError('现金不足的路线不得派发任何模型请求')
    result = run_task({'task': '简短回答', 'mode': 'run', 'method': 'A', 'qualityMin': 80,
        'costMax': 100, 'latencyMaxMs': 300000, 'plan': plan.to_dict()}, compiled.manifest,
        profile, client=Client(), production_limit=100, evaluation_limit=100,
        configured_application=True, configuration=compiled)
    assert result['routing']['status'] == 'no-feasible-route'
    assert result['routing']['diagnostics']['rejected_combinations']['cash'] > 0
    assert result['calls'] == []


def test_second_level_rejects_cash_tool_continuation_even_when_reference_fits():
    route = {'prediction': {'cost': 1.0, 'cash_cost': .04}}
    shortage = _route_budget_shortfall(route, reference_allowance=2.0,
        cash_allowance=.07, judge_reference=.01, judge_is_metered=True,
        remaining_production=10, remaining_evaluation=1,
        remaining_cash=.10, remaining_evaluation_cash=.02)
    assert shortage == {'production_cash': pytest.approx(.01)}


def test_second_level_keeps_subscription_tool_and_judge_when_cash_is_exhausted():
    route = {'prediction': {'cost': 1.0, 'cash_cost': 0.0}}
    shortage = _route_budget_shortfall(route, reference_allowance=2.0,
        cash_allowance=0.0, judge_reference=.01, judge_is_metered=False,
        remaining_production=10, remaining_evaluation=1,
        remaining_cash=0.0, remaining_evaluation_cash=0.0)
    assert shortage == {}


def test_second_level_rejects_metered_evaluation_cash_shortfall():
    route = {'prediction': {'cost': 1.0, 'cash_cost': 0.0}}
    shortage = _route_budget_shortfall(route, reference_allowance=2.0,
        cash_allowance=0.0, judge_reference=.03, judge_is_metered=True,
        remaining_production=10, remaining_evaluation=1,
        remaining_cash=0.0, remaining_evaluation_cash=.02)
    assert shortage == {'evaluation_cash': pytest.approx(.01)}


def test_each_configured_model_reports_why_it_cannot_execute_a_node():
    plan = preview_plan('概述结果')
    base = replace(model(), context_window=200000, max_output_tokens=2048)
    candidates = {name: replace(base, model_id=name) for name in ('ready', 'weak', 'unknown', 'small')}
    candidates['small'] = replace(candidates['small'], context_window=65536)
    profiles = tuple(NodeProfile(name, 'generation', score, 1, 100, 0)
        for name, score in (('ready', 90), ('weak', 60), ('small', 90)))
    row = admission_diagnostics(plan, '概述结果', candidates, profiles, 80)['deliverable']
    assert row['eligible_models'] == ['ready']
    assert row['model_reasons'] == {'ready': 'eligible', 'weak': 'quality-below-minimum',
                                   'unknown': 'missing-profile', 'small': 'input-or-output-capacity'}


def test_live_comparison_stops_after_planner_when_tool_cash_is_insufficient(tmp_path):
    from tests.test_automatic_actual_catalog import fixture
    from tests.test_live_execution import CompactClient, authorization
    from refractrouter.agent import run_agent
    from refractrouter.dsh_model_pool import compile_dsh_model_pool
    from refractrouter.tool_runtime import StdioToolRuntime

    pool, catalog = fixture('deepseek-official', 'deepseek-flash', 'CNY')
    pool.update(schemaVersion='refractagent-dsh-model-pool-v5',
                cashLimits={'production': .1, 'evaluation': 1})
    config, _ = compile_dsh_model_pool(pool, catalog)
    schemas = [{'name': 'web_search', 'description': '查询网页', 'parameters': {'type': 'object'}}]
    runtime = StdioToolRuntime(schemas, object(), max_calls=2)
    payload = {'task': '分别比较甲与乙，再汇总。', 'strategy': 'auto', 'maxDshToolCalls': 2}
    preview = run_agent(payload, provider_config=config, runs_dir=tmp_path/'preview',
                        tool_runtime=runtime, production_budget=100, evaluation_budget=100)
    client = CompactClient()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
                       provider_config=config, runs_dir=tmp_path/'live', mode='live',
                       execute_paid_run=True, client=client, tool_runtime=runtime,
                       production_budget=100, evaluation_budget=100)
    assert result['status'] == 'no-feasible-route'
    assert set(result['route_comparison']['budget_shortfalls']) == {'direct', 'dag'}
    assert all('production_cash' in shortage
               for shortage in result['route_comparison']['budget_shortfalls'].values())
    assert len(client.calls) == 1  # 已结算的规划探测；不派发执行和工具调用
