from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from refractrouter.adapters import ModelAdapter, OpenAICompatibleAdapter
from refractrouter.benchmark import (
    BenchmarkObservation,
    aggregate_observations,
    baseline_markdown,
    failure_taxonomy,
    failure_taxonomy_markdown,
    oracle_gap_markdown,
    oracle_gate,
    pareto_front_markdown,
)
from refractrouter.dataset import BenchmarkDataset, load_benchmark_dataset
from refractrouter.deepagents_executor import DeepAgentsGraphExecutor
from refractrouter.judge import IndependentJudge, apply_judge_score
from refractrouter.judge import JudgeEvaluation
from refractrouter.manifest import ModelManifest, load_model_manifest
from refractrouter.model_registry import ModelRegistry
from refractrouter.openai_compatible import ModelInvocationError, OpenAICompatibleClient
from refractrouter.routing import (
    node_oracle,
    node_type_rule,
    statistical_q,
    task_level_router,
    task_oracle,
)
from refractrouter.schemas import ModelSpec, NodeResult, TaskDAG, TaskResult


ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class CostLedger:
    billing_unit: str
    production_limit: float
    evaluation_limit: float
    estimated_production_input_tokens: int
    estimated_evaluation_input_tokens: int
    estimated_output_tokens: int
    production_spent: float = 0.0
    evaluation_spent: float = 0.0


@dataclass(frozen=True, slots=True)
class TaskStrategyBundle:
    results: dict[str, TaskResult]
    single_results: dict[str, TaskResult]


class BudgetedAdapter:
    def __init__(self, delegate: ModelAdapter, ledger: CostLedger):
        self.delegate = delegate
        self.ledger = ledger

    def invoke(self, task, node, prompt, context, model):
        reserve = _estimated_invocation_cost(
            model,
            self.ledger.estimated_production_input_tokens,
            self.ledger.estimated_output_tokens,
        )
        if self.ledger.production_spent + reserve > self.ledger.production_limit:
            return NodeResult(
                node_id=node.node_id,
                node_type=node.node_type,
                model_id=model.model_id,
                output="",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                billing_unit=model.billing_unit,
                latency_ms=0,
                status="failed",
                failure_type="production-budget-exhausted",
                attempts=0,
                error_message="Paid-run production budget exhausted",
            )
        result = self.delegate.invoke(task, node, prompt, context, model)
        self.ledger.production_spent += result.cost
        return result


def _estimated_invocation_cost(
    model: ModelSpec,
    input_tokens: int,
    output_tokens: int,
) -> float:
    return (
        input_tokens / 1000 * model.input_cost_per_1k
        + output_tokens / 1000 * model.output_cost_per_1k
    )


def run_task_strategies(
    task: TaskDAG,
    registry: ModelRegistry,
    adapter: ModelAdapter,
    training_results: Sequence[TaskResult] = (),
    *,
    include_learned: bool,
) -> dict[str, TaskResult]:
    return build_task_strategy_bundle(
        task,
        registry,
        adapter,
        training_results,
        include_learned=include_learned,
    ).results


def build_task_strategy_bundle(
    task: TaskDAG,
    registry: ModelRegistry,
    adapter: ModelAdapter,
    training_results: Sequence[TaskResult] = (),
    *,
    include_learned: bool,
) -> TaskStrategyBundle:
    executor = DeepAgentsGraphExecutor(task, adapter, registry)
    singles: dict[str, TaskResult] = {}
    for model in registry.list():
        assignments = {node.node_id: model.model_id for node in task.nodes}
        singles[model.model_id] = executor.execute(
            assignments, f"single:{model.model_id}"
        )

    weak_id = registry.cheapest().model_id
    strong_id = registry.strongest().model_id
    weak = _retag(singles[weak_id], "weak-all")
    strong = _retag(singles[strong_id], "strong-all")
    task_assignments = task_oracle(task, registry, tuple(singles.values()))
    task_model_id = next(iter(task_assignments.values()))
    task_best = _retag(singles[task_model_id], "task-oracle", task_assignments)

    reference_context = {
        result.node_id: result.output for result in strong.node_results
    }
    probes: list[TaskResult] = []
    for node in task.nodes:
        for model in registry.list():
            node_result = executor.probe_node(node.node_id, model.model_id, reference_context)
            probes.append(_probe_result(task, node_result))
    node_assignments = node_oracle(task, registry, probes)
    node_best = executor.execute(node_assignments, "node-oracle")

    priced = sorted(
        registry.list(),
        key=lambda model: (
            model.input_cost_per_1k + model.output_cost_per_1k,
            model.model_id,
        ),
    )
    middle = priced[len(priced) // 2].model_id
    rules = {
        "planning": middle,
        "extraction": weak_id,
        "synthesis": strong_id,
        "generation": strong_id,
        "rendering": middle,
        "verification": weak_id,
    }
    rule = executor.execute(node_type_rule(task, registry, rules), "node-type-rule")
    results = {
        "weak-all": weak,
        "strong-all": strong,
        "node-type-rule": rule,
        "task-oracle": task_best,
        "node-oracle": node_best,
    }
    if include_learned:
        results["task-level-router"] = executor.execute(
            task_level_router(task, registry, training_results),
            "task-level-router",
        )
        results["statistical-q"] = executor.execute(
            statistical_q(task, registry, training_results),
            "statistical-q",
        )
    return TaskStrategyBundle(results=results, single_results=singles)


def _retag(
    result: TaskResult,
    strategy: str,
    assignments: Mapping[str, str] | None = None,
) -> TaskResult:
    return replace(
        result,
        strategy=strategy,
        model_assignments=dict(assignments or result.model_assignments),
    )


def _probe_result(task: TaskDAG, result: NodeResult) -> TaskResult:
    failures = (result.failure_type,) if result.failure_type else ()
    return TaskResult(
        task_id=task.task_id,
        strategy=f"probe:{result.node_id}:{result.model_id}",
        model_assignments={result.node_id: result.model_id},
        node_results=(result,),
        final_output="",
        task_score=result.score,
        total_cost=result.cost,
        billing_unit=result.billing_unit,
        critical_path_latency_ms=result.latency_ms,
        failure_types=failures,
    )


def select_judged_task_oracle(
    single_results: Mapping[str, TaskResult],
    evaluations: Mapping[str, JudgeEvaluation],
) -> str:
    if set(single_results) != set(evaluations):
        raise ValueError("Task-oracle selection requires every single-model evaluation")
    return max(
        single_results,
        key=lambda model_id: (
            evaluations[model_id].final_score,
            -single_results[model_id].total_cost,
        ),
    )


def phase_tasks(
    dataset: BenchmarkDataset,
    phase: str,
) -> tuple[tuple[TaskDAG, ...], tuple[TaskDAG, ...], bool]:
    if phase == "dry-run":
        return (), (dataset.all_tasks[0],), False
    if phase == "pilot":
        selected = set(dataset.pilot_task_ids)
        return (
            tuple(task for task in dataset.train_tasks if task.task_id in selected),
            tuple(task for task in dataset.test_tasks if task.task_id in selected),
            True,
        )
    if phase == "final":
        return dataset.train_tasks, dataset.test_tasks, True
    raise ValueError(f"Unknown phase: {phase}")


def call_plan(
    train_tasks: Sequence[TaskDAG],
    test_tasks: Sequence[TaskDAG],
    candidate_count: int,
    repeats: int,
    include_learned: bool,
) -> dict[str, int]:
    node_count = len((train_tasks or test_tasks)[0].nodes)
    training_calls = len(train_tasks) * candidate_count * node_count
    per_test = candidate_count * node_count + candidate_count * node_count + 2 * node_count
    if include_learned:
        per_test += 2 * node_count
    strategies = 7 if include_learned else 5
    production_calls = training_calls + len(test_tasks) * repeats * per_test
    judge_calls = len(test_tasks) * repeats * strategies
    return {
        "training_model_calls": training_calls,
        "production_model_calls": production_calls,
        "judge_model_calls": judge_calls,
        "total_model_calls": production_calls + judge_calls,
    }


def estimate_costs(
    plan: Mapping[str, int],
    manifest: ModelManifest,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, float]:
    strongest_price = max(
        manifest.candidates,
        key=lambda model: model.input_cost_per_1k + model.output_cost_per_1k,
    )
    production = int(plan["production_model_calls"]) * (
        input_tokens / 1000 * strongest_price.input_cost_per_1k
        + output_tokens / 1000 * strongest_price.output_cost_per_1k
    )
    judge = manifest.judge
    evaluation = int(plan["judge_model_calls"]) * (
        input_tokens * 2 / 1000 * judge.input_cost_per_1k
        + output_tokens / 1000 * judge.output_cost_per_1k
    )
    return {
        "billing_unit": manifest.billing_unit,
        "production_upper_estimate": round(production, 2),
        "evaluation_upper_estimate": round(evaluation, 2),
        "total_upper_estimate": round(production + evaluation, 2),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the RefractRouter real-model benchmark")
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "data" / "benchmarks" / "v0.1.json"
    )
    parser.add_argument(
        "--tasks-root", type=Path, default=ROOT / "data" / "tasks"
    )
    parser.add_argument(
        "--source-pack-root", type=Path, default=ROOT / "data" / "source_packs"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "data" / "model-manifests" / "openai-gpt-5.4.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "reports" / "v0.1-real"
    )
    parser.add_argument("--phase", choices=("dry-run", "pilot", "final"), default="dry-run")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--max-production-cost", type=float)
    parser.add_argument("--max-evaluation-cost", type=float)
    parser.add_argument("--estimated-input-tokens", type=int, default=4000)
    parser.add_argument("--estimated-output-tokens", type=int, default=1200)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.timeout_seconds <= 0 or args.max_retries < 0:
        parser.error("timeout must be positive and max retries cannot be negative")

    dataset = load_benchmark_dataset(
        args.dataset.resolve(), args.tasks_root.resolve(), args.source_pack_root.resolve()
    )
    manifest = load_model_manifest(args.manifest.resolve())
    train_tasks, test_tasks, include_learned = phase_tasks(dataset, args.phase)
    plan = call_plan(
        train_tasks, test_tasks, len(manifest.candidates), args.repeats, include_learned
    )
    cost_estimates = estimate_costs(
        plan, manifest, args.estimated_input_tokens, args.estimated_output_tokens
    )
    preflight = {
        "schema_version": "v0.2",
        "phase": args.phase,
        "repeats": args.repeats,
        "train_task_ids": [task.task_id for task in train_tasks],
        "test_task_ids": [task.task_id for task in test_tasks],
        "human_audit_task_ids": list(dataset.human_audit_task_ids),
        "candidate_models": [model.api_model for model in manifest.candidates],
        "judge_model": manifest.judge.api_model,
        "pricing_snapshot_date": manifest.pricing_snapshot_date,
        "billing_unit": manifest.billing_unit,
        "wire_api": manifest.candidates[0].wire_api,
        "base_url": manifest.candidates[0].base_url,
        "provider": manifest.candidates[0].provider,
        "execution_policy": {
            "temperature": 0,
            "timeout_seconds": args.timeout_seconds,
            "max_retries": args.max_retries,
            "request_options_by_model": {
                model.api_model: dict(model.request_options)
                for model in manifest.models
            },
        },
        "call_plan": plan,
        "cost_estimate_assumptions": {
            "input_tokens_per_production_call": args.estimated_input_tokens,
            "input_tokens_per_judge_call": args.estimated_input_tokens * 2,
            "output_tokens_per_call": args.estimated_output_tokens,
            "manifest_max_output_tokens": max(
                model.max_output_tokens or 0 for model in manifest.models
            ),
            "cached_input_discount_assumed": False,
        },
        "cost_estimates": cost_estimates,
        "credential_env": manifest.candidates[0].api_key_env,
        "credential_available": bool(
            os.environ.get(manifest.candidates[0].api_key_env or "")
        ),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not args.execute_paid_run:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0
    if args.max_production_cost is None or args.max_production_cost <= 0:
        parser.error("paid runs require a positive --max-production-cost")
    if args.max_evaluation_cost is None or args.max_evaluation_cost <= 0:
        parser.error("paid runs require a positive --max-evaluation-cost")
    manifest_output_cap = max(model.max_output_tokens or 0 for model in manifest.models)
    if args.estimated_output_tokens < manifest_output_cap:
        parser.error(
            "--estimated-output-tokens must cover the manifest request cap "
            f"{manifest_output_cap}"
        )
    if args.max_production_cost < cost_estimates["production_upper_estimate"]:
        parser.error(
            "--max-production-cost must cover the preflight estimate "
            f"{cost_estimates['production_upper_estimate']} {manifest.billing_unit}"
        )
    if args.max_evaluation_cost < cost_estimates["evaluation_upper_estimate"]:
        parser.error(
            "--max-evaluation-cost must cover the preflight estimate "
            f"{cost_estimates['evaluation_upper_estimate']} {manifest.billing_unit}"
        )
    required_env = manifest.candidates[0].api_key_env or ""
    if manifest.candidates[0].wire_api != "dsh-llm" and not os.environ.get(required_env):
        parser.error(f"paid run requires environment variable {required_env}")
    if manifest.candidates[0].wire_api == "dsh-llm" and os.environ.get(
        "REFRACTROUTER_DSH_BRIDGE"
    ) != "stdio":
        parser.error("dsh-llm paid runs require the RefractRouter DSH plugin bridge")
    if manifest.candidates[0].wire_api == "dsh-llm" and args.max_retries != 0:
        parser.error("dsh-llm paid runs require --max-retries 0 for bounded spend")

    ledger = CostLedger(
        billing_unit=manifest.billing_unit,
        production_limit=args.max_production_cost,
        evaluation_limit=args.max_evaluation_cost,
        estimated_production_input_tokens=args.estimated_input_tokens,
        estimated_evaluation_input_tokens=args.estimated_input_tokens * 2,
        estimated_output_tokens=args.estimated_output_tokens,
    )
    client = OpenAICompatibleClient(
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
    )
    adapter = BudgetedAdapter(OpenAICompatibleAdapter(client), ledger)
    registry = manifest.candidate_registry()

    training_results: list[TaskResult] = []
    for task in train_tasks:
        executor = DeepAgentsGraphExecutor(task, adapter, registry)
        for model in registry.list():
            assignments = {node.node_id: model.model_id for node in task.nodes}
            training_results.append(
                executor.execute(assignments, f"train-single:{model.model_id}")
            )

    judge = IndependentJudge(client, manifest.judge)
    observations: list[BenchmarkObservation] = []
    for task in test_tasks:
        for repeat_index in range(1, args.repeats + 1):
            bundle = build_task_strategy_bundle(
                task,
                registry,
                adapter,
                training_results,
                include_learned=include_learned,
            )
            single_evaluations = {}
            single_errors = {}
            for model_id, single_result in bundle.single_results.items():
                evaluation, error = _evaluate_with_budget(
                    judge, task, single_result, ledger
                )
                single_evaluations[model_id] = evaluation
                single_errors[model_id] = error
            if all(value is not None for value in single_evaluations.values()):
                task_model_id = select_judged_task_oracle(
                    bundle.single_results,
                    {
                        model_id: evaluation
                        for model_id, evaluation in single_evaluations.items()
                        if evaluation is not None
                    },
                )
                assignments = {
                    node.node_id: task_model_id for node in task.nodes
                }
                bundle.results["task-oracle"] = _retag(
                    bundle.single_results[task_model_id],
                    "task-oracle",
                    assignments,
                )
            reused_models = {
                "weak-all": registry.cheapest().model_id,
                "strong-all": registry.strongest().model_id,
                "task-oracle": next(
                    iter(bundle.results["task-oracle"].model_assignments.values())
                ),
            }
            for strategy, raw_result in bundle.results.items():
                evaluation = None
                judge_error = None
                result = raw_result
                reused_model = reused_models.get(strategy)
                if reused_model is not None:
                    evaluation = single_evaluations.get(reused_model)
                    judge_error = single_errors.get(reused_model)
                else:
                    evaluation, judge_error = _evaluate_with_budget(
                        judge, task, raw_result, ledger
                    )
                if evaluation is not None:
                    result = apply_judge_score(raw_result, evaluation)
                observations.append(
                    BenchmarkObservation(
                        task_id=task.task_id,
                        repeat=repeat_index,
                        strategy=strategy,
                        result=result,
                        judge=evaluation,
                        judge_error=judge_error,
                    )
                )

    _write_outputs(args.output_dir, args, manifest, observations, ledger, preflight)
    return 0


def _evaluate_with_budget(
    judge: IndependentJudge,
    task: TaskDAG,
    result: TaskResult,
    ledger: CostLedger,
):
    if not result.final_output:
        return None, "missing-final-output"
    reserve = _estimated_invocation_cost(
        judge.judge_model,
        ledger.estimated_evaluation_input_tokens,
        ledger.estimated_output_tokens,
    )
    if ledger.evaluation_spent + reserve > ledger.evaluation_limit:
        return None, "evaluation-budget-exhausted"
    try:
        evaluation = judge.evaluate(task, result)
    except (ModelInvocationError, ValueError, json.JSONDecodeError) as exc:
        return None, getattr(exc, "failure_type", type(exc).__name__)
    ledger.evaluation_spent += evaluation.cost
    return evaluation, None


def _write_outputs(
    output_dir: Path,
    args: argparse.Namespace,
    manifest: ModelManifest,
    observations: Sequence[BenchmarkObservation],
    ledger: CostLedger,
    preflight: Mapping[str, object],
) -> None:
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for observation in observations:
        path = runs_dir / observation.task_id / f"repeat-{observation.repeat}"
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{observation.strategy}.json").write_text(
            json.dumps(asdict(observation), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    summary = aggregate_observations(observations)
    gate = oracle_gate(summary)
    failures = failure_taxonomy(observations)
    model_run_complete = all(
        float(values["judge_coverage"]) == 1.0 for values in summary.values()
    ) and not any("budget-exhausted" in name for name in failures)
    status = (
        "awaiting-human-audit"
        if model_run_complete and args.phase == "final"
        else "complete"
        if model_run_complete
        else "incomplete"
    )
    payload = {
        "schema_version": "v0.2",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase,
        "repeats": args.repeats,
        "manifest": {
            "path": str(args.manifest.resolve()),
            "sha256": _sha256(args.manifest.resolve()),
            "pricing_snapshot_date": manifest.pricing_snapshot_date,
        },
        "preflight": preflight,
        "strategies": summary,
        "oracle_gate": gate,
        "failure_taxonomy": failures,
        "costs": {
            "billing_unit": ledger.billing_unit,
            "production": round(ledger.production_spent, 8),
            "evaluation": round(ledger.evaluation_spent, 8),
        },
    }
    summary_path = output_dir / "benchmark-summary.json"
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "baseline-table.md").write_text(
        baseline_markdown(summary), encoding="utf-8"
    )
    (output_dir / "oracle-gap.md").write_text(
        oracle_gap_markdown(gate), encoding="utf-8"
    )
    (output_dir / "pareto-front.md").write_text(
        pareto_front_markdown(summary), encoding="utf-8"
    )
    (output_dir / "failure-taxonomy.md").write_text(
        failure_taxonomy_markdown(failures), encoding="utf-8"
    )
    artifacts = sorted(
        path for path in output_dir.rglob("*") if path.is_file() and path.name != "evidence-index.json"
    )
    evidence = {
        "schema_version": "v0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            str(path.relative_to(output_dir)): _sha256(path) for path in artifacts
        },
    }
    (output_dir / "evidence-index.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
