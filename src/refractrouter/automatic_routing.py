"""v4 安全约束自动选路：零调用筛选与 direct/DAG 预计值比较。

本模块只消费用户声明的预测与调用前特征，不读取测试答案，也不发起模型调用。
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .privacy_placement import allows_sensitive
from .task_plan import validate_plan
from .task_scheduling import ExecutionPolicy, estimate_schedule

POLICY_VERSION = 'automatic-route-v1'
SENSITIVE_GRADES = frozenset({'S1', 'S2', 'unknown'})


def _ratio(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'invalid {label}')
    if not 0 <= value <= 1:
        raise ValueError(f'{label} must be in 0..1')
    return float(value)


@dataclass(frozen=True)
class RouteFeatures:
    subtask_independence: float
    parallel_work_ratio: float
    mixed_sensitive_public: bool
    legal_model_price_ratio: float
    direct_already_low_cost: bool
    dependency_density: float
    merge_risk: float

    def __post_init__(self):
        for name in ('subtask_independence', 'parallel_work_ratio', 'dependency_density', 'merge_risk'):
            object.__setattr__(self, name, _ratio(getattr(self, name), name))
        if not isinstance(self.mixed_sensitive_public, bool) or not isinstance(self.direct_already_low_cost, bool):
            raise ValueError('route feature flags must be booleans')
        if (isinstance(self.legal_model_price_ratio, bool)
                or not isinstance(self.legal_model_price_ratio, (int, float))
                or not math.isfinite(self.legal_model_price_ratio)
                or self.legal_model_price_ratio < 1):
            raise ValueError('legal_model_price_ratio must be finite and at least 1')


@dataclass(frozen=True)
class CallEnvelope:
    input_tokens: int
    output_tokens: int
    grade: str = 'S3'
    cached_input_tokens: int = 0
    tool_continuations: int = 0
    fallback_calls: int = 0
    latency_ms: float | None = None

    def __post_init__(self):
        for name in ('input_tokens', 'output_tokens', 'cached_input_tokens',
                     'tool_continuations', 'fallback_calls'):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f'{name} must be a non-negative integer')
        if self.input_tokens < self.cached_input_tokens:
            raise ValueError('cached_input_tokens cannot exceed input_tokens')
        if self.grade not in {'S1', 'S2', 'S3', 'unknown'}:
            raise ValueError('grade must be S1, S2, S3 or unknown')
        if (self.latency_ms is not None
                and (isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float))
                     or not math.isfinite(self.latency_ms) or self.latency_ms <= 0)):
            raise ValueError('latency_ms must be finite and positive')

    @property
    def calls(self):
        return 1 + self.tool_continuations + self.fallback_calls


def first_level_gate(features, *, dag_mode='auto'):
    """判断是否值得支付 planner 调用；阈值固定记录，不能解释为校准概率。"""
    if not isinstance(features, RouteFeatures):
        raise ValueError('features must be RouteFeatures')
    if dag_mode not in {'auto', 'never', 'force'}:
        raise ValueError('dag_mode must be auto, never or force')
    thresholds = {'price_ratio': 1.5, 'independence': .5, 'parallel_work_ratio': .35,
                  'dependency_density_block': .75, 'merge_risk_block': .75}
    signals = []
    if features.mixed_sensitive_public:
        signals.append('security-placement')
    if features.legal_model_price_ratio >= thresholds['price_ratio'] and not features.direct_already_low_cost:
        signals.append('model-price-gap')
    if (features.subtask_independence >= thresholds['independence']
            and features.parallel_work_ratio >= thresholds['parallel_work_ratio']):
        signals.append('parallel-work')
    blockers = []
    if features.dependency_density >= thresholds['dependency_density_block']:
        blockers.append('dense-dependencies')
    if features.merge_risk >= thresholds['merge_risk_block']:
        blockers.append('high-merge-risk')
    if dag_mode == 'never':
        call_planner, reason = False, 'dag-mode-never'
    elif dag_mode == 'force':
        call_planner, reason = True, 'research-force'
    elif not signals:
        call_planner, reason = False, 'no-potential-net-benefit'
    elif blockers and 'security-placement' not in signals:
        call_planner, reason = False, 'structural-risk-blocked'
    else:
        call_planner, reason = True, 'potential-net-benefit'
    return {'policy_version': POLICY_VERSION, 'call_planner': call_planner, 'reason': reason,
            'signals': signals, 'blockers': blockers, 'thresholds': thresholds,
            'features': features.__dict__.copy()}


def _sensitive(grade):
    return grade in SENSITIVE_GRADES


def _forecast(configuration, model, envelope):
    row = configuration.predictions.get(model.model_id)
    latency = (envelope.latency_ms if envelope.latency_ms is not None
               else row.get('latency_ms') if row else None)
    if latency is None:
        raise ValueError(f'missing latency forecast for {model.model_id}')
    return {'quality': row.get('quality') if row else None, 'latency_ms': latency}


def _prices(model, *, cloud=False):
    if cloud and model.deployment == 'simulated-local' and model.declared_pricing:
        row = model.declared_pricing
        return row['inputPer1k'], row['cachedInputPer1k'], row['outputPer1k']
    return model.input_cost_per_1k, model.cached_input_cost_per_1k, model.output_cost_per_1k


def _call_estimate(configuration, model, envelope):
    forecast = _forecast(configuration, model, envelope)
    output = envelope.output_tokens
    uncached = envelope.input_tokens - envelope.cached_input_tokens

    def cost(cloud):
        inp, cached, out = _prices(model, cloud=cloud)
        return envelope.calls * ((uncached * inp + envelope.cached_input_tokens * cached
                                  + output * out) / 1000)

    return {'model_id': model.model_id, 'provider': model.provider, 'deployment': model.deployment,
            'calls': envelope.calls, 'input_tokens_per_call': envelope.input_tokens,
            'cached_input_tokens_per_call': envelope.cached_input_tokens,
            'output_tokens_per_call': output, 'quality': forecast['quality'],
            'latency_ms': forecast['latency_ms'] * envelope.calls,
            'marginal_cost': cost(False), 'actual_cloud_cost': cost(True)}


def _choose_call(configuration, role, envelope, *, quality_min=None):
    candidates = []
    excluded = {'security-placement': 0, 'capacity': 0, 'quality': 0}
    declared = [model for model in configuration.manifest.models if role in getattr(model, 'roles', ())]
    for model in declared:
        if _sensitive(envelope.grade) and not allows_sensitive(model.deployment, configuration.privacy):
            excluded['security-placement'] += 1
            continue
        if (envelope.output_tokens > model.max_output_tokens
                or envelope.input_tokens + envelope.output_tokens > model.context_window):
            excluded['capacity'] += 1
            continue
        row = _call_estimate(configuration, model, envelope)
        if quality_min is not None and (row['quality'] is None or row['quality'] < quality_min):
            excluded['quality'] += 1
            continue
        candidates.append((row['marginal_cost'], row['latency_ms'], model.model_id, model, row))
    if not candidates:
        return None, excluded
    _, _, _, model, row = min(candidates)
    return (model, row), excluded


def _sum_calls(calls):
    return {'marginal_cost': sum(row['marginal_cost'] for row in calls),
            'actual_cloud_cost': sum(row['actual_cloud_cost'] for row in calls)}


def _require_no_grade_downgrade(source_grade, envelope, label):
    if _sensitive(source_grade) and not _sensitive(envelope.grade):
        raise ValueError(f'{label} cannot downgrade sensitive input')


def choose_route(configuration, *, direct, plan=None, nodes=None, planner=None,
                 direct_judge=None, dag_judge=None, max_concurrency=1,
                 cost_risk_margin=0.0, quality_risk_margin=0.0,
                 cost_tie_tolerance=1e-9, dag_mode=None):
    """在已编译的 v4 配置上比较 direct 与候选 DAG；返回可归档的零调用审计。"""
    if configuration.objective is None or configuration.role_pools is None:
        raise ValueError('automatic routing requires a compiled v4 configuration')
    if not isinstance(direct, CallEnvelope):
        raise ValueError('direct must be a CallEnvelope')
    for value, label in ((cost_risk_margin, 'cost_risk_margin'),
                         (quality_risk_margin, 'quality_risk_margin'),
                         (cost_tie_tolerance, 'cost_tie_tolerance')):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{label} must be finite and non-negative')
    objective = configuration.objective
    dag_mode = objective['dagMode'] if dag_mode is None else dag_mode
    if dag_mode not in {'auto', 'never', 'force'}:
        raise ValueError('invalid dag mode')
    minimum = objective['qualityMin']
    audit = {'policy_version': POLICY_VERSION, 'objective': objective.copy(), 'status': 'pending',
             'route': None, 'reason': None, 'excluded_candidates': {}, 'direct': None, 'dag': None}

    direct_worker, excluded = _choose_call(configuration, 'worker', direct, quality_min=minimum)
    audit['excluded_candidates']['direct_worker'] = excluded
    judge_envelope = direct_judge or CallEnvelope(direct.input_tokens + direct.output_tokens,
                                                  min(2048, direct.output_tokens), direct.grade)
    _require_no_grade_downgrade(direct.grade, judge_envelope, 'judge')
    direct_judge, judge_excluded = _choose_call(configuration, 'judge', judge_envelope)
    audit['excluded_candidates']['direct_judge'] = judge_excluded
    if direct_worker and direct_judge:
        worker_model, worker_call = direct_worker
        _, judge_call = direct_judge
        totals = _sum_calls([worker_call, judge_call])
        audit['direct'] = {**totals, 'quality': worker_call['quality'],
                           'latency_ms': worker_call['latency_ms'] + judge_call['latency_ms'],
                           'calls': {'worker': worker_call, 'judge': judge_call},
                           'model_id': worker_model.model_id}

    if dag_mode != 'never' and plan is not None:
        plan = validate_plan(plan)
        if (not isinstance(nodes, dict) or set(nodes) != {node.node_id for node in plan.nodes}
                or any(not isinstance(value, CallEnvelope) for value in nodes.values())):
            raise ValueError('nodes must provide one CallEnvelope for every DAG node')
        planner_envelope = planner or CallEnvelope(direct.input_tokens, min(1200, direct.output_tokens), direct.grade)
        _require_no_grade_downgrade(direct.grade, planner_envelope, 'planner')
        planner_call, planner_excluded = _choose_call(configuration, 'planner', planner_envelope)
        audit['excluded_candidates']['planner'] = planner_excluded
        if planner_call and audit['direct'] is not None:
            _, planned = planner_call
            direct_calls = audit['direct']['calls']
            totals = _sum_calls([planned, direct_calls['worker'], direct_calls['judge']])
            audit['direct'].update(
                **totals,
                latency_ms=planned['latency_ms'] + audit['direct']['latency_ms'],
                calls={'planner_probe': planned, **direct_calls},
            )
        most_sensitive = 'S1' if any(_sensitive(value.grade) for value in nodes.values()) else 'S3'
        dag_judge_envelope = dag_judge or CallEnvelope(
            direct.input_tokens + sum(value.output_tokens for value in nodes.values()),
            min(2048, direct.output_tokens), most_sensitive)
        _require_no_grade_downgrade(most_sensitive, dag_judge_envelope, 'judge')
        dag_judge, dag_judge_excluded = _choose_call(configuration, 'judge', dag_judge_envelope)
        audit['excluded_candidates']['dag_judge'] = dag_judge_excluded
        assignments, node_calls, node_excluded = {}, {}, {}
        required_quality = minimum + quality_risk_margin
        for spec in plan.nodes:
            selected, count = _choose_call(configuration, 'worker', nodes[spec.node_id],
                                           quality_min=required_quality)
            node_excluded[spec.node_id] = count
            if selected is None:
                assignments = None
                break
            model, row = selected
            assignments[spec.node_id], node_calls[spec.node_id] = model, row
        audit['excluded_candidates']['dag_workers'] = node_excluded
        if planner_call and dag_judge and assignments is not None:
            _, planned = planner_call
            _, judged = dag_judge
            calls = [planned, *node_calls.values(), judged]
            totals = _sum_calls(calls)
            schedule = estimate_schedule(plan,
                {nid: row['latency_ms'] for nid, row in node_calls.items()},
                {nid: assignments[nid].provider for nid in assignments},
                ExecutionPolicy(max_concurrency=max_concurrency))
            quality = min(row['quality'] for row in node_calls.values()) - quality_risk_margin
            audit['dag'] = {**totals, 'cost_with_risk_margin': totals['marginal_cost'] + cost_risk_margin,
                'quality': quality, 'latency_ms': planned['latency_ms'] + schedule['makespan_ms'] + judged['latency_ms'],
                'critical_path': schedule, 'calls': {'planner': planned, 'nodes': node_calls, 'judge': judged},
                'assignments': {nid: model.model_id for nid, model in assignments.items()}}

    direct_row, dag_row = audit['direct'], audit['dag']
    if dag_mode == 'force' and dag_row is None:
        audit.update(status='infeasible', route='infeasible', reason='forced-dag-unavailable-or-infeasible')
    elif direct_row is None and dag_row is None:
        audit.update(status='infeasible', route='infeasible', reason='no-legal-quality-qualified-route')
    elif dag_mode == 'force' and dag_row is not None:
        audit.update(status='selected', route='dag', reason='research-force')
    elif direct_row is None:
        audit.update(status='selected', route='dag', reason='direct-infeasible')
    elif dag_row is None:
        audit.update(status='selected', route='direct', reason='dag-unavailable-or-infeasible')
    else:
        delta = dag_row['cost_with_risk_margin'] - direct_row['marginal_cost']
        if delta < -cost_tie_tolerance:
            audit.update(status='selected', route='dag', reason='lower-total-cost-after-risk')
        elif abs(delta) <= cost_tie_tolerance and dag_row['latency_ms'] < direct_row['latency_ms']:
            audit.update(status='selected', route='dag', reason='cost-tie-lower-latency')
        else:
            audit.update(status='selected', route='direct', reason='direct-cost-not-worse')
    return audit
