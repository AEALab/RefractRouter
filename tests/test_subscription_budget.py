"""同币种参考成本与现金费用分别约束，订阅调用不得挤占现金额度。"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace, dataclass

import pytest

from refractrouter.planning_budget import PlanningBudget, REFERENCE
from refractrouter.schemas import ModelSpec
from refractrouter.openai_compatible import ChatResponse


@dataclass(frozen=True)
class BillingModel(ModelSpec):
    billing_mode: str = 'metered'
    cache_write_cost_per_1k: float | None = None


def model(mode='subscription'):
    return BillingModel('ark-model', 'ark', 1, 1, 1, billing_unit='CNY',
                     billing_mode=mode, context_window=10000, max_output_tokens=10)


def test_subscription_and_cash_share_reference_ceiling_but_not_cash_ledger():
    budget = PlanningBudget({'CNY': .5}, reference_limit=1)
    sub = budget.reserve(model(), [], label='subscription')
    budget.dispatch(sub)
    budget.settle(sub, ChatResponse('ok', 100, 10, 0, 0, 1, 1, 'stop', 'mock'))
    assert budget.remaining('CNY') == .5
    assert budget.reference_snapshot()['occupied'] == pytest.approx(.11)
    assert sub.row['cash_cost_cny'] is None
    assert sub.row['cost_basis'] == 'subscription-reference-valuation'
    paid = budget.reserve(model('metered'), [], label='cash')
    budget.dispatch(paid)
    budget.settle(paid, ChatResponse('ok', 100, 10, 0, 0, 1, 1, 'stop', 'mock'))
    assert budget.remaining('CNY') == pytest.approx(.39)
    assert budget.reference_snapshot()['occupied'] == pytest.approx(.22)
    costs, _ = budget.snapshot()
    assert costs['CNY']['production'] == pytest.approx(.11)
    assert budget.requirements(model(), .3) == {REFERENCE: .3}
    assert budget.requirements(model('metered'), .3) == {REFERENCE: .3, 'CNY': .3}


def test_shared_reference_limit_is_atomic_and_cancel_releases_only_undispatched():
    budget = PlanningBudget({'CNY': 0}, reference_limit=.4)
    def attempt(i):
        try:
            return budget.reserve(model(), [], label=str(i))
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    accepted = [row for row in results if row]
    assert len(accepted) == 1
    budget.dispatch(accepted[0])
    with pytest.raises(ValueError, match='usage'):
        budget.settle(accepted[0], replace(ChatResponse('ok', 100, 10, 0, 0, 1, 1, 'stop', 'mock'), usage_available=False))
    occupied = budget.reference_snapshot()['occupied']
    budget.stop()
    assert budget.reference_snapshot()['occupied'] == occupied
    assert budget.remaining('CNY') == float('inf')
    other = PlanningBudget({'CNY': 0}, reference_limit=.4)
    other.reserve(model(), [], label='not-dispatched')
    other.stop()
    assert other.reference_snapshot()['occupied'] == 0


def test_legacy_ledger_cannot_silently_accept_subscription_currency():
    with pytest.raises(ValueError, match='新版参考成本'):
        PlanningBudget({'CNY': 10}).reserve(model(), [], label='subscription')


@pytest.mark.parametrize('limit', [True, -1, float('inf'), float('nan')])
def test_reference_limit_requires_finite_nonnegative_value(limit):
    with pytest.raises(ValueError, match='上限'):
        PlanningBudget({'CNY': 0}, reference_limit=limit)


def test_automatic_cash_ceiling_does_not_charge_subscription_reference():
    from refractrouter.task_budget import TaskCallBudget
    budget = TaskCallBudget(None, 10, 1, cash_limits={'production': .001, 'evaluation': .001})
    sub = budget.reserve(model(), [], label='subscription')
    budget.dispatch(sub)
    budget.settle(sub, ChatResponse('ok', 100, 10, 0, 0, 1, 1, 'stop', 'mock'))
    assert budget.cash_snapshot()['production'] == 0
    assert budget.snapshot()[0]['production'] == pytest.approx(.11)
    assert sub.row['cash_cost_cny'] is None
    with pytest.raises(ValueError, match='cash-budget-exhausted'):
        budget.reserve(model('metered'), [], label='cash')


def test_subscription_media_settlement_and_cancellation_keep_cash_separate():
    budget = PlanningBudget({'CNY': .01}, reference_limit=1)
    def reserve():
        return budget.reserve_non_token('CNY', .44, label='image', purpose='image-generate',
            usage={'basis': 'image', 'model': 'seedream', 'provider': 'ark-plan'}, billing_mode='subscription')
    first = reserve()
    budget.cancel_non_token(first)
    assert budget.reference_snapshot()['occupied'] == 0
    second = reserve()
    budget.dispatch_non_token(second, operation_id='generated')
    budget.settle_non_token(second, .22, {'basis': 'image', 'actualUnits': 1})
    assert second['cash_cost_cny'] is None
    assert second['reference_cost_cny'] == .22
    third = reserve()
    budget.dispatch_non_token(third, operation_id='unknown')
    budget.stop()
    assert budget.reference_snapshot()['occupied'] == pytest.approx(.66)
    assert budget.snapshot()[0]['CNY']['production'] == 0


def test_subscription_media_requires_reference_ledger():
    with pytest.raises(ValueError, match='新版参考成本'):
        PlanningBudget({'CNY': 10}).reserve_non_token('CNY', .22, label='x', purpose='image',
            usage={'basis': 'image'}, billing_mode='subscription')


def test_subscription_priority_survives_dominated_reduction_and_quality_gate():
    from refractrouter.node_routing import NodeProfile, route_nodes
    from refractrouter.task_plan import validate_plan
    from tests.test_text_tasks import branched_plan
    plan = validate_plan(branched_plan())
    profiles = tuple(NodeProfile(mid, kind, quality, cost, 1, 3)
        for mid, quality, cost in [('cash', 90, 1), ('sub', 90, 4)]
        for kind in ('synthesis', 'generation'))
    args = dict(method='A', quality_min=80, cost_max=100, latency_max_ms=100,
        reduce_dominated=True, model_providers={'cash': 'same', 'sub': 'same'},
        model_billing_modes={'cash': 'metered', 'sub': 'subscription'})
    result = route_nodes(plan, profiles, **args)
    assert set(result['assignments'].values()) == {'sub'}
    assert result['prediction']['cash_cost'] == 0
    assert result['prediction']['reference_cost'] > 0
    weak = tuple(replace(p, quality=70) if p.model_id == 'sub' else p for p in profiles)
    assert set(route_nodes(plan, weak, **args)['assignments'].values()) == {'cash'}
    # 未迁移的历史路径保持原参考成本排序。
    args.pop('model_billing_modes')
    assert set(route_nodes(plan, profiles, **args)['assignments'].values()) == {'cash'}


def test_route_comparison_prefers_less_cash_without_claiming_reference_savings():
    from refractrouter.automatic_routing import compare_executable_routes
    def route(cost):
        return {'status': 'selected', 'assignments': {}, 'prediction': {
            'cost': cost, 'scheduled_latency_ms': 10, 'mean_node_quality_proxy': 90}}
    result = compare_executable_routes(route(1), route(5), planner_cost=1, judge_cost=1,
        cash_costs={'direct': 1, 'dag': 0})
    assert result['route'] == 'dag'
    assert result['reason'] == 'lower-additional-cash-cost'
    assert result['dag_net_savings_forecast_positive'] is False


def test_subscription_reference_preflight_includes_expensive_cache_writes():
    budget = PlanningBudget({'CNY': 0}, reference_limit=.4)
    expensive = replace(model(), cache_write_cost_per_1k=10)
    with pytest.raises(ValueError, match='reference-CNY'):
        budget.reserve(expensive, [], label='cache-write')
    assert budget.records == []
    assert budget.reference_snapshot()['occupied'] == 0


def test_task_quality_gate_precedes_subscription_cash_preference():
    from refractrouter.planning_decision import select_task_candidate
    costs = {'sub': {'unit': 'CNY', 'amount': 2, 'cashAmount': 0},
             'cash': {'unit': 'CNY', 'amount': 1, 'cashAmount': 1}}
    rows = [{'candidateId': 'sub', 'qualified': True}, {'candidateId': 'cash', 'qualified': True}]
    result = select_task_candidate(rows, 'cash', costs)
    assert result['candidateId'] == 'sub'
    assert result['reason'] == 'quality-then-cash-then-reference-cost'
    rows[0]['qualified'] = False
    assert select_task_candidate(rows, 'cash', costs)['candidateId'] == 'cash'
