from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .cli import load_task
from .schemas import TaskDAG
from .source_pack import attach_source_pack


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    schema_version: str
    train_tasks: tuple[TaskDAG, ...]
    test_tasks: tuple[TaskDAG, ...]
    pilot_task_ids: tuple[str, ...]
    human_audit_task_ids: tuple[str, ...]

    @property
    def all_tasks(self) -> tuple[TaskDAG, ...]:
        return self.train_tasks + self.test_tasks


def load_benchmark_dataset(
    manifest_path: Path,
    tasks_root: Path,
    source_pack_root: Path,
) -> BenchmarkDataset:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "v0.1":
        raise ValueError("Unsupported benchmark dataset schema_version")
    train_ids = _ids(data, "train_task_ids")
    test_ids = _ids(data, "test_task_ids")
    pilot_ids = _ids(data, "pilot_task_ids")
    audit_ids = _ids(data, "human_audit_task_ids")
    if set(train_ids) & set(test_ids):
        raise ValueError("Train and test task IDs must be disjoint")
    all_ids = set(train_ids) | set(test_ids)
    if not set(pilot_ids) <= all_ids:
        raise ValueError("Pilot task IDs must belong to the dataset")
    if not set(audit_ids) <= all_ids:
        raise ValueError("Human-audit task IDs must belong to the dataset")

    def load_many(task_ids: tuple[str, ...]) -> tuple[TaskDAG, ...]:
        tasks = tuple(
            attach_source_pack(load_task(tasks_root / f"{task_id}.json"), source_pack_root)
            for task_id in task_ids
        )
        for task in tasks:
            if len(task.source_documents) < 8:
                raise ValueError(f"Task {task.task_id} must contain at least eight sources")
        return tasks

    return BenchmarkDataset(
        schema_version="v0.1",
        train_tasks=load_many(train_ids),
        test_tasks=load_many(test_ids),
        pilot_task_ids=pilot_ids,
        human_audit_task_ids=audit_ids,
    )


def _ids(data: object, key: str) -> tuple[str, ...]:
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        raise ValueError(f"Dataset field must be an array: {key}")
    values = tuple(str(value) for value in data[key])
    if len(values) != len(set(values)):
        raise ValueError(f"Dataset field contains duplicate IDs: {key}")
    return values
