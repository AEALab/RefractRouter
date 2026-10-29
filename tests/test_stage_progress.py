"""结构化进展反例；合成验收不证明模型能力或开放任务收益。"""
from copy import deepcopy

import pytest

from refractrouter.stage_progress import CHECK_VERSION, VERSION, compile_shadow, decide

TASK, SUITE = "a" * 64, "b" * 64


def configuration():
    return {"schemaVersion": VERSION, "holdTurns": 2, "stallConfirmations": 2,
            "checkers": [{"id": "tests", "revision": "frozen-r1", "suiteSha256": SUITE,
                          "assertionIds": ["A", "B"]}]}


def evidence(identifier, failed=("A",), snapshot="1", **changes):
    packet = {"schemaVersion": CHECK_VERSION, "taskSha256": TASK, "checkerId": "tests",
        "checkerRevision": "frozen-r1", "suiteSha256": SUITE, "snapshotSha256": snapshot * 64,
        "codeGeneration": int(snapshot, 16),
        "phase": "acceptance", "complete": True,
        "checks": [{"id": key, "status": "failed" if key in failed else "passed"} for key in ("A", "B")]}
    packet.update(changes)
    return {"id": identifier, "callId": identifier, "tool": "checker", "kind": "observe",
            "fingerprint": "same-command", "status": "completed", "validation": packet}


def run(events, state=None, config=None):
    return decide(events, state, config or configuration(), TASK)


def strong_state():
    state, _ = run([evidence("first")])
    state, decision = run([evidence("second")], state)
    assert decision["role"] == "capable"
    return state


def test_expected_red_green_tests_do_not_upgrade():
    state, _ = run([evidence("red1", phase="expected-red")])
    state, decision = run([evidence("red2", phase="expected-red")], state)
    assert decision["role"] == "efficient" and "normal-red-test" in decision["progress"]
    _, decision = run([evidence("green", failed=(), snapshot="2")], state)
    assert decision["role"] == "efficient"


def test_same_assertion_stall_upgrades_but_replay_cannot_add_failure():
    state, decision = run([evidence("first")])
    assert decision["role"] == "efficient"
    state, decision = run([evidence("first")], state)
    assert decision["evidenceIds"] == [] and decision["role"] == "efficient"
    _, decision = run([evidence("second")], state)
    assert decision["reason"] == "assertion-stall-upgrade"


def test_failure_set_shrink_is_progress_not_complete_acceptance():
    state, _ = run([evidence("first", failed=("A", "B"))])
    state, decision = run([evidence("shrunk", failed=("A",), snapshot="2")], state)
    assert "failure-set-shrunk" in decision["progress"] and decision["role"] == "efficient"
    state, _ = run([evidence("stalled", snapshot="2")], state)
    state, _ = run([], state)
    _, decision = run([evidence("still-failing", snapshot="3")], state)
    assert decision["role"] == "capable"


def test_hold_expiry_and_successful_write_do_not_restore_without_acceptance():
    state = strong_state()
    state, _ = run([], state)
    write = {"id": "write", "callId": "write", "tool": "write", "kind": "mutate",
             "status": "completed", "fingerprint": "write"}
    state, decision = run([write], state)
    assert decision["role"] == "capable"
    _, decision = run([], state)
    assert decision["reason"] == "no-new-acceptance-keep-capable"


def test_full_acceptance_requires_changed_snapshot_and_failure_can_recur():
    state = strong_state()
    state, _ = run([], state)
    state, decision = run([evidence("same-snapshot-green", failed=())], state)
    assert decision["role"] == "capable"
    state, decision = run([evidence("changed-green", failed=(), snapshot="2")], state)
    assert decision["role"] == "efficient"
    _, decision = run([evidence("regression", snapshot="3")], state)
    assert decision["role"] == "capable" and "failure-after-restore" in decision["progress"]


@pytest.mark.parametrize("change", [
    {"checkerRevision": "another"}, {"suiteSha256": "d" * 64}, {"taskSha256": "e" * 64},
    {"complete": False}, {"checks": [{"id": "A", "status": "passed"}]},
    {"checks": [{"id": "A", "status": "passed"}, {"id": "B", "status": "unknown"}]},
])
def test_missing_incomparable_or_unknown_checks_do_not_restore(change):
    state = strong_state()
    state, _ = run([], state)
    _, decision = run([evidence("invalid-green", failed=(), snapshot="2", **change)], state)
    assert decision["role"] == "capable"


@pytest.mark.parametrize("status", ["denied", "infrastructure", "unclassified-error", "unclassified", "unconfirmed"])
def test_environment_and_unknown_events_are_not_model_failure(status):
    first, second = evidence("one"), evidence("two")
    first["status"] = second["status"] = status
    _, decision = run([first, second])
    assert decision["role"] == "efficient"
    state = strong_state()
    state, _ = run([], state)
    first["validation"] = evidence("green", failed=(), snapshot="2")["validation"]
    _, decision = run([first], state)
    assert decision["role"] == "capable"


def test_different_failure_sets_are_not_repeated_failure():
    state, _ = run([evidence("one", failed=("A",))])
    _, decision = run([evidence("two", failed=("B",), snapshot="2")], state)
    assert decision["role"] == "efficient" and "different-failures-unknown" in decision["progress"]


def test_latest_complete_pass_resolves_earlier_failures_in_same_boundary():
    _, decision = run([evidence("one"), evidence("two"), evidence("green", failed=(), snapshot="2")])
    assert decision["role"] == "efficient"


def test_resolved_stall_cannot_upgrade_different_first_failure_in_same_boundary():
    _, decision = run([evidence("one"), evidence("two"), evidence("green", failed=(), snapshot="2"),
                       evidence("different-first-failure", failed=("B",), snapshot="3")])
    assert decision["role"] == "efficient"


def test_old_snapshot_arriving_late_cannot_restore_or_reupgrade():
    state, _ = run([evidence("old-green", failed=(), snapshot="1")])
    state, _ = run([evidence("one", snapshot="2"), evidence("two", snapshot="2")], state)
    state, _ = run([], state)
    state, decision = run([evidence("late-old-green", failed=(), snapshot="1")], state)
    assert decision["role"] == "capable" and "stale-code-generation" in decision["progress"]
    state, _ = run([evidence("new-green", failed=(), snapshot="3")], state)
    _, decision = run([evidence("late-old-failure", snapshot="1")], state)
    assert decision["role"] == "efficient"


def test_write_invalidates_old_generation_even_with_fresh_event_id():
    state = strong_state()
    state, _ = run([], state)
    write = {"id": "write", "callId": "write", "tool": "write", "kind": "mutate",
             "status": "completed", "fingerprint": "write"}
    _, decision = run([write, evidence("old-but-new-id", failed=())], state)
    assert decision["role"] == "capable" and "stale-code-generation" in decision["progress"]


def test_new_task_resets_strong_state_and_checker_history():
    state = strong_state()
    other_task = "f" * 64
    state, decision = decide([evidence("green", failed=(), snapshot="2", taskSha256=other_task)],
                             state, configuration(), other_task)
    assert decision["role"] == "efficient" and "task-context-reset" in decision["progress"]
    assert state["unresolved"] == {} and "first" not in state["seen"]


def test_all_checkers_must_pass_same_snapshot_before_restore():
    cfg = configuration()
    cfg["checkers"].append({**deepcopy(cfg["checkers"][0]), "id": "integration"})
    state, _ = run([evidence("one"), evidence("two")], config=cfg)
    state, _ = run([], state, cfg)
    state, decision = run([evidence("green", failed=(), snapshot="2")], state, cfg)
    assert decision["role"] == "capable"
    state, decision = run([evidence("other-old", failed=(), snapshot="3", checkerId="integration")], state, cfg)
    assert decision["role"] == "capable"
    _, decision = run([evidence("same", failed=(), snapshot="3")], state, cfg)
    assert decision["role"] == "efficient"


def test_checker_config_drift_and_same_event_mutation_are_rejected():
    cfg = configuration()
    state, _ = run([evidence("one")], config=cfg)
    cfg["checkers"][0]["revision"] = "changed"
    with pytest.raises(ValueError, match="漂移"):
        run([], state, cfg)
    with pytest.raises(ValueError, match="矛盾"):
        run([evidence("one", failed=())], state)
    cfg = configuration()
    cfg["checkers"][0]["assertionIds"].append("A")
    with pytest.raises(ValueError, match="不重复"):
        compile_shadow(cfg)


def runtime_configuration():
    from tests.test_planning_routing import configuration as base
    cfg = base()
    cfg.update(schemaVersion="refractagent-planning-v8", billingUnit="CNY", stageShadow=configuration())
    for model in cfg["models"]:
        model["billingUnit"] = "CNY"
    return cfg


def test_runtime_records_shadow_without_switching_actual_rule_or_adding_judge(tmp_path):
    from refractrouter.planning_runtime import PlanningRuntime
    from refractrouter.task_outcomes import digest
    from refractrouter.task_projection import summary
    from tests.test_planning_routing import begin, step, receipt
    runtime = PlanningRuntime(tmp_path)
    run_id = begin(runtime, config=runtime_configuration())
    action = step(runtime, run_id)
    assert action["model"]["id"] == "small"
    receipt(runtime, run_id, action)
    task_sha = digest(summary(runtime.runs[run_id]["state"]["currentTask"]))
    history = []
    for identifier in ("one", "two"):
        ev = evidence(identifier, taskSha256=task_sha)
        ev["status"] = "failed"
        history.append(ev)
        receipt(runtime, run_id, step(runtime, run_id, toolEvidence=history))
    receipt(runtime, run_id, step(runtime, run_id, toolEvidence=history))
    action = step(runtime, run_id, toolEvidence=history)
    # 原固定保持已经恢复小模型；影子认为没有新验收，不影响实际选择。
    assert action["model"]["id"] == "small"
    assert runtime.runs[run_id]["state"]["stageProgressShadow"]["role"] == "capable"
    receipt(runtime, run_id, action)
    runtime.handle({"op": "end", "runId": run_id})
    outcome = runtime.handle({"op": "outcome", "runId": run_id, "identity": runtime.runs[run_id]["identity"]})
    assert outcome["stageProgressShadow"]["actualSelectionChanged"] is False
    assert len(outcome["calls"]) == 5 and all(c["purpose"] == "execute" for c in outcome["calls"])


def test_stage_shadow_is_explicit_v8_rules_only_and_old_config_stays_disabled():
    from refractrouter.planning_config import compile_config
    from tests.test_planning_routing import configuration as base
    assert compile_config(base())["stage_shadow"] is None
    cfg = runtime_configuration()
    cfg["schemaVersion"] = "refractagent-planning-v7"
    with pytest.raises(ValueError, match="v8"):
        compile_config(cfg)
    cfg = runtime_configuration()
    cfg["defaultStrategy"] = "static"
    with pytest.raises(ValueError, match="独立规则 Stage"):
        compile_config(cfg)
