"""任务结果追加日志；只存候选身份、反馈和调用引用，不复制费用账本。

访问范围由接入层认证后传入。哈希链检出意外篡改，不是对本机管理员的签名认证。
"""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3


VERSION = "task-outcome-event-v1"
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
SHA = re.compile(r"[0-9a-f]{64}")
STATUSES = {"candidate": {"generated"}, "delivery": {"accepted", "discarded", "unknown"},
            "feedback": {"accepted", "needs_revision", "rejected", "unknown"},
            "call-reference": {"known", "unknown"}}
ZERO = "0" * 64


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def key(value):
    if type(value) is not str or KEY.fullmatch(value) is None:
        raise ValueError("结果日志身份无效")


def validate_event(event):
    fields = {"schemaVersion", "eventId", "kind", "source", "actor", "candidateId", "candidateSha256",
              "status", "supersedes", "callIds", "artifactSha256", "criteriaVersion", "reasonCode"}
    if type(event) is not dict or set(event) != fields or event["schemaVersion"] != VERSION:
        raise ValueError("结果事件版本或字段无效")
    for name in ("eventId", "actor", "criteriaVersion", "reasonCode"):
        key(event[name])
    kind = event["kind"]
    if type(kind) is not str or kind not in STATUSES or type(event["status"]) is not str or event["status"] not in STATUSES[kind]:
        raise ValueError("结果事件类型或状态无效")
    sources = {"user", "tool", "model-review", "hidden-evaluation"} if kind == "feedback" else {"router"}
    if type(event["source"]) is not str or event["source"] not in sources:
        raise ValueError("结果事件来源不符合用途")
    if kind == "call-reference":
        if event["candidateId"] is not None or event["candidateSha256"] is not None:
            raise ValueError("调用引用不得伪装为候选")
    else:
        key(event["candidateId"])
        if type(event["candidateSha256"]) is not str or SHA.fullmatch(event["candidateSha256"]) is None:
            raise ValueError("缺少精确候选哈希")
    if event["supersedes"] is not None:
        key(event["supersedes"])
        if kind != "feedback":
            raise ValueError("只有反馈可以显式替代旧反馈")
    for field, validator in (("callIds", KEY), ("artifactSha256", SHA)):
        values = event[field]
        if (type(values) is not list or len(values) > 10000
                or any(type(value) is not str or validator.fullmatch(value) is None for value in values)
                or len(values) != len(set(values))):
            raise ValueError("引用列表无效或重复")
    if kind in {"candidate", "call-reference"} and not event["callIds"]:
        raise ValueError("候选及调用事件必须绑定实际调用身份")
    return json.loads(encoded(event))


class TaskOutcomeJournal:
    def __init__(self, root):
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "outcomes.sqlite3"
        if self.path.is_symlink():
            raise ValueError("结果日志不能是符号链接")
        # 首次创建与重新打开分开；文件锁同时覆盖跨线程、跨进程的初始化。
        lock_fd = os.open(root / ".outcomes-init.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(lock_fd, "r+b") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            existed = self.path.exists()
            if not existed and guard.read():
                raise ValueError("结果日志数据库缺失；禁止自动重建历史")
            if not existed:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            with closing(sqlite3.connect(self.path, isolation_level=None)) as db:
                if existed:
                    self._schema(db)
                else:
                    db.execute("PRAGMA journal_mode=WAL")
                    db.execute("BEGIN IMMEDIATE")
                    self._initialize(db)
                    db.execute("PRAGMA user_version=1")
                    db.execute("COMMIT")
            guard.seek(0)
            guard.write(VERSION.encode())
            guard.flush()
            os.fsync(guard.fileno())
        os.chmod(self.path, 0o600)

    @staticmethod
    def _initialize(db):
        db.execute("CREATE TABLE events (scope TEXT, task TEXT, seq INTEGER, "
                   "event_id TEXT, payload TEXT, created_at TEXT, previous_hash TEXT, event_hash TEXT, "
                   "PRIMARY KEY(scope,task,seq), UNIQUE(scope,task,event_id))")
        db.execute("CREATE TABLE heads (scope TEXT, task TEXT, seq INTEGER, "
                   "event_hash TEXT, PRIMARY KEY(scope,task))")
        db.execute("CREATE TABLE deleted (scope TEXT, task TEXT, previous_hash TEXT, "
                   "event_count INTEGER, deleted_at TEXT, PRIMARY KEY(scope,task))")

    @staticmethod
    def _schema(db):
        columns = {"events": ["scope", "task", "seq", "event_id", "payload", "created_at", "previous_hash", "event_hash"],
                   "heads": ["scope", "task", "seq", "event_hash"],
                   "deleted": ["scope", "task", "previous_hash", "event_count", "deleted_at"]}
        if db.execute("PRAGMA user_version").fetchone()[0] != 1 or any(
                [r[1] for r in db.execute(f"PRAGMA table_info({name})")] != fields
                for name, fields in columns.items()):
            raise ValueError("结果日志结构损坏或版本不受支持；禁止自动重建")

    @contextmanager
    def _transaction(self, *, write=True):
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            self._schema(db)
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _read(db, scope, task):
        rows = db.execute("SELECT * FROM events WHERE scope=? AND task=? ORDER BY seq", (scope, task)).fetchall()
        head = db.execute("SELECT * FROM heads WHERE scope=? AND task=?", (scope, task)).fetchone()
        previous, result = ZERO, []
        for seq, row in enumerate(rows, 1):
            event = validate_event(json.loads(row["payload"]))
            expected = digest({"scope": scope, "task": task, "seq": seq, "event": event,
                               "createdAt": row["created_at"], "previousHash": previous})
            if (row["seq"] != seq or row["event_id"] != event["eventId"]
                    or row["previous_hash"] != previous or row["event_hash"] != expected):
                raise ValueError("结果日志哈希链损坏，不能继续追加")
            result.append({"sequence": seq, "createdAt": row["created_at"], "hash": expected,
                           "previousHash": previous, "event": event})
            previous = expected
        if ((head is None) != (not rows)
                or head is not None and (head["seq"] != len(rows) or head["event_hash"] != previous)):
            raise ValueError("结果日志头或尾记录不完整")
        return result

    def read(self, scope, task):
        key(scope)
        key(task)
        with self._transaction(write=False) as db:
            return self._read(db, scope, task)

    def snapshot(self, scope, task):
        key(scope)
        key(task)
        with self._transaction(write=False) as db:
            rows = self._read(db, scope, task)
            deleted = db.execute("SELECT * FROM deleted WHERE scope=? AND task=?", (scope, task)).fetchone()
            return {"events": rows, "head": rows[-1]["hash"] if rows else ZERO,
                    "deleted": dict(deleted) if deleted else None}

    def delete(self, scope, task, expected_head):
        """只删除此日志的候选/反馈元数据；不触碰原始财务证据，不允许重新生成。"""
        key(scope)
        key(task)
        with self._transaction() as db:
            old = db.execute("SELECT * FROM deleted WHERE scope=? AND task=?", (scope, task)).fetchone()
            if old:
                if old["previous_hash"] != expected_head:
                    raise ValueError("删除确认与原日志不符")
                return dict(old)
            history = self._read(db, scope, task)
            if not history or history[-1]["hash"] != expected_head:
                raise ValueError("删除确认已过期或日志为空")
            stamp = datetime.now(timezone.utc).isoformat()
            db.execute("INSERT INTO deleted VALUES (?,?,?,?,?)", (scope, task, expected_head, len(history), stamp))
            db.execute("DELETE FROM events WHERE scope=? AND task=?", (scope, task))
            db.execute("DELETE FROM heads WHERE scope=? AND task=?", (scope, task))
            return {"scope": scope, "task": task, "previous_hash": expected_head,
                    "event_count": len(history), "deleted_at": stamp}

    def append(self, scope, task, event):
        return self.append_many(scope, task, [event])[0]

    def append_many(self, scope, task, events):
        """一次同步只校验一次历史并原子追加，避免逐个事件重读整条链。"""
        key(scope)
        key(task)
        events = [validate_event(event) for event in events]
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM deleted WHERE scope=? AND task=?", (scope, task)).fetchone():
                raise ValueError("结果元数据已删除，不能自动恢复或追加")
            history = self._read(db, scope, task)
            known = {row["event"]["eventId"]: row for row in history}
            candidates = {row["event"]["candidateId"]: row["event"] for row in history
                          if row["event"]["kind"] == "candidate"}
            replaced = {row["event"]["supersedes"] for row in history if row["event"]["supersedes"]}
            result = []
            for event in events:
                old = known.get(event["eventId"])
                if old:
                    if old["event"] != event:
                        raise ValueError("同一事件身份的矛盾重放")
                    result.append(old)
                    continue
                if event["kind"] == "candidate":
                    if event["candidateId"] in candidates:
                        raise ValueError("候选版本不能改写；必须创建新身份")
                elif event["kind"] in {"delivery", "feedback"}:
                    candidate = candidates.get(event["candidateId"])
                    if candidate is None or candidate["candidateSha256"] != event["candidateSha256"]:
                        raise ValueError("候选版本或哈希不属于当前任务")
                if event["supersedes"]:
                    previous = known.get(event["supersedes"], {}).get("event")
                    if (previous is None or previous["kind"] != "feedback"
                        or any(previous[field] != event[field] for field in
                               ("source", "actor", "candidateId", "candidateSha256", "criteriaVersion"))
                        or event["supersedes"] in replaced):
                        raise ValueError("反馈替代目标无效、跨来源/候选或已被替代")
                    replaced.add(event["supersedes"])
                sequence = len(history) + 1
                parent = history[-1]["hash"] if history else ZERO
                created = datetime.now(timezone.utc).isoformat()
                hashed = digest({"scope": scope, "task": task, "seq": sequence, "event": event,
                                 "createdAt": created, "previousHash": parent})
                db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                           (scope, task, sequence, event["eventId"], encoded(event), created, parent, hashed))
                db.execute("INSERT INTO heads VALUES (?,?,?,?) ON CONFLICT(scope,task) DO UPDATE SET "
                           "seq=excluded.seq,event_hash=excluded.event_hash", (scope, task, sequence, hashed))
                row = {"sequence": sequence, "createdAt": created, "hash": hashed,
                       "previousHash": parent, "event": event}
                known[event["eventId"]] = row
                if event["kind"] == "candidate":
                    candidates[event["candidateId"]] = event
                history.append(row)
                result.append(row)
            return result
