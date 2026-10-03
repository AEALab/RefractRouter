"""OpenRouter Decisions 的渠道、费用及故障合同；不访问网络。"""
import json

import pytest

from refractrouter.jev_decision import JevClient
from refractrouter.jev_transport import route_spec
from refractrouter.planning_config import compile_config
from refractrouter.planning_runtime import PlanningRuntime
from tests.test_jev_decision import Response
from tests.test_jev_planning_integration import configuration, begin, step, receipt, response, complete


def openrouter_result(action, choice="APPROVE", cost=.00002):
    result = response(action, choice)
    result.update(model="typesafe/jev-1.13-20260917", provider="TypeSafe", id="gen-fixture")
    result["usage"]["cost"] = cost
    return result


def test_openrouter_wire_keeps_typed_questions_and_disables_fallback():
    calls = []
    questions = {"q": {"type": "noul", "instructions": "是否明确要求退款？"}}
    result = {"model": "typesafe/jev-1.13-20260917", "id": "gen-fixture", "provider": "TypeSafe",
              "answers": {"q": {"type": "noul", "noul": .9}},
              "usage": {"input_tokens": 20, "output_tokens": 4, "cost": .00000084}}
    def transport(request, timeout):
        calls.append(request)
        return Response(result)
    actual = JevClient("test-secret", route="openrouter", transport=transport).predict("请退款", questions)
    assert actual == result
    assert len(calls) == 1
    assert calls[0].full_url == "https://openrouter.ai/api/alpha/decisions"
    payload = json.loads(calls[0].data)
    assert payload["model"] == "typesafe/jev-1.13"
    assert payload["questions"] == questions
    assert payload["provider"] == {"only": ["TypeSafe"], "allow_fallbacks": False}
    assert b"test-secret" not in calls[0].data


@pytest.mark.parametrize("cost", [0, .00002])
def test_openrouter_advisor_settles_reported_cost_and_actual_version(tmp_path, cost):
    cfg = configuration("advisor")
    cfg["jev"] = {"route": "openrouter"}
    compiled = compile_config(cfg)
    assert compiled["jev"]["credentialRef"] == "OPENROUTER_API_KEY"
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    judge = receipt(runtime, run, step(runtime, run))
    assert judge["endpoint"] == route_spec("openrouter")["endpoint"]
    assert judge["credentialRef"] == "OPENROUTER_API_KEY"
    result = openrouter_result(judge, cost=cost)
    accepted = complete(runtime, run, judge, result)
    assert accepted["action"] == "release"
    row = next(r for r in runtime.runs[run]["budget"].records if r["provider"] == "openrouter")
    assert row["charged"] == cost * compiled["jev"]["fxRate"]
    assert row["actual_model"] == result["model"]
    assert row["provider_request_id"] == "gen-fixture"
    assert row["upstream_provider"] == "TypeSafe"
    assert row["requested_model"] == "typesafe/jev-1.13"


@pytest.mark.parametrize("change", [
    {"usage": {"input_tokens": 300, "output_tokens": 20}},
    {"usage": {"input_tokens": 300, "output_tokens": 20, "cost": float("nan")}},
    {"usage": {"input_tokens": 32001, "output_tokens": 20, "cost": .001}},
    {"model": "typesafe/jev-1.14-20261001"},
    {"provider": "Other"}, {"id": ""},
])
def test_openrouter_unconfirmed_receipt_stops_and_retains_reservation(tmp_path, change):
    cfg = configuration("advisor")
    cfg["jev"] = {"route": "openrouter"}
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    judge = receipt(runtime, run, step(runtime, run))
    result = openrouter_result(judge)
    result.update(change)
    with pytest.raises(ValueError):
        complete(runtime, run, judge, result)
    row = runtime.runs[run]["budget"].records[-1]
    assert row["status"] == "unknown-usage"
    assert row["charged"] == row["reserved"] > 0
    assert runtime.runs[run]["status"] != "running"


def test_openrouter_capacity_rejects_before_transport():
    calls = []
    with pytest.raises(ValueError, match="容量"):
        JevClient("test", route="openrouter", transport=lambda *a, **k: calls.append(1)).predict(
            "x" * 99000, {"q": {"type": "noul", "instructions": "ok?"}})
    assert not calls


def test_openrouter_cost_over_reservation_is_persisted_and_stops(tmp_path):
    cfg = configuration("advisor")
    cfg["jev"] = {"route": "openrouter"}
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    judge = receipt(runtime, run, step(runtime, run))
    with pytest.raises(ValueError, match="超过预留"):
        complete(runtime, run, judge, openrouter_result(judge, cost=1))
    record = runtime.handle({"op": "query", "runId": run})
    assert record["status"] == "jev-budget-overage"
    row = record["calls"][-1]
    assert row["status"] == "billed"
    assert row["charged"] > row["reserved"]
    assert row["provider_request_id"] == "gen-fixture"


def test_old_configuration_keeps_typesafe_and_unknown_channel_is_rejected():
    cfg = configuration("advisor")
    assert compile_config(cfg)["jev"]["route"] == "typesafe"
    cfg["jev"]["route"] = "https://untrusted.invalid"
    with pytest.raises(ValueError, match="接入方式"):
        compile_config(cfg)
