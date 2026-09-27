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
from refractrouter.planning_decision import (LayaDecisionAdapter, LocalDecisionCapacityError,
                                             candidate_assessments, decision_request, filter_candidates,
                                             parse_decision, select_task_candidate, task_state)
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


def task_pool_configuration(*, judge_type="llm", model_path=None):
    cfg = configuration("task")
    cfg.update(schemaVersion="refractagent-planning-v3", billingUnit="CNY",
               maxProductionCostByUnit={"CNY": 10})
    for model in cfg["models"]:
        model["billingUnit"] = "CNY"
        model["capabilities"] = {"mainExecutor": model["id"] != "judge",
            "toolCalling": "verified", "modalities": {}}
    judge = ({"type": "llm", "modelId": "judge"} if judge_type == "llm" else
             {"type": "local-decision", "adapter": "laya-mlx", "modelPath": str(model_path),
              "sourceModel": "aac6fef/laya-multilingual-mlx", "revision": "test", "device": "cpu",
              "dtype": "float32"})
    cfg["task"] = {"pool": ["small", "large"], "fallback": "large", "judge": judge,
                   "threshold": .8, "maxInputChars": 12000}
    return cfg


def write_laya_fixture(path, revision="test"):
    path.mkdir()
    (path / "model.safetensors").write_bytes(b"fixture")
    (path / "mlx_config.json").write_text("{}")
    (path / "rl_agent_config.json").write_text("{}")
    (path / "encoder").mkdir()
    (path / "encoder/config.json").write_text("{}")
    (path / "refractrouter-laya.json").write_text(json.dumps({
        "sourceModel": "aac6fef/laya-multilingual-mlx", "revision": revision,
        "adapter": "laya-mlx"}))


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
        arguments = json.dumps({"command": "python -m pytest",
                               "description": f"第 {index + 1} 次执行"})
        call = {"type": "tool-call", "id": call_id, "name": "bash",
                "arguments": arguments}
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
    assert decision["ruleVersion"] == "stage-v3"


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


def test_task_v3_llm_judge_selects_once_and_keeps_model(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=task_pool_configuration())
    judge = step(r, run)
    assert judge["purpose"] == "task" and judge["model"]["id"] == "judge"
    payload = {"answers": {
        "candidates": {"small": {"score": .91, "missingInformation": .02},
                       "large": {"score": .08, "missingInformation": .1}}}}
    execute = receipt(r, run, judge, json.dumps(payload))
    assert execute["model"]["id"] == "small"
    receipt(r, run, execute)
    followup = step(r, run)
    assert followup["purpose"] == "execute" and followup["model"]["id"] == "small"
    assert [row["purpose"] for row in r.runs[run]["budget"].records] == ["task", "execute", "execute"]


def test_task_quality_gate_precedes_cost_and_uses_pool_order_on_equal_cost():
    assessments = candidate_assessments({"answers": {"candidates": {
        "fast": {"score": .83, "missingInformation": 0},
        "strong": {"score": .97, "missingInformation": 0}}}}, ["fast", "strong"], .8)
    selected = select_task_candidate(assessments, "strong", {
        "fast": {"unit": "AFP", "amount": 2}, "strong": {"unit": "AFP", "amount": 5}})
    assert selected["candidateId"] == "fast"
    assert selected["reason"] == "quality-then-first-call-cost"
    assert selected["latencyBasis"] == "unavailable"
    missing = candidate_assessments({"answers": {"candidates": {
        "fast": {"score": .99, "missingInformation": .9},
        "strong": {"score": .83, "missingInformation": .1}}}}, ["fast", "strong"], .8)
    assert select_task_candidate(missing, "strong", {
        "fast": {"unit": "AFP", "amount": 2},
        "strong": {"unit": "AFP", "amount": 5}})["candidateId"] == "strong"


def test_task_cross_unit_and_missing_quality_use_explicit_fallback():
    rows = [{"candidateId": "a", "score": .9, "missingInformation": 0, "qualified": True},
            {"candidateId": "b", "score": .9, "missingInformation": 0, "qualified": True}]
    result = select_task_candidate(rows, "b", {
        "a": {"unit": "AFP", "amount": 1}, "b": {"unit": "CNY", "amount": 1}})
    assert result["candidateId"] == "b" and result["reason"] == "incomparable-billing-units"
    rows[0]["qualified"] = rows[1]["qualified"] = False
    assert select_task_candidate(rows, "b", {
        "a": {"unit": "AFP", "amount": 1}, "b": {"unit": "CNY", "amount": 1}})["reason"] == \
        "no-quality-qualified-candidate"


def test_task_judge_rejects_partial_or_forged_candidate_assessments():
    for entries in ({"small": {"score": .9, "missingInformation": 0}},
                    {"small": {"score": .9, "missingInformation": 0},
                     "forged": {"score": .9, "missingInformation": 0}},
                    {"small": {"score": float("nan"), "missingInformation": 0},
                     "large": {"score": .9, "missingInformation": 0}}):
        with pytest.raises(ValueError):
            candidate_assessments({"answers": {"candidates": entries}}, ["small", "large"], .8)


def test_task_filters_unaffordable_candidate_before_paid_judge(tmp_path):
    cfg = task_pool_configuration()
    cfg["maxProductionCostByUnit"] = {"CNY": .2}
    cfg["models"][1]["inputPer1k"] = 20
    cfg["models"][1]["outputPer1k"] = 20
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run)
    assert action["purpose"] == "execute" and action["model"]["id"] == "small"
    assert [row["purpose"] for row in runtime.runs[run]["budget"].records] == ["execute"]
    assert any(row["id"] == "large" and "预算不足" in row["reason"]
               for row in runtime.runs[run]["flow"]["rejectedCandidates"])


def test_task_llm_judge_cannot_override_cost_order_after_quality_gate(tmp_path):
    cfg = task_pool_configuration()
    cfg["models"][0]["inputPer1k"] = cfg["models"][0]["outputPer1k"] = .001
    cfg["models"][1]["inputPer1k"] = cfg["models"][1]["outputPer1k"] = .1
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    judge = step(runtime, run)
    execute = receipt(runtime, run, judge, json.dumps({"answers": {"candidates": {
        "small": {"score": .81, "missingInformation": .1},
        "large": {"score": .99, "missingInformation": 0}}}}))
    assert execute["model"]["id"] == "small"
    decision = runtime.runs[run]["state"]["judge_decision"]
    assert decision["reason"] == "quality-then-first-call-cost"
    assert decision["candidateId"] == "small"
    assert decision["firstCallUpperBounds"]["small"]["amount"] < \
           decision["firstCallUpperBounds"]["large"]["amount"]


def test_task_privacy_filters_cloud_candidate_before_judge(tmp_path):
    cfg = task_pool_configuration()
    cfg["models"][1]["deployment"] = "external-cloud"
    cfg["models"][0]["deployment"] = "local"
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run, [{"role": "user", "content": "查看 /Users/example/work/README.md"}])
    assert action["purpose"] == "execute" and action["model"]["id"] == "small"
    assert any(item["id"] == "large" and "数据域" in item["reason"]
               for item in runtime.runs[run]["flow"]["rejectedCandidates"])


def test_task_v3_preflight_respects_request_output_limit(tmp_path):
    cfg = task_pool_configuration()
    cfg["maxProductionCostByUnit"] = {"CNY": 1}
    for model in cfg["models"]:
        model.update(contextWindow=200000, maxOutputTokens=100000,
                     inputPer1k=.25, outputPer1k=.25)
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run, maxTokens=512)
    assert action["purpose"] == "task"
    assert action["model"]["maxTokens"] == 512


def test_task_judge_preflight_prices_the_exact_dispatched_request(tmp_path, monkeypatch):
    runtime = PlanningRuntime(tmp_path)
    run_id = begin(runtime, "task", config=task_pool_configuration())
    priced = []
    original = runtime._cost_bound

    def capture(model, messages, tools, output_cap=None):
        amount = original(model, messages, tools, output_cap)
        if model.model_id == "judge":
            priced.append((deepcopy(messages), amount))
        return amount

    monkeypatch.setattr(runtime, "_cost_bound", capture)
    step(runtime, run_id)
    row = runtime.runs[run_id]["budget"].records[0]
    assert len(priced) == 2
    assert all(messages == row["request_messages"] for messages, _ in priced)
    assert all(amount == pytest.approx(row["reserved"]) for _, amount in priced)


@pytest.mark.parametrize("score", [1.01, 1.8, 2, float("nan"), float("inf"), True])
def test_task_judge_rejects_out_of_contract_scores(score):
    with pytest.raises(ValueError, match="适合度分数"):
        parse_decision({"answers": {"selection": "small", "suitability": {"score": score},
                                   "missing_information": False}}, ["small", "large"], .8)


def test_local_judge_does_not_prefer_an_incomplete_candidate(monkeypatch):
    class Agent:
        batch_size = 16

        def predict(self, state, questions):
            return {"answers": {
                "candidate:small:suitability": {"score": 1.8},
                "candidate:small:missing": {"noul": .1},
                "candidate:large:suitability": {"score": 1.98},
                "candidate:large:missing": {"noul": .9}}}

    adapter = object.__new__(LayaDecisionAdapter)
    adapter.agent, adapter.model, adapter.cold_start_ms = Agent(), "fixture", None
    monkeypatch.setattr(adapter, "_ensure_complete", lambda state, questions: None)
    request = decision_request({"text": "任务", "media": [], "tools": []},
                               [{"id": "small"}, {"id": "large"}], .8)
    result = adapter.decide(request)
    parsed = parse_decision(result.payload, ["small", "large"], .8)
    assert parsed["candidateId"] == "small"
    assert not parsed["uncertain"]


def test_task_v3_uses_task_output_cap_below_model_capacity(tmp_path):
    cfg = task_pool_configuration()
    cfg["maxProductionCostByUnit"] = {"CNY": 3}
    cfg["task"]["maxExecutionOutputTokens"] = 1024
    for model in cfg["models"]:
        model.update(contextWindow=500000, maxOutputTokens=393216,
                     inputPer1k=.25, outputPer1k=.25)
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run)
    assert action["purpose"] == "task"
    assert action["model"]["maxTokens"] == 1024


def test_task_v3_single_eligible_media_candidate_skips_judge(tmp_path):
    cfg = task_pool_configuration()
    cfg["models"][1]["capabilities"]["modalities"] = {"imageInput": "verified"}
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    messages = [{"role": "user", "content": [{"type": "image", "attachment": {
        "id": "att-1", "mediaType": "image/png", "name": "sample.png", "byteLength": 12}}]}]
    action = step(r, run, messages)
    assert action["purpose"] == "execute" and action["model"]["id"] == "large"
    assert len(r.runs[run]["budget"].records) == 1
    assert r.runs[run]["state"]["judge_decision"]["reason"] == "single-eligible-candidate"


def test_task_v3_media_candidate_checks_format_dimensions_and_count():
    cfg = compile_config(task_pool_configuration())
    small = cfg["models"]["small"]
    small.capabilities["modalities"]["imageInput"] = "verified"
    small.capabilities["formats"] = {"imageInput": ["image/png"]}
    small.capabilities["limits"] = {"maxImages": 1, "maxWidth": 1024}
    large = cfg["models"]["large"]
    large.capabilities["modalities"]["imageInput"] = "verified"
    large.capabilities["formats"] = {"imageInput": ["image/jpeg"]}
    messages = [{"role": "user", "content": [{"type": "image", "attachment": {
        "mediaType": "image/png", "byteLength": 12, "width": 2048, "height": 512}}]}]
    state = task_state(messages, [], 12000)
    accepted, rejected = filter_candidates(cfg, state)
    assert accepted == []
    assert rejected == [{"id": "small", "reason": "image-dimensions-unsupported"},
                        {"id": "large", "reason": "image-format-unsupported"}]


def test_task_judge_state_ignores_dsh_injected_skill_catalog():
    messages = [
        {"role": "user", "source": {"kind": "user"},
         "content": [{"type": "text", "text": "只执行 pwd"}]},
        {"role": "user", "source": {"kind": "plugin", "plugin": "system-prompt"},
         "content": [{"type": "text", "text": "插件环境说明" * 2000}]},
        {"role": "user", "source": {"kind": "skill-catalog"},
         "content": [{"type": "text", "text": "技能目录" * 2000}]},
    ]
    state = task_state(messages, [], 12000)
    assert state["complete"]
    assert state["text"] == "只执行 pwd"


def test_task_v3_uncertain_uses_only_configured_fallback(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=task_pool_configuration())
    judge = step(r, run)
    payload = {"answers": {"candidates": {
        "small": {"score": .2, "missingInformation": .9},
        "large": {"score": .3, "missingInformation": .8}}}}
    execute = receipt(r, run, judge, json.dumps(payload))
    assert execute["model"]["id"] == "large"
    assert r.runs[run]["state"]["judge_decision"]["reason"] == "llm-judge-uncertain"


def test_task_v3_invalid_llm_result_stops_without_repair_call(tmp_path):
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=task_pool_configuration())
    judge = step(r, run)
    with pytest.raises(ValueError, match="不会自动修复"):
        receipt(r, run, judge, '{"answers":{"selection":{"choice":"forged"}}}')
    assert r.runs[run]["status"] == "task-judge-invalid"
    assert len(r.runs[run]["budget"].records) == 1


def test_task_v3_local_judge_is_persistent_and_has_no_api_call(tmp_path, monkeypatch):
    model_path = tmp_path / "laya"
    write_laya_fixture(model_path)
    cfg = task_pool_configuration(judge_type="local-decision", model_path=model_path)
    cfg["models"][0]["capabilityCard"] = "已验证可处理短文本与简单代码修改"
    calls = []

    class Result:
        payload = {"answers": {"selection": {"choice": "small", "probabilities": {"small": .9}},
            "suitability": {"score": .9}, "missing_information": {"noul": .0}}}
        model = "local-laya"
        cold_start_ms = 50
        latency_ms = 4
        usage = {"forwards": 2}

    class FakeLocal:
        def __init__(self, config):
            calls.append(("load", config["modelPath"]))
        def decide(self, request):
            assert request["candidates"][0]["capabilityCard"] == "已验证可处理短文本与简单代码修改"
            calls.append(("decide", request["contract"]))
            return Result()

    monkeypatch.setattr("refractrouter.planning_runtime.LayaDecisionAdapter", FakeLocal)
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    action = step(r, run)
    assert action["model"]["id"] == "small"
    assert len(r.runs[run]["budget"].records) == 1
    assert calls == [("load", str(model_path)), ("decide", "task-decision-v2")]


def test_task_v3_local_capacity_uses_only_configured_fallback(tmp_path, monkeypatch):
    model_path = tmp_path / "laya"
    write_laya_fixture(model_path)
    cfg = task_pool_configuration(judge_type="local-decision", model_path=model_path)

    class CapacityLimited:
        def __init__(self, _config):
            pass

        def decide(self, _request):
            raise LocalDecisionCapacityError("输入需要 800 tokens，但只剩 400 tokens")

    monkeypatch.setattr("refractrouter.planning_runtime.LayaDecisionAdapter", CapacityLimited)
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run)
    assert action["model"]["id"] == "large"
    assert runtime.runs[run]["state"]["judge_decision"]["reason"] == "local-judge-capacity"
    assert [row["purpose"] for row in runtime.runs[run]["budget"].records] == ["execute"]
    decision = next(item for item in runtime.runs[run]["decisions"]
                    if item["reason"] == "local-judge-capacity")
    assert decision["reason"] == "local-judge-capacity"
    assert "800 tokens" in decision["decision"]["issue"]


def test_laya_adapter_scores_every_candidate_in_one_task_batch(monkeypatch):
    class Agent:
        batch_size = 16
        def predict(self, state, questions):
            assert "candidates" not in state
            assert len(questions) == 4
            return {"model": "laya-local", "usage": {"input_tokens": 40, "output_tokens": 0},
                "answers": {
                    "candidate:small:suitability": {"score": 1.2},
                    "candidate:small:missing": {"noul": .1},
                    "candidate:large:suitability": {"score": 1.8},
                    "candidate:large:missing": {"noul": .1}}}
    adapter = object.__new__(LayaDecisionAdapter)
    adapter.agent, adapter.model, adapter.cold_start_ms = Agent(), "laya-local", 12
    monkeypatch.setattr(adapter, "_ensure_complete", lambda state, questions: None)
    state = {"text": "复杂中文任务", "media": [], "tools": ["read"]}
    candidates = [{"id": "small", "provider": "p", "model": "s", "capabilities": {}},
                  {"id": "large", "provider": "p", "model": "l", "capabilities": {}}]
    result = adapter.decide(decision_request(state, candidates, .8))
    assert result.payload["answers"]["selection"]["choice"] == "large"
    assert result.payload["rawPerCandidate"][1]["score"] == .9
    assert result.usage["questions"] == 4 and result.usage["forwards"] == 1
    parsed = parse_decision(result.payload, ["small", "large"], .8)
    assert parsed["candidateId"] == "large" and not parsed["uncertain"]


def test_laya_noul_probability_means_missing_information(monkeypatch):
    class Agent:
        batch_size = 16
        def predict(self, _state, _questions):
            return {"model": "laya-local", "usage": {"input_tokens": 20}, "answers": {
                "candidate:small:suitability": {"score": 1.9},
                "candidate:small:missing": {"noul": .98},
                "candidate:large:suitability": {"score": 1.7},
                "candidate:large:missing": {"noul": .1}}}

    adapter = object.__new__(LayaDecisionAdapter)
    adapter.agent, adapter.model, adapter.cold_start_ms = Agent(), "laya-local", None
    monkeypatch.setattr(adapter, "_ensure_complete", lambda _state, _questions: None)
    state = {"text": "需要工具的任务", "media": [], "tools": ["bash"]}
    candidates = [{"id": "small", "capabilities": {}}, {"id": "large", "capabilities": {}}]
    result = adapter.decide(decision_request(state, candidates, .8))
    parsed = parse_decision(result.payload, ["small", "large"], .8)
    assert parsed["candidateId"] == "large"
    assert parsed["score"] == .85
    assert parsed["missingInformation"] == .1
    assert not parsed["uncertain"]
    assert result.payload["rawPerCandidate"][0]["missingInformation"] == .98


def test_laya_choice_v2_uses_one_question_and_preserves_score_kind(monkeypatch):
    class Agent:
        def predict(self, state, questions):
            assert state == "执行 pwd"
            assert list(questions) == ["selection"]
            assert questions["selection"]["criteria"]["small"] == "已验证终端工具"
            return {"model": "laya-local", "usage": {"input_tokens": 80}, "answers": {
                "selection": {"choice": "small", "probabilities": {
                    "small": .9, "large": .06, "insufficient": .04}}}}

    adapter = object.__new__(LayaDecisionAdapter)
    adapter.agent, adapter.model, adapter.cold_start_ms = Agent(), "laya-local", None
    adapter.method = "choice-v2"
    monkeypatch.setattr(adapter, "_ensure_complete", lambda _state, _questions: None)
    state = {"text": "执行 pwd", "media": [], "tools": ["bash"]}
    candidates = [{"id": "small", "model": "s", "capabilities": {},
                   "capabilityCard": "已验证终端工具"},
                  {"id": "large", "model": "l", "capabilities": {},
                   "capabilityCard": "仅支持文字"}]
    result = adapter.decide(decision_request(state, candidates, .8))
    parsed = parse_decision(result.payload, ["small", "large"], .8)
    assert parsed["candidateId"] == "small" and not parsed["uncertain"]
    assert parsed["score"] == .9 and parsed["missingInformation"] == .04
    assert result.payload["scoreKind"] == "choice-probability"
    assert result.usage["questions"] == result.usage["forwards"] == 1


def test_task_choice_v2_missing_card_uses_fallback_without_judge(tmp_path, monkeypatch):
    model_path = tmp_path / "laya"
    write_laya_fixture(model_path)
    cfg = task_pool_configuration(judge_type="local-decision", model_path=model_path)
    cfg["task"]["judge"]["method"] = "choice-v2"
    monkeypatch.setattr("refractrouter.planning_runtime.LayaDecisionAdapter",
                        lambda _config: (_ for _ in ()).throw(AssertionError("不应加载 Judge")))
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run)
    assert action["model"]["id"] == "large"
    assert runtime.runs[run]["state"]["judge_decision"]["reason"] == \
        "local-judge-no-capability-evidence"


def test_task_choice_v2_equal_evidence_uses_fallback_without_judge(tmp_path, monkeypatch):
    model_path = tmp_path / "laya"
    write_laya_fixture(model_path)
    cfg = task_pool_configuration(judge_type="local-decision", model_path=model_path)
    cfg["task"]["judge"]["method"] = "choice-v2"
    for model in cfg["models"]:
        if model["id"] in cfg["task"]["pool"]:
            model["capabilityCard"] = "文字与工具已接通；任务质量待验收。"
    monkeypatch.setattr("refractrouter.planning_runtime.LayaDecisionAdapter",
                        lambda _config: (_ for _ in ()).throw(AssertionError("无区分证据不应加载 Judge")))
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", config=cfg)
    action = step(runtime, run)
    assert action["model"]["id"] == "large"
    assert runtime.runs[run]["state"]["judge_decision"]["reason"] == \
        "local-judge-no-differentiating-evidence"


def test_task_choice_v2_rejects_unknown_method():
    cfg = task_pool_configuration()
    cfg["task"]["judge"] = {"type": "local-decision", "adapter": "laya-mlx",
                            "modelPath": "/tmp/laya", "sourceModel": "laya",
                            "revision": "fixed", "method": "other"}
    with pytest.raises(ValueError, match="method 无效"):
        compile_config(cfg)


def test_media_non_token_reservation_and_async_state_are_persisted(tmp_path):
    cfg = task_pool_configuration()
    cfg["mediaRoutes"] = [{"id": "seedream", "provider": "ark-plan",
        "model": "doubao-seedream-5.0-lite", "operations": ["image-generate", "image-edit"],
        "billingUnit": "AFP", "pricing": {"basis": "image", "unitCost": 99,
            "source": "火山方舟 Agent Plan", "checkedAt": "2026-09-26"},
        "deployment": "external-cloud", "verified": True,
        "endpoint": "https://ark.cn-beijing.volces.com/api/plan/v3"}]
    cfg["maxProductionCostByUnit"]["AFP"] = 500
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    reserved = r.handle({"op": "media-reserve", "runId": run, "routeId": "seedream",
        "operation": "image-generate", "maxUnits": 2, "requestHash": "abc",
        "input": {"prompt": "公开风景", "references": []}})
    assert reserved["reserved"] == 198 and reserved["billingUnit"] == "AFP"
    submitted = r.handle({"op": "media-update", "runId": run,
        "operationId": reserved["operationId"], "status": "submitted", "providerTaskId": "image-1"})
    assert submitted["status"] == "submitted"
    completed = r.handle({"op": "media-update", "runId": run,
        "operationId": reserved["operationId"], "status": "succeeded", "providerTaskId": "image-1",
        "actualUnits": 1, "artifacts": [{"attachmentId": "sha256:1"}]})
    assert completed["status"] == "succeeded"
    costs, rows = r.runs[run]["budget"].snapshot()
    assert costs["AFP"]["production"] == 99
    assert rows[-1]["usage_type"] == "non-token" and rows[-1]["artifacts"][0]["attachmentId"] == "sha256:1"


def test_media_unknown_submission_stops_without_resubmission(tmp_path):
    cfg = task_pool_configuration()
    cfg["mediaRoutes"] = [{"id": "seedance", "provider": "ark-plan", "model": "seedance",
        "operations": ["video-generate"], "billingUnit": "AFP",
        "pricing": {"basis": "output-10k-token", "unitCost": 2,
            "source": "火山方舟 Agent Plan", "checkedAt": "2026-09-26"},
        "verified": True, "endpoint": "https://ark.cn-beijing.volces.com/api/plan/v3"}]
    cfg["maxProductionCostByUnit"]["AFP"] = 500
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    reserved = r.handle({"op": "media-reserve", "runId": run, "routeId": "seedance",
        "operation": "video-generate", "maxUnits": 100,
        "input": {"prompt": "公开风景", "references": []}})
    result = r.handle({"op": "media-update", "runId": run,
        "operationId": reserved["operationId"], "status": "unknown"})
    assert result == {"operationId": reserved["operationId"], "status": "unknown", "retry": False}
    assert r.runs[run]["status"] == "media-usage-unknown"
    with pytest.raises(ValueError, match="已停止"):
        r.handle({"op": "media-reserve", "runId": run, "routeId": "seedance",
            "operation": "video-generate", "maxUnits": 100,
            "input": {"prompt": "公开风景", "references": []}})


def test_connected_media_route_can_be_saved_but_not_dispatched_before_acceptance(tmp_path):
    cfg = task_pool_configuration()
    cfg["mediaRoutes"] = [{"id": "seedream", "provider": "ark-plan", "credentialProvider": "ark",
        "model": "doubao-seedream-5.0-lite", "operations": ["image-generate"],
        "billingUnit": "AFP", "pricing": {"basis": "image", "unitCost": 99,
            "source": "火山方舟 Agent Plan", "checkedAt": "2026-09-26"},
        "verification": "connected", "endpoint": "https://ark.cn-beijing.volces.com/api/plan/v3"}]
    cfg["maxProductionCostByUnit"]["AFP"] = 500
    report = preview(cfg)
    assert report["mediaRoutes"][0]["available"] is False
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    with pytest.raises(ValueError, match="尚未通过真实接口验收"):
        r.handle({"op": "media-reserve", "runId": run, "routeId": "seedream",
            "operation": "image-generate", "maxUnits": 1,
            "input": {"prompt": "公开风景", "references": []}})


def test_media_cancellation_before_dispatch_releases_reservation(tmp_path):
    cfg = task_pool_configuration()
    cfg["mediaRoutes"] = [{"id": "seedream", "provider": "ark-plan", "model": "seedream",
        "operations": ["image-generate"], "billingUnit": "AFP",
        "pricing": {"basis": "image", "unitCost": 99, "source": "官方", "checkedAt": "2026-09-26"},
        "verified": True, "endpoint": "https://ark.cn-beijing.volces.com/api/plan/v3"}]
    cfg["maxProductionCostByUnit"]["AFP"] = 500
    r = PlanningRuntime(tmp_path)
    run = begin(r, "task", config=cfg)
    reserved = r.handle({"op": "media-reserve", "runId": run, "routeId": "seedream",
        "operation": "image-generate", "maxUnits": 1, "input": {"prompt": "公开风景"}})
    r.handle({"op": "media-update", "runId": run, "operationId": reserved["operationId"],
        "status": "cancelled", "actualUnits": 0})
    costs, rows = r.runs[run]["budget"].snapshot()
    assert costs["AFP"]["production"] == 0
    assert rows[-1]["status"] == "cancelled-before-dispatch"


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
