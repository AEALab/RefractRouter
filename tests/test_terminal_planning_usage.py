"""取消后的迟到用量只结算原调用，不能放行候选、重发或产生下一次审核。"""
import pytest

from refractrouter.planning_runtime import PlanningRuntime
from tests.test_planning_routing import begin, step, receipt


@pytest.mark.parametrize("finish", [None, "length", "error", "tool_calls", "stop"])
def test_cancelled_call_with_known_usage_is_settled_once_without_judge(tmp_path, finish):
    runtime = PlanningRuntime(tmp_path)
    run_id = begin(runtime, "advisor")
    action = step(runtime, run_id)
    runtime.handle({"op": "cancel", "runId": run_id})
    result = receipt(runtime, run_id, action, content="未接受的中文🦀候选", finishReason=finish)
    assert result["action"] == "stop" and runtime.runs[run_id]["status"] == "cancelled"
    rows = runtime.runs[run_id]["budget"].records
    dispatched = [r for r in rows if r.get("call_id")]
    assert len(dispatched) == 1 and dispatched[0]["status"] == "billed"
    assert dispatched[0]["disposition"] == "discarded" and dispatched[0]["finish_reason"] == finish
    assert 0 < dispatched[0]["charged"] < dispatched[0]["reserved"]
    before = runtime.runs[run_id]["budget"].snapshot()
    with pytest.raises(ValueError, match="已结算"):
        receipt(runtime, run_id, action, finishReason=finish)
    assert runtime.runs[run_id]["budget"].snapshot() == before


def test_cancelled_call_without_valid_usage_keeps_full_unknown_reserve(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run_id = begin(runtime, "static")
    action = step(runtime, run_id)
    runtime.handle({"op": "cancel", "runId": run_id})
    with pytest.raises(ValueError, match="unconfirmed"):
        receipt(runtime, run_id, action, usageAvailable=False, finishReason=None)
    row = runtime.runs[run_id]["budget"].records[0]
    assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"] > 0
