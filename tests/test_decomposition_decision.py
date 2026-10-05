"""自动路由本地拆分判别合同；全部使用确定性夹具。"""
from copy import deepcopy

import pytest

from refractrouter.decomposition_decision import (build_request, parse_answer,
                                                   validate_evidence)
from refractrouter.planning_decision import LayaDecisionAdapter, LocalDecisionCapacityError
from refractrouter.planning_runtime import PlanningRuntime


def judge_config(tmp_path):
    return {"type": "local-decision", "adapter": "laya-mlx",
            "modelPath": str(tmp_path / "laya"),
            "sourceModel": "aac6fef/laya-multilingual-mlx", "revision": "test",
            "device": "cpu", "dtype": "float16", "method": "choice-v2"}


def test_request_binds_full_input_but_only_exposes_bounded_structure_state():
    request = build_request("继续把上述两个方案分别核对", "很长的完整宿主上下文")
    assert request["state"] == {"task": "继续把上述两个方案分别核对",
                                "contextDependency": "referenced", "contextAvailable": True}
    assert "很长" not in str(request["state"])
    changed = deepcopy(request)
    changed.update(parse_answer({"choice": "SEPARABLE", "probabilities": {
        "SEPARABLE": .9, "COUPLED": .05, "UNKNOWN": .05}}, threshold=.65))
    changed.update(model="fixture", revision="test")
    assert validate_evidence(changed, "继续把上述两个方案分别核对", "很长的完整宿主上下文")["verdict"] == "SEPARABLE"
    with pytest.raises(ValueError, match="输入已改变"):
        validate_evidence(changed, "不同任务", "很长的完整宿主上下文")
    stale = {**changed, "ruleVersion": "automatic-decomposition-hybrid-v1"}
    with pytest.raises(ValueError, match="规则版本不兼容"):
        validate_evidence(stale, "继续把上述两个方案分别核对", "很长的完整宿主上下文")


def test_low_confidence_becomes_unknown_without_rewriting_raw_answer():
    result = parse_answer({"choice": "COUPLED", "probabilities": {
        "SEPARABLE": .25, "COUPLED": .55, "UNKNOWN": .2}}, threshold=.65)
    assert result["verdict"] == "UNKNOWN"
    assert result["rawVerdict"] == "COUPLED" and result["confidence"] == .55


def test_laya_adapter_batches_two_noul_questions_and_preserves_provenance(monkeypatch):
    class Agent:
        batch_size = 16
        def predict(self, state, questions):
            assert state["task"] == "分别核对两个独立来源"
            assert list(questions) == ["requires_previous_output", "can_start_independently"]
            return {"model": "laya-fixture", "usage": {"input_tokens": 20},
                    "answers": {"requires_previous_output": {"noul": .05},
                                "can_start_independently": {"noul": .91}}}

    adapter = object.__new__(LayaDecisionAdapter)
    adapter.agent, adapter.model, adapter.cold_start_ms = Agent(), "laya-fixture", 12
    monkeypatch.setattr(adapter, "_ensure_complete", lambda _state, _questions: None)
    request = build_request("分别核对两个独立来源", "")
    result = adapter.decide_decomposition(request)
    assert result.payload["verdict"] == "SEPARABLE"
    assert result.payload["inputSha256"] == request["inputSha256"]
    assert result.usage["questions"] == 2 and result.usage["forwards"] == 1


def test_runtime_uses_loaded_service_and_reports_queue_separately(tmp_path):
    class Service:
        def call(self, operation, key, config, *, request=None, timeout_ms=30000):
            assert operation == "decomposition" and request["contract"] == "decomposition-decision-v1"
            assert timeout_ms == 1200 and key
            return {"payload": {"contract": request["contract"],
                    "ruleVersion": request["ruleVersion"], "inputSha256": request["inputSha256"],
                    "verdict": "COUPLED", "rawVerdict": "COUPLED", "confidence": .82,
                    "probabilities": {"SEPARABLE": .08, "COUPLED": .82, "UNKNOWN": .1},
                    "experimental": True}, "model": "fixture", "coldStartMs": None,
                    "latencyMs": 2, "usage": {"questions": 1, "forwards": 1}}

    runtime = PlanningRuntime(tmp_path)
    runtime.local_service = Service()
    result = runtime.handle({"op": "decomposition-decision", "judge": judge_config(tmp_path),
                             "task": "逐步修复同一个缺陷", "context": "", "threshold": .65,
                             "timeoutMs": 1200, "maxInputBytes": 4096})
    assert result["verdict"] == "COUPLED" and result["model"] == "fixture"
    assert result["latencyMs"] == 2 and result["queueMs"] >= 0


def test_context_reference_and_input_capacity_preserve_rules_without_dispatch(tmp_path):
    class Service:
        def call(self, *args, **kwargs):
            raise AssertionError("这些输入不应送入本地 Judge")

    runtime = PlanningRuntime(tmp_path)
    runtime.local_service = Service()
    base = {"op": "decomposition-decision", "judge": judge_config(tmp_path),
            "context": "前文含有需要的细节", "threshold": .65,
            "timeoutMs": 1200, "maxInputBytes": 1024}
    referenced = runtime.handle({**base, "task": "继续处理刚才的问题"})
    assert referenced["verdict"] == "UNKNOWN"
    assert referenced["reason"] == "context-dependent"
    assert referenced["usage"]["forwards"] == 0
    long_input = runtime.handle({**base, "task": "核对资料 " * 200})
    assert long_input["verdict"] == "UNKNOWN"
    assert long_input["reason"] == "input-too-long"


def test_in_task_pronoun_does_not_skip_decomposition_judge():
    from refractrouter.decomposition_decision import build_request
    task = "先调用工具取得数值，再根据实际结果计算它的两倍。"
    assert build_request(task, "")["state"]["contextDependency"] == "standalone"


def test_tokenizer_capacity_preserves_rules_after_dispatch(tmp_path):
    class Service:
        def call(self, operation, key, config, *, request, timeout_ms):
            raise LocalDecisionCapacityError("本地问题超过 tokenizer 容量")

    runtime = PlanningRuntime(tmp_path)
    runtime.local_service = Service()
    result = runtime.handle({"op": "decomposition-decision", "judge": judge_config(tmp_path),
                             "task": "分别整理两组互不依赖的资料", "context": "",
                             "timeoutMs": 1200})
    assert result["verdict"] == "UNKNOWN"
    assert result["reason"] == "token-capacity"
    assert result["usage"]["forwards"] is None
