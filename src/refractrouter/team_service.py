"""团队 Router 的静态身份、项目限制与 SQLite 持久任务存储。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
from threading import Condition
from typing import Iterable
from uuid import uuid4


TEAM_SCHEMA = 'refractrouter-service-v1'
TERMINAL_STATES = {'completed', 'failed', 'cancelled', 'recovery_required'}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or not all(
        character.isalnum() or character in '._-' for character in value
    ):
        raise ValueError(f'invalid {name}')
    return value


def _positive_integer(value: object, name: str, maximum: int) -> int:
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError(f'invalid {name}')
    return value


def _positive_number(value: object, name: str) -> float:
    if type(value) not in {int, float} or not 0 < float(value):
        raise ValueError(f'invalid {name}')
    return float(value)


@dataclass(frozen=True)
class TeamProject:
    id: str
    runs_dir: Path
    max_concurrent_tasks: int
    production_budget: float
    evaluation_budget: float
    timeout_ms: int
    max_output_tokens: int


@dataclass(frozen=True)
class TeamMember:
    id: str
    role: str
    token_env: str
    projects: tuple[str, ...]


@dataclass(frozen=True)
class TeamConfiguration:
    state_path: Path
    projects: dict[str, TeamProject]
    members: tuple[TeamMember, ...]

    def authenticate(self, authorization: str) -> TeamMember | None:
        supplied = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
        matched = None
        for member in self.members:
            expected = os.environ.get(member.token_env, '')
            if expected and supplied and hmac.compare_digest(supplied, expected):
                matched = member
        return matched


def load_team_configuration(path: Path, *, default_runs_dir: Path) -> TeamConfiguration:
    """读取不含密钥的团队配置；相对路径以配置文件目录为基准。"""
    source = json.loads(path.read_text())
    if not isinstance(source, dict) or source.get('schemaVersion') != TEAM_SCHEMA:
        raise ValueError('invalid Router team service schema')
    if set(source) - {'schemaVersion', 'statePath', 'projects', 'members'}:
        raise ValueError('unknown Router team service field')
    if not isinstance(source.get('projects'), list) or not source['projects']:
        raise ValueError('team service requires projects')
    if not isinstance(source.get('members'), list) or not source['members']:
        raise ValueError('team service requires members')
    base = path.resolve().parent
    state_value = source.get('statePath', 'refractrouter-service.sqlite3')
    if not isinstance(state_value, str) or not state_value:
        raise ValueError('invalid statePath')
    state_path = Path(state_value).expanduser()
    if not state_path.is_absolute():
        state_path = base / state_path
    projects: dict[str, TeamProject] = {}
    for raw in source['projects']:
        if not isinstance(raw, dict) or set(raw) - {
            'id', 'runsDir', 'maxConcurrentTasks', 'productionBudget',
            'evaluationBudget', 'timeoutMs', 'maxOutputTokens',
        }:
            raise ValueError('invalid team project')
        project_id = _identifier(raw.get('id'), 'project id')
        if project_id in projects:
            raise ValueError('duplicate project id')
        runs_value = raw.get('runsDir')
        if runs_value is None:
            runs_dir = default_runs_dir / project_id
        elif not isinstance(runs_value, str) or not runs_value:
            raise ValueError('invalid project runsDir')
        else:
            runs_dir = Path(runs_value).expanduser()
            if not runs_dir.is_absolute():
                runs_dir = base / runs_dir
        max_output_tokens = _positive_integer(
            raw.get('maxOutputTokens', 128_000), 'maxOutputTokens', 128_000)
        if max_output_tokens < 1000:
            raise ValueError('invalid maxOutputTokens')
        projects[project_id] = TeamProject(
            id=project_id,
            runs_dir=runs_dir,
            max_concurrent_tasks=_positive_integer(
                raw.get('maxConcurrentTasks', 2), 'maxConcurrentTasks', 64),
            production_budget=_positive_number(
                raw.get('productionBudget', 40), 'productionBudget'),
            evaluation_budget=_positive_number(
                raw.get('evaluationBudget', 80), 'evaluationBudget'),
            timeout_ms=_positive_integer(raw.get('timeoutMs', 300_000), 'timeoutMs', 7_200_000),
            max_output_tokens=max_output_tokens,
        )
    members = []
    seen_members: set[str] = set()
    seen_token_envs: set[str] = set()
    seen_token_values: set[str] = set()
    for raw in source['members']:
        if not isinstance(raw, dict) or set(raw) != {'id', 'role', 'tokenEnv', 'projects'}:
            raise ValueError('invalid team member')
        member_id = _identifier(raw.get('id'), 'member id')
        role = raw.get('role')
        token_env = raw.get('tokenEnv')
        member_projects = raw.get('projects')
        if role not in {'member', 'maintainer'}:
            raise ValueError('invalid member role')
        if not isinstance(token_env, str) or not token_env.isidentifier():
            raise ValueError('invalid member token environment reference')
        if not isinstance(member_projects, list) or not member_projects:
            raise ValueError('member requires project access')
        project_ids = tuple(_identifier(value, 'member project') for value in member_projects)
        if any(project_id not in projects for project_id in project_ids):
            raise ValueError('member references unknown project')
        if member_id in seen_members or token_env in seen_token_envs:
            raise ValueError('duplicate member or token environment reference')
        token_value = os.environ.get(token_env)
        if not token_value:
            raise ValueError(f'missing Router team credential: {token_env}')
        if token_value in seen_token_values:
            raise ValueError('team member credentials must be unique')
        seen_members.add(member_id)
        seen_token_envs.add(token_env)
        seen_token_values.add(token_value)
        members.append(TeamMember(member_id, role, token_env, project_ids))
    return TeamConfiguration(state_path.resolve(), projects, tuple(members))


class IdempotencyConflict(ValueError):
    pass


class ProjectCapacityExceeded(ValueError):
    pass


class TaskStore:
    """每个操作使用独立连接；BEGIN IMMEDIATE 保证并发准入与幂等原子化。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.changed = Condition()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('PRAGMA journal_mode = WAL')
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    evidence_run_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(member_id, project_id, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS tasks_project_state
                    ON tasks(project_id, state);
                CREATE TABLE IF NOT EXISTS task_events (
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    sequence INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(task_id, sequence)
                );
            ''')
            stamp = _now()
            rows = connection.execute(
                "SELECT id FROM tasks WHERE state IN ('queued','running','cancel_requested')"
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE tasks SET state='recovery_required', updated_at=? WHERE id=?",
                    (stamp, row['id']),
                )
                self._append_event(connection, row['id'], 'status', {
                    'status': 'recovery_required',
                    'reason': 'Router 服务重启；任务不会自动重放。',
                })

    @staticmethod
    def canonical_request(value: object) -> tuple[str, str]:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                             sort_keys=True, separators=(',', ':'))
        return encoded, hashlib.sha256(encoded.encode()).hexdigest()

    def submit(self, *, member_id: str, project: TeamProject, idempotency_key: str,
               envelope: object) -> tuple[dict, bool]:
        if not 1 <= len(idempotency_key) <= 200:
            raise ValueError('invalid Idempotency-Key')
        encoded, request_hash = self.canonical_request(envelope)
        task_id = str(uuid4())
        stamp = _now()
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute(
                'SELECT * FROM tasks WHERE member_id=? AND project_id=? AND idempotency_key=?',
                (member_id, project.id, idempotency_key),
            ).fetchone()
            if existing:
                if existing['request_hash'] != request_hash:
                    raise IdempotencyConflict('Idempotency-Key was already used for another request')
                connection.commit()
                return self._task(existing), True
            active = connection.execute(
                "SELECT COUNT(*) FROM tasks WHERE project_id=? "
                "AND state IN ('queued','running','cancel_requested')", (project.id,),
            ).fetchone()[0]
            if active >= project.max_concurrent_tasks:
                raise ProjectCapacityExceeded('project concurrent task limit reached')
            connection.execute(
                'INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (task_id, project.id, member_id, idempotency_key, request_hash, encoded,
                 'queued', None, None, None, stamp, stamp),
            )
            self._append_event(connection, task_id, 'status', {'status': 'queued'})
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        self._notify()
        return self.get(task_id), False

    def claim(self, task_id: str) -> bool:
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            changed = connection.execute(
                "UPDATE tasks SET state='running', updated_at=? WHERE id=? AND state='queued'",
                (_now(), task_id),
            ).rowcount
            if changed:
                self._append_event(connection, task_id, 'status', {'status': 'running'})
        if changed:
            self._notify()
        return bool(changed)

    def append_event(self, task_id: str, kind: str, value: object) -> int:
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            sequence = self._append_event(connection, task_id, kind, value)
        self._notify()
        return sequence

    @staticmethod
    def _append_event(connection: sqlite3.Connection, task_id: str, kind: str,
                      value: object) -> int:
        sequence = connection.execute(
            'SELECT COALESCE(MAX(sequence), 0) + 1 FROM task_events WHERE task_id=?',
            (task_id,),
        ).fetchone()[0]
        connection.execute(
            'INSERT INTO task_events VALUES (?,?,?,?,?)',
            (task_id, sequence, kind,
             json.dumps(value, ensure_ascii=False, allow_nan=False), _now()),
        )
        return int(sequence)

    def finish(self, task_id: str, state: str, *, result: object | None = None,
               error: object | None = None) -> dict:
        if state not in TERMINAL_STATES:
            raise ValueError('invalid terminal task state')
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            current = connection.execute('SELECT state FROM tasks WHERE id=?', (task_id,)).fetchone()
            if current is None:
                raise KeyError(task_id)
            if current['state'] in TERMINAL_STATES:
                return self.get(task_id)
            if current['state'] == 'cancel_requested':
                state = 'cancelled'
                result = None
            result_json = (json.dumps(result, ensure_ascii=False, allow_nan=False)
                           if result is not None else None)
            error_json = (json.dumps(error, ensure_ascii=False, allow_nan=False)
                          if error is not None else None)
            evidence = result.get('run_id') if isinstance(result, dict) else None
            connection.execute(
                'UPDATE tasks SET state=?, result_json=?, error_json=?, evidence_run_id=?, '
                'updated_at=? WHERE id=?',
                (state, result_json, error_json, evidence, _now(), task_id),
            )
            self._append_event(connection, task_id, 'result' if state == 'completed' else 'error',
                               result if state == 'completed' else (
                                   error or {'code': 'REFRACTAGENT_EXECUTION_ABORTED',
                                             'message': '任务已取消。'}))
            self._append_event(connection, task_id, 'status', {'status': state})
        self._notify()
        return self.get(task_id)

    def request_cancel(self, task_id: str) -> dict:
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT state FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row['state'] in TERMINAL_STATES or row['state'] == 'cancel_requested':
                return self.get(task_id)
            connection.execute(
                "UPDATE tasks SET state='cancel_requested', updated_at=? WHERE id=?", (_now(), task_id),
            )
            self._append_event(connection, task_id, 'status', {'status': 'cancel_requested'})
        self._notify()
        return self.get(task_id)

    def get(self, task_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return self._task(row)

    def list(self, *, project_ids: Iterable[str], member_id: str | None, limit: int,
             before: str | None = None) -> list[dict]:
        ids = tuple(project_ids)
        if not ids:
            return []
        clauses = [f"project_id IN ({','.join('?' for _ in ids)})"]
        parameters: list[object] = list(ids)
        if member_id is not None:
            clauses.append('member_id=?')
            parameters.append(member_id)
        if before is not None:
            clauses.append('created_at<?')
            parameters.append(before)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM tasks WHERE {' AND '.join(clauses)} "
                'ORDER BY created_at DESC LIMIT ?', parameters,
            ).fetchall()
        return [self._task(row) for row in rows]

    def events(self, task_id: str, after: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                'SELECT * FROM task_events WHERE task_id=? AND sequence>? ORDER BY sequence',
                (task_id, after),
            ).fetchall()
        return [{
            'sequence': row['sequence'], 'type': row['kind'],
            'value': json.loads(row['value_json']), 'createdAt': row['created_at'],
        } for row in rows]

    def envelope(self, task_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute('SELECT envelope_json FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return json.loads(row['envelope_json'])

    @staticmethod
    def _task(row: sqlite3.Row) -> dict:
        return {
            'taskId': row['id'], 'projectId': row['project_id'], 'memberId': row['member_id'],
            'status': row['state'], 'createdAt': row['created_at'], 'updatedAt': row['updated_at'],
            **({'result': json.loads(row['result_json'])} if row['result_json'] else {}),
            **({'error': json.loads(row['error_json'])} if row['error_json'] else {}),
            **({'evidenceRunId': row['evidence_run_id']} if row['evidence_run_id'] else {}),
        }

    def _notify(self) -> None:
        with self.changed:
            self.changed.notify_all()
