"""采样控制、并发 HTTP 证据绑定和无挑选接续；全部使用本地模拟响应。"""
from copy import deepcopy
import json
from pathlib import Path
from threading import Barrier, RLock

import pytest

import refractrouter.node_tool_study as study
from refractrouter.compact_planning import COMPACT_PLANNER_SYSTEM
from refractrouter.node_study_transport import StudyWireTransport
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse
from experiments.audit_node_tool_pilot import audit_case


class Backend:
    def __init__(self):
        self.lock, self.barrier, self.calls = RLock(), Barrier(2), []

    def post(self, url, headers, body, timeout_seconds):
        payload = json.loads(body)
        with self.lock:
            self.calls.append(payload)
            number = len(self.calls)
        system = payload["input"][0]["content"]
        if system == COMPACT_PLANNER_SYSTEM:
            content = json.dumps({"reason": "禁网并发绑定测试", "nodes": [
                {"id": "alpha", "type": "synthesis", "job": "分析第一项材料", "parents": [], "difficulty": "medium", "risk": "medium"},
                {"id": "beta", "type": "verification", "job": "核对第二项材料", "parents": [], "difficulty": "medium", "risk": "medium"},
                {"id": "answer", "type": "generation", "job": "完整交付", "parents": ["alpha", "beta"], "difficulty": "medium", "risk": "medium"}]})
        elif system in study.PROMPTS.values():
            content = json.dumps({"answer": "本地模拟交付，不是质量证据", "findings": []})
        else:
            self.barrier.wait(timeout=5)
            content = "本地模拟分析，不进行网络调用。"
        data = {"id": "resp-" + str(number), "model": "deepseek-v4-flash-ga-260731", "status": "completed",
                "output": [{"type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": content}]}],
                "usage": {"input_tokens": 100, "output_tokens": 50,
                          "input_tokens_details": {"cached_tokens": 0},
                          "output_tokens_details": {"reasoning_tokens": 20}}}
        return TransportResponse(200, {"x-request-id": "request-" + str(number)}, json.dumps(data).encode())


def test_dag_sampling_matches_native_wire_and_parallel_receipts_stay_bound(tmp_path):
    backend = Backend()
    def factory(path):
        return OpenAICompatibleClient(transport=StudyWireTransport(path, backend=backend),
            environment={"CODEX_ARK_API_KEY": "offline-not-a-secret"}, max_retries=0, timeout_seconds=None)
    case = study.case_spec(study.load_tasks()[0][0], "dag", 1, "existing-contract")
    result = study.run_dag(case, tmp_path / "case", simulated=True, client=factory)
    assert result["status"] == "completed"
    assert result["execution"]["peak_running_nodes"] == 2
    assert len(backend.calls) == len(result["calls"]) == 4
    native = json.loads(next((study.ROOT / "reports/node-tool-pilot-20261029-live-02").glob("*/wire/*-request.json")).read_text())
    for row in result["calls"]:
        prefix = tmp_path / "case" / row["wire_evidence_prefix"]
        request = json.loads(Path(str(prefix) + "-request.json").read_text())
        receipt = json.loads(Path(str(prefix) + "-receipt.json").read_text())
        for key in ("model", "temperature", "max_output_tokens", "top_p", "reasoning"):
            assert request.get(key) == native.get(key)
        assert receipt["requestId"] == row["request_id"]
        assert receipt["providerReportedModel"] == "deepseek-v4-flash-ga-260731"
    assert all("offline-not-a-secret" not in p.read_text() for p in (tmp_path / "case/wire").iterdir())
    row = {**result, "phase": "comparison", "arm": "dag", "factStatus": "fail", "checks": [],
           "chargedOrReserved": sum(c["charged"] for c in result["calls"])}
    audited = audit_case(row, tmp_path / "case", study.prepare())
    assert audited["errors"] == []
    assert all(r["requestedTemperature"] == 0 and r["providerReportedModel"] == "deepseek-v4-flash-ga-260731"
               for r in audited["receipts"])


def test_wire_control_rejects_missing_or_boolean_temperature_before_backend(tmp_path):
    backend = Backend()
    transport = StudyWireTransport(tmp_path / "wire", backend=backend)
    for temperature in (None, False, .7):
        payload = {"model": "deepseek-v4-flash", "max_output_tokens": 384000, "temperature": temperature}
        with pytest.raises(ValueError, match="冻结控制"):
            transport.post("https://ark.cn-beijing.volces.com/api/plan/v3/responses", {}, json.dumps(payload).encode(), None)
    assert backend.calls == []


def test_reuse_keeps_failed_native_outcome_and_excludes_uncontrolled_dag(tmp_path, monkeypatch):
    expected = study.prepare()
    task = study.load_tasks()[0][0]
    case = study.case_spec(task, "node-as-tool", 1, "explicit-verification")
    dag = study.case_spec(task, "dag", 1, "explicit-verification")
    old = tmp_path / "old"; (old / "cases").mkdir(parents=True)
    prior = deepcopy(expected); prior.pop("sampling")
    study.write(old / "frozen.json", prior)
    row = {"runId": case["runId"], "phase": "comparison", "arm": "node-as-tool", "status": "completed",
           "costKnown": True, "factStatus": "fail", "qualityError": "原始格式不通过",
           "calls": [{"status": "billed", "charged": .1}]}
    study.write(old / "summary.json", {"status": "stopped-implementation-changed", "simulated": False,
        "protocolSha256": "old", "runs": [row, {**row, "runId": dag["runId"], "arm": "dag"}]})
    study.write(old / "cases" / (case["runId"] + ".json"), case)
    wire = old / case["runId"] / "wire"; wire.mkdir(parents=True)
    study.write(wire / "001-request.json", {"model": "deepseek-v4-flash", "temperature": 0, "max_output_tokens": 384000})
    monkeypatch.setattr(study, "ROOT", tmp_path)
    _, entries, excluded = study.resumed_optimization([old / "summary.json"], expected)
    assert [e["runId"] for e in entries] == [case["runId"]]
    assert [e["runId"] for e in excluded] == [dag["runId"]]
    reused = study.reused_rows({"reusedSamples": entries})
    assert reused[0]["factStatus"] == "fail" and reused[0]["qualityError"] == "原始格式不通过"
    study.write(wire / "001-request.json", {"model": "deepseek-v4-flash", "temperature": .7, "max_output_tokens": 384000})
    with pytest.raises(ValueError, match="temperature"):
        study.resumed_optimization([old / "summary.json"], expected)


def test_imported_comparison_outcomes_cannot_tune_the_baseline_prompt():
    rows = [{"phase": "prompt-audit", "promptId": "existing-contract", "factStatus": "fail",
             "checks": [{"status": "fail"}], "chargedOrReserved": .1},
            {"phase": "prompt-audit", "promptId": "explicit-verification", "factStatus": "pass",
             "checks": [{"status": "pass"}], "chargedOrReserved": .2}]
    rows += [{"phase": "comparison", "promptId": "existing-contract", "factStatus": "pass",
              "checks": [], "chargedOrReserved": .01}] * 20
    chosen, ranking = study.select_prompt(rows)
    assert chosen == "explicit-verification"
    assert next(r for r in ranking if r[-1] == "existing-contract")[0] == 0
