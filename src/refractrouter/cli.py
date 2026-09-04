from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters import FakeModelAdapter
from .graph_executor import GraphExecutor
from .model_registry import ModelRegistry
from .report_renderer import save_html_report
from .routing import strong_all, weak_all
from .schemas import ModelSpec, NodeSpec, TaskDAG
from .source_pack import attach_source_pack


def load_task(path: Path) -> TaskDAG:
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = tuple(
        NodeSpec(
            node_id=node["node_id"],
            node_type=node["node_type"],
            prompt_template=node["prompt_template"],
            parents=tuple(node.get("parents", [])),
            expected_output=node.get("expected_output"),
        )
        for node in data["nodes"]
    )
    return TaskDAG(
        task_id=data["task_id"],
        domain=data["domain"],
        nodes=nodes,
        required_sections=tuple(data.get("required_sections", [])),
        output_constraints=tuple(data.get("output_constraints", [])),
        source_pack_id=data.get("source_pack_id"),
        scoring_rubric_version=data.get("scoring_rubric_version", "v0.1"),
    )


def default_registry() -> ModelRegistry:
    return ModelRegistry(
        [
            ModelSpec("cheap-model", "fake", 0.001, 0.002, 0.35),
            ModelSpec("mid-model", "fake", 0.004, 0.008, 0.65),
            ModelSpec("strong-model", "fake", 0.012, 0.024, 0.95),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="refractrouter")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one task DAG with a baseline strategy")
    run_parser.add_argument("--task", required=True, type=Path)
    run_parser.add_argument("--strategy", choices=("weak-all", "strong-all"), default="strong-all")
    run_parser.add_argument("--output", required=True, type=Path)
    run_parser.add_argument("--source-pack-root", type=Path)

    args = parser.parse_args()
    if args.command == "run":
        task = load_task(args.task)
        source_pack_root = args.source_pack_root or args.task.parent.parent / "source_packs"
        task = attach_source_pack(task, source_pack_root)
        registry = default_registry()
        assignments = weak_all(task, registry) if args.strategy == "weak-all" else strong_all(task, registry)
        executor = GraphExecutor(task, FakeModelAdapter(registry), registry)
        result = executor.execute(assignments, args.strategy)
        save_html_report(args.output, result.final_output)
        print(
            json.dumps(
                {
                    "task_id": result.task_id,
                    "strategy": result.strategy,
                    "task_score": result.task_score,
                    "cost_usd": result.total_cost_usd,
                    "critical_path_latency_ms": result.critical_path_latency_ms,
                    "failure_types": result.failure_types,
                    "output": str(args.output),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
