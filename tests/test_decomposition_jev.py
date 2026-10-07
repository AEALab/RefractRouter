"""自动拆分 Jev：真实网络由夹具替代，验证预算和证据闭环。"""
import json
import threading
from pathlib import Path

import pytest

from refractrouter.decomposition_decision import validate_evidence
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.live_execution import complexity_gate


def request(**changes):
    return {"identity": "session/agent/turn-1", "task": "分别比较苹果与梨的颜色", "context": "",
            "config": {"jev": {"route": "openrouter"}}, "maxCostCny": .02, **changes}


def response(dependency=.05, independent=.95, single=.05, **changes):
    return {"model": "typesafe/jev-1.13-20260917", "provider": "TypeSafe", "id": "gen-test",
            "usage": {"input_tokens": 100, "output_tokens": 10, "cost": .0000042},
            "answers": {"requires_previous_output": {"type": "noul", "noul": dependency},
                        "can_start_independently": {"type": "noul", "noul": independent},
                        "single_work_unit": {"type": "noul", "noul": single}}, **changes}


def start(runtime, **changes):
    return runtime.handle({"op": "decomposition-jev-begin", **request(**changes)})


def finish(runtime, action, result=None):
    return runtime.handle({"op": "decomposition-jev-complete", "callId": action["callId"],
                           "result": result or response(), "latencyMs": 123})


def test_preflight_no_dispatch_and_one_call_three_noul_then_bound_gate(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    preview = runtime.handle({"op": "decomposition-jev-preflight", **request()})
    assert preview["maximumCalls"] == 1 and 0 < preview["maximumCostCny"] < .02
    assert not list(tmp_path.rglob("*.json"))
    action = start(runtime)
    assert action["route"] == "openrouter" and action["payload"]["provider"]["allow_fallbacks"] is False
    assert len(action["payload"]["questions"]) == 3
    assert set(q["type"] for q in action["payload"]["questions"].values()) == {"noul"}
    evidence = finish(runtime, action)["evidence"]
    assert evidence["verdict"] == "SEPARABLE" and evidence["rawAnswers"] == response()["answers"]
    assert validate_evidence(evidence, request()["task"], "")["backend"] == "jev"
    gate = complexity_gate({"task": request()["task"]}, "", decomposition=evidence)
    assert gate["decision"] == "dag"
    record = json.loads(next((tmp_path / "decomposition").glob("*.json")).read_text())
    row = record["calls"][0]
    assert row["status"] == "billed" and row["billing_unit"] == "CNY"
    assert row["charged"] == pytest.approx(.0000042 * row["conversion_rate"])
    assert record["costsByUnit"]["CNY"]["production"] == pytest.approx(row["charged"])
    with pytest.raises(ValueError, match="已经结算"):
        finish(runtime, action)
    with pytest.raises(ValueError, match="不会重复调用"):
        start(runtime)
    with pytest.raises(ValueError, match="不会重复调用"):
        start(PlanningRuntime(tmp_path))


@pytest.mark.parametrize("dependency,independent,single,verdict", [
    (.95, .05, .05, "COUPLED"), (.5, .5, .05, "UNKNOWN"), (.19, .07, .91, "SINGLE"),
    (.95, .05, .95, "UNKNOWN")])
def test_answer_semantics(tmp_path, dependency, independent, single, verdict):
    runtime = PlanningRuntime(tmp_path)
    evidence = finish(runtime, start(runtime), response(dependency, independent, single))["evidence"]
    assert evidence["verdict"] == verdict


@pytest.mark.parametrize("changes,match", [({"maxCostCny": .00001}, "预算不足"),
    ({"maxCostCny": float("nan")}, "正数"), ({"task": "读取 /Users/example/work"}, "数据域")])
def test_preflight_rejects_without_ledger(tmp_path, changes, match):
    runtime = PlanningRuntime(tmp_path)
    with pytest.raises(ValueError, match=match):
        start(runtime, **changes)
    assert not list(tmp_path.rglob("*.json"))


def test_context_and_capacity_use_rules_without_cloud(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    for task, reason in (("继续处理上述结果", "context-dependent"), ("a" * 1100, "input-too-long")):
        result = start(runtime, task=task, maxInputBytes=1024)
        assert result["action"] == "complete" and result["evidence"]["reason"] == reason
    assert not list(tmp_path.rglob("*.json"))


def test_frozen_sequential_tool_task_reaches_judge_and_keeps_direct_route(tmp_path):
    protocol = json.loads((Path(__file__).resolve().parents[1] /
        'data/acceptance/automatic-product-finalization-v1.json').read_text())
    task = next(row['task'] for row in protocol['cases'] if row['id'] == 'dependent-tools')
    runtime = PlanningRuntime(tmp_path)
    action = start(runtime, task=task)
    assert action['action'] == 'jev'
    evidence = finish(runtime, action, response(.95, .05, .05))['evidence']
    assert evidence['verdict'] == 'COUPLED'
    assert complexity_gate({'task': task}, '', decomposition=evidence)['decision'] == 'direct'
    assert len(runtime.decomposition_jev.jobs[action['callId']]['budget'].records) == 1


def test_unknown_usage_stops_and_retains_reservation(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    action = start(runtime)
    with pytest.raises(ValueError, match="用量缺失"):
        finish(runtime, action, response(usage={}))
    row = runtime.decomposition_jev.jobs[action["callId"]]["budget"].records[0]
    assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"]
    assert runtime.decomposition_jev.jobs[action["callId"]]["status"] == "stopped"


def test_cancel_late_result_settles_without_delivering_decision(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    action = start(runtime)
    runtime.handle({"op": "decomposition-jev-stop", "callId": action["callId"]})
    assert finish(runtime, action)["action"] == "stop"
    job = runtime.decomposition_jev.jobs[action["callId"]]
    assert job["budget"].records[0]["status"] == "billed"
    assert "evidence" not in job


def test_invalid_answers_are_billed_but_never_released(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    action = start(runtime)
    with pytest.raises(ValueError, match="答案不完整"):
        finish(runtime, action, response(answers={}))
    job = runtime.decomposition_jev.jobs[action["callId"]]
    assert job["budget"].records[0]["status"] == "billed" and job["status"] == "stopped"


def test_parallel_duplicate_requests_dispatch_once(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    results = []
    def submit():
        try:
            results.append(start(runtime)["action"])
        except ValueError:
            results.append("blocked")
    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["blocked", "jev"]


def test_persist_failure_never_returns_dispatch(tmp_path, monkeypatch):
    runtime = PlanningRuntime(tmp_path)
    monkeypatch.setattr("refractrouter.decomposition_jev.os.replace", lambda *a: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError, match="full"):
        start(runtime)
    assert next(iter(runtime.decomposition_jev.jobs.values()))["status"] == "evidence-failed"
