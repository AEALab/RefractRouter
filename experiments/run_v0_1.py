from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Sequence

from refractrouter.adapters import FakeModelAdapter
from refractrouter.cli import load_task
from refractrouter.deepagents_executor import DeepAgentsGraphExecutor
from refractrouter.metrics import pareto_front
from refractrouter.model_registry import ModelRegistry
from refractrouter.report_renderer import save_html_report
from refractrouter.routing import node_oracle, node_type_rule, strong_all, task_oracle, weak_all
from refractrouter.schemas import ModelSpec, TaskDAG, TaskResult
from refractrouter.source_pack import attach_source_pack


ROOT = Path(__file__).resolve().parents[1]


def default_registry() -> ModelRegistry:
    return ModelRegistry(
        [
            ModelSpec("cheap-model", "fake", 0.001, 0.002, 0.35),
            ModelSpec("mid-model", "fake", 0.004, 0.008, 0.65),
            ModelSpec("strong-model", "fake", 0.012, 0.024, 0.95),
        ]
    )


def run_single_model_baselines(
    task: TaskDAG,
    registry: ModelRegistry,
) -> dict[str, TaskResult]:
    executor = DeepAgentsGraphExecutor(task, FakeModelAdapter(registry), registry)
    results: dict[str, TaskResult] = {}
    for model in registry.list():
        assignments = {node.node_id: model.model_id for node in task.nodes}
        results[model.model_id] = executor.execute(assignments, f"single:{model.model_id}")
    return results


def probe_node_candidates(
    task: TaskDAG,
    registry: ModelRegistry,
    executor: DeepAgentsGraphExecutor,
    reference_result: TaskResult,
) -> list[TaskResult]:
    """Probe candidate models with a fixed strong-model upstream context."""
    reference_context = {
        result.node_id: result.output for result in reference_result.node_results
    }
    results: list[TaskResult] = []
    for target_node in task.nodes:
        for candidate in registry.list():
            node_result = executor.probe_node(
                target_node.node_id,
                candidate.model_id,
                reference_context,
            )
            failures = (
                (node_result.failure_type,) if node_result.failure_type is not None else ()
            )
            results.append(
                TaskResult(
                    task_id=task.task_id,
                    strategy=f"probe:{target_node.node_id}:{candidate.model_id}",
                    model_assignments={target_node.node_id: candidate.model_id},
                    node_results=(node_result,),
                    final_output="",
                    task_score=node_result.score,
                    total_cost=node_result.cost,
                    critical_path_latency_ms=node_result.latency_ms,
                    failure_types=failures,
                )
            )
    return results


def build_baseline_table(results: Iterable[tuple[str, TaskResult]]) -> str:
    rows = [
        "| Strategy | Task score | Cost (USD) | Critical path (ms) |",
        "|---|---:|---:|---:|",
    ]
    for strategy, result in results:
        rows.append(
            f"| `{strategy}` | {result.task_score:.3f} | "
            f"{result.total_cost:.6f} | {result.critical_path_latency_ms} |"
        )
    return "\n".join(rows) + "\n"


def build_pareto_report(results: Iterable[tuple[str, TaskResult]]) -> str:
    items = tuple(results)
    front = pareto_front(result for _, result in items)
    front_names = {result.strategy for result in front}
    rows = [
        "| Strategy | Task score | Cost (USD) | Critical path (ms) | On front |",
        "|---|---:|---:|---:|:---:|",
    ]
    for name, result in items:
        rows.append(
            f"| `{name}` | {result.task_score:.3f} | "
            f"{result.total_cost:.6f} | {result.critical_path_latency_ms} | "
            f"{'Yes' if result.strategy in front_names else 'No'} |"
        )
    return "\n".join(rows) + "\n"


def build_oracle_gap_report(results: Iterable[tuple[str, TaskResult]]) -> str:
    by_name = dict(results)
    task = by_name.get("task-oracle")
    node = by_name.get("node-oracle")
    if task is None or node is None:
        raise ValueError("Oracle gap report requires task-oracle and node-oracle results")

    quality_delta = node.task_score - task.task_score
    cost_delta = node.total_cost - task.total_cost
    latency_ratio = node.critical_path_latency_ms / max(1, task.critical_path_latency_ms)
    cost_reduction = -cost_delta / max(1e-12, task.total_cost) * 100
    same_quality = abs(quality_delta) < 2
    latency_pass = latency_ratio <= 1.2
    gate = "Go" if same_quality and cost_reduction >= 20 and latency_pass else "No-go"

    return (
        "# Oracle Gap Analysis\n\n"
        "| Metric | task-oracle | node-oracle | Delta |\n"
        "|---|---:|---:|---:|\n"
        f"| Task score | {task.task_score:.3f} | {node.task_score:.3f} | {quality_delta:+.3f} |\n"
        f"| Cost (USD) | {task.total_cost:.6f} | {node.total_cost:.6f} | {cost_delta:+.6f} |\n"
        f"| Critical path (ms) | {task.critical_path_latency_ms} | {node.critical_path_latency_ms} | {latency_ratio:.2f}x |\n\n"
        f"- Cost reduction: {cost_reduction:.2f}%\n"
        f"- Latency ratio: {latency_ratio:.2f}x\n"
        f"- Full three-objective gate: **{gate}**\n\n"
        "The current canonical task shows a clear quality-cost advantage for node-oracle, "
        "but it fails the latency ceiling in the v0.1 Go/No-Go rule. Node candidates are "
        "probed with a fixed strong-model upstream context.\n"
    )


def build_run_record(task: TaskDAG, result: TaskResult, metadata: dict[str, str]) -> dict[str, object]:
    task_result = asdict(result)
    task_result["total_cost_usd"] = task_result.pop("total_cost")
    task_result.pop("billing_unit", None)
    for node in task_result["node_results"]:
        node["cost_usd"] = node.pop("cost")
        node.pop("billing_unit", None)
    return {
        "task_id": task.task_id,
        "strategy": result.strategy,
        "task_result": task_result,
        "metadata": metadata,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RefractRouter v0.1 experiment")
    parser.add_argument("--task", type=Path, default=ROOT / "data" / "tasks" / "report_001.json")
    parser.add_argument("--source-pack-root", type=Path, default=ROOT / "data" / "source_packs")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "v0.1")
    args = parser.parse_args(argv)

    task_path = args.task.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    task = attach_source_pack(load_task(task_path), args.source_pack_root.resolve())
    registry = default_registry()
    executor = DeepAgentsGraphExecutor(task, FakeModelAdapter(registry), registry)

    single_results = run_single_model_baselines(task, registry)
    single_model_results = list(single_results.values())

    weak = executor.execute(weak_all(task, registry), "weak-all")
    strong = executor.execute(strong_all(task, registry), "strong-all")
    task_best = executor.execute(task_oracle(task, registry, single_model_results), "task-oracle")
    node_probes = probe_node_candidates(task, registry, executor, strong)
    node_best = executor.execute(node_oracle(task, registry, node_probes), "node-oracle")
    rule = executor.execute(
        node_type_rule(
            task,
            registry,
            {
                "planning": "mid-model",
                "extraction": "cheap-model",
                "synthesis": "strong-model",
                "generation": "strong-model",
                "rendering": "mid-model",
                "verification": "cheap-model",
            },
        ),
        "node-type-rule",
    )

    strategy_results = [
        ("weak-all", weak),
        ("strong-all", strong),
        ("node-type-rule", rule),
        ("task-oracle", task_best),
        ("node-oracle", node_best),
    ]

    baseline_path = output_dir / "baseline-table.md"
    baseline_path.write_text(build_baseline_table(strategy_results), encoding="utf-8")
    pareto_path = output_dir / "pareto-front.md"
    pareto_path.write_text(build_pareto_report(strategy_results), encoding="utf-8")
    oracle_gap_path = output_dir / "oracle-gap.md"
    oracle_gap_path.write_text(build_oracle_gap_report(strategy_results), encoding="utf-8")

    html_path = output_dir / "report_001.html"
    save_html_report(html_path, node_best.final_output)

    summary = {
        "task_id": task.task_id,
        "strategies": {
            name: {
                "task_score": result.task_score,
                "total_cost_usd": result.total_cost,
                "critical_path_latency_ms": result.critical_path_latency_ms,
                "model_assignments": result.model_assignments,
            }
            for name, result in strategy_results
        },
    }
    summary_path = output_dir / "experiment-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = {
        "framework": "deepagents",
        "adapter": "fake",
        "node_oracle_probe": "strong-upstream",
        "scoring_rubric_version": task.scoring_rubric_version,
    }
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for _, result in strategy_results:
        strategy_path = runs_dir / f"{result.strategy}.json"
        strategy_path.write_text(
            json.dumps(build_run_record(task, result, metadata), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    record_path = output_dir / "run-record.json"
    record_path.write_text(
        json.dumps(build_run_record(task, node_best, metadata), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {baseline_path}")
    print(f"Wrote {pareto_path}")
    print(f"Wrote {oracle_gap_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {record_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
