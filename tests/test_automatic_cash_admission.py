"""自动节点搜索与实际账本使用独立现金上限，不以参考价替代现金。"""
import pytest

from refractrouter.node_routing import NodeProfile, route_nodes
from refractrouter.task_budget import TaskCallBudget
from refractrouter.task_plan import validate_plan
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
