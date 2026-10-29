"""整任务费用观测的真实核心往返，全部模型响应为确定性模拟。"""
from copy import deepcopy
from decimal import Decimal
import json

import pytest

from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.task_cost_observation import observe
from tests.test_planning_routing import begin, step, receipt, advisor_gate_configuration


def view(runtime, run):
    return runtime.handle({"op": "outcome", "runId": run, "identity": runtime.runs[run]["identity"]})


def static_result(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run), content="模拟交付")
    runtime.handle({"op": "end", "runId": run})
    return view(runtime, run)


def test_full_advisor_attempt_review_redo_fees_are_included_without_changing_ledger(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", config=advisor_gate_configuration())
    judge = receipt(runtime, run, step(runtime, run), content="旧候选")
    redo = receipt(runtime, run, judge, content=json.dumps({"verdict": "REDO", "feedback": "补充证据"}))
    second = receipt(runtime, run, redo, content="新候选")
    receipt(runtime, run, second, content=json.dumps({"verdict": "APPROVE"}))
    runtime.handle({"op": "end", "runId": run})
    source = view(runtime, run)
    path = runtime.root / (run + ".json")
    before = path.read_bytes()
    result = observe(source)
    assert len(result["callIds"]) == 4
    assert sum(Decimal(c["knownCalculated"]) for c in result["costs"]) == sum(Decimal(str(c["charged"])) for c in source["calls"])
    assert len(result["byPurpose"]) >= 3
    assert result["wholeTaskQuality"] == "unknown"
    assert result["actualProviderDebit"] == "not-established-by-this-view"
    assert result["financialLedgerChanged"] is False and path.read_bytes() == before


def test_cancelled_unknown_usage_is_protected_and_not_converted_to_zero(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    step(runtime, run)
    runtime.handle({"op": "cancel", "runId": run})
    source = view(runtime, run)
    result = observe(source)
    assert result["pricedCallAmountsComplete"] is False
    assert result["costs"][0]["knownCalculated"] == "0"
    assert Decimal(result["costs"][0]["unknownProtected"]) == Decimal(str(source["calls"][0]["reserved"]))
    assert result["unknownCallIds"] == [source["calls"][0]["call_id"]]


def test_subscription_reference_is_separate_from_metered_budget_and_actual_cash(tmp_path):
    source = static_result(tmp_path)
    call = source["calls"][0]
    call["billing_mode"] = "subscription"
    source["costsByUnit"] = {}
    source["referenceCosts"] = {"currency": "CNY", "occupied": call["charged"], "includesCashCalls": True}
    result = observe(source)
    assert result["costs"][0]["lane"] == "subscription-reference"
    assert result["actualProviderDebit"] == "not-established-by-this-view"


def test_mixed_currencies_are_reported_without_conversion_or_sum(tmp_path):
    source = static_result(tmp_path)
    other = deepcopy(source["calls"][0])
    other.update(call_id="another-call", billing_unit="AFP")
    source["calls"].append(other)
    source["costsByUnit"]["AFP"] = {"production": other["charged"], "evaluation": 0}
    result = observe(source)
    assert {c["unit"] for c in result["costs"]} == {"CNY", "AFP"}
    assert "totalCost" not in result


def test_duplicate_or_missing_billed_calls_cannot_understate_costs(tmp_path):
    source = static_result(tmp_path)
    bad = deepcopy(source)
    bad["calls"].append(deepcopy(source["calls"][0]))
    with pytest.raises(ValueError, match="重复"):
        observe(bad)
    bad = deepcopy(source)
    bad["calls"] = []
    with pytest.raises(ValueError, match="总账不一致"):
        observe(bad)
