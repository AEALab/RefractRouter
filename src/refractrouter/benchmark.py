from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable, Mapping

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


def aggregate_observations(
    observations: Iterable[BenchmarkObservation],
) -> dict[str, dict[str, float | int | str]]:
    grouped: dict[str, list[BenchmarkObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.strategy].append(observation)
    summary: dict[str, dict[str, float | int | str]] = {}
    for strategy, items in sorted(grouped.items()):
        results = [item.result for item in items]
        latencies = [result.critical_path_latency_ms for result in results]
        production_costs = [result.total_cost for result in results]
        evaluation_costs = [item.judge.cost for item in items if item.judge]
        failed = sum(bool(result.failure_types) for result in results)
        retried_nodes = sum(
            result.attempts > 1
            for task_result in results
            for result in task_result.node_results
        )
        node_count = sum(len(result.node_results) for result in results)
        billing_units = {result.billing_unit for result in results}
        billing_units.update(
            item.judge.billing_unit for item in items if item.judge is not None
        )
        if len(billing_units) != 1:
            raise ValueError("Benchmark observations contain mixed billing units")
        summary[strategy] = {
            "billing_unit": next(iter(billing_units)),
            "runs": len(items),
            "task_count": len({item.task_id for item in items}),
            "quality_mean": round(mean(result.task_score for result in results), 3),
            "quality_stddev": round(
                pstdev(result.task_score for result in results), 3
            ),
            "production_cost_mean": round(mean(production_costs), 8),
            "production_cost_stddev": round(pstdev(production_costs), 8),
            "production_cost_p50": round(_percentile(production_costs, 0.50), 8),
            "production_cost_p95": round(_percentile(production_costs, 0.95), 8),
            "production_cost_total": round(sum(production_costs), 8),
            "evaluation_cost_total": round(sum(evaluation_costs), 8),
            "critical_path_p50_ms": round(_percentile(latencies, 0.50)),
            "critical_path_p95_ms": round(_percentile(latencies, 0.95)),
            "critical_path_stddev_ms": round(pstdev(latencies)),
            "success_rate": round((len(items) - failed) / len(items), 4),
            "judge_coverage": round(sum(item.judge is not None for item in items) / len(items), 4),
            "retry_rate": round(retried_nodes / max(1, node_count), 4),
        }
    return summary


def oracle_gate(
    summary: Mapping[str, Mapping[str, float | int | str]],
) -> dict[str, float | str | bool]:
    task = summary["task-oracle"]
    node = summary["node-oracle"]
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


def baseline_markdown(summary: Mapping[str, Mapping[str, float | int | str]]) -> str:
    unit = str(next(iter(summary.values()))["billing_unit"])
    rows = [
        "# Real-model baseline summary",
        "",
        f"| Strategy | Quality mean ± sd | Production cost mean ± sd ({unit}) | p50 / p95 latency (ms) | Success | Judge coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for strategy, values in summary.items():
        rows.append(
            f"| `{strategy}` | {float(values['quality_mean']):.3f} ± "
            f"{float(values['quality_stddev']):.3f} | "
            f"{float(values['production_cost_mean']):.8f} ± "
            f"{float(values['production_cost_stddev']):.8f} | "
            f"{int(values['critical_path_p50_ms'])} / "
            f"{int(values['critical_path_p95_ms'])} | "
            f"{float(values['success_rate']):.2%} | "
            f"{float(values['judge_coverage']):.2%} |"
        )
    return "\n".join(rows) + "\n"


def oracle_gap_markdown(gate: Mapping[str, float | str | bool]) -> str:
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
    summary: Mapping[str, Mapping[str, float | int | str]],
) -> str:
    """Render the quality-production-cost frontier; latency remains a reported guardrail."""
    front: set[str] = set()
    for strategy, candidate in summary.items():
        quality = float(candidate["quality_mean"])
        cost = float(candidate["production_cost_mean"])
        dominated = any(
            float(other["quality_mean"]) >= quality
            and float(other["production_cost_mean"]) <= cost
            and (
                float(other["quality_mean"]) > quality
                or float(other["production_cost_mean"]) < cost
            )
            for other_name, other in summary.items()
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
        rows.append(
            f"| `{strategy}` | {float(values['quality_mean']):.3f} | "
            f"{float(values['production_cost_mean']):.8f} | "
            f"{int(values['critical_path_p95_ms'])} | "
            f"{'Yes' if strategy in front else 'No'} |"
        )
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
