"""只重采可证明的输入字段误拒收；其他已结算失败原样保留，绝不补零或清账。"""
from copy import deepcopy
import json

import refractrouter.node_tool_study as study


def evidence(tmp_path):
    expected = study.prepare()
    task = study.load_tasks()[0][2]
    case = study.case_spec(task, "node-as-tool", 2, "explicit-verification")
    directory = tmp_path / "old"; (directory / "cases").mkdir(parents=True)
    core_path = directory / case["runId"] / "evidence/planning/core.json"
    core_path.parent.mkdir(parents=True)
    request = {"intent": "check", "task": "事件 p1 的金额为 100", "context": "按事件身份去重"}
    content = json.dumps({"artifact": "核对委派材料", "quotes": ["p1 的金额为 100", "按事件身份去重"], "limitations": []})
    calls = [{"call_id": "main", "purpose": "execute", "status": "billed", "charged": .1},
             {"call_id": "expert", "purpose": "node-tool", "status": "billed", "charged": .1,
              "finish_reason": "stop", "request_messages": [{"role": "system", "content": "专家"},
                  {"role": "user", "content": json.dumps(request)}], "response_output": content}]
    row = {"runId": case["runId"], "phase": "comparison", "arm": "node-as-tool", "taskId": task["task_id"],
           "repeat": 2, "promptId": "explicit-verification", "status": "failed", "factStatus": "not-evaluated",
           "failureKind": "model-output", "coreStatus": "node-output-invalid", "costKnown": True,
           "chargedOrReserved": .2, "calls": calls}
    core = {"timing": {"elapsedMs": 1000}, "nodeTools": {"invocations": [{"status": "failed", "modelCallId": "expert",
            "reason": "专家引文不是输入材料的逐字子串"}]}}
    study.write(core_path, core)
    old = deepcopy(expected); old["schema"] = "node-tool-three-arm-pilot-v4"; old.pop("quotePolicy")
    study.write(directory / "frozen.json", old)
    study.write(directory / "cases" / (case["runId"] + ".json"), case)
    source = directory / "summary.json"
    study.write(source, {"simulated": False, "status": "stopped-implementation-changed", "protocolSha256": "old",
                        "realModelCalls": 2, "actualOrReservedAfp": .2, "runs": [row]})
    wire = directory / case["runId"] / "wire"; wire.mkdir()
    for index in (1, 2):
        study.write(wire / f"{index:03}-request.json", {"model": "deepseek-v4-flash", "temperature": 0,
                                                      "max_output_tokens": 384000})
    return expected, source, row


def test_only_proven_quote_field_bug_is_diagnostic_and_original_cost_is_retained(tmp_path, monkeypatch):
    expected, source, row = evidence(tmp_path)
    monkeypatch.setattr(study, "ROOT", tmp_path)
    _, reused, excluded = study.resumed_optimization([source], expected)
    assert reused == [] and len(excluded) == 1
    proof = excluded[0]
    assert proof["kind"] == "quote-input-field" and proof["originalOutcome"]["status"] == "failed"
    assert proof["quoteSourcesUnderCorrection"][0]["inputFields"] == ["task"]
    assert proof["coreEvidenceSha256"] and proof["sourceSha256"]
    assert study.carry_in([source])[0]["actualOrReservedAfp"] == .2
    assert json.loads(source.read_text())["runs"][0] == row  # 不追改旧结果。


def test_genuine_model_output_failure_is_reused_unchanged_instead_of_retried(tmp_path, monkeypatch):
    expected, source, row = evidence(tmp_path)
    row["calls"][1]["response_output"] = json.dumps({"artifact": "输出", "quotes": ["输入不存在的句子"], "limitations": []})
    summary = json.loads(source.read_text()); summary["runs"] = [row]; study.write(source, summary)
    monkeypatch.setattr(study, "ROOT", tmp_path)
    _, reused, excluded = study.resumed_optimization([source], expected)
    assert excluded == [] and len(reused) == 1
    restored = study.reused_rows({"reusedSamples": reused})[0]
    assert restored["status"] == "failed" and restored["factStatus"] == "not-evaluated"
    assert restored["chargedOrReserved"] == .2 and restored["importedFrom"]["summary"]
