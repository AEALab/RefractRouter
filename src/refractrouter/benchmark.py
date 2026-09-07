from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev
from math import isfinite
from typing import Any, Iterable, Mapping

from .judge import JudgeEvaluation
from .schemas import TaskResult


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    task_id: str
    repeat: int
    strategy: str
    result: TaskResult
    judge: JudgeEvaluation | None = None
    judge_error: str | None = None


def comparison_exclusions(item: BenchmarkObservation) -> list[str]:
    """A comparison uses successful, independently judged runs for all three metrics."""
    reasons = []
    if item.result.failure_types or any(n.status != "ok" for n in item.result.node_results):
        reasons.append("failed-execution")
    if not item.result.final_output:
        reasons.append("missing-final-output")
    if item.judge is None:
        reasons.append("missing-judge")
    if item.judge_error:
        reasons.append("judge:" + item.judge_error)
    metrics = {"cost": item.result.total_cost, "latency": item.result.critical_path_latency_ms}
    if item.judge is not None:
        metrics["quality"] = item.judge.final_score
    for name, value in metrics.items():
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not isfinite(value) or value < 0 or (name == "quality" and value > 100)):
            reasons.append("invalid-" + name)
    return reasons


def aggregate_observations(
    observations: Iterable[BenchmarkObservation],
    *,
    expected_blocks: Iterable[tuple[str, int]] | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[BenchmarkObservation]] = defaultdict(list)
    seen = set()
    for observation in observations:
        key = (observation.task_id, observation.repeat, observation.strategy)
        if key in seen:
            raise ValueError(f"Duplicate observation: {key}")
        seen.add(key)
        grouped[observation.strategy].append(observation)
    observed_blocks = {key[:2] for key in seen}
    blocks = set(expected_blocks) if expected_blocks is not None else observed_blocks
    if observed_blocks - blocks:
        raise ValueError("Observation outside expected task/repeat blocks")
    summary = {}
    for strategy, items in sorted(grouped.items()):
        items = sorted(items, key=lambda item: (item.task_id, item.repeat))
        results = [item.result for item in items]
        included, excluded = [], []
        for item in items:
            reasons = comparison_exclusions(item)
            if reasons:
                excluded.append(dict(task_id=item.task_id, repeat=item.repeat, reasons=reasons))
            else:
                included.append(item)
        missing = sorted(blocks - {(item.task_id, item.repeat) for item in items})
        excluded.extend(dict(task_id=task, repeat=repeat, reasons=["missing-run"])
                        for task, repeat in missing)
        judged_scores = [item.judge.final_score for item in included]
        latencies = [item.result.critical_path_latency_ms for item in included]
        production_costs = [item.result.total_cost for item in included]
        all_costs = [result.total_cost for result in results]
        evaluation_costs = [item.judge.cost for item in items if item.judge]
        failed = sum(bool(result.failure_types) or any(n.status != "ok" for n in result.node_results)
                     for result in results)
        retried_nodes = sum(n.attempts > 1 for result in results for n in result.node_results)
        node_count = sum(len(result.node_results) for result in results)
        billing_units = {result.billing_unit for result in results}
        billing_units.update(item.judge.billing_unit for item in items if item.judge is not None)
        if len(billing_units) != 1:
            raise ValueError("Benchmark observations contain mixed billing units")
        judged = sum(item.judge is not None and not item.judge_error for item in items)
        summary[strategy] = {
            "billing_unit": next(iter(billing_units)),
            "runs": len(items), "expected_runs": len(blocks),
            "task_count": len({item.task_id for item in items}),
            "cohort": {
                "policy": "successful-independently-judged-v1",
                "included": [dict(task_id=item.task_id, repeat=item.repeat) for item in included],
                "excluded": sorted(excluded, key=lambda row: (row["task_id"], row["repeat"])),
                "complete": len(included) == len(blocks),
            },
            "comparison_runs": len(included),
            "quality_mean": round(mean(judged_scores), 3) if included else None,
            "quality_stddev": round(pstdev(judged_scores), 3) if included else None,
            "production_cost_mean": round(mean(production_costs), 8) if included else None,
            "production_cost_stddev": round(pstdev(production_costs), 8) if included else None,
            "production_cost_p50": round(_percentile(production_costs, 0.50), 8) if included else None,
            "production_cost_p95": round(_percentile(production_costs, 0.95), 8) if included else None,
            # All recorded strategy runs, including excluded failures. The runner's ledger
            # remains authoritative for billed totals (reused baselines are not new calls).
            "production_cost_total": _known_total(all_costs),
            "evaluation_cost_total": _known_total(evaluation_costs),
            "critical_path_p50_ms": round(_percentile(latencies, 0.50)) if included else None,
            "critical_path_p95_ms": round(_percentile(latencies, 0.95)) if included else None,
            "critical_path_stddev_ms": round(pstdev(latencies)) if included else None,
            "success_rate": round((len(items) - failed) / len(blocks), 4),
            "judge_coverage": round(judged / len(blocks), 4),
            "retry_rate": round(retried_nodes / max(1, node_count), 4),
        }
    return summary


def oracle_gate(
    summary: Mapping[str, Mapping[str, Any]],
) -> dict[str, float | str | bool | None]:
    task = summary["task-oracle"]
    node = summary["node-oracle"]
    cohorts_match = task.get("cohort", {}).get("included") == node.get("cohort", {}).get("included")
    cohorts_complete = all(values.get("cohort", {}).get("complete", True) for values in (task, node))
    judge_complete = float(task["judge_coverage"]) == 1 and float(node["judge_coverage"]) == 1
    if not judge_complete or not cohorts_complete or not cohorts_match:
        return {
            "quality_delta": None, "cost_reduction_percent": None,
            "relative_cost_delta_percent": None, "p95_latency_ratio": None,
            "quality_path_pass": False, "cost_path_pass": False,
            "latency_pass": False, "reliability_pass": False,
            "judge_complete": judge_complete, "comparison_complete": False,
            "cohorts_aligned": cohorts_match,
            "decision": "Insufficient-evidence",
        }
    quality_delta = float(node["quality_mean"]) - float(task["quality_mean"])
    task_cost = float(task["production_cost_mean"])
    node_cost = float(node["production_cost_mean"])
    cost_reduction = (task_cost - node_cost) / max(task_cost, 1e-12) * 100
    latency_ratio = float(node["critical_path_p95_ms"]) / max(
        float(task["critical_path_p95_ms"]), 1
    )
    relative_cost_delta = abs(node_cost - task_cost) / max(task_cost, 1e-12) * 100
    quality_path_pass = relative_cost_delta < 5 and quality_delta >= 5
    cost_path_pass = abs(quality_delta) < 2 and cost_reduction >= 20
    latency_pass = latency_ratio <= 1.2
    reliability_pass = float(node["success_rate"]) >= float(task["success_rate"])
    judge_complete = (
        float(task["judge_coverage"]) == 1.0
        and float(node["judge_coverage"]) == 1.0
    )
    passed = (
        (quality_path_pass or cost_path_pass)
        and latency_pass
        and reliability_pass
        and judge_complete
    )
    return {
        "quality_delta": round(quality_delta, 6),
        "cost_reduction_percent": round(cost_reduction, 6),
        "relative_cost_delta_percent": round(relative_cost_delta, 6),
        "p95_latency_ratio": round(latency_ratio, 6),
        "quality_path_pass": quality_path_pass,
        "cost_path_pass": cost_path_pass,
        "latency_pass": latency_pass,
        "reliability_pass": reliability_pass,
        "judge_complete": judge_complete,
        "comparison_complete": True,
        "cohorts_aligned": cohorts_match,
        "decision": "Go" if passed else "No-go",
    }


def failure_taxonomy(
    observations: Iterable[BenchmarkObservation],
) -> dict[str, int]:
    failures: Counter[str] = Counter()
    for observation in observations:
        failures.update(observation.result.failure_types)
        if observation.judge_error:
            failures[f"judge:{observation.judge_error}"] += 1
    return dict(sorted(failures.items()))


def baseline_markdown(summary: Mapping[str, Mapping[str, Any]]) -> str:
    unit = str(next(iter(summary.values()))["billing_unit"])
    rows = [
        "# Real-model baseline summary",
        "",
        "Quality, cost and latency use the same successful, independently judged task/repeat cohort.",
        "Success and judge coverage use all expected blocks; excluded costs remain in totals and the run ledger.",
        "Partial cohorts are descriptive; paired comparisons are the primary comparison evidence.",
        "",
        f"| Strategy | Quality mean ± sd | Production cost mean ± sd ({unit}) | p50 / p95 latency (ms) | Success | Judge coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for strategy, values in summary.items():
        quality = (
            f"{float(values['quality_mean']):.3f} ± {float(values['quality_stddev']):.3f}"
            if values["quality_mean"] is not None else "N/A (unjudged)"
        )
        rows.append(
            f"| `{strategy}` | {quality} | "
            f"{_display(values['production_cost_mean'], '.8f')} ± "
            f"{_display(values['production_cost_stddev'], '.8f')} | "
            f"{_display(values['critical_path_p50_ms'], '.0f')} / "
            f"{_display(values['critical_path_p95_ms'], '.0f')} | "
            f"{float(values['success_rate']):.2%} | "
            f"{float(values['judge_coverage']):.2%} |"
        )
    rows.extend(_cohort_notes(summary))
    return "\n".join(rows) + "\n"


def oracle_gap_markdown(gate: Mapping[str, float | str | bool | None]) -> str:
    if not gate["judge_complete"] or not gate.get("comparison_complete", True):
        return (
            "# Real-model oracle gap\n\n"
            "Oracle comparison evidence is incomplete or task/repeat cohorts differ. Quality, cost and latency deltas are not "
            "interpretable as a valid oracle comparison. Deterministic fallback scores are not "
            "independent quality evaluations.\n\n"
            f"- Decision: **{gate['decision']}**\n"
        )
    return (
        "# Real-model oracle gap\n\n"
        f"- Quality delta: {float(gate['quality_delta']):+.3f}\n"
        f"- Production cost reduction: {float(gate['cost_reduction_percent']):.2f}%\n"
        f"- p95 latency ratio: {float(gate['p95_latency_ratio']):.2f}x\n"
        f"- Same-cost quality path: {gate['quality_path_pass']}\n"
        f"- Same-quality cost path: {gate['cost_path_pass']}\n"
        f"- Latency pass: {gate['latency_pass']}\n"
        f"- Reliability pass: {gate['reliability_pass']}\n"
        f"- Judge complete: {gate['judge_complete']}\n"
        + (f"- Minimum three repeats: {gate['repeated']}\n"
           f"- Routing assignment changes observed: {gate['routing_change_observed']}\n"
           f"- Complete evaluation evidence: {gate['matrix_complete']}\n"
           if "repeated" in gate else "")
        + f"- Decision: **{gate['decision']}**\n"
    )


def pareto_front_markdown(
    summary: Mapping[str, Mapping[str, Any]],
) -> str:
    """Render the quality-production-cost frontier; latency remains a reported guardrail."""
    front: set[str] = set()
    eligible = {name: values for name, values in summary.items()
                if values["quality_mean"] is not None and float(values.get("judge_coverage", 1)) == 1
                and float(values.get("success_rate", 1)) == 1
                and values.get("cohort", {}).get("complete", True)}
    for strategy, candidate in summary.items():
        if strategy not in eligible:
            continue
        quality = float(candidate["quality_mean"])
        cost = float(candidate["production_cost_mean"])
        dominated = any(
            float(other["quality_mean"]) >= quality
            and float(other["production_cost_mean"]) <= cost
            and (
                float(other["quality_mean"]) > quality
                or float(other["production_cost_mean"]) < cost
            )
            for other_name, other in eligible.items()
            if other_name != strategy
        )
        if not dominated:
            front.add(strategy)
    unit = str(next(iter(summary.values()))["billing_unit"])
    rows = [
        "# Real-model Pareto front",
        "",
        "The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.",
        "",
        f"| Strategy | Quality mean | Production cost mean ({unit}) | p95 latency (ms) | On quality-cost front |",
        "|---|---:|---:|---:|:---:|",
    ]
    for strategy, values in summary.items():
        quality = f"{float(values['quality_mean']):.3f}" if values["quality_mean"] is not None else "N/A"
        rows.append(
            f"| `{strategy}` | {quality} | "
            f"{_display(values['production_cost_mean'], '.8f')} | "
            f"{_display(values['critical_path_p95_ms'], '.0f')} | "
            f"{'Yes' if strategy in front else 'No'} |"
        )
    rows.extend(_cohort_notes(summary))
    return "\n".join(rows) + "\n"


def failure_taxonomy_markdown(failures: Mapping[str, int]) -> str:
    rows = ["# Failure taxonomy", "", "| Failure type | Count |", "|---|---:|"]
    rows.extend(f"| `{name}` | {count} |" for name, count in failures.items())
    if not failures:
        rows.append("| _none_ | 0 |")
    return "\n".join(rows) + "\n"


def _percentile(values: list[int] | list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _display(value, specification):
    return format(value, specification) if value is not None else "N/A"


def _cohort_notes(summary):
    lines = ["", "Cohorts (task/repeat; same blocks for quality, cost and latency):"]
    for strategy, values in summary.items():
        if "cohort" not in values:
            continue
        cohort = values["cohort"]
        blocks = ", ".join(f"{r['task_id']}/{r['repeat']}" for r in cohort["included"]) or "none"
        lines.append(f"- `{strategy}`: {values['comparison_runs']}/{values['expected_runs']} blocks: {blocks}.")
        for row in cohort["excluded"]:
            lines.append(f"  Excluded {row['task_id']}/{row['repeat']}: {', '.join(row['reasons'])}.")
    return lines


def _known_total(values):
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not isfinite(value) or value < 0 for value in values):
        return None
    return round(sum(values), 8)
