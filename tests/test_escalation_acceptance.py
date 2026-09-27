import json
from pathlib import Path

from experiments.accept_escalation_routing import plan as dsh_plan
from experiments.preflight_escalation_acceptance import preflight
from refractrouter.escalation_decision import decision_request, llm_messages, parse_decision


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_escalation_judge_suite_is_balanced_and_multilingual():
    suite = json.loads((ROOT / "data/benchmarks/escalation-judge-v1.json").read_text())
    assert suite["schemaVersion"] == "escalation-judge-suite-v1"
    assert len(suite["cases"]) == 24
    for verdict in ("PROCEED", "DEFECT", "STALL", "UNCERTAIN"):
        rows = [case for case in suite["cases"] if case["expected"] == verdict]
        assert len(rows) == 6
        assert {case["language"] for case in rows} == {"zh", "en", "mixed"}


def test_escalation_preflight_is_zero_call_and_within_existing_authorization():
    row = preflight()
    assert row["realModelCalls"] == 0
    assert row["callPlan"]["maximumModelCalls"] == 42
    assert row["costUpper"]["maximumIncludingPriorAfp"] <= 2000
    assert row["limits"]["httpRetries"] == 0
    assert row["limits"]["delegation"] is False


def test_escalation_llm_contract_rejects_untrusted_evidence_reference():
    request = decision_request([{"role": "user", "content": "检查输出"}],
        [{"id": "e1", "tool": "bash", "status": "completed"}],
        {"content": "完成", "toolCalls": []}, "stop", .8)
    assert llm_messages(request)[0]["role"] == "system"
    try:
        parse_decision({"verdict": "PROCEED", "confidence": .9,
                        "evidenceIds": ["forged"], "reason": "完成"}, {"e1"}, .8)
    except ValueError as exc:
        assert "证据 ID" in str(exc)
    else:
        raise AssertionError("伪造证据引用必须被拒绝")


def test_escalation_dsh_acceptance_is_zero_call_and_bounded():
    config, row = dsh_plan()
    assert config["schemaVersion"] == "refractagent-planning-v4"
    assert config["escalation"]["initial"] != config["escalation"]["takeover"]
    assert row["realModelCalls"] == 0
    assert row["maximumModelCalls"] == 6
    assert row["maximumIncludingPriorAfp"] < row["authorizedCumulativeAfp"]
