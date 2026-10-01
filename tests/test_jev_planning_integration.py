"""官方 Jev 接入：核心只签发结构化判别，宿主回执后才推进策略。"""

import pytest

from refractrouter.jev_decision import JEV_MODEL
from refractrouter.planning_config import preview
from refractrouter.planning_runtime import PlanningRuntime


def configuration(strategy):
    models = [{"id": name, "provider": "fake", "model": name, "billingUnit": "CNY",
               "contextWindow": 32000, "maxOutputTokens": 2048,
               "inputPer1k": .001, "outputPer1k": .002, "deployment": "local",
               "capabilityCard": "适合快速文本工作" if name == "small" else "适合复杂文本推理",
               "capabilities": {"mainExecutor": name != "judge", "toolCalling": "verified",
                                "modalities": {}}} for name in ("small", "large", "judge")]
    config = {"schemaVersion": "refractagent-planning-v6", "enabled": True,
              "defaultStrategy": strategy, "billingUnit": "CNY",
              "maxProductionCostByUnit": {"CNY": 100}, "maxCalls": 12,
              "models": models,
              "roles": {"efficient": "small", "capable": "large",
                        "classifier": "judge", "advisor": "judge"}}
    if strategy == "advisor":
        config["advisor"] = {"executor": "small", "judge": {"type": "jev"},
            "threshold": .8, "judgeTimeoutMs": 30000, "maxJudgeInputBytes": 8000,
            "maxExecutionOutputTokens": 2048, "maxJudgeOutputTokens": 256}
    if strategy == "escalation":
        config["escalation"] = {"initial": "small", "takeover": "large",
            "judge": {"type": "jev"}, "threshold": .8, "stallConfirmations": 2,
            "judgeTimeoutMs": 30000, "maxJudgeInputBytes": 8000,
            "maxExecutionOutputTokens": 2048, "maxJudgeOutputTokens": 256}
    if strategy == "task":
        config["task"] = {"pool": ["small", "large"], "fallback": "large",
            "judge": {"type": "jev"}, "threshold": .8, "maxInputChars": 12000}
    config["jev"] = {"credentialRef": "TYPESAFE_API_KEY", "deployment": "external-cloud"}
    return config


def begin(runtime, strategy, config):
    return runtime.handle({"op": "begin", "identity": {"session": "a", "agent": "a", "turn": 1},
                           "strategy": strategy, "config": config})["runId"]


def step(runtime, run, messages=None, events=None):
    payload = {"op": "step", "runId": run, "messages": messages or [
        {"role": "user", "content": "完成任务"}], "tools": [
            {"name": "read", "description": "read", "parameters": {"type": "object"}}]}
    if events is not None:
        payload["events"] = events
    return runtime.handle(payload)


def receipt(runtime, run, action, content="完成", tools=()):
    return runtime.handle({"op": "complete", "runId": run, "callId": action["callId"],
        "response": {"content": content, "inputTokens": 100, "outputTokens": 20,
                     "finishReason": "tool_calls" if tools else "stop",
                     "toolCalls": list(tools), "usageAvailable": True, "latencyMs": 10}})


def response(action, choice, *, selected=.95, input_tokens=300):
    question_id, definition = next(iter(action["payload"]["questions"].items()))
    keys = list(definition["criteria"])
    others = [key for key in keys if key != choice]
    probabilities = {key: (selected if key == choice else (1-selected)/len(others))
                     for key in keys}
    return {"model": JEV_MODEL, "answers": {question_id: {
        "type": "choice", "choice": choice, "probabilities": probabilities,
        "confidence": selected}}, "usage": {"input_tokens": input_tokens,
                                            "output_tokens": 20}}


def complete(runtime, run, action, result):
    return runtime.handle({"op": "jev-complete", "runId": run, "callId": action["callId"],
                           "result": result, "latencyMs": 42})


def test_advisor_jev_approval_and_cny_ledger(tmp_path):
    cfg = configuration("advisor")
    assert next(row for row in preview(cfg)["strategies"] if row["id"] == "advisor")["available"]
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    execution = step(runtime, run)
    judge = receipt(runtime, run, execution, "已经完成")
    assert judge["action"] == "jev", (judge, runtime.runs[run]["decisions"])
    assert judge["payload"]["model"] == JEV_MODEL
    assert "TYPESAFE_API_KEY" not in str(judge["payload"])
    accepted = complete(runtime, run, judge, response(judge, "APPROVE"))
    assert accepted["action"] == "release"
    assert accepted["callId"] == execution["callId"]
    billed = [row for row in runtime.runs[run]["budget"].records if row.get("provider") == "typesafe"]
    assert len(billed) == 1 and billed[0]["status"] == "billed"
    assert billed[0]["billing_unit"] == "CNY"
    assert 0 < billed[0]["charged"] < billed[0]["reserved"]
    assert runtime.runs[run]["decisions"][-1]["selectedProbability"] == .95


def test_advisor_jev_redo_requires_second_review_before_release(tmp_path):
    cfg = configuration("advisor")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    initial = step(runtime, run)
    first = receipt(runtime, run, initial, "遗漏要求")
    redo = complete(runtime, run, first, response(first, "REDO_REQUIREMENT"))
    assert redo["action"] == "call" and redo["model"]["id"] == "small"
    assert next(row for row in runtime.runs[run]["budget"].records
                if row.get("call_id") == initial["callId"])["disposition"] == "discarded"
    second = receipt(runtime, run, redo, "按要求完成")
    assert second["action"] == "jev" and second["callId"] != first["callId"]
    delivered = complete(runtime, run, second, response(second, "APPROVE"))
    assert delivered["action"] == "release" and delivered["callId"] == redo["callId"]
    assert len([row for row in runtime.runs[run]["budget"].records
                if row.get("provider") == "typesafe" and row["status"] == "billed"]) == 2


def test_escalation_jev_defect_discards_candidate_and_takes_over(tmp_path):
    cfg = configuration("escalation")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "escalation", cfg)
    initial = step(runtime, run)
    judge = receipt(runtime, run, initial, "错误结果", tools=[{"id":"t1","name":"read","arguments":"{}"}])
    assert judge["action"] == "jev"
    takeover = complete(runtime, run, judge, response(judge, "DEFECT"))
    assert takeover["action"] == "call" and takeover["model"]["id"] == "large"
    assert runtime.runs[run]["state"]["latched"]
    assert next(row for row in runtime.runs[run]["budget"].records
                if row.get("call_id") == initial["callId"])["disposition"] == "discarded"


def test_task_jev_choice_is_once_per_task(tmp_path):
    cfg = configuration("task")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "task", cfg)
    judge = step(runtime, run)
    assert judge["action"] == "jev"
    execution = complete(runtime, run, judge, response(judge, "small"))
    assert execution["model"]["id"] == "small"
    released = receipt(runtime, run, execution, tools=[{"id":"t1","name":"read","arguments":"{}"}])
    assert released["action"] == "release"
    following = step(runtime, run, messages=[{"role":"user","content":"完成任务"}])
    assert following["action"] == "call" and following["model"]["id"] == "small"
    assert len([row for row in runtime.runs[run]["budget"].records
                if row.get("provider") == "typesafe"]) == 1


def test_jev_invalid_usage_keeps_reservation_and_stops(tmp_path):
    cfg = configuration("advisor")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    judge = receipt(runtime, run, step(runtime, run), "候选")
    result = response(judge, "APPROVE")
    result.pop("usage")
    with pytest.raises(ValueError, match="用量缺失"):
        complete(runtime, run, judge, result)
    row = next(row for row in runtime.runs[run]["budget"].records
               if row.get("provider") == "typesafe")
    assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"]
    assert runtime.runs[run]["status"] != "running"


def test_cancelled_jev_late_receipt_only_settles_cost(tmp_path):
    cfg = configuration("advisor")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    judge = receipt(runtime, run, step(runtime, run), "候选")
    runtime.handle({"op": "cancel", "runId": run})
    result = complete(runtime, run, judge, response(judge, "APPROVE"))
    assert result["action"] == "stop"
    assert runtime.runs[run]["status"] == "cancelled"
    assert next(row for row in runtime.runs[run]["budget"].records
                if row.get("provider") == "typesafe")["status"] == "billed"


def test_jev_sensitive_input_requires_explicit_trust(tmp_path):
    cfg = configuration("advisor")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    execution = step(runtime, run, messages=[{"role":"user","content":"查看 /Users/alice/private.txt"}])
    with pytest.raises(ValueError, match="Jev 判别输入不允许"):
        receipt(runtime, run, execution, "候选")
    assert not any(row.get("provider") == "typesafe" for row in runtime.runs[run]["budget"].records)


def test_jev_text_only_rejects_media_before_reservation(tmp_path):
    from refractrouter.jev_bridge import build_request
    cfg = configuration("advisor")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    request = {"contract": "advisor-local-review-v2", "messages": [
        {"role": "user", "content": [{"type": "image", "attachment": {"id": "i1"}}]}],
        "candidate": {"content": "描述"}, "events": []}
    with pytest.raises(ValueError, match="只支持文本判别"):
        build_request("advisor", request)
    assert not any(row.get("provider") == "typesafe" for row in runtime.runs[run]["budget"].records)


def test_stage_jev_uses_new_tool_evidence_and_records_cost(tmp_path):
    from tests.test_stage_hybrid import messages
    cfg = configuration("stage")
    cfg["stage"] = {"mode": "hybrid", "allowExperimental": True,
                    "judge": {"type": "jev"}, "judgeTimeoutMs": 30000}
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "stage", cfg)
    first = step(runtime, run, messages(0))
    assert first["model"]["id"] == "small"
    receipt(runtime, run, first)
    judge = step(runtime, run, messages(1))
    assert judge["action"] == "jev", (judge, runtime.runs[run]["decisions"])
    answers = {}
    for key, definition in judge["payload"]["questions"].items():
        choice = "CAPABLE" if key == "route" else "PROGRESS"
        choices = definition["criteria"]
        answers[key] = {"type": "choice", "choice": choice,
                        "probabilities": {item: .96 if item == choice else .04/(len(choices)-1)
                                          for item in choices}, "confidence": .9}
    selected = complete(runtime, run, judge, {"model": JEV_MODEL, "answers": answers,
        "usage": {"input_tokens": 500, "output_tokens": 30}})
    assert selected["model"]["id"] == "large"
    record = runtime.runs[run]["state"]["stageHybrid"]["localRecords"][-1]
    assert record["status"] == "billed" and record["apiCost"] > 0
    assert runtime.runs[run]["decisions"][-1]["decision"]["backend"] == "jev"


def test_stage_jev_protects_judge_and_either_execution_route(tmp_path):
    from tests.test_stage_hybrid import messages
    cfg = configuration("stage")
    cfg["stage"] = {"mode": "hybrid", "allowExperimental": True,
                    "judge": {"type": "jev"}, "judgeTimeoutMs": 30000}
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "stage", cfg)
    first = step(runtime, run, messages(0))
    receipt(runtime, run, first)
    remaining = runtime.runs[run]["budget"].remaining("CNY")
    tools = [{"name": "read", "description": "read", "parameters": {"type": "object"}}]
    bounds = [runtime._cost_bound(runtime._resolve_model(runtime.runs[run], model_id=model_id),
              messages(1), tools, None)
              for model_id in ("small", "large")]
    runtime.runs[run]["budget"].ledgers["CNY"].limits["production"] -= remaining - max(bounds) - .00001
    with pytest.raises(ValueError, match="Stage Jev 判别前"):
        step(runtime, run, messages(1))
    assert not any(row.get("provider") == "typesafe" for row in runtime.runs[run]["budget"].records)


def test_composite_jev_task_then_stage_without_reclassifying(tmp_path):
    from tests.test_stage_hybrid import messages
    cfg = configuration("composite")
    cfg["composite"] = {"pool": ["small", "large"], "takeover": "large",
        "judge": {"type": "jev"}, "threshold": .8, "maxInputChars": 12000,
        "stage": {"mode": "hybrid", "allowExperimental": True,
                  "judge": {"type": "jev"}, "judgeTimeoutMs": 30000}}
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "composite", cfg)
    task_judge = step(runtime, run, messages(0))
    assert task_judge["action"] == "jev"
    initial = complete(runtime, run, task_judge, response(task_judge, "small"))
    assert initial["model"]["id"] == "small"
    receipt(runtime, run, initial)
    stage_judge = step(runtime, run, messages(1))
    assert stage_judge["action"] == "jev"
    assert set(stage_judge["payload"]["questions"]) == {"progress", "route"}
    answers = {}
    for key, definition in stage_judge["payload"]["questions"].items():
        choice = "CAPABLE" if key == "route" else "PROGRESS"
        options = definition["criteria"]
        answers[key] = {"type": "choice", "choice": choice,
            "probabilities": {option: .96 if option == choice else .04/(len(options)-1)
                              for option in options}, "confidence": .9}
    selected = complete(runtime, run, stage_judge, {"model": JEV_MODEL,
        "answers": answers, "usage": {"input_tokens": 500, "output_tokens": 30}})
    assert selected["model"]["id"] == "large"
    assert len([row for row in runtime.runs[run]["budget"].records
                if row.get("provider") == "typesafe"]) == 2


def test_jev_invalid_choice_is_billed_but_never_released(tmp_path):
    cfg = configuration("advisor")
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", cfg)
    judge = receipt(runtime, run, step(runtime, run), "候选")
    invalid = response(judge, "APPROVE")
    invalid["answers"]["review"]["choice"] = "UNKNOWN"
    with pytest.raises(ValueError, match="判别答案无效"):
        complete(runtime, run, judge, invalid)
    row = next(row for row in runtime.runs[run]["budget"].records
               if row.get("provider") == "typesafe")
    assert row["status"] == "billed"
    assert runtime.runs[run]["status"] == "jev-invalid-answer"
