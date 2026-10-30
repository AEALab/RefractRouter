"""结果视图接入真实运行时，模型全部模拟；反馈、删除不修改财务证据。"""
from copy import deepcopy
import json

import pytest

from refractrouter.agent_cli import main as cli
from refractrouter.planning_runtime import PlanningRuntime
from refractrouter.task_results import candidate_of
from tests.test_planning_routing import begin, step, receipt, configuration, advisor_gate_configuration


def query(runtime, run, op="outcome", **updates):
    identity = runtime.runs[run]["identity"] if run in runtime.runs else {"session": "a", "agent": "a", "turn": 1}
    return runtime.handle({"op": op, "runId": run, "identity": identity, **updates})


def feedback(candidate, eid="u1", **extra):
    return {"eventId": eid, "actor": "tester", "candidateId": candidate["candidateId"],
        "candidateSha256": candidate["candidateSha256"], "status": "accepted", "criteriaVersion": "manual-v1",
        "reasonCode": "user-accepted", "supersedes": None, **extra}


def test_success_restart_duplicate_and_user_acceptance_does_not_create_objective_truth(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    action = step(runtime, run)
    receipt(runtime, run, action, content="私有用户文本，只留原始证据")
    runtime.handle({"op": "end", "runId": run})
    view = query(runtime, run)
    assert view["costsByUnit"] == runtime.handle({"op": "query", "runId": run})["costsByUnit"]
    assert len(view["calls"]) == 1 and view["candidates"][0]["routerDisposition"] == "accepted"
    assert view["candidates"][0]["transportDelivery"] == "unknown"
    candidate = view["candidates"][0]
    request = feedback(candidate)
    accepted = query(runtime, run, "outcome-feedback", feedback=request)
    assert query(runtime, run, "outcome-feedback", feedback=request) == accepted
    assert accepted["candidates"][0]["acceptanceBySource"] == {
        "user": "accepted", "hidden-evaluation": "unknown", "tool": "unknown", "model-review": "unknown"}
    assert "私有用户文本" not in json.dumps(accepted, ensure_ascii=False)
    path = runtime.root / (run + ".json")
    before = path.read_bytes()
    reopened = PlanningRuntime(tmp_path)
    assert query(reopened, run) == accepted
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="不得自动"):
        reopened.begin({"identity": accepted["identity"], "config": configuration("static")})


def test_cancel_unknown_usage_still_links_dispatched_reserve_and_no_new_calls(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    action = step(runtime, run)
    runtime.handle({"op": "cancel", "runId": run})
    view = query(runtime, run)
    assert view["status"] == "cancelled"
    assert view["calls"][0]["status"] == "unknown-usage"
    assert view["calls"][0]["charged"] == view["calls"][0]["reserved"] > 0
    assert view["events"][0]["event"]["callIds"] == [action["callId"]]
    assert not view["candidates"]
    assert len(runtime.runs[run]["budget"].records) == 1


def test_failed_review_redo_and_new_candidate_keep_all_fees_and_do_not_inherit_feedback(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "advisor", config=advisor_gate_configuration())
    initial = step(runtime, run)
    judge = receipt(runtime, run, initial, content="旧候选")
    redo = receipt(runtime, run, judge, content=json.dumps({"verdict": "REDO", "feedback": "补充证据"}))
    second_judge = receipt(runtime, run, redo, content="新候选")
    receipt(runtime, run, second_judge, content=json.dumps({"verdict": "APPROVE"}))
    view = query(runtime, run)
    assert len(view["calls"]) == 4
    assert len(view["candidates"]) == 2
    old, new = view["candidates"]
    assert old["routerDisposition"] == "discarded" and old["acceptanceBySource"]["model-review"] == "needs_revision"
    assert new["routerDisposition"] == "accepted" and new["acceptanceBySource"]["model-review"] == "accepted"
    assert old["candidateSha256"] != new["candidateSha256"]
    total = sum(row["charged"] for row in view["calls"])
    assert total == pytest.approx(sum(row["production"] for row in view["costsByUnit"].values()))
    assert old["callIds"][0] in [c["call_id"] for c in view["calls"]]


def test_conflict_feedback_is_unknown_until_explicit_same_criteria_supersession(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run))
    candidate = query(runtime, run)["candidates"][0]
    query(runtime, run, "outcome-feedback", feedback=feedback(candidate))
    view = query(runtime, run, "outcome-feedback", feedback=feedback(candidate, "u2", status="rejected"))
    assert view["candidates"][0]["acceptanceBySource"]["user"] == "unknown"
    view = query(runtime, run, "outcome-feedback", feedback=feedback(candidate, "u3", status="rejected", supersedes="u1"))
    assert view["candidates"][0]["acceptanceBySource"]["user"] == "rejected"
    with pytest.raises(ValueError, match="字段"):
        query(runtime, run, "outcome-feedback", feedback={**feedback(candidate, "u4"), "source": "hidden-evaluation"})


def test_wrong_identity_cannot_read_write_or_touch_canonical_record(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run))
    path = runtime.root / (run + ".json")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="访问域"):
        query(runtime, run, identity={"session": "other", "agent": "b", "turn": 1})
    assert path.read_bytes() == before


def test_delete_metadata_is_terminal_scoped_and_preserves_financial_record(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run))
    with pytest.raises(ValueError, match="仍在执行"):
        query(runtime, run, "outcome-delete", expectedHead=query(runtime, run)["eventHead"])
    runtime.handle({"op": "end", "runId": run})
    view = query(runtime, run)
    path = runtime.root / (run + ".json")
    before = path.read_bytes()
    reopened = PlanningRuntime(tmp_path)
    deleted = query(reopened, run, "outcome-delete", expectedHead=view["eventHead"])
    assert deleted["metadataStatus"] == "deleted" and deleted["events"] == []
    assert deleted["costsByUnit"] == view["costsByUnit"]
    assert path.read_bytes() == before
    with pytest.raises(ValueError, match="已删除"):
        query(reopened, run, "outcome-feedback", feedback=feedback(view["candidates"][0]))
    assert query(PlanningRuntime(tmp_path), run)["metadataStatus"] == "deleted"


def test_cli_export_is_private_does_not_overwrite_and_does_not_spawn_models(tmp_path, capsys):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run))
    runtime.handle({"op": "end", "runId": run})
    args = tmp_path / "query.json"
    args.write_text(json.dumps({"op": "outcome-export", "runId": run, "identity": runtime.runs[run]["identity"]}))
    output = tmp_path / "export.json"
    argv = ["outcome", "--runs-dir", str(tmp_path), "--request-file", str(args), "--output", str(output)]
    assert cli(argv) == 0
    assert json.loads(output.read_text())["schemaVersion"] == "task-result-v1"
    assert output.stat().st_mode & 0o777 == 0o600
    assert cli(argv) != 0
    assert len(runtime.runs[run]["budget"].records) == 1


def test_late_cancel_receipt_settles_fee_without_releasing_candidate(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    action = step(runtime, run)
    runtime.handle({"op": "cancel", "runId": run})
    assert receipt(runtime, run, action)["action"] == "stop"
    view = query(runtime, run)
    assert view["calls"][0]["status"] == "billed"
    assert view["candidates"][0]["routerDisposition"] == "discarded"
    assert view["candidates"][0]["acceptanceBySource"]["user"] == "unknown"


def test_journal_failure_keeps_settled_fee_and_prevents_new_dispatch(tmp_path, monkeypatch):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    action = step(runtime, run)
    monkeypatch.setattr(runtime.task_results.journal, "append_many", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        receipt(runtime, run, action)
    assert runtime.runs[run]["status"] == "evidence-failed"
    assert runtime.runs[run]["budget"].records[0]["status"] == "billed"
    assert runtime.runs[run]["budget"].records[0]["charged"] > 0
    with pytest.raises(ValueError, match="停止"):
        step(runtime, run)
    saved = json.loads((runtime.root / (run + ".json")).read_text())
    assert saved["calls"][0]["status"] == "billed"
    assert len(saved["calls"]) == 1


def test_legacy_result_is_read_without_inventing_feedback_or_rewriting_evidence(tmp_path):
    runtime = PlanningRuntime(tmp_path / "new")
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run))
    record = runtime.handle({"op": "query", "runId": run})
    record.pop("resultSchemaVersion")
    record["status"] = "completed"
    old = PlanningRuntime(tmp_path / "old")
    old.root.mkdir(parents=True)
    path = old.root / (run + ".json")
    path.write_text(json.dumps(record))
    before = path.read_bytes()
    view = query(old, run)
    assert view["metadataStatus"] == "legacy-unknown" and view["candidates"] == []
    assert view["calls"][0]["charged"] == record["calls"][0]["charged"]
    assert path.read_bytes() == before


def test_required_host_tool_rejection_is_bound_to_candidate_as_tool_feedback(tmp_path):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    action = step(runtime, run, toolRequirements={"required": True, "tools": ["read"]},
                  taskToolEvidence=[], requireConfirmedToolEvidence=True)
    with pytest.raises(ValueError, match="明确工具要求"):
        receipt(runtime, run, action, content="声称已经读完")
    view = query(runtime, run)
    assert view["candidates"][0]["routerDisposition"] == "discarded"
    assert view["candidates"][0]["acceptanceBySource"]["tool"] == "rejected"
    assert view["candidates"][0]["acceptanceBySource"]["model-review"] == "unknown"
    assert view["calls"][0]["charged"] > 0


def test_cli_cannot_delete_an_idle_but_running_task_in_another_runtime(tmp_path, capsys):
    runtime = PlanningRuntime(tmp_path)
    run = begin(runtime, "static")
    receipt(runtime, run, step(runtime, run))
    view = query(runtime, run)
    path = runtime.root / (run + ".json")
    before = path.read_bytes()
    request = tmp_path / "delete.json"
    request.write_text(json.dumps({"op": "outcome-delete", "runId": run,
        "identity": view["identity"], "expectedHead": view["eventHead"]}))
    assert cli(["outcome", "--runs-dir", str(tmp_path), "--request-file", str(request)]) != 0
    assert "仍在执行" in capsys.readouterr().out
    assert path.read_bytes() == before
    assert query(runtime, run)["metadataStatus"] == "recorded"
    assert runtime.runs[run]["status"] == "running"
