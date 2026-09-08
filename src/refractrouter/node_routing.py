"""Exact bounded assignment search over empirical node-type profiles.

Quality is a local proxy, cost a forecast, and latency a serial forecast. None is a final-task SLA.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import product
import math

from .model_selection import Weights
from .task_plan import NODE_TYPES, TaskPlan, text
from .task_scheduling import ExecutionPolicy, estimate_schedule


def number(value, field, *, maximum=None, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or value < 0 or (positive and value == 0) or (maximum is not None and value > maximum)):
        raise ValueError(f"invalid {field}")
    return value


@dataclass(frozen=True)
class NodeProfile:
    model_id: str
    node_type: str
    quality: float
    cost: float
    latency_ms: float
    samples: int
    difficulty: str | None = None
    risk: str | None = None
    input_min_tokens: int | None = None
    input_max_tokens: int | None = None

    def __post_init__(self):
        text(self.model_id, "profile model_id", 100)
        if self.node_type not in NODE_TYPES:
            raise ValueError("unsupported profile node_type")
        number(self.quality, "quality", maximum=100)
        number(self.cost, "cost")
        number(self.latency_ms, "latency_ms")
        if isinstance(self.samples, bool) or not isinstance(self.samples, int) or self.samples < 0:
            raise ValueError("invalid profile samples")

        selector = (self.difficulty, self.risk, self.input_min_tokens, self.input_max_tokens)
        if any(v is not None for v in selector):
            if self.difficulty not in ('low', 'medium', 'high') or self.risk not in ('low', 'medium', 'high'):
                raise ValueError('invalid profile difficulty/risk stratum')
            if (type(self.input_min_tokens) is not int or type(self.input_max_tokens) is not int
                    or not 256 <= self.input_min_tokens < self.input_max_tokens <= 131073):
                raise ValueError('invalid profile input interval')

    def matches(self, node, plan):
        if self.node_type != node.node_type:
            return False
        if self.difficulty is None:
            return True
        features = plan.contracts.get(node.node_id, {}).get('capability', {})
        return (features.get('difficulty') == self.difficulty and features.get('risk') == self.risk
                and self.input_min_tokens <= features.get('input_budget_tokens', -1) < self.input_max_tokens)


def validate_profiles(profiles):
    for i, left in enumerate(profiles):
        for right in profiles[i+1:]:
            if (left.model_id, left.node_type) != (right.model_id, right.node_type):
                continue
            if left.difficulty is None or right.difficulty is None:
                raise ValueError('duplicate or ambiguous model/type profile')
            if ((left.difficulty, left.risk) == (right.difficulty, right.risk)
                    and max(left.input_min_tokens, right.input_min_tokens) < min(left.input_max_tokens, right.input_max_tokens)):
                raise ValueError('overlapping model/type profile strata')


def load_profile(raw, manifest):
    if not isinstance(raw, dict) or raw.get("schema_version") not in {"node-routing-profile-v1", "node-routing-profile-v2"}:
        raise ValueError("unsupported routing profile")
    if raw.get("billing_unit") != manifest.billing_unit:
        raise ValueError("routing profile billing unit differs from manifest")
    if raw.get("kind") not in {"empirical", "synthetic", "configured"}:
        raise ValueError("profile kind must be empirical, synthetic or configured")
    text(raw.get("scope"), "profile scope", 2000)
    text(raw.get("provenance"), "profile provenance", 2000)
    rows = raw.get("candidates")
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty routing profile")
    known = {m.model_id for m in manifest.candidates}
    bindings = raw.get("model_bindings")
    if not isinstance(bindings, dict) or any(bindings.get(m.model_id) != m.api_model for m in manifest.candidates):
        raise ValueError("profile model bindings differ from manifest")
    profiles = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid profile row")
        mid, kind = row.get("model_id"), row.get("node_type")
        if not isinstance(mid, str) or mid not in known or not isinstance(kind, str) or kind not in NODE_TYPES:
            raise ValueError("unknown profile model/type")
        samples = row.get("samples")
        if (type(samples) is not int or (samples != 0 if raw["kind"] == "configured" else samples < 1)):
            raise ValueError("invalid profile samples")
        fields = {"model_id", "node_type", "quality", "cost", "latency_ms", "samples"}
        selector = {}
        if raw["schema_version"] == "node-routing-profile-v2":
            fields |= {"difficulty", "risk", "input_min_tokens", "input_max_tokens"}
            selector = {key: row.get(key) for key in fields - {"model_id", "node_type", "quality", "cost", "latency_ms", "samples"}}
            if any(value is None for value in selector.values()):
                raise ValueError("v2 profile requires complete strata")
        if set(row) != fields:
            raise ValueError("invalid profile row fields")
        profiles.append(NodeProfile(mid, kind, number(row.get("quality"), "quality", maximum=100),
                                    number(row.get("cost"), "cost"),
                                    number(row.get("latency_ms"), "latency_ms"), samples, **selector))
    validate_profiles(profiles)
    return tuple(profiles)


def route_nodes(plan: TaskPlan, profiles: tuple[NodeProfile, ...], *, method: str,
                quality_min: float, cost_max: float, latency_max_ms: float,
                weights: Weights | None = None,
                eligible_models: dict[str, list[str]] | None = None,
                execution_policy: ExecutionPolicy | None = None,
                model_providers: dict[str, str] | None = None,
                assignment_mode: str = 'per-node'):
    if assignment_mode not in {'per-node', 'single-model'}:
        raise ValueError('unsupported assignment mode')
    if method not in {"A", "B"} or (method == "B" and weights is None) or (method == "A" and weights is not None):
        raise ValueError("A requires constraints; B also requires explicit weights")
    number(quality_min, "quality_min", maximum=100)
    number(cost_max, "cost_max")
    number(latency_max_ms, "latency_max_ms")
    validate_profiles(profiles)
    policy = execution_policy or ExecutionPolicy()
    providers = model_providers or {p.model_id: 'default' for p in profiles}
    if (policy.provider_concurrency or policy.provider_min_interval_ms) and model_providers is None:
        raise ValueError('provider policy requires model_providers')
    normalized = weights.normalized() if weights else None
    options, utilities, bounds = [], {}, {}
    for node in plan.nodes:
        pool = sorted((p for p in profiles if p.matches(node, plan) and
                       (eligible_models is None or p.model_id in eligible_models.get(node.node_id, []))),
                      key=lambda p: p.model_id)
        limits = {k: (min(getattr(p, k) for p in pool), max(getattr(p, k) for p in pool))
                  for k in ("quality", "cost", "latency_ms")} if pool else {}
        bounds[node.node_id] = limits
        for p in pool:
            score = 0
            for metric in ("quality", "cost"):
                lo, hi = limits[metric]
                utility = 1 if hi == lo else ((getattr(p, metric)-lo)/(hi-lo) if metric == "quality"
                                             else (hi-getattr(p, metric))/(hi-lo))
                score += utility * (normalized[metric] if normalized else 0)
            utilities[(node.node_id, p.model_id)] = score
        options.append(pool)
    count = math.prod(map(len, options))
    if count > 100000:
        raise ValueError("assignment search exceeds 100000 combinations; narrow the profile or DAG")
    def schedule(combination):
        return estimate_schedule(plan, {n.node_id: p.latency_ms for n, p in zip(plan.nodes, combination)},
            {n.node_id: providers[p.model_id] for n, p in zip(plan.nodes, combination)}, policy)
    # 在硬质量/成本/时延约束前确定归一化范围，避免阈值改变分值标尺。
    records = []
    for combination in product(*options):
        latency = schedule(combination)['makespan_ms']
        records.append((combination, sum(p.cost for p in combination), latency,
                        sum(p.quality for p in combination) / len(combination)))
    latency_bounds = (min(r[2] for r in records), max(r[2] for r in records)) if records else None
    best, best_key, feasible = None, None, 0
    for combination, cost, latency, quality in records:
        # 对称单模型基线只限制分配空间；目标、归一化标尺、约束和调度均保持一致。
        if assignment_mode == 'single-model' and len({p.model_id for p in combination}) != 1:
            continue
        if any(p.quality < quality_min for p in combination) or cost > cost_max or latency > latency_max_ms:
            continue
        feasible += 1
        score = sum(utilities[(n.node_id, p.model_id)] for n, p in zip(plan.nodes, combination)) / len(combination)
        if normalized:
            lo, hi = latency_bounds
            score += normalized['latency'] * (1 if hi == lo else (hi-latency)/(hi-lo))
        tie = (cost, -quality, latency, tuple(p.model_id for p in combination))
        key = (-score, *tie) if method == "B" else tie
        if best_key is None or key < best_key:
            best_key, best = key, (combination, cost, latency, quality, score)
    result = {"policy_version": "node-routing-v2", "method": method,
              "assignment_mode": assignment_mode,
              "status": "selected" if best else "no-feasible-route", "assignments": {},
              "quality_min_per_node": quality_min, "cost_max": cost_max,
              "latency_max_ms": latency_max_ms, "weights": asdict(weights) if weights else None,
              "normalized_weights": normalized, "normalization_bounds": bounds, "eligible_models": eligible_models,
              "scheduled_latency_bounds_ms": latency_bounds, "execution_policy": policy.to_dict(),
              "combinations": count, "feasible_combinations": feasible,
              "prediction": None, "nodes": {}}
    if best:
        combination, cost, latency, quality, score = best
        result["assignments"] = {n.node_id: p.model_id for n, p in zip(plan.nodes, combination)}
        result["nodes"] = {n.node_id: asdict(p) for n, p in zip(plan.nodes, combination)}
        result["prediction"] = {"cost": cost, "serial_latency_ms": sum(p.latency_ms for p in combination),
                                "scheduled_latency_ms": latency, "schedule": schedule(combination),
                                "mean_node_quality_proxy": quality, "weighted_score": score if weights else None}
    return result
