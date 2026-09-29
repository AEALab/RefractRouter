from collections import Counter

from refractrouter.dsh_strategy_stability import (
    AUTHORIZED_AFP, STRATEGY_COUNTS, configuration, frozen_tasks, patch_text,
    preflight, verify_record,
)


def test_stability_matrix_has_larger_complex_strategy_cohorts():
    tasks = frozen_tasks()
    assert len(tasks) == 128
    assert Counter(row["strategy"] for row in tasks) == Counter(STRATEGY_COUNTS)
    assert len({row["id"] for row in tasks}) == len(tasks)
    assert STRATEGY_COUNTS["static"] > 10
    for strategy in ("stage", "composite", "advisor", "escalation"):
        assert STRATEGY_COUNTS[strategy] >= 2 * STRATEGY_COUNTS["static"]


def test_preflight_is_zero_call_and_bounded_by_authorization():
    result = preflight()
    assert result["realModelCalls"] == 0
    assert result["taskCount"] == 128
    assert result["limits"]["maximumProductionAfp"] <= AUTHORIZED_AFP
    assert result["limits"]["httpRetries"] == 0
    assert not result["limits"]["delegation"]
    assert len(result["preflightDigest"]) == 64


def test_all_six_strategies_are_available_and_patch_uses_global_install():
    config = configuration()
    for strategy in STRATEGY_COUNTS:
        patch = patch_text(config, strategy)
        assert f'"reasoningEffort":"rr:{strategy}"' in patch
        assert f'"defaultStrategy":"{strategy}"' in patch
        assert '"pythonExecutable":"refractagent"' in patch
        assert '"maxRetries":0' in patch
        assert "tool-subagent\n  disabled: true" in patch


def _record(strategy, reasons, purposes, *, tool_calls=0, state=None):
    calls = []
    for index, purpose in enumerate(purposes):
        calls.append({"purpose": purpose, "status": "billed", "actual_model": "m",
            "latency_ms": 1, "ttft_ms": 1 if index == 0 else None,
            "response": {"attempts": 1,
                "tool_calls": [{"id": "t"}] if index == 0 and tool_calls else []}})
    return {"runId": "r", "strategy": strategy, "status": "completed",
        "decisions": [{"reason": reason} for reason in reasons], "calls": calls,
        "state": state or {}, "costs": {"AFP": {"production": 1}}}


def test_verify_record_requires_strategy_specific_trace():
    task = next(row for row in frozen_tasks() if row["strategy"] == "static")
    good = verify_record(task, 0, task["expected"],
        _record("static", ["static-random-selected"], ["execute"]))
    assert good["success"]
    bad = verify_record(task, 0, task["expected"],
        _record("static", ["no-signal"], ["execute"]))
    assert not bad["success"] and "static-route-mismatch" in bad["issues"]
