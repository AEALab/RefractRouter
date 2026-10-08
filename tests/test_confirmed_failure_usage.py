"""失败终止回执必须结算，但不得作为有效回复、工具或重试依据。"""
from dataclasses import asdict
import pytest

from refractrouter.openai_compatible import ChatResponse, ModelInvocationError, OpenAICompatibleClient
from refractrouter.task_budget import TaskCallBudget
from refractrouter.application_config import ApplicationModelSpec
from experiments.run_automatic_applicability import record_invocation_failure
from tests.test_openai_compatible import real_model


class Bridge:
    def __init__(self, **changes):
        self.calls = 0
        self.result = {'ok': False, 'failure_type': 'provider-error', 'message': 'fixture failure',
            'request_id': 'failed-request', 'usage_confirmed': True, 'content': 'partial',
            'usage': {'input_tokens': 105, 'output_tokens': 12, 'cached_input_tokens': 20,
                      'cache_write_tokens': 5, 'reasoning_tokens': 3}, **changes}

    def complete(self, *_args, **_kwargs):
        self.calls += 1
        return self.result


def setup(bridge):
    model = ApplicationModelSpec(**{**asdict(real_model()), 'wire_api':'dsh-llm',
        'billing_unit':'CNY', 'context_window':32768, 'cache_write_cost_per_1k':.004})
    client = OpenAICompatibleClient(dsh_bridge=bridge, max_retries=2, sleep=lambda _: None)
    return model, client, TaskCallBudget(client, 10, 10, capture_payload=True)


def test_confirmed_failure_is_billed_once_without_accepting_tools_or_retrying():
    bridge = Bridge(tool_calls=[{'id': 'must-not-run'}])
    model, _, budget = setup(bridge)
    reservation = budget.reserve(model, [{'role': 'user', 'content': 'test'}], label='failed')
    with pytest.raises(ModelInvocationError) as error:
        budget.invoke(reservation)
    assert error.value.failure_type == 'provider-error'
    assert bridge.calls == 1
    receipt = error.value.confirmed_response
    assert receipt.finish_reason == 'error' and receipt.tool_calls == ()
    assert reservation.row['status'] == 'billed'
    assert reservation.row['charged'] == pytest.approx(.00028)
    assert reservation.row['response_output'] == 'partial'
    assert reservation.row['request_id'] == 'failed-request'
    charged = budget.charged.copy()
    with pytest.raises(ValueError, match='already settled'):
        budget.settle_failure(reservation, error.value)
    assert budget.charged == charged
    assert 'partial' not in str(error.value.public_details())


@pytest.mark.parametrize('changes', [
    {'usage_confirmed': False}, {'usage_confirmed': 'true'}, {'usage': {}},
    {'usage': {'input_tokens': 10, 'output_tokens': 2, 'cached_input_tokens': 11, 'reasoning_tokens': 0}},
    {'usage': {'input_tokens': '10', 'output_tokens': 2, 'cached_input_tokens': 0, 'reasoning_tokens': 0}},
    {'usage': {'input_tokens': 10, 'output_tokens': 2, 'cached_input_tokens': 0, 'reasoning_tokens': 3}},
    {'usage': {'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0, 'reasoning_tokens': 0}},
    {'usage': {'input_tokens': True, 'output_tokens': 2, 'cached_input_tokens': 0, 'reasoning_tokens': 0}},
])
def test_unconfirmed_or_malformed_receipt_retains_reservation(changes):
    bridge = Bridge(**changes)
    model, client, budget = setup(bridge)
    client.max_retries = 0
    reservation = budget.reserve(model, [{'role': 'user', 'content': 'test'}], label='unknown')
    with pytest.raises(ModelInvocationError) as error:
        budget.invoke(reservation)
    assert error.value.confirmed_response is None
    assert reservation.row['status'] == 'unknown-usage'
    budget.stop()
    assert reservation.row['charged'] == reservation.row['reserved']


@pytest.mark.parametrize('kind,confirmed,stopped', [
    ('provider-error', True, False), ('provider-error', False, True),
    ('authentication', True, True), ('transport-error', True, True), ('timeout', True, True),
])
def test_batch_failure_policy_continues_only_confirmed_independent_provider_failure(kind, confirmed, stopped):
    model, _, budget = setup(Bridge())
    reservation = budget.reserve(model, [{'role':'user','content':'test'}], label='batch')
    budget.dispatch(reservation)
    receipt = ChatResponse('partial', 100, 20, 0, 0, 12, 1, 'error', 'id') if confirmed else None
    error = ModelInvocationError(kind, 'fixture', 1, 12, confirmed_response=receipt)
    record_invocation_failure(budget, reservation, error)
    assert budget.stopped is stopped
    assert reservation.row['status'] == ('billed' if confirmed else 'unknown-usage')


def test_excess_failure_usage_stops_and_preserves_billing():
    model, _, budget = setup(Bridge())
    reservation = budget.reserve(model, [{'role':'user','content':'test'}], label='excess')
    budget.dispatch(reservation)
    receipt = ChatResponse('partial', 100, 50000, 0, 0, 12, 1, 'error', 'id')
    with pytest.raises(ValueError, match='exceeded'):
        record_invocation_failure(budget, reservation,
            ModelInvocationError('provider-error', 'fixture', 1, 12, confirmed_response=receipt))
    assert budget.stopped and reservation.row['status'] == 'billed'
