"""规划路由离线行为验收：真实策略和账本，模拟宿主执行。"""
from copy import deepcopy
from datetime import datetime
import json
import threading
from zoneinfo import ZoneInfo

import pytest

from refractrouter.planning_config import compile_config, preview, DEFAULTS
from refractrouter.planning_policy import stage, stage_decision, tool_events
from refractrouter.planning_runtime import PlanningRuntime, historical_billing_warning
from refractrouter.task_budget import TaskCallBudget
from refractrouter.deepseek_official_pricing import pricing as deepseek_cny_pricing
from refractrouter.dsh_model_pool import frozen_usd_cny_rate


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


def test_unpriced_optional_model_does_not_block_static(tmp_path):
    cfg = configuration("static")
    cfg["models"].append({"id": "unpriced", "provider": "fake", "model": "new",
        "contextWindow": 32000, "maxOutputTokens": 1024,
        "inputPer1k": None, "outputPer1k": None, "deployment": "local"})
    cfg["roles"]["classifier"] = "unpriced"
    report = preview(cfg)
    assert report["valid"]
    assert next(s for s in report["strategies"] if s["id"] == "static")["available"]
    task = next(s for s in report["strategies"] if s["id"] == "task")
    assert not task["available"] and "unpriced" in task["issues"][0]
    assert "inputPer1k" in report["issues"][0]
    runtime = PlanningRuntime(tmp_path)
    assert step(runtime, begin(runtime, "static", config=cfg))["model"]["id"] == "small"
    with pytest.raises(ValueError, match="配置未完成"):
        begin(runtime, "task", turn=2, config=cfg)


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


def test_static_preflight_uses_actual_request_instead_of_entire_context_window(tmp_path):
    cfg = configuration("static")
    cfg["models"][0]["contextWindow"] = 1_048_576
    cfg["models"][0]["inputPer1k"] = 0.05
    cfg["models"][0]["outputPer1k"] = 0.05
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static", config=cfg)
    action = step(runtime, run)
    assert action["model"]["id"] == "small"
    assert runtime.runs[run]["budget"].records[0]["reserved"] < cfg["maxProductionCost"]


def test_stage_reserves_only_selected_model(tmp_path):
    cfg = configuration("stage")
    cfg["maxProductionCost"] = .01
    cfg["models"][1]["outputPer1k"] = 100
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "stage", config=cfg)
    action = step(runtime, run)
    assert action["model"]["id"] == "small"
    assert runtime.runs[run]["budget"].records[0]["model_id"] == "small"
    assert len(runtime.runs[run]["budget"].records) == 1


def test_stage_selected_capable_model_budget_shortage_stops_explicitly(tmp_path):
    cfg = configuration("stage")
    cfg["maxProductionCost"] = .01
    cfg["models"][1]["outputPer1k"] = 100
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "stage", config=cfg)
    messages, events = [], []
    for index in range(2):
        call_id = f"call-{index}"
        call = {"type": "tool-call", "id": call_id, "name": "bash",
                "arguments": '{"cmd":"pytest"}'}
        result = {"type": "tool-result", "toolCallId": call_id, "isError": True,
                  "content": [{"type": "text", "text": "test failed"}]}
        messages.extend([{"role": "assistant", "content": [call]},
                         {"role": "user", "content": [result]}])
        events.extend([
            {"type": "tool/call", "data": {"turn": 1, "step": index, "callId": call_id,
             "name": "bash", "arguments": '{"cmd":"pytest"}'}},
            {"type": "tool/result", "data": {"turn": 1, "step": index,
             "message": {"content": [result]}, "error": {"name": "CommandError", "code": "EXIT_NONZERO"},
             "meta": {"exitCode": 1}}},
        ])
    with pytest.raises(ValueError, match="无法派发 capable 模型 fake/large"):
        step(runtime, run, messages, events=events)
    assert runtime.runs[run]["status"] == "failed"


def test_stage_uses_canonical_host_shell_result_without_parsing_body(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "stage")
    messages, events = [], []
    for index in range(2):
        call_id = f"shell-{index}"
        call = {"type": "tool-call", "id": call_id, "name": "bash",
                "arguments": '{"command":"python -m pytest"}'}
        result = {"type": "tool-result", "toolCallId": call_id, "isError": False,
                  "content": [{"type": "text", "text": "test output"}]}
        messages.extend([{"role": "assistant", "content": [call]},
                         {"role": "user", "content": [result]}])
        events.extend([
            {"type": "tool/call", "data": {"turn": 1, "step": index + 1,
             "callId": call_id, "name": "bash", "arguments": call["arguments"]}},
            {"type": "tool/result", "data": {"turn": 1, "step": index + 1,
             "message": {"source": {"kind": "tool", "callId": call_id}, "content": [result]},
             "hostResult": {"exitCode": 7, "signal": None, "timedOut": False,
                            "aborted": False}}},
        ])
    action = step(runtime, run, messages, events=events)
    assert action["model"]["id"] == "large"
    decision = runtime.runs[run]["decisions"][-1]
    assert decision["reason"] == "repeated-failure"
    assert decision["evidenceSummary"] == "任务失败 2"


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


def test_afp_and_cny_calls_keep_separate_budgets_and_history(tmp_path):
    cfg = configuration("task")
    legacy = deepcopy(cfg)
    legacy["models"][2]["billingUnit"] = "AFP"
    with pytest.raises(ValueError, match="需要 refractagent-planning-v2"):
        compile_config(legacy)
    cfg["schemaVersion"] = "refractagent-planning-v2"
    cfg["billingUnit"] = "USD"
    cfg["maxProductionCost"] = 10
    cfg["maxProductionCostByUnit"] = {"AFP": 10, "CNY": 10}
    cfg["models"][2]["billingUnit"] = "AFP"
    compiled = compile_config(cfg)
    fx, _ = frozen_usd_cny_rate()
    assert compiled["budgets"]["CNY"] == 10  # 显式 CNY 预算优先于遗留 USD 预算
    assert compiled["models"]["small"].billing_unit == "CNY"
    assert compiled["models"]["small"].input_cost_per_1k == pytest.approx(.001 * fx)
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    judge = step(r, run)
    assert judge["model"]["id"] == "judge"
    execute = receipt(r, run, judge, '{"p_solve":0.8,"capability_boundary":"supported"}')
    assert execute["model"]["id"] == "small"
    result = receipt(r, run, execute)
    record = result["record"]
    assert record["billingUnit"] is None
    assert record["costs"]["production"] is None
    assert record["costsByUnit"]["AFP"]["production"] > 0
    assert record["costsByUnit"]["CNY"]["production"] > 0
    assert [call["billing_unit"] for call in record["calls"]] == ["AFP", "CNY"]
    cash_call = next(call for call in record["calls"] if call["billing_unit"] == "CNY")
    assert cash_call["source_billing_unit"] == "USD"
    assert cash_call["conversion_rate"] > 0
    assert cash_call["conversion_source"]
    assert cash_call["conversion_as_of"]
    history = r.handle({"op": "history", "session": "a"})["records"][0]
    assert history["costsByUnit"] == record["costsByUnit"]
    capped = deepcopy(cfg)
    capped["maxProductionCostByUnit"] = {"AFP": .001}
    capped_runtime = PlanningRuntime(tmp_path / "capped-other")
    capped_run = begin(capped_runtime, "task", config=capped)
    with pytest.raises(ValueError, match="剩余预算"):
        step(capped_runtime, capped_run)
    assert capped_runtime.runs[capped_run]["budget"].records == []
    del cfg["maxProductionCostByUnit"]
    unavailable = preview(cfg)
    assert "缺少 AFP 生产预算" in next(row for row in unavailable["strategies"]
        if row["id"] == "task")["issues"]
    with pytest.raises(ValueError, match="缺少 AFP 生产预算"):
        begin(PlanningRuntime(tmp_path / "other"), "task", config=cfg)


def test_legacy_usd_only_cash_budget_migrates_to_cny(tmp_path):
    cfg = configuration("static")
    cfg["schemaVersion"] = "refractagent-planning-v2"
    cfg["billingUnit"] = "USD"
    cfg["maxProductionCost"] = 0
    cfg["maxProductionCostByUnit"] = {"USD": 4}
    compiled = compile_config(cfg)
    rate, _ = frozen_usd_cny_rate()
    assert compiled["budgets"] == {"CNY": pytest.approx(4 * rate)}
    assert all(model.billing_unit == "CNY" for model in compiled["models"].values())
    fx = PlanningRuntime(tmp_path).handle({"op": "fx"})
    assert fx["rate"] == rate and fx["source"] and fx["asOf"]


def test_mixed_budget_unknown_afp_usage_stops_all_managed_calls(tmp_path):
    cfg = configuration("task")
    cfg.update(schemaVersion="refractagent-planning-v2", billingUnit="USD",
               maxProductionCostByUnit={"AFP": 10, "CNY": 10})
    cfg["models"][2]["billingUnit"] = "AFP"
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    judge = step(runtime, run)
    with pytest.raises(ValueError, match="missing or unconfirmed model usage"):
        receipt(runtime, run, judge, usageAvailable=False)
    record = runtime.handle({"op": "query", "runId": run})
    assert record["status"] == "call-failed"
    assert record["calls"][0]["billing_unit"] == "AFP"
    assert record["calls"][0]["status"] == "unknown-usage"
    assert record["costsByUnit"]["AFP"]["production"] > 0
    assert record["costsByUnit"]["CNY"]["production"] == 0
    with pytest.raises(ValueError, match="已停止"):
        step(runtime, run)


def test_stage_structured_evidence_and_hold():
    msgs = []
    for i in range(2):
        msgs += [{"role": "assistant", "content": [{"type": "tool-call", "id": str(i), "name": "edit", "arguments": "{}"}]},
                 {"role": "user", "content": [{"type": "tool-result", "toolCallId": str(i), "isError": True, "error": {"code": "CODE_RUN_FAILED"}}]}]
    events = tool_events(msgs)
    role, reason, hold, _ = stage(events, {"hold": 0}, DEFAULTS, "efficient")
    assert (role, reason, hold) == ("capable", "repeated-failure", 1)
    role, _, hold, _ = stage([], {"hold": hold}, DEFAULTS, "efficient")
    assert role == "capable" and hold == 0
    assert stage([], {"hold": hold}, DEFAULTS, "efficient")[0] == "efficient"
    msgs[-1]["content"][0]["error"] = {"code": "PERMISSION_DENIED"}
    assert tool_events(msgs)[-1]["status"] == "denied"
    msgs[-1]["content"][0].pop("isError")
    msgs[-1]["content"][0].pop("error")
    msgs[-1]["content"][0]["content"] = [{"type": "text", "text": "失败失败失败"}]
    assert tool_events(msgs)[-1]["status"] == "completed"


def test_stage_consumes_old_failure_and_does_not_retrigger():
    events = [
        {"id": "one", "status": "failed", "kind": "mutate", "fingerprint": "same"},
        {"id": "two", "status": "failed", "kind": "mutate", "fingerprint": "same"},
    ]
    decision = stage_decision(events, {"hold": 0, "consumedEvidenceIds": []}, DEFAULTS, "efficient")
    assert decision["reason"] == "repeated-failure"
    assert decision["holdBefore"] == 0 and decision["holdAfter"] == 1
    state = {"hold": 0, "consumedEvidenceIds": ["one", "two"]}
    decision = stage_decision(events + [
        {"id": "three", "status": "completed", "kind": "observe", "fingerprint": "read"}
    ], state, DEFAULTS, "efficient")
    assert decision["role"] == "efficient"
    assert decision["reason"] == "ambiguous"


def test_stage_uses_structured_exit_code_and_ignores_failure_words():
    call = {"type": "tool-call", "id": "x", "name": "bash", "arguments": '{"cmd":"pytest"}'}
    result = {"type": "tool-result", "toolCallId": "x", "isError": False,
              "content": [{"type": "text", "text": "失败"}]}
    messages = [{"role": "assistant", "content": [call]}, {"role": "user", "content": [result]}]
    native = [{"type": "tool/call", "data": {"turn": 4, "step": 2, "callId": "x",
               "name": "bash", "arguments": '{"cmd":"pytest"}'}},
              {"type": "tool/result", "data": {"turn": 4, "step": 2,
               "message": {"content": [result]}, "meta": {"process": {"exitCode": 1}}}}]
    event = tool_events(messages, native)[0]
    assert event["status"] == "failed"
    assert event["failure"]["exitCode"] == 1
    assert event["id"] == "4:2:x"
    native[1]["data"].pop("meta")
    assert tool_events(messages, native)[0]["status"] == "completed"
    result["isError"] = True
    assert tool_events(messages, native)[0]["status"] == "unclassified-error"


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
    rate, _ = frozen_usd_cny_rate()
    assert released["record"]["costs"]["production"] == pytest.approx(.00042 * rate, abs=2e-8)
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
    rate, _ = frozen_usd_cny_rate()
    b = TaskCallBudget(None, .0026 * rate, 1)
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


def test_zero_limits_are_unbounded_without_changing_cost_ledger(tmp_path):
    cfg = configuration("static")
    cfg.update(maxProductionCost=0, timeoutMs=0, maxCalls=0)
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static", config=cfg)
    assert r.runs[run]["deadline"] is None
    assert r.describe(r.runs[run])["remainingMs"] is None
    assert r.runs[run]["budget"].max_calls is None
    first = step(r, run)
    receipt(r, run, first)
    second = step(r, run)
    result = receipt(r, run, second)
    assert result["record"]["costs"]["production"] > 0
    assert len(result["record"]["calls"]) == 2


def test_model_metadata_only_fills_verified_matching_billing_unit(tmp_path):
    r = PlanningRuntime(tmp_path)
    official = r.handle({"op": "metadata", "provider": "deepseek-official",
        "model": "deepseek-flash", "billingUnit": "USD",
        "host": {"contextWindow": 64000, "maxOutputTokens": 4096}})
    assert official["capacity"] == {"contextWindow": 64000, "maxOutputTokens": 4096}
    assert official["pricing"]["inputPer1k"] > 0
    assert official["sources"]["pricing"].startswith("https://")
    direct = r.handle({"op": "metadata", "provider": "deepseek-official",
        "model": "deepseek-flash", "billingUnit": "AUTO", "host": {}})
    assert direct["billingUnit"] == "CNY"
    assert direct["pricing"]["inputPer1k"] in (0.001, 0.002)
    assert direct["sources"]["pricing"] == "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"
    assert "冻结汇率" not in direct["sources"].get("pricingNote", "")
    reference_only = r.handle({"op": "metadata", "provider": "ark",
        "model": "minimax-m3", "billingUnit": "CNY", "host": {}})
    assert reference_only["pricing"] is None
    assert reference_only["capacity"] is None
    plan = r.handle({"op": "metadata", "provider": "ark-plan", "model": "minimax-m3",
        "billingUnit": "AFP", "host": {}})
    assert plan["pricing"]["inputPer1k"] >= 0
    assert plan["capacity"]["contextWindow"] > plan["capacity"]["maxOutputTokens"]
    alias = r.handle({"op": "metadata", "provider": "ark", "model": "minimax-m3",
        "billingUnit": "AFP", "host": {},
        "providerBaseURL": "https://ark.cn-beijing.volces.com/api/plan/v3"})
    assert alias["pricing"] == plan["pricing"]
    newly_documented = r.handle({"op": "metadata", "provider": "ark",
        "model": "deepseek-v4.1-flash", "billingUnit": "AUTO", "host": {},
        "providerBaseURL": "https://ark.cn-beijing.volces.com/api/plan/v3"})
    assert newly_documented["billingUnit"] == "AFP"
    assert newly_documented["pricing"] == {"inputPer1k": .25, "outputPer1k": .25,
                                            "cachedInputPer1k": .25}
    assert newly_documented["issues"] == []
    assert newly_documented["sources"]["pricingCheckedAt"] == "2026-09-25"
    mixed = r.handle({"op": "metadata", "provider": "ark", "model": "minimax-m3",
        "billingUnit": "CNY", "host": {},
        "providerBaseURL": "https://ark.cn-beijing.volces.com/api/plan/v3"})
    assert mixed["pricing"] is None
    assert any("按 AFP 计量" in issue for issue in mixed["issues"])


def test_deepseek_official_cny_peak_and_offpeak_price_snapshot():
    cn = ZoneInfo("Asia/Shanghai")
    offpeak = deepseek_cny_pricing("deepseek-flash", at=datetime(2026, 9, 26, 10, tzinfo=cn))
    peak = deepseek_cny_pricing("deepseek-v4-flash", at=datetime(2026, 9, 25, 10, tzinfo=cn))
    assert (offpeak["inputPer1k"], offpeak["outputPer1k"], offpeak["cachedInputPer1k"]) == (.001, .004, .00002)
    assert (peak["inputPer1k"], peak["outputPer1k"], peak["cachedInputPer1k"]) == (.002, .008, .00004)
    assert peak["tier"] == "peak"
    assert deepseek_cny_pricing("deepseek-flash", at=datetime(2026, 9, 26, 10, tzinfo=cn),
                                conservative=True)["tier"] == "peak-upper-bound"
    pro = deepseek_cny_pricing("deepseek-v4-pro", at=datetime(2026, 9, 26, 10, tzinfo=cn))
    assert (pro["inputPer1k"], pro["outputPer1k"]) == (.0045, .0135)
    assert deepseek_cny_pricing("unknown") is None


def test_deepseek_official_cny_reserves_peak_and_settles_call_tier(tmp_path, monkeypatch):
    import refractrouter.planning_runtime as module
    actual = {"inputPer1k": .001, "outputPer1k": .004, "cachedInputPer1k": .00002,
              "tier": "offpeak", "source": "official", "checkedAt": "2026-09-24"}
    upper = {**actual, "inputPer1k": .002, "outputPer1k": .008, "tier": "peak-upper-bound"}
    monkeypatch.setattr(module, "deepseek_cny_pricing", lambda model, conservative=False:
                        upper if conservative else actual)
    cfg = configuration("static")
    cfg.update(schemaVersion="refractagent-planning-v2", billingUnit="CNY",
               maxProductionCostByUnit={"CNY": 0})
    cfg["models"][0].update(provider="deepseek-official", model="deepseek-flash",
                             billingUnit="CNY", cachedInputPer1k=.00002)
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static", config=cfg)
    action = step(runtime, run)
    pending = runtime.runs[run]["flow"]["pending"][1]
    assert pending.row["pricing_tier"] == "offpeak"
    assert pending.row["reserved"] > .008
    result = receipt(runtime, run, action)
    call = result["record"]["calls"][0]
    assert call["charged"] == pytest.approx(.00018)
    assert call["charged"] < call["reserved"]


def test_agent_plan_unit_conflict_blocks_dispatch_and_flags_legacy_display(tmp_path):
    cfg = configuration("static")
    cfg["billingUnit"] = "CNY"
    cfg["models"][0].update(provider="ark", model="deepseek-v4-pro",
                            inputPer1k=.55, outputPer1k=.55)
    runtime = PlanningRuntime(tmp_path)
    issue = "Ark Agent Plan 按 AFP 计量；当前预算单位 CNY，不能把订阅点数当作现金价格"
    with pytest.raises(ValueError, match="按 AFP 计量"):
        runtime.handle({"op": "begin", "identity": {"session": "a", "agent": "a", "turn": 1},
            "strategy": "static", "config": cfg, "hostIssues": {"small": issue}})
    assert not list((tmp_path / "planning").glob("*.json"))
    record = {"billingUnit": "CNY", "configuration": cfg,
        "calls": [{"provider": "ark", "model_id": "small", "actual_model": "deepseek-v4-pro",
                   "status": "billed"}]}
    assert "不能视为人民币" in historical_billing_warning(record)


def test_preview_explains_unpriced_agent_plan_role_without_disabling_static():
    cfg = configuration("static")
    cfg["models"][2].update(provider="ark", model="minimax-m3",
                            inputPer1k=None, outputPer1k=None)
    report = preview(cfg, {"judge": "Ark Agent Plan 按 AFP 计量；当前预算单位 CNY"})
    assert next(row for row in report["strategies"] if row["id"] == "static")["available"]
    task = next(row for row in report["strategies"] if row["id"] == "task")
    assert not task["available"]
    assert "按 AFP 计量" in task["issues"][0]
    assert "inputPer1k 数值不合法" not in task["issues"][0]


def test_replay_admission_child_isolation_compaction(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static")
    messages = [{"role": "assistant", "source": {"kind": "model", "provider": "fake", "model": "large",
        "replayState": {"response": {"opaque": True}}}, "content": [{"type": "tool-call",
            "id": "read1", "name": "read", "arguments": "{}"}]},
        {"role": "user", "content": [{"type": "tool-result", "toolCallId": "read1",
            "content": [{"type": "text", "text": "完成"}]}]}]
    forwarded = step(r, run, deepcopy(messages))["messages"]
    assert forwarded[0]["content"] == messages[0]["content"]
    assert forwarded[0]["source"] == {"kind": "model", "provider": "fake", "model": "large"}
    malformed = deepcopy(messages)
    del malformed[0]["content"][0]["name"]
    with pytest.raises(ValueError, match="兼容"):
        step(r, begin(r, "static", turn=3), malformed)
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


def test_plain_legacy_model_history_needs_no_replay_pair(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "static")
    messages = [{"role": "assistant", "source": {"kind": "model", "provider": "refract-fixture",
        "model": "small"}, "content": [{"type": "text", "text": "历史普通文本"}]}]
    assert step(r, run, messages)["model"]["id"] == "small"
    opaque = [{**messages[0], "source": {**messages[0]["source"],
        "replayState": {"response": {"providerSpecific": True}}}, "content": [
            {"type": "reasoning", "text": "旧提供方思考"}, *messages[0]["content"]]}]
    run = begin(r, "static", turn=2)
    forwarded = step(r, run, opaque)["messages"][0]
    assert forwarded["source"] == {"kind": "model", "provider": "refract-fixture", "model": "small"}
    assert forwarded["content"] == messages[0]["content"]


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


def test_static_random_keeps_one_model_for_native_tool_continuation(tmp_path):
    cfg = configuration("static")
    cfg["parameters"] = {"staticMode": "random", "seed": 4}
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static", config=cfg)
    first = step(runtime, run)
    call = {"type": "tool-call", "id": "read1", "name": "read", "arguments": "{}"}
    receipt(runtime, run, first, content="", tools=(call,))
    continued = step(runtime, run, [
        {"role": "assistant", "content": [call]},
        {"role": "user", "content": [{"type": "tool-result", "toolCallId": "read1",
            "content": [{"type": "text", "text": "数据"}]}]}])
    assert continued["model"]["id"] == first["model"]["id"]
    assert [row["role"] for row in runtime.runs[run]["decisions"]] in (
        ["efficient", "efficient"], ["capable", "capable"])


def test_authorized_cloud_accepts_native_system_path_without_disabling_data_guard(tmp_path):
    cfg = configuration("static")
    cfg["models"][0].update(provider="deepseek-official", model="deepseek-flash",
                            deployment="external-cloud")
    messages = [{"role": "system", "content": "工作目录 /Users/alice/project/repo"},
                {"role": "user", "content": "只回答 21"}]
    runtime = PlanningRuntime(tmp_path)
    blocked = begin(runtime, "static", config=cfg)
    with pytest.raises(ValueError, match="local-absolute-path"):
        step(runtime, blocked, messages)
    assert not runtime.runs[blocked]["budget"].records

    cfg["trustPolicies"] = [{"id": "deepseek-paths", "residency": "CN",
                              "auditLogging": True, "allowsSensitiveData": True}]
    cfg["models"][0].update(deployment="trusted-cloud", trustPolicy="deepseek-paths")
    allowed = begin(runtime, "static", turn=2, config=cfg)
    action = step(runtime, allowed, messages)
    assert action["model"]["provider"] == "deepseek-official"
    assert action["messages"] == messages


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
    rate, _ = frozen_usd_cny_rate()
    assert result["record"]["costs"]["production"] == pytest.approx(.00023 * rate, abs=5e-9)
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
