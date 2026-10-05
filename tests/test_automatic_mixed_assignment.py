"""混合 AFP/CNY 节点选择的质量、额度及确定性检查。"""
import pytest

from refractrouter.automatic_mixed_assignment import route_nodes_mixed
from refractrouter.node_routing import NodeProfile
from refractrouter.task_plan import validate_plan


PLAN = validate_plan({'nodes': [
    {'node_id': 'facts', 'node_type': 'extraction', 'prompt_template': '提取事实', 'parents': []},
    {'node_id': 'answer', 'node_type': 'synthesis', 'prompt_template': '汇总', 'parents': ['facts']},
], 'final_node_id': 'answer', 'acceptance_criteria': ['完整回答']})


def profiles():
    return tuple(NodeProfile(model, kind, quality, cost, 100, 0)
        for model, quality, cost in [('ark', 90, 3), ('cash', 90, .02), ('weak', 70, 1)]
        for kind in ('extraction', 'synthesis'))


UNITS = {'ark': 'AFP', 'cash': 'CNY', 'weak': 'AFP'}


def choose(*, budgets=None, quality_min=80, reference=None, candidates=None):
    return route_nodes_mixed(PLAN, profiles(), model_units=UNITS, quality_min=quality_min,
        budgets=budgets or {'AFP': 10, 'CNY': 1}, quality_reference=reference,
        eligible_models=candidates)


def test_subscription_wins_only_after_quality_gate():
    result = choose()
    assert result['assignments'] == {'facts': 'ark', 'answer': 'ark'}
    assert result['prediction']['costs_by_unit'] == {'AFP': 6, 'CNY': 0}
    assert result['quality_noninferiority_verified'] is False
    assert result['quality_basis'] == 'configured-profile-prior'


def test_afp_shortfall_uses_affordable_cash_instead_of_converting_units():
    result = choose(budgets={'AFP': 2, 'CNY': 1})
    assert result['assignments'] == {'facts': 'cash', 'answer': 'cash'}
    assert result['prediction']['costs_by_unit'] == {'AFP': 0, 'CNY': .04}
    assert result['rejected_combinations']['unit-budget'] > 0


def test_weak_afp_is_not_selected_only_because_it_is_cheaper():
    result = choose(quality_min=65, reference=90)
    assert 'weak' not in result['assignments'].values()
    assert result['excluded_afp_below_cash_quality_prior']['facts'] == ['weak']


def test_unaffordable_cash_is_not_a_quality_reference_for_the_only_affordable_route():
    result = choose(quality_min=65, budgets={'AFP': 10, 'CNY': .01},
        candidates={'facts': ['weak', 'cash'], 'answer': ['weak', 'cash']})
    assert result['status'] == 'selected'
    assert result['assignments'] == {'facts': 'weak', 'answer': 'weak'}
    assert result['excluded_afp_below_cash_quality_prior'] == {'facts': [], 'answer': []}


def test_mixed_nodes_keep_each_cost_in_native_ledger():
    result = choose(candidates={'facts': ['ark'], 'answer': ['cash']})
    assert result['assignments'] == {'facts': 'ark', 'answer': 'cash'}
    assert result['prediction']['costs_by_unit'] == {'AFP': 3, 'CNY': .02}


def test_both_unit_limits_can_make_route_infeasible():
    result = choose(budgets={'AFP': 2, 'CNY': .01})
    assert result['status'] == 'no-feasible-route'
    assert result['prediction'] is None


def test_missing_model_unit_and_invalid_budget_fail_closed():
    with pytest.raises(ValueError, match='actual billing unit'):
        route_nodes_mixed(PLAN, profiles(), model_units={'ark': 'AFP'},
            quality_min=80, budgets={'AFP': 10, 'CNY': 1})
    with pytest.raises(ValueError, match='AFP and CNY budgets'):
        choose(budgets={'AFP': 10})
