"""交付观测不得结算、释放预留或变更实际选模。"""
import pytest

from refractrouter.planning_runtime import PlanningRuntime
from tests.test_planning_routing import begin, step, receipt


@pytest.fixture
def runtime(tmp_path):
    value = PlanningRuntime(tmp_path)
    yield value
    value.local_service.close()


def packet():
    return {'schemaVersion': 'planning-transport-observation-v1', 'clockOrigin': 'dsh-model-request-start',
            'firstTextMs': 30., 'releasedTextBytes': len('中文🦀'.encode()), 'mode': 'live-text',
            'routerOperationMs': 3., 'routerRoundTripMs': 5.}


def record(runtime, run_id, call_id, observation):
    return runtime.handle({'op': 'delivery-observation', 'runId': run_id, 'callId': call_id, 'observation': observation})


def test_cancelled_unknown_call_can_record_visibility_without_releasing_reserve(runtime):
    run_id = begin(runtime, 'static')
    action = step(runtime, run_id)
    assert action['routerOperationMs'] >= 0
    runtime.handle({'op': 'cancel', 'runId': run_id})
    before = runtime.runs[run_id]['budget'].snapshot()[0]
    record(runtime, run_id, action['callId'], packet())
    record(runtime, run_id, action['callId'], packet())
    assert runtime.runs[run_id]['budget'].snapshot()[0] == before
    row = runtime.runs[run_id]['budget'].records[0]
    assert row['status'] == 'unknown-usage' and row['charged'] == row['reserved'] > 0
    assert row['userFirstTextMs'] == 30 and row['releasedTextBytes'] == len('中文🦀'.encode())
    assert runtime.runs[run_id]['status'] == 'cancelled'


@pytest.mark.parametrize('change', [
    {'firstTextMs': -1}, {'firstTextMs': float('nan')}, {'firstTextMs': True},
    {'mode': 'other'}, {'releasedTextBytes': 0}, {'clockOrigin': 'upstream-token-time'},
])
def test_invalid_diagnostic_has_no_financial_or_task_side_effect(runtime, change):
    run_id = begin(runtime, 'static')
    action = step(runtime, run_id)
    before = runtime.runs[run_id]['budget'].snapshot()
    value = {**packet(), **change}
    with pytest.raises(ValueError, match='观测'):
        record(runtime, run_id, action['callId'], value)
    assert runtime.runs[run_id]['budget'].snapshot() == before
    assert runtime.runs[run_id]['status'] == 'running'


def test_other_task_and_conflicting_first_timestamp_cannot_overwrite(runtime):
    first = begin(runtime, 'static')
    action = step(runtime, first)
    other = begin(runtime, 'static', turn=2)
    with pytest.raises(ValueError, match='本任务'):
        record(runtime, other, action['callId'], packet())
    record(runtime, first, action['callId'], packet())
    before = runtime.runs[first]['budget'].snapshot()
    with pytest.raises(ValueError, match='冲突'):
        record(runtime, first, action['callId'], {**packet(), 'firstTextMs': 31})
    assert runtime.runs[first]['budget'].snapshot() == before


def test_nonfinancial_router_metric_does_not_invalidate_known_usage(runtime):
    run_id = begin(runtime, 'static')
    action = step(runtime, run_id)
    receipt(runtime, run_id, action, routerOperationMs=float('nan'))
    row = runtime.runs[run_id]['budget'].records[0]
    assert row['status'] == 'billed' and row['routerOperationMsStatus'] == 'invalid-observation'
    assert 'routerOperationMs' not in row
