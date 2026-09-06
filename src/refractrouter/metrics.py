from __future__ import annotations

from collections.abc import Iterable

from .schemas import TaskResult


def aggregate_results(results: Iterable[TaskResult]) -> dict[str, float]:
    results = tuple(results)
    if not results:
        return {
            "count": 0,
            "quality": 0.0,
            "cost": 0.0,
            "critical_path_latency_ms": 0.0,
        }
    return {
        "count": len(results),
        "quality": sum(result.task_score for result in results) / len(results),
        "cost": sum(result.total_cost for result in results) / len(results),
        "critical_path_latency_ms": sum(result.critical_path_latency_ms for result in results) / len(results),
    }


def pareto_front(results: Iterable[TaskResult]) -> tuple[TaskResult, ...]:
    items = tuple(results)
    front: list[TaskResult] = []
    for candidate in items:
        dominated = any(
            other.task_score >= candidate.task_score
            and other.total_cost <= candidate.total_cost
            and other.critical_path_latency_ms <= candidate.critical_path_latency_ms
            and (
                other.task_score > candidate.task_score
                or other.total_cost < candidate.total_cost
                or other.critical_path_latency_ms < candidate.critical_path_latency_ms
            )
            for other in items
            if other is not candidate
        )
        if not dominated:
            front.append(candidate)
    return tuple(front)
