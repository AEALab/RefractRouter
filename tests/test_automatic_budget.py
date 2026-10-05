"""自动路由双单位账本的原子预留与故障停止。"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from refractrouter.automatic_budget import AutomaticMixedBudget
from refractrouter.openai_compatible import ChatResponse
from tests.test_native_tool_runtime import real_model


MESSAGES = [{'role': 'user', 'content': '固定请求'}]


def model(unit):
    return replace(real_model(), billing_unit=unit, input_cost_per_1k=1,
                   output_cost_per_1k=1, max_output_tokens=100,
                   context_window=10000)


def budget(*, afp=10, cny=10, max_calls=10, client=None):
    return AutomaticMixedBudget(client, {
        'AFP': {'production': afp, 'evaluation': 10},
        'CNY': {'production': cny, 'evaluation': 10},
    }, max_calls=max_calls)


def request(unit, label):
    return {'model': model(unit), 'messages': MESSAGES, 'label': label}


def test_mixed_path_reserves_each_unit_without_conversion():
    ledger = budget()
    first, second = ledger.reserve_many([request('AFP', 'execute'), request('CNY', 'judge')])
    charged, rows = ledger.snapshot()
    assert charged['AFP']['production'] == pytest.approx(first.row['reserved'])
    assert charged['CNY']['production'] == pytest.approx(second.row['reserved'])
    assert [row['billing_unit'] for row in rows] == ['AFP', 'CNY']
    assert all(row['status'] == 'reserved' for row in rows)


def test_insufficient_second_unit_releases_first_reservation():
    ledger = budget(cny=.001)
    with pytest.raises(ValueError, match='production-budget-exhausted'):
        ledger.reserve_many([request('AFP', 'execute'), request('CNY', 'judge')])
    charged, rows = ledger.snapshot()
    assert charged['AFP']['production'] == 0
    assert charged['CNY']['production'] == 0
    assert rows[0]['status'] == 'cancelled-before-dispatch'


def test_shared_call_limit_blocks_cross_unit_path_without_partial_charge():
    ledger = budget(max_calls=1)
    with pytest.raises(ValueError, match='study-call-limit-exhausted'):
        ledger.reserve_many([request('AFP', 'execute'), request('CNY', 'judge')])
    assert ledger.snapshot()[1] == []


def test_concurrent_paths_cannot_each_spend_same_afp_balance():
    probe = budget().reserve(model('AFP'), MESSAGES, label='probe').row['reserved']
    ledger = budget(afp=probe * 1.5)
    barrier = Barrier(2)

    def attempt(label):
        barrier.wait(2)
        try:
            return ledger.reserve_many([request('AFP', label), request('CNY', label)])
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ('one', 'two')))
    assert sum(result is not None for result in outcomes) == 1
    charged, rows = ledger.snapshot()
    assert charged['AFP']['production'] == pytest.approx(probe)
    assert charged['CNY']['production'] > 0
    assert len([row for row in rows if row['status'] == 'reserved']) == 2


def test_unknown_usage_retains_dispatched_unit_and_stops_both_ledgers():
    ledger = budget()
    dispatched, waiting = ledger.reserve_many([request('AFP', 'execute'), request('CNY', 'judge')])
    ledger.dispatch(dispatched)
    response = ChatResponse('回复', 0, 0, 0, 0, 1, 1, 'stop', None, usage_available=False)
    with pytest.raises(ValueError, match='missing or unconfirmed model usage'):
        ledger.settle(dispatched, response)
    charged, rows = ledger.snapshot()
    assert rows[0]['status'] == 'unknown-usage'
    assert charged['AFP']['production'] == pytest.approx(dispatched.row['reserved'])
    assert rows[1]['status'] == 'cancelled-before-dispatch'
    assert charged['CNY']['production'] == 0
    with pytest.raises(ValueError, match='stopped'):
        ledger.reserve(model('CNY'), MESSAGES, label='late')


def test_cancel_releases_only_calls_not_dispatched():
    ledger = budget()
    dispatched, waiting = ledger.reserve_many([request('AFP', 'execute'), request('CNY', 'judge')])
    ledger.dispatch(dispatched)
    ledger.stop()
    charged, rows = ledger.snapshot()
    assert rows[0]['status'] == 'unknown-usage'
    assert rows[1]['status'] == 'cancelled-before-dispatch'
    assert charged['AFP']['production'] == pytest.approx(dispatched.row['reserved'])
    assert charged['CNY']['production'] == 0


def test_invalid_but_metered_output_can_be_recovered_without_stopping_task():
    ledger = budget()
    call = ledger.reserve(model('AFP'), MESSAGES, label='first')
    ledger.dispatch(call)
    invalid = ChatResponse('', 20, 10, 0, 0, 1, 1, 'length', None)
    with pytest.raises(ValueError, match='invalid or truncated output'):
        ledger.settle(call, invalid)
    assert call.row['status'] == 'billed'
    assert ledger.reserve(model('CNY'), MESSAGES, label='replacement').row['status'] == 'reserved'


def test_evidence_write_failure_stops_all_units():
    ledger = budget()

    def broken(_):
        raise OSError('evidence unavailable')

    ledger.on_reserve = broken
    with pytest.raises(OSError, match='evidence unavailable'):
        ledger.reserve_many([request('AFP', 'execute'), request('CNY', 'judge')])
    charged, rows = ledger.snapshot()
    assert charged['AFP']['production'] == charged['CNY']['production'] == 0
    assert all(row['status'] == 'cancelled-before-dispatch' for row in rows)
    with pytest.raises(ValueError, match='stopped'):
        ledger.reserve(model('AFP'), MESSAGES, label='late')


def test_final_review_keeps_one_call_slot_until_its_real_reservation():
    ledger = budget(max_calls=2)
    protection = ledger.protect_review(model('CNY'), 1)
    ledger.reserve(model('AFP'), MESSAGES, label='execute')
    with pytest.raises(ValueError, match='study-call-limit-exhausted'):
        ledger.reserve(model('AFP'), MESSAGES, label='extra-execute')
    review = ledger.reserve(model('CNY'), MESSAGES, category='evaluation', label='final-judge')
    assert review.row['status'] == 'reserved'
    assert protection['status'] == 'converted-to-call'
    ledger.dispatch(review)
    ledger.stop()
    assert protection['status'] == 'converted-to-call'


def test_cancel_before_final_review_dispatch_releases_its_protection():
    ledger = budget(max_calls=1)
    protection = ledger.protect_review(model('CNY'), 1)
    ledger.reserve(model('CNY'), MESSAGES, category='evaluation', label='final-judge')
    ledger.stop()
    assert protection['status'] == 'released-unspent'
    assert ledger.snapshot()[0]['CNY']['evaluation'] == 0


def test_final_review_output_allowance_stays_available_during_execution():
    ledger = AutomaticMixedBudget(None, {
        'AFP': {'production': 10, 'evaluation': 10},
        'CNY': {'production': 10, 'evaluation': 10},
    }, max_total_output_tokens=200)
    ledger.protect_review(model('CNY'), 1)
    ledger.reserve(model('AFP'), MESSAGES, label='execute')
    with pytest.raises(ValueError, match='task-output-budget-exhausted'):
        ledger.reserve(model('AFP'), MESSAGES, label='extra-execute')
    assert ledger.reserve(model('CNY'), MESSAGES, category='evaluation',
                          label='final-judge').row['status'] == 'reserved'


def test_final_review_budget_cannot_be_consumed_by_other_evaluation():
    ledger = AutomaticMixedBudget(None, {
        'AFP': {'production': 10, 'evaluation': 10},
        'CNY': {'production': 10, 'evaluation': 1}}, max_calls=3)
    protection = ledger.protect_review(model('CNY'), .9)
    with pytest.raises(ValueError, match='reserved for final review'):
        ledger.reserve(model('CNY'), MESSAGES, category='evaluation', label='other-evaluation')
    assert ledger.snapshot()[0]['CNY']['evaluation'] == 0
    assert protection['status'] == 'protected'
    ledger.stop()
    assert protection['status'] == 'released-unspent'
