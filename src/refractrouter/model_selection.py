"""Offline, cohort-aligned single-model selection; never dispatches model calls."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import mean, pstdev
from typing import Iterable

from .benchmark import BenchmarkObservation, _percentile


def _number(value, name, upper=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not isfinite(value) or value < 0 or (upper is not None and value > upper)):
        raise ValueError(f"Invalid {name}: {value!r}")


@dataclass(frozen=True)
class Candidate:
    model_id: str
    quality_mean: float | None
    cost_afp_mean: float | None
    latency_p95_ms: float | None
    runs: int
    quality_stddev: float | None = None
    latency_p50_ms: float | None = None
    exclusions: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.model_id:
            raise ValueError("A model ID is required")
        if not self.exclusions:
            _number(self.quality_mean, "quality_mean", 100)
            _number(self.cost_afp_mean, "cost_afp_mean")
            _number(self.latency_p95_ms, "latency_p95_ms")
            if self.runs < 1:
                raise ValueError("An eligible candidate requires observed runs")


@dataclass(frozen=True)
class Constraints:
    quality_min: float
    cost_afp_max: float
    latency_p95_ms_max: float

    def __post_init__(self):
        _number(self.quality_min, "quality_min", 100)
        _number(self.cost_afp_max, "cost_afp_max")
        _number(self.latency_p95_ms_max, "latency_p95_ms_max")


@dataclass(frozen=True)
class Weights:
    quality: float
    cost: float
    latency: float

    def normalized(self):
        values = asdict(self)
        for name, value in values.items():
            _number(value, name)
        total = sum(values.values())
        if not isfinite(total) or total <= 0:
            raise ValueError("Weights must have a finite positive sum")
        return {name: value / total for name, value in values.items()}


def build_candidates(
    observations: Iterable[BenchmarkObservation], *,
    expected_model_ids: Iterable[str], expected_blocks: Iterable[tuple[str, int]],
) -> tuple[Candidate, ...]:
    """Require every frozen block for each model; do not drop failed repeats."""
    model_ids = tuple(expected_model_ids)
    blocks = tuple(expected_blocks)
    if not model_ids or len(set(model_ids)) != len(model_ids):
        raise ValueError("Expected model IDs must be nonempty and unique")
    if not blocks or len(set(blocks)) != len(blocks):
        raise ValueError("Expected task/repeat blocks must be nonempty and unique")
    indexed = {}
    for item in observations:
        block = (item.task_id, item.repeat)
        key = (item.strategy, block)
        if item.strategy not in model_ids or block not in blocks:
            raise ValueError(f"Unexpected model or block: {key}")
        if key in indexed:
            raise ValueError(f"Duplicate observation: {key}")
        indexed[key] = item

    candidates = []
    for model_id in sorted(model_ids):
        issues, scores, costs, latencies = [], [], [], []
        for block in sorted(blocks):
            label = f"{block[0]}/repeat-{block[1]}"
            item = indexed.get((model_id, block))
            if item is None:
                issues.append(f"{label}:missing-run")
                continue
            result = item.result
            if result.task_id != item.task_id:
                issues.append(f"{label}:task-id-mismatch")
            if set(result.model_assignments.values()) != {model_id}:
                issues.append(f"{label}:not-single-model")
            nodes = result.node_results
            if (not nodes or len(nodes) != len(result.model_assignments)
                    or {node.node_id for node in nodes} != set(result.model_assignments)
                    or any(node.model_id != model_id for node in nodes)):
                issues.append(f"{label}:incomplete-node-records")
            if result.failure_types or any(node.status != "ok" or node.failure_type for node in nodes):
                issues.append(f"{label}:failed-run")
            if item.judge is None or item.judge_error:
                issues.append(f"{label}:missing-judge")
            if result.billing_unit != "AFP" or (item.judge and item.judge.billing_unit != "AFP"):
                issues.append(f"{label}:non-AFP-billing")
            quality = item.judge.final_score if item.judge and not item.judge_error else None
            try:
                _number(quality, "quality", 100)
                _number(result.total_cost, "cost")
                _number(result.critical_path_latency_ms, "latency")
            except ValueError:
                issues.append(f"{label}:invalid-metrics")
                continue
            scores.append(quality)
            costs.append(result.total_cost)
            latencies.append(result.critical_path_latency_ms)
        candidates.append(Candidate(
            model_id=model_id,
            quality_mean=mean(scores) if not issues else None,
            cost_afp_mean=mean(costs) if not issues else None,
            latency_p95_ms=_percentile(latencies, .95) if not issues else None,
            runs=sum((model_id, block) in indexed for block in blocks),
            quality_stddev=pstdev(scores) if not issues else None,
            latency_p50_ms=_percentile(latencies, .5) if not issues else None,
            exclusions=tuple(issues),
        ))
    return tuple(candidates)


def _pool(candidates):
    candidates = tuple(candidates)
    if len({c.model_id for c in candidates}) != len(candidates):
        raise ValueError("Duplicate candidate model ID")
    return candidates


def _tie(candidate):
    return (candidate.cost_afp_mean, -candidate.quality_mean,
            candidate.latency_p95_ms, candidate.model_id)


def quality_baseline(candidates: Iterable[Candidate]) -> str | None:
    eligible = [c for c in _pool(candidates) if not c.exclusions]
    best = min(eligible, key=lambda c: (-c.quality_mean, *_tie(c)), default=None)
    return best.model_id if best else None


def pareto_model_ids(candidates: Iterable[Candidate]) -> list[str]:
    eligible = [c for c in _pool(candidates) if not c.exclusions]
    def metrics(c):
        return (-c.quality_mean, c.cost_afp_mean, c.latency_p95_ms)
    return sorted(c.model_id for c in eligible if not any(
        all(a <= b for a, b in zip(metrics(other), metrics(c)))
        and any(a < b for a, b in zip(metrics(other), metrics(c)))
        for other in eligible
    ))


def _reasons(candidate, constraints):
    reasons = list(candidate.exclusions)
    if not reasons and constraints:
        if candidate.quality_mean < constraints.quality_min:
            reasons.append("quality-below-minimum")
        if candidate.cost_afp_mean > constraints.cost_afp_max:
            reasons.append("cost-above-budget")
        if candidate.latency_p95_ms > constraints.latency_p95_ms_max:
            reasons.append("latency-above-maximum")
    return reasons


def select_model(
    candidates: Iterable[Candidate], *, method: str,
    constraints: Constraints | None = None, weights: Weights | None = None,
) -> dict:
    """A minimizes cost within constraints; B maximizes normalized weighted utility."""
    candidates = _pool(candidates)
    if method not in {"A", "B"}:
        raise ValueError("Method must be A or B")
    if method == "A" and (constraints is None or weights is not None):
        raise ValueError("A requires constraints and does not accept weights")
    if method == "B" and weights is None:
        raise ValueError("B requires explicit weights")
    normalized_weights = weights.normalized() if weights else None
    eligible = [c for c in candidates if not c.exclusions]
    # Freeze normalization before hard constraints; infeasible candidates retain anchors.
    attributes = {"quality": "quality_mean", "cost": "cost_afp_mean", "latency": "latency_p95_ms"}
    bounds = {name: {"min": min(getattr(c, attr) for c in eligible),
                     "max": max(getattr(c, attr) for c in eligible)}
              for name, attr in attributes.items()} if eligible and method == "B" else {}
    decisions = {}
    feasible = []
    for c in sorted(candidates, key=lambda c: c.model_id):
        reasons = _reasons(c, constraints)
        row = {"feasible": not reasons, "reasons": reasons, "utilities": None, "score": None}
        if method == "B" and not c.exclusions:
            utilities = {}
            for name, attr in attributes.items():
                low, high = bounds[name]["min"], bounds[name]["max"]
                value = getattr(c, attr)
                utilities[name] = (1.0 if high == low else
                                   (value-low)/(high-low) if name == "quality" else
                                   (high-value)/(high-low))
            row.update(utilities=utilities,
                       score=sum(utilities[n] * normalized_weights[n] for n in attributes))
        decisions[c.model_id] = row
        if not reasons:
            feasible.append(c)
    if method == "A":
        best = min(feasible, key=_tie, default=None)
    else:
        best = min(feasible, key=lambda c: (-decisions[c.model_id]["score"], *_tie(c)), default=None)
    return {
        "policy_version": "single-model-three-metric-v1", "method": method,
        "status": "selected" if best else "no-feasible-model",
        "quality_baseline": quality_baseline(candidates),
        "selected_model": best.model_id if best else None,
        "constraints": asdict(constraints) if constraints else None,
        "weights": asdict(weights) if weights else None,
        "normalized_weights": normalized_weights, "normalization_bounds": bounds,
        "candidates": decisions,
    }
