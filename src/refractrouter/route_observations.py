"""持久保存实际路线调用观测；不会主动发起 probe 或把失败伪装成成功时延。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from threading import Lock


WINDOW_SIZE = 50
PERCENTILE = 0.90
LOCAL_DATABASE = 'route-observations.sqlite3'
_INITIALIZE_LOCK = Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def local_observation_path(runs_dir):
    return Path(runs_dir).expanduser().resolve() / LOCAL_DATABASE


def _connect(path):
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 30000')
    return connection


def _initialize(connection):
    connection.execute('PRAGMA journal_mode = WAL')
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS route_latency_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            effective_model TEXT NOT NULL,
            reasoning_effort TEXT NOT NULL,
            project_scope TEXT NOT NULL,
            run_id TEXT NOT NULL,
            call_label TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cached_input_tokens INTEGER,
            finish_reason TEXT,
            failure_type TEXT,
            observed_at TEXT NOT NULL,
            UNIQUE(project_scope, run_id, call_label)
        );
        CREATE INDEX IF NOT EXISTS route_latency_identity
            ON route_latency_observations(project_scope, provider, model, effective_model, reasoning_effort, id);
    ''')


def _identity(binding):
    required = ('provider', 'model', 'effective_model', 'reasoning_effort')
    if not isinstance(binding, dict) or any(not isinstance(binding.get(key), str)
                                            or not binding[key] for key in required):
        raise ValueError('invalid route observation binding')
    return tuple(binding[key] for key in required)


class RouteObservationStore:
    def __init__(self, path, *, scope='local'):
        self.path = Path(path).expanduser().resolve()
        if not isinstance(scope, str) or not scope or len(scope) > 128:
            raise ValueError('invalid route observation scope')
        self.scope = scope

    def _writable(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        return _connect(self.path)

    def _ensure_schema(self):
        with _INITIALIZE_LOCK:
            with _connect(self.path) as connection:
                _initialize(connection)

    def record_run(self, run_id, calls, bindings):
        """记录一次真实运行；只有正常 stop 的 billed 响应进入成功时延样本。"""
        if not isinstance(run_id, str) or not run_id or not isinstance(calls, list):
            raise ValueError('invalid route observation run')
        rows = []
        stamp = _now()
        for call in calls:
            if not isinstance(call, dict) or call.get('model_id') not in bindings:
                continue
            provider, model, effective, effort = _identity(bindings[call['model_id']])
            dispatched = call.get('status') not in {'reserved', 'cancelled-before-dispatch'}
            if not dispatched:
                continue
            latency = call.get('latency_ms')
            latency = latency if type(latency) is int and latency >= 0 else None
            success = call.get('status') == 'billed' and call.get('finish_reason') == 'stop' and latency is not None
            failure = call.get('failure')
            failure_type = ((failure.get('failure_type') or failure.get('type'))
                            if isinstance(failure, dict) else None)
            rows.append((provider, model, effective, effort, self.scope, run_id, str(call.get('label', '')),
                         'success' if success else 'failed', latency,
                         call.get('input_tokens') if type(call.get('input_tokens')) is int else None,
                         call.get('output_tokens') if type(call.get('output_tokens')) is int else None,
                         call.get('cached_input_tokens') if type(call.get('cached_input_tokens')) is int else None,
                         call.get('finish_reason') if isinstance(call.get('finish_reason'), str) else None,
                         failure_type, stamp))
        if not rows:
            return 0
        with self._writable() as connection:
            before = connection.total_changes
            connection.executemany('''
                INSERT OR IGNORE INTO route_latency_observations
                (provider,model,effective_model,reasoning_effort,project_scope,run_id,call_label,status,latency_ms,
                 input_tokens,output_tokens,cached_input_tokens,finish_reason,failure_type,observed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ''', rows)
            return connection.total_changes - before

    def latency_profiles(self):
        if not self.path.is_file():
            return {}
        self._ensure_schema()
        with _connect(self.path) as connection:
            identities = connection.execute('''
                SELECT DISTINCT provider,model,effective_model,reasoning_effort
                FROM route_latency_observations WHERE project_scope=?
            ''', (self.scope,)).fetchall()
            profiles = {}
            for identity in identities:
                values = connection.execute('''
                    SELECT id,latency_ms,observed_at FROM route_latency_observations
                    WHERE provider=? AND model=? AND effective_model=? AND reasoning_effort=?
                      AND project_scope=?
                      AND status='success' AND latency_ms IS NOT NULL
                    ORDER BY id DESC LIMIT ?
                ''', (*tuple(identity), self.scope, WINDOW_SIZE)).fetchall()
                if not values:
                    continue
                latencies = sorted(row['latency_ms'] for row in values)
                prediction = latencies[max(0, math.ceil(PERCENTILE * len(latencies)) - 1)]
                serialized = json.dumps([dict(row) for row in values], sort_keys=True,
                                        separators=(',', ':'))
                route_key = (f"{identity['provider']}/{identity['model']}\0"
                             f"{identity['effective_model']}\0{identity['reasoning_effort']}")
                profiles[route_key] = {
                    'prediction_ms': prediction,
                    'samples': len(values),
                    'window': f'latest-{WINDOW_SIZE}-successful-p90',
                    'last_observed_at': max(row['observed_at'] for row in values),
                    'snapshot_id': hashlib.sha256(serialized.encode()).hexdigest(),
                    'effective_model': identity['effective_model'],
                    'reasoning_effort': identity['reasoning_effort'],
                }
            return profiles

    def status_counts(self):
        if not self.path.is_file():
            return {}
        self._ensure_schema()
        with _connect(self.path) as connection:
            rows = connection.execute('''
                SELECT provider,model,status,COUNT(*) AS count
                FROM route_latency_observations WHERE project_scope=? GROUP BY provider,model,status
            ''', (self.scope,)).fetchall()
        result = {}
        for row in rows:
            result.setdefault(f"{row['provider']}/{row['model']}", {})[row['status']] = row['count']
        return result

    def catalog(self):
        counts = self.status_counts()
        profiles = []
        for key, profile in sorted(self.latency_profiles().items()):
            route, effective_model, reasoning_effort = key.split('\0')
            profiles.append({'route': route, 'effectiveModel': effective_model,
                'reasoningEffort': reasoning_effort, **profile,
                'statusCounts': counts.get(route, {})})
        return {'schemaVersion': 'refractrouter-route-profiles-v1',
                'profiles': profiles, 'modelCalls': 0}
