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
        CREATE TABLE IF NOT EXISTS route_value_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_scope TEXT NOT NULL,
            run_id TEXT NOT NULL,
            route TEXT NOT NULL,
            task_status TEXT NOT NULL,
            predicted_costs_by_unit TEXT,
            actual_costs_by_unit TEXT NOT NULL,
            unconfirmed_costs_by_unit TEXT NOT NULL,
            judge_passed INTEGER,
            tool_receipt_passed INTEGER,
            quality_source TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            UNIQUE(project_scope, run_id)
        );
        CREATE INDEX IF NOT EXISTS route_value_scope
            ON route_value_observations(project_scope, route, id);
    ''')


def _identity(binding):
    required = ('provider', 'model', 'effective_model', 'reasoning_effort')
    if not isinstance(binding, dict) or any(not isinstance(binding.get(key), str)
                                            or not binding[key] for key in required):
        raise ValueError('invalid route observation binding')
    return tuple(binding[key] for key in required)


def route_value_observation(comparison, plan_origin, calls, billing_unit, status, evaluation,
                            tool_validation=None):
    """从真实账本取被选路线的预测与结算；未执行的反事实不算观测。"""
    if billing_unit not in {'AFP', 'CNY', 'USD', 'MIXED'} or not isinstance(calls, list):
        raise ValueError('invalid route value ledger')
    route = comparison.get('route') if isinstance(comparison, dict) else None
    if route not in {'direct', 'dag'}:
        route = 'direct' if plan_origin in {'direct-gate', 'direct-after-probe'} else 'dag' if plan_origin == 'model' else 'unknown'
    selected = comparison.get(route) if isinstance(comparison, dict) else None
    predicted = None
    if isinstance(selected, dict):
        if isinstance(selected.get('total_estimated_by_unit'), dict):
            predicted = dict(selected['total_estimated_by_unit'])
        elif billing_unit != 'MIXED' and isinstance(selected.get('total_estimated_cost'), (int, float)):
            predicted = {billing_unit: selected['total_estimated_cost']}
    actual = {unit: 0.0 for unit in ('AFP', 'CNY', 'USD')}
    unconfirmed = dict(actual)
    for call in calls:
        if not isinstance(call, dict) or call.get('billing_unit') not in actual:
            continue
        amount = call.get('charged')
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0:
            continue
        if call.get('status') == 'billed':
            actual[call['billing_unit']] += amount
        elif call.get('status') in {'reserved', 'unknown-usage'}:
            unconfirmed[call['billing_unit']] += amount
    judge_passed = evaluation.get('passed') if isinstance(evaluation, dict) else None
    tool_passed = tool_validation.get('passed') if isinstance(tool_validation, dict) else None
    return {'route': route, 'task_status': status, 'predicted_costs_by_unit': predicted,
            'actual_costs_by_unit': actual, 'unconfirmed_costs_by_unit': unconfirmed,
            'judge_passed': judge_passed if type(judge_passed) is bool else None,
            'tool_receipt_passed': tool_passed if type(tool_passed) is bool else None,
            'quality_source': 'model-review-unverified' if type(judge_passed) is bool else 'none',
            'counterfactual_observed': False}


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

    def record_route_value(self, run_id, observation):
        if not isinstance(run_id, str) or not run_id or not isinstance(observation, dict):
            raise ValueError('invalid route value observation')
        if observation.get('route') not in {'direct', 'dag', 'unknown'} or not isinstance(observation.get('task_status'), str):
            raise ValueError('invalid route value identity')
        with self._writable() as connection:
            before = connection.total_changes
            connection.execute('''
                INSERT OR IGNORE INTO route_value_observations
                (project_scope,run_id,route,task_status,predicted_costs_by_unit,actual_costs_by_unit,
                 unconfirmed_costs_by_unit,judge_passed,tool_receipt_passed,quality_source,observed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ''', (self.scope, run_id, observation['route'], observation['task_status'],
                  json.dumps(observation['predicted_costs_by_unit'], sort_keys=True),
                  json.dumps(observation['actual_costs_by_unit'], sort_keys=True),
                  json.dumps(observation['unconfirmed_costs_by_unit'], sort_keys=True),
                  observation['judge_passed'], observation['tool_receipt_passed'],
                  observation['quality_source'], _now()))
            return connection.total_changes - before

    def value_summary(self):
        """被动观测的预测偏差；不能把自身审核或未执行路线解释为收益证明。"""
        if not self.path.is_file():
            return {'runs': 0, 'byRoute': {}, 'costRatioP90ByRouteAndUnit': {},
                    'counterfactualObserved': False, 'qualityVerified': False}
        self._ensure_schema()
        with _connect(self.path) as connection:
            rows = connection.execute('''
                SELECT route,task_status,predicted_costs_by_unit,actual_costs_by_unit,
                       unconfirmed_costs_by_unit,judge_passed,tool_receipt_passed
                FROM route_value_observations WHERE project_scope=? ORDER BY id DESC
            ''', (self.scope,)).fetchall()
        counts, ratios = {}, {}
        for row in rows:
            route = row['route']
            counts.setdefault(route, {'runs': 0, 'completed': 0, 'modelReviewPassed': 0,
                                      'toolReceiptPassed': 0, 'toolReceiptFailed': 0})
            counts[route]['runs'] += 1
            counts[route]['completed'] += row['task_status'] == 'completed'
            counts[route]['modelReviewPassed'] += row['task_status'] == 'completed' and row['judge_passed'] == 1
            counts[route]['toolReceiptPassed'] += row['tool_receipt_passed'] == 1
            counts[route]['toolReceiptFailed'] += row['tool_receipt_passed'] == 0
            predicted = json.loads(row['predicted_costs_by_unit'])
            actual = json.loads(row['actual_costs_by_unit'])
            unknown = json.loads(row['unconfirmed_costs_by_unit'])
            if row['task_status'] != 'completed' or not isinstance(predicted, dict) or any(unknown.values()):
                continue
            for unit, estimate in predicted.items():
                if type(estimate) in (int, float) and estimate > 0 and unit in actual:
                    ratios.setdefault(route, {}).setdefault(unit, []).append(actual[unit] / estimate)
        p90 = {route: {unit: {'ratio': sorted(values)[math.ceil(.9 * len(values)) - 1],
                               'samples': len(values)} for unit, values in units.items()}
               for route, units in ratios.items()}
        return {'runs': len(rows), 'byRoute': counts, 'costRatioP90ByRouteAndUnit': p90,
                'counterfactualObserved': False, 'qualityVerified': False}

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
                    SELECT id,call_label,latency_ms,input_tokens,output_tokens,observed_at FROM route_latency_observations
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
                    'observations': [{k: row[k] for k in ('input_tokens', 'output_tokens', 'latency_ms')}
                        for row in values if row['call_label'] not in {'planner', 'planner-repair', 'final-judge'}
                            and not row['call_label'].startswith(('dynamic-planner', 'classifier'))
                            and all(type(row[k]) is int and row[k] >= 0
                            for k in ('input_tokens', 'output_tokens', 'latency_ms'))],
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
                'profiles': profiles, 'valueObservations': self.value_summary(), 'modelCalls': 0}
