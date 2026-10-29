"""持久化、候选修订、反馈来源、范围隔离及损坏检测；无网络。"""
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from refractrouter.task_outcomes import TaskOutcomeJournal, VERSION


def event(identifier, kind="candidate", **updates):
    return {"schemaVersion": VERSION, "eventId": identifier, "kind": kind,
            "source": "user" if kind == "feedback" else "router", "actor": "actor-1",
            "candidateId": "candidate-1", "candidateSha256": "a" * 64,
            "status": {"candidate": "generated", "delivery": "accepted", "feedback": "accepted"}[kind],
            "supersedes": None, "callIds": ["call-1"], "artifactSha256": [],
            "criteriaVersion": "criteria-1", "reasonCode": "fixture", **updates}


def test_reopen_idempotence_and_conflicting_replay(tmp_path):
    journal = TaskOutcomeJournal(tmp_path)
    first = journal.append("scope-1", "task-1", event("event-1"))
    reopened = TaskOutcomeJournal(tmp_path)
    assert reopened.append("scope-1", "task-1", event("event-1")) == first
    assert reopened.read("scope-1", "task-1") == [first]
    with pytest.raises(ValueError, match="矛盾重放"):
        reopened.append("scope-1", "task-1", event("event-1", candidateSha256="b" * 64))


def test_candidate_revision_cannot_inherit_feedback_or_change_bytes(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    j.append("scope", "task", event("generated"))
    j.append("scope", "task", event("review", "feedback"))
    with pytest.raises(ValueError, match="候选版本不能改写"):
        j.append("scope", "task", event("new", candidateSha256="b" * 64))
    j.append("scope", "task", event("new", candidateId="candidate-2", candidateSha256="b" * 64))
    rows = j.read("scope", "task")
    assert len(rows) == 3
    assert not any(r["event"]["kind"] == "feedback" and r["event"]["candidateId"] == "candidate-2" for r in rows)


def test_feedback_sources_and_supersession_are_separate(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    j.append("scope", "task", event("generated"))
    j.append("scope", "task", event("user-accept", "feedback"))
    j.append("scope", "task", event("model-reject", "feedback", source="model-review", status="rejected"))
    with pytest.raises(ValueError, match="反馈替代目标"):
        j.append("scope", "task", event("wrong", "feedback", source="model-review", supersedes="user-accept"))
    j.append("scope", "task", event("user-revise", "feedback", status="needs_revision", supersedes="user-accept"))
    assert len(j.read("scope", "task")) == 4


def test_scope_task_and_candidate_hash_are_bound(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    j.append("scope", "task", event("generated"))
    assert j.read("other-scope", "task") == []
    assert j.read("scope", "other-task") == []
    for scope, task, payload in [("other-scope", "task", event("review", "feedback")),
                                 ("scope", "task", event("review", "feedback", candidateSha256="b" * 64))]:
        with pytest.raises(ValueError, match="不属于当前任务"):
            j.append(scope, task, payload)


def test_concurrent_duplicate_is_only_recorded_once(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda _: j.append("scope", "task", event("generated")), range(8)))
    assert all(row == rows[0] for row in rows)
    assert len(j.read("scope", "task")) == 1


@pytest.mark.parametrize("damage", ["payload", "delete-tail"])
def test_damage_stops_reads_and_new_events(tmp_path, damage):
    j = TaskOutcomeJournal(tmp_path)
    j.append("scope", "task", event("generated"))
    with sqlite3.connect(j.path) as db:
        if damage == "payload":
            db.execute("UPDATE events SET event_hash='changed'")
        else:
            db.execute("DELETE FROM events")
    with pytest.raises(ValueError, match="日志"):
        j.read("scope", "task")
    with pytest.raises(ValueError, match="日志"):
        j.append("scope", "task", event("new"))


def test_fee_payload_and_unknown_fields_rejected(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    with pytest.raises(ValueError, match="字段"):
        j.append("scope", "task", event("generated", cashCost=0))


@pytest.mark.parametrize("damage", ["empty-file", "missing-table", "missing-file"])
def test_corrupt_existing_database_is_not_recreated(tmp_path, damage):
    j = TaskOutcomeJournal(tmp_path)
    j.append("scope", "task", event("generated"))
    if damage == "empty-file":
        j.path.write_bytes(b"")
    elif damage == "missing-file":
        j.path.unlink()
    else:
        with sqlite3.connect(j.path) as db:
            db.execute("DROP TABLE events")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        TaskOutcomeJournal(tmp_path)


def test_reads_keep_committed_snapshot_while_other_task_has_write_lock(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    expected = j.append("scope", "task", event("generated"))
    with sqlite3.connect(j.path) as writer:
        writer.execute("BEGIN IMMEDIATE")
        assert j.read("scope", "task") == [expected]
        writer.rollback()


def test_independent_instances_can_initialize_concurrently(tmp_path):
    def initialize(_):
        j = TaskOutcomeJournal(tmp_path)
        return j.append("scope", "task", event("generated"))
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(initialize, range(32)))
    assert all(result == results[0] for result in results)


def test_feedback_versions_do_not_replace_each_other(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    j.append("scope", "task", event("generated"))
    j.append("scope", "task", event("review", "feedback"))
    with pytest.raises(ValueError, match="替代目标"):
        j.append("scope", "task", event("review-2", "feedback", criteriaVersion="criteria-2", supersedes="review"))


def test_delete_is_scoped_and_cannot_recreate_history(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    first = j.append("scope", "task", event("generated"))
    other = j.append("other", "task", event("generated"))
    with pytest.raises(ValueError, match="过期"):
        j.delete("scope", "task", "b" * 64)
    deletion = j.delete("scope", "task", first["hash"])
    assert j.delete("scope", "task", first["hash"]) == deletion
    assert j.snapshot("scope", "task")["deleted"] == deletion
    assert j.read("other", "task") == [other]
    with pytest.raises(ValueError, match="已删除"):
        j.append("scope", "task", event("generated"))


def test_batch_append_rolls_back_all_events_on_late_conflict(tmp_path):
    j = TaskOutcomeJournal(tmp_path)
    with pytest.raises(ValueError, match="候选版本"):
        j.append_many("scope", "task", [event("one"), event("two", candidateSha256="b" * 64)])
    assert j.read("scope", "task") == []
    assert j.snapshot("scope", "task")["head"] == "0" * 64
