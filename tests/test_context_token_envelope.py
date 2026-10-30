"""回答和思考分开受限时，以共享上下文保护费用；不缩减线缆回答上限。"""
from dataclasses import replace

import pytest

from refractrouter.application_config import ExecutionModelSpec
from refractrouter.openai_compatible import ChatResponse
from refractrouter.task_budget import TaskCallBudget


def model(**changes):
    return ExecutionModelSpec(model_id='强', provider='ark', input_cost_per_1k=.45,
        output_cost_per_1k=.45, capability=1, context_window=1024000,
        max_output_tokens=131072, billing_unit='AFP', billing_mode='subscription',
        token_limit_parameter='max_tokens', **changes)


MESSAGES = [{'role': 'user', 'content': '仅测试，不访问网络'}]


def test_native_answer_cap_unchanged_and_reasoning_billed_above_answer_cap():
    budget = TaskCallBudget(None, 1000, 1)
    reservation = budget.reserve(model(), MESSAGES, label='研究', context_token_envelope=1048576)
    assert reservation.model.max_output_tokens == 131072
    assert reservation.row['reserved'] == pytest.approx(471.8592)
    assert reservation.row['protected_total_tokens'] == 1048576
    budget.dispatch(reservation)
    response = ChatResponse('完成', 100, 150000, 0, 149990, 1, 1, 'stop', '模拟',
        raw_usage={'completion_tokens_details': {'reasoning_tokens': 149990}})
    assert budget.settle(reservation, response) is response
    assert reservation.row['charged'] == pytest.approx(67.545)
    assert reservation.row['status'] == 'billed'


@pytest.mark.parametrize('raw', [None, {'completion_tokens_details': {'reasoning_tokens': 0}}])
def test_known_excess_answer_or_unverifiable_answer_billed_then_stopped(raw):
    budget = TaskCallBudget(None, 1000, 1)
    reservation = budget.reserve(model(), MESSAGES, label='研究', context_token_envelope=1048576)
    budget.dispatch(reservation)
    with pytest.raises(ValueError, match='exceeded conservative'):
        budget.settle(reservation, ChatResponse('完成', 100, 150000, 0, 0, 1, 1, 'stop', '模拟', raw_usage=raw))
    assert budget.stopped
    assert reservation.row['status'] == 'billed'
    assert not reservation.row['answer_bound_confirmed']


def test_unknown_usage_keeps_whole_context_reserve():
    budget = TaskCallBudget(None, 1000, 1)
    reservation = budget.reserve(model(), MESSAGES, label='研究', context_token_envelope=1048576)
    budget.dispatch(reservation)
    with pytest.raises(ValueError, match='reservation retained'):
        budget.settle(reservation, ChatResponse('完成', 1, 1, 0, 0, 1, 1, 'stop', '模拟', usage_available=False))
    assert reservation.row['status'] == 'unknown-usage'
    assert budget.remaining() == pytest.approx(528.1408)


def test_usage_exceeding_context_billed_then_stops_even_at_zero_price():
    budget = TaskCallBudget(None, 1000, 1)
    free = replace(model(), input_cost_per_1k=0, output_cost_per_1k=0)
    reservation = budget.reserve(free, MESSAGES, label='研究', context_token_envelope=1048576)
    budget.dispatch(reservation)
    with pytest.raises(ValueError, match='exceeded conservative'):
        budget.settle(reservation, ChatResponse('完成', 100, 1048500, 0, 0, 1, 1, 'stop', '模拟'))
    assert reservation.row['status'] == 'billed'
    assert budget.stopped


@pytest.mark.parametrize('envelope', [True, 1023999, 10000001, 1048576.0, -1])
def test_invalid_envelope_never_dispatches(envelope):
    budget = TaskCallBudget(None, 1000, 1)
    with pytest.raises(ValueError, match='envelope'):
        budget.reserve(model(), MESSAGES, label='研究', context_token_envelope=envelope)
    assert budget.records == []


@pytest.mark.parametrize('changes', [{'price_policy': 'deepseek-official-cny-v1'},
    {'reference_pricing': {'schedule': []}}])
def test_dynamic_pricing_requires_separate_proven_bound(changes):
    with pytest.raises(ValueError, match='envelope'):
        TaskCallBudget(None, 1000, 1).reserve(replace(model(), **changes), MESSAGES,
            label='研究', context_token_envelope=1048576)


def test_uses_most_expensive_cache_price_and_full_envelope_for_call_limit():
    budget = TaskCallBudget(None, 2000, 1, max_total_output_tokens=1048576)
    reservation = budget.reserve(replace(model(), cache_write_cost_per_1k=1), MESSAGES,
        label='研究', context_token_envelope=1048576)
    assert reservation.row['reserved'] == pytest.approx(1048.576)
    with pytest.raises(ValueError, match='output-budget-exhausted'):
        budget.reserve(model(), MESSAGES, label='下一次', context_token_envelope=1048576)
    budget.release(reservation)
    assert budget.reserve(model(), MESSAGES, label='未派发可释放', context_token_envelope=1048576)


def test_small_money_budget_stops_before_dispatch_without_lowering_answer_limit():
    budget = TaskCallBudget(None, 1, 1)
    with pytest.raises(ValueError, match='budget-exhausted'):
        budget.reserve(model(), MESSAGES, label='研究', context_token_envelope=1048576)
    assert budget.records == []
