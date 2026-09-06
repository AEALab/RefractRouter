from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from .model_registry import ModelRegistry
from .schemas import TaskDAG, TaskResult


def weak_all(task: TaskDAG, registry: ModelRegistry) -> dict[str, str]:
    model = registry.cheapest()
    return {node.node_id: model.model_id for node in task.nodes}


def strong_all(task: TaskDAG, registry: ModelRegistry) -> dict[str, str]:
    model = registry.strongest()
    return {node.node_id: model.model_id for node in task.nodes}


def task_level_router(
    task: TaskDAG,
    registry: ModelRegistry,
    training_results: Sequence[TaskResult] = (),
) -> dict[str, str]:
    if not training_results:
        model = registry.strongest()
    else:
        scores: dict[str, list[float]] = defaultdict(list)
        for result in training_results:
            if result.task_id == task.task_id:
                continue
            for node in result.node_results:
                scores[node.model_id].append(node.score)
        model_id = max(scores, key=lambda mid: (sum(scores[mid]) / len(scores[mid]), -registry.get(mid).input_cost_per_1k))
        model = registry.get(model_id)
    return {node.node_id: model.model_id for node in task.nodes}


def node_type_rule(
    task: TaskDAG,
    registry: ModelRegistry,
    rules: Mapping[str, str],
) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for node in task.nodes:
        model_id = rules.get(node.node_type)
        if model_id is None:
            raise ValueError(f"Missing node-type rule for: {node.node_type}")
        registry.get(model_id)
        assignments[node.node_id] = model_id
    return assignments


def statistical_q(
    task: TaskDAG,
    registry: ModelRegistry,
    training_results: Sequence[TaskResult],
) -> dict[str, str]:
    scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    for result in training_results:
        if result.task_id == task.task_id:
            continue
        for node in result.node_results:
            scores[(node.node_type, node.model_id)].append(node.score)
    assignments: dict[str, str] = {}
    for node in task.nodes:
        candidates = [
            model for model in registry.list()
            if (node.node_type, model.model_id) in scores
        ]
        if not candidates:
            model = registry.cheapest()
        else:
            model = max(
                candidates,
                key=lambda candidate: (
                    sum(scores[(node.node_type, candidate.model_id)]) / len(scores[(node.node_type, candidate.model_id)]),
                    -candidate.input_cost_per_1k,
                ),
            )
        assignments[node.node_id] = model.model_id
    return assignments


def task_oracle(
    task: TaskDAG,
    registry: ModelRegistry,
    all_results: Sequence[TaskResult],
) -> dict[str, str]:
    candidates = [result for result in all_results if result.task_id == task.task_id]
    if not candidates:
        return strong_all(task, registry)
    best = max(candidates, key=lambda result: (result.task_score, -result.total_cost))
    model_id = next(iter(best.model_assignments.values()))
    return {node.node_id: model_id for node in task.nodes}


def node_oracle(
    task: TaskDAG,
    registry: ModelRegistry,
    all_results: Sequence[TaskResult],
) -> dict[str, str]:
    node_scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    for result in all_results:
        if result.task_id != task.task_id:
            continue
        for node in result.node_results:
            node_scores[(node.node_id, node.model_id)].append(node.score)
    assignments: dict[str, str] = {}
    for node in task.nodes:
        candidates = [
            model for model in registry.list()
            if (node.node_id, model.model_id) in node_scores
        ]
        if not candidates:
            model = registry.cheapest()
        else:
            model = max(
                candidates,
                key=lambda candidate: (
                    sum(node_scores[(node.node_id, candidate.model_id)])
                    / len(node_scores[(node.node_id, candidate.model_id)]),
                    -candidate.input_cost_per_1k,
                ),
            )
        assignments[node.node_id] = model.model_id
    return assignments
