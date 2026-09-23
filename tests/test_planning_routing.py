"""规划路由离线行为验收：真实策略和账本，模拟宿主执行。"""
from copy import deepcopy
import json
import threading

import pytest

from refractrouter.planning_config import compile_config, preview, DEFAULTS
from refractrouter.planning_policy import stage, tool_events
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.task_budget import TaskCallBudget


def configuration(strategy="stage"):
    return {"schemaVersion": "refractagent-planning-v1", "enabled": True,
        "defaultStrategy": strategy, "maxProductionCost": 10, "timeoutMs": 300000,
        "models": [{"id": id, "provider": "fake", "model": id, "contextWindow": 32000,
                    "maxOutputTokens": 1024, "inputPer1k": .001, "outputPer1k": .002,
                    "deployment": "local", "reasoningEffort": "low"}
                   for id in ("small", "large", "judge")],
        "roles": {"efficient": "small", "capable": "large", "classifier": "judge", "advisor": "judge"}}


def begin(runtime, strategy="stage", turn=1, session="a", child=False, config=None):
    return runtime.handle({"op": "begin", "identity": {"session": session, "agent": session, "turn": turn},
        "strategy": strategy, "config": config or configuration(strategy), "child": child})["runId"]


def step(runtime, run, messages=None, **kw):
    return runtime.handle({"op": "step", "runId": run, "messages": messages or [
        {"role": "system", "content": "遵循工具权限"},
        {"role": "user", "content": [{"type": "text", "text": "完成任务"}]}],
        "tools": [{"name": "read", "description": "read", "parameters": {"type": "object"}}], **kw})


def receipt(runtime, run, action, content="完成", tools=(), **overrides):
    return runtime.handle({"op": "complete", "runId": run, "callId": action["callId"],
        "response": {"content": content, "inputTokens": 100, "outputTokens": 20,
            "finishReason": "tool_calls" if tools else "stop", "toolCalls": list(tools),
            "usageAvailable": True, "latencyMs": 10, **overrides}})


def test_zero_call_availability_and_freeze(tmp_path):
    cfg = configuration()
    del cfg["roles"]["classifier"]
    report = preview(cfg)
    assert next(s for s in report["strategies"] if s["id"] == "stage")["available"]
    assert not next(s for s in report["strategies"] if s["id"] == "task")["available"]
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, config=cfg)
    cfg["roles"]["efficient"] = "large"
    assert step(runtime, run)["model"]["id"] == "small"
    assert begin(runtime, "static") == run  # 同轮追加指导不重新获预算
    assert runtime.runs[run]["strategy"] == "stage"


def test_native_tools_no_dag_and_complete_two_steps(tmp_path, monkeypatch):
    import refractrouter.planning_runtime as module
    # 模块依赖中没有图执行入口；步骤回执只返回工具，不执行工具。
    assert "planner" not in module.__dict__
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    tools = ({"type": "tool-call", "id": "one", "name": "read", "arguments": "{}"},)
    action = step(runtime, run)
    assert action["buffered"] is False
    assert receipt(runtime, run, action, "", tools)["action"] == "release"
    messages = [{"role": "assistant", "content": list(tools)},
        {"role": "user", "content": [{"type": "tool-result", "toolCallId": "one",
            "content": [{"type": "text", "text": "数据"}]}]}]
    action = step(runtime, run, messages)
    assert action["messages"] == messages
    receipt(runtime, run, action)
    assert runtime.runs[run]["state"]["step"] == 2
    assert len(runtime.runs[run]["budget"].records) == 2


@pytest.mark.parametrize("strategy", ["task", "composite"])
def test_classifier_once_per_turn(strategy, tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, strategy)
    judge = step(r, run)
    assert judge["purpose"] == "task"
    execute = receipt(r, run, judge, '{"p_solve":0.2,"capability_boundary":"unsupported"}')
    assert execute["model"]["id"] == "large"
    receipt(r, run, execute)
    assert step(r, run)["purpose"] == "execute"
    new = begin(r, strategy, turn=2)
    assert step(r, new)["purpose"] == "task"
    other = begin(r, strategy, session="b")
    assert step(r, other)["purpose"] == "task"


def test_stage_structured_evidence_and_hold():
    msgs = []
    for i in range(2):
        msgs += [{"role": "assistant", "content": [{"type": "tool-call", "id": str(i), "name": "edit", "arguments": "{}"}]},
                 {"role": "user", "content": [{"type": "tool-result", "toolCallId": str(i), "isError": True, "error": {"code": "CODE_RUN_FAILED"}}]}]
    events = tool_events(msgs)
    role, reason, hold, _ = stage(events, {"hold": 0}, DEFAULTS, "efficient")
    assert (role, reason, hold) == ("capable", "repeated-failure", 2)
    for remaining in (1, 0):
        role, _, hold, _ = stage([], {"hold": hold}, DEFAULTS, "efficient")
        assert role == "capable" and hold == remaining
    assert stage([], {"hold": hold}, DEFAULTS, "efficient")[0] == "efficient"
    msgs[-1]["content"][0]["error"] = {"code": "PERMISSION_DENIED"}
    assert tool_events(msgs)[-1]["status"] == "denied"
    msgs[-1]["content"][0].pop("isError")
    msgs[-1]["content"][0].pop("error")
    msgs[-1]["content"][0]["content"] = [{"type": "text", "text": "失败失败失败"}]
    assert tool_events(msgs)[-1]["status"] == "completed"


def test_native_error_origin_and_turn_filter():
    block = {"type": "tool-result", "toolCallId": "x", "isError": True}
    msgs = [{"role": "user", "content": [block]}]
    native = [{"type": "tool/result", "data": {"message": {"content": [block]},
        "error": {"code": "APPROVAL_REJECTED"}}}]
    assert tool_events(msgs, native)[0]["status"] == "denied"
    assert tool_events(msgs, []) == []


def test_advisor_discard_redo_all_billed(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "advisor")
    execution = step(r, run)
    assert execution["buffered"]
    judge = receipt(r, run, execution, "不合格候选")
    assert judge["purpose"] == "advisor"
    redo = receipt(r, run, judge, '{"verdict":"REDO","feedback":"补充证据"}')
    assert redo["purpose"] == "redo"
    assert "补充证据" in redo["messages"][-1]["content"][0]["text"]
    released = receipt(r, run, redo, "修订")
    assert released["callId"] == redo["callId"]
    calls = released["record"]["calls"]
    assert [c["disposition"] for c in calls] == ["discarded", "consult", "accepted"]
    assert calls[0]["response_output"] == "不合格候选"
    assert released["record"]["costs"]["production"] == pytest.approx(.00042)
    assert calls[-1]["review_status"] == "revised-unreviewed"


@pytest.mark.parametrize("strategy,verdict", [("advisor", "APPROVE"), ("escalation", "{}")])
def test_invalid_verdict_never_accepted(tmp_path, strategy, verdict):
    r = PlanningRuntime(tmp_path)
    run = begin(r, strategy)
    judge = receipt(r, run, step(r, run))
    with pytest.raises(ValueError):
        receipt(r, run, judge, verdict)
    assert r.runs[run]["status"] != "running"


def test_escalation_two_confirmations_and_new_task_reset(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "escalation")
    for index in range(2):
        weak = step(r, run)
        assert weak["model"]["id"] == "small"
        judge = receipt(r, run, weak)
        outcome = receipt(r, run, judge, '{"escalate":true}')
        if index == 0:
            assert outcome["callId"] == weak["callId"]
        else:
            assert outcome["purpose"] == "takeover" and outcome["model"]["id"] == "large"
            receipt(r, run, outcome)
    assert step(r, run)["model"]["id"] == "large"
    new = begin(r, "escalation", turn=2)
    assert step(r, new)["model"]["id"] == "small"


def test_unknown_usage_crash_and_cancel_settlement(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static")
    action = step(r, run)
    with pytest.raises(ValueError, match="unconfirmed"):
        receipt(r, run, action, usageAvailable=False)
    assert r.runs[run]["budget"].records[0]["status"] == "unknown-usage"
    with pytest.raises(ValueError, match="不得自动"):
        begin(PlanningRuntime(tmp_path), "static")
    run2 = begin(r, "static", turn=2)
    action = step(r, run2)
    r.handle({"op": "cancel", "runId": run2})
    assert receipt(r, run2, action)["action"] == "stop"
    assert r.runs[run2]["budget"].records[0]["status"] == "billed"


def test_atomic_budget_envelope_and_no_duplicate_step(tmp_path):
    r = PlanningRuntime(tmp_path)
    cfg = configuration("advisor")
    cfg["maxProductionCost"] = .001
    run = begin(r, "advisor", config=cfg)
    with pytest.raises(ValueError, match="完整策略"):
        step(r, run)
    assert not r.runs[run]["budget"].records
    model = compile_config(configuration())["models"]["small"]
    b = TaskCallBudget(None, .0026, 1)
    outcomes = []
    def reserve():
        try:
            b.reserve(model, [{"role": "user", "content": "hi"}], label="x")
            outcomes.append(True)
        except ValueError:
            outcomes.append(False)
    threads = [threading.Thread(target=reserve) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(outcomes) == [False, True]


def test_replay_admission_child_isolation_compaction(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static")
    messages = [{"role": "assistant", "source": {"kind": "model", "provider": "fake", "model": "large",
        "replayState": {"response": {"opaque": True}}}, "content": [{"type": "text", "text": "历史"}]}]
    with pytest.raises(ValueError, match="兼容"):
        step(r, run, messages)
    cfg = configuration("static")
    cfg["compatiblePairs"] = [["large", "small"]]
    run = begin(r, "static", turn=2, config=cfg)
    assert step(r, run, messages)["messages"] == messages
    child = begin(r, "escalation", session="child", child=True)
    assert r.runs[child]["strategy"] == "static"
    action = step(r, child, purpose="compaction")
    assert action["purpose"] == "compaction"
    receipt(r, child, action)
    assert r.runs[child]["state"]["step"] == 0
    assert r.runs[child]["state"]["compactions"] == 1


def test_random_seed_reproducible_and_sensitive_preflight(tmp_path):
    from refractrouter.planning_policy import static_choice
    params = {**DEFAULTS, "staticMode": "random"}
    assert [static_choice(params, "a", i) for i in range(10)] == [static_choice(params, "a", i) for i in range(10)]
    cfg = configuration("static")
    cfg["models"][0]["deployment"] = "external-cloud"
    cfg["security"] = {"sensitiveTerms": ["confidential-project"]}
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static", config=cfg)
    with pytest.raises(ValueError, match="数据域"):
        step(r, run, [{"role": "user", "content": "confidential-project"}])
    assert not r.runs[run]["budget"].records


@pytest.mark.parametrize("strategy", ["static", "stage", "task", "composite", "advisor", "escalation"])
def test_offline_simulation_never_creates_production_history(tmp_path, strategy):
    r = PlanningRuntime(tmp_path)
    result = r.handle({"op": "simulate", "config": configuration(strategy)})
    assert result["simulated"] and result["actualModelCalls"] == 0
    assert result["simulatedCalls"] >= 3
    assert not list(tmp_path.glob("planning/*.json"))


def test_cache_write_price_and_billed_cancellation(tmp_path):
    r = PlanningRuntime(tmp_path)
    cfg = configuration("static")
    cfg["models"][0]["cacheWritePer1k"] = .004
    run = begin(r, "static", config=cfg)
    action = step(r, run)
    result = receipt(r, run, action, cacheWriteTokens=30)
    assert result["record"]["costs"]["production"] == pytest.approx(.00023)
    assert result["record"]["calls"][0]["reserved"] >= .002
    run = begin(r, "static", turn=2)
    action = step(r, run)
    with pytest.raises(ValueError, match="缓存写入价格"):
        receipt(r, run, action, cacheWriteTokens=30)
    assert r.runs[run]["budget"].records[0]["status"] == "unknown-usage"


def test_evidence_write_failure_prevents_dispatch(tmp_path, monkeypatch):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static")
    def fail(*args):
        raise OSError("磁盘不可写")
    monkeypatch.setattr("refractrouter.planning_runtime.os.replace", fail)
    with pytest.raises(OSError):
        step(r, run)
    assert r.runs[run]["status"] == "evidence-failed"
    assert r.runs[run]["budget"].stopped


def test_tools_pairing_nested_multimodal_and_stage_downgrade(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "stage")
    with pytest.raises(ValueError, match="对应调用"):
        step(r, run, [{"role": "user", "content": [{"type": "tool-result", "toolCallId": "orphan"}]}])
    with pytest.raises(ValueError, match="仅支持文本"):
        step(r, run, [{"role": "user", "content": [{"type": "image", "data": "fake"}]}])
    events = [{"status": "completed", "kind": "mutate", "fingerprint": str(i)} for i in range(3)]
    assert stage(events, {"hold": 0}, DEFAULTS, "capable")[0] == "efficient"
    assert stage([{"status":"failed","kind":"unknown","fingerprint":"test"}],
        {"hold":0}, DEFAULTS, "efficient")[0] == "efficient"


def test_selected_strategy_availability_uses_host_catalogue():
    report = preview(configuration(), {"judge": "已删除"})
    rows = {s["id"]: s for s in report["strategies"]}
    assert rows["stage"]["available"] and not rows["task"]["available"]
