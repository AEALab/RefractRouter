import json
from pathlib import Path

from experiments.evaluate_advisor_judge import summarize
from experiments.preflight_advisor_acceptance import preflight
from refractrouter.advisor_decision import decision_request, llm_messages, parse_decision


ROOT = Path(__file__).resolve().parents[1]


def test_frozen_advisor_suite_has_four_multilingual_groups_and_paired_rechecks():
    suite = json.loads((ROOT / "data/benchmarks/advisor-judge-v1.json").read_text())
    assert suite["schemaVersion"] == "advisor-judge-suite-v1"
    assert len(suite["cases"]) == 24
    for category in ("qualified", "defect", "insufficient", "recheck"):
        rows = [case for case in suite["cases"] if case["category"] == category]
        assert len(rows) == 6
        assert {case["language"] for case in rows} == {"zh", "en", "mixed"}
    rechecks = [case for case in suite["cases"] if case["category"] == "recheck"]
    assert {case["pairId"] for case in rechecks} == {"requirement", "evidence", "format"}
    for pair in {case["pairId"] for case in rechecks}:
        assert {case["expected"] for case in rechecks if case["pairId"] == pair} == {"APPROVE", "REDO"}


def test_advisor_preflight_is_zero_call_and_within_existing_authorization():
    row = preflight()
    assert row["realModelCalls"] == 0
    assert row["callPlan"]["maximumModelCalls"] == 42
    assert row["costUpper"]["maximumIncludingPriorAfp"] <= 2000
    assert row["limits"]["httpRetries"] == 0
    assert row["limits"]["delegation"] is False


def test_advisor_llm_contract_is_strict_and_carries_recheck_feedback():
    request = decision_request([{"role": "user", "content": "返回 JSON"}], [],
        {"content": "修订", "toolCalls": []}, .8, review_count=2,
        previous_feedback="只能输出 JSON")
    assert json.loads(llm_messages(request)[1]["content"])["previousFeedback"] == "只能输出 JSON"
    assert parse_decision({"verdict": "APPROVE"})["verdict"] == "APPROVE"
    for invalid in ({"verdict": "REDO"}, {"verdict": "APPROVE", "feedback": "多余"},
                    {"verdict": "APPROVE", "extra": True}):
        try:
            parse_decision(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("无效审核输出必须停止")


def test_advisor_release_gate_does_not_hide_local_quality_failure():
    suite = {"checkpoint": "local", "revision": "r", "threshold": .8}
    rows = []
    for category, expected, outcome in (
        ("qualified", "APPROVE", "UNRESOLVED"),
        ("defect", "REDO", "REDO"),
        ("insufficient", "UNRESOLVED", "UNRESOLVED"),
        ("recheck", "APPROVE", "UNRESOLVED"),
    ):
        rows.extend({"category": category, "expected": expected, "outcome": outcome,
                     "matched": expected == outcome} for _ in range(6))
    report = summarize(suite, rows, cases=Path("fixture.json"), cold_start_ms=1)
    assert report["defectsApproved"] == 0
    assert report["qualifiedApproved"] == 0
    assert report["dailyUseAccepted"] is False
