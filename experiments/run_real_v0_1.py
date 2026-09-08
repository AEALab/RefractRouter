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
from refractrouter.comparisons import paired_comparisons, comparisons_markdown
from refractrouter.dataset import BenchmarkDataset, load_benchmark_dataset
from refractrouter.deepagents_executor import DeepAgentsGraphExecutor
from refractrouter.judge import IndependentJudge, apply_judge_score
from refractrouter.judge import JudgeEvaluation, JudgeResponseError
from refractrouter.manifest import ModelManifest, load_model_manifest
from refractrouter.model_registry import ModelRegistry
from refractrouter.node_availability import (
    matrix_availability, evaluation_state, select_available_candidates,
    LEGACY_SELECTION_POLICY, REJECTION_SELECTION_POLICY, SELECTION_POLICIES,
)
from refractrouter.node_judge import IndependentNodeJudge, NodeJudgeError, NODE_RUBRIC_PATH, NODE_RUBRIC_VERSION
from refractrouter.node_contracts import CONTRACT_FAILURES, prompt_contract_snapshot
from refractrouter.scoring import NODE_CHECKS_VERSION, node_contract_checks
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
    node_matrix: tuple[dict, ...] = ()
    matrix_complete: bool = True
    selection_decision: dict | None = None


class NodeQualityRecorder:
    """Persist every cell, including failed/unevaluated candidates, before selection."""

    def __init__(self, judge, ledger, output_dir, models=(), selection_policy=LEGACY_SELECTION_POLICY):
        self.selection_policy = selection_policy
        self.judge = judge
        self.ledger = ledger
        self.output_dir = output_dir
        self.rows = []
        self.models = {model.model_id: model for model in models}

    def record(self, task, node, result, context, *, repeat, stage):
        upstream = {parent: context.get(parent, "") for parent in node.parents}
        checks = node_contract_checks(task, node, result.output, upstream)
        evaluation = {"error": None, "final_score": 0.0, "cost": 0.0, "checks": checks}
        if result.status != "ok" and result.failure_type not in CONTRACT_FAILURES:
            evaluation.update(method="execution-unavailable", final_score=None,
                              error=result.failure_type or "execution-failed")
        elif result.status != "ok" or checks["score_cap"] == 0:
            evaluation["method"] = "deterministic-rejection"
        else:
            reserve = _estimated_invocation_cost(
                self.judge.judge_model, self.ledger.estimated_evaluation_input_tokens,
                self.ledger.estimated_output_tokens,
            )
            if self.ledger.evaluation_spent + reserve > self.ledger.evaluation_limit:
                evaluation["error"] = "evaluation-budget-exhausted"
                evaluation["final_score"] = None
            else:
                try:
                    evaluation = {**self.judge.evaluate(task, node, result, upstream), "error": None,
                                  "method": "independent-node-judge"}
                except NodeJudgeError as exc:
                    evaluation.update(exc.telemetry)
                    evaluation.update(error=exc.failure_type, final_score=None)
                except ModelInvocationError as exc:
                    evaluation.update(error=exc.failure_type, final_score=None)
                self.ledger.evaluation_spent += evaluation["cost"]
        row = {
            "task_id": task.task_id, "repeat": repeat, "stage": stage,
            "node_id": node.node_id, "node_type": node.node_type, "model_id": result.model_id,
            "api_model": self.models[result.model_id].api_model if result.model_id in self.models else None,
            "upstream": upstream,
            "upstream_sha256": hashlib.sha256(json.dumps(upstream, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
            "node_result": asdict(result), "evaluation": evaluation,
            "evaluation_state": (
                "unavailable" if evaluation["error"] else
                "contract-rejected" if evaluation.get("method") == "deterministic-rejection" else
                "judged"
            ),
            "eligible": result.status == "ok" and checks["score_cap"] > 0 and evaluation["error"] is None,
            "selected": False,
        }
        self.rows.append(row)
        with (self.output_dir / "node-evaluations.ndjson").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def write_matrix(self):
        payload = {"rubric_version": self.judge.rubric_version,
                   "rubric_sha256": self.judge.rubric_sha256, "rows": self.rows,
                   "raw_node_score_kind": "deterministic contract cap; use evaluation.final_score for selection",
                   "selection": "highest eligible semantic score, then lowest observed node cost",
                   "selection_policy": self.selection_policy,
                   "global_oracle": False}
        (self.output_dir / "node-quality-matrix.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = ["# Node quality matrix", "",
                 "Independent semantic scores capped by contract checks. * marks the selected model.",
                 "Full outputs, checks, rationale, telemetry and exclusions are in the JSON matrix.", ""]
        blocks = dict.fromkeys((r["stage"], r["task_id"], r["repeat"]) for r in self.rows)
        for stage, task_id, repeat in blocks:
            rows = [r for r in self.rows if (r["stage"], r["task_id"], r["repeat"]) == (stage, task_id, repeat)]
            models = list(dict.fromkeys(r["model_id"] for r in rows))
            labels = {r["model_id"]: r["api_model"] or r["model_id"] for r in rows}
            lines.extend([f"## {stage} / {task_id} / repeat {repeat}", "",
                          "| Node | " + " | ".join(labels[m] for m in models) + " |",
                          "|---|" + "---:|" * len(models)])
            for node_id in dict.fromkeys(r["node_id"] for r in rows):
                cells = []
                for model in models:
                    row = next(r for r in rows if r["node_id"] == node_id and r["model_id"] == model)
                    score = row["evaluation"]["final_score"]
                    label = str(score) if score is not None else "unevaluated"
                    label += " *" if row["selected"] else "" if row["eligible"] else " (ineligible)"
                    cells.append(label)
                lines.append("| " + node_id + " | " + " | ".join(cells) + " |")
            lines.append("")
        (self.output_dir / "node-quality-matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")



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
    node_evaluator=None,
    single_recorder=None,
    selection_policy=LEGACY_SELECTION_POLICY,
    include_rule: bool = True,
) -> TaskStrategyBundle:
    if selection_policy not in SELECTION_POLICIES:
        raise ValueError(f"Unknown node selection policy: {selection_policy}")
    if selection_policy == REJECTION_SELECTION_POLICY and node_evaluator is None:
        raise ValueError("v2 selection requires independent node evaluations")
    executor = DeepAgentsGraphExecutor(task, adapter, registry)
    singles: dict[str, TaskResult] = {}
    for model in registry.list():
        assignments = {node.node_id: model.model_id for node in task.nodes}
        singles[model.model_id] = executor.execute(
            assignments, f"single:{model.model_id}"
        )
        if single_recorder is not None:
            single_recorder(model.model_id, singles[model.model_id])

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
    matrix = []
    matrix_complete = True
    reference_status = {r.node_id: r.status for r in strong.node_results}
    eligible_nodes = set()
    for node in task.nodes:
        for model in registry.list():
            invalid_reference = any(reference_status.get(parent) != "ok" for parent in node.parents)
            if invalid_reference:
                node_result = NodeResult(node.node_id, node.node_type, model.model_id, "", 0, 0, 0, 0,
                                         billing_unit=model.billing_unit, status="failed",
                                         failure_type="invalid-reference-context", attempts=0)
            else:
                node_result = executor.probe_node(node.node_id, model.model_id, reference_context)
            if node_evaluator is not None:
                row = node_evaluator(task, node, node_result, reference_context)
                matrix.append(row)
                matrix_complete = (matrix_complete and row["evaluation"]["error"] is None
                                   and node_result.status == "ok" and not invalid_reference)
                if row["eligible"]:
                    eligible_nodes.add(node.node_id)
                    probes.append(_probe_result(task, replace(node_result, score=row["evaluation"]["final_score"])))
            else:
                probes.append(_probe_result(task, node_result))
    decision = None
    if selection_policy == REJECTION_SELECTION_POLICY:
        decision = select_available_candidates(matrix, task=task,
                        model_ids=[model.model_id for model in registry.list()], policy=selection_policy)
        matrix_complete = decision["route_executable"]
    if node_evaluator is not None and (not matrix_complete or len(eligible_nodes) != len(task.nodes)):
        matrix_complete = False
        node_assignments = {}
        failed = tuple(NodeResult(n.node_id, n.node_type, "unselected", "", 0, 0, 0, 0,
                                 billing_unit=registry.cheapest().billing_unit, status="failed",
                                 failure_type="node-quality-incomplete", attempts=0) for n in task.nodes)
        node_best = TaskResult(task.task_id, "node-oracle", {}, failed, "", 0, 0, 0,
                               billing_unit=registry.cheapest().billing_unit,
                               failure_types=("node-quality-incomplete",))
    else:
        node_assignments = decision["assignments"] if decision else node_oracle(task, registry, probes)
        node_best = executor.execute(node_assignments, "node-oracle")
    for row in matrix:
        row["selected"] = row["eligible"] and node_assignments.get(row["node_id"]) == row["model_id"]

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
    rule = executor.execute(node_type_rule(task, registry, rules), "node-type-rule") if include_rule else None
    results = {
        "weak-all": weak,
        "strong-all": strong,
        "node-type-rule": rule,
        "task-oracle": task_best,
        "node-oracle": node_best,
    }
    if not include_rule:
        del results["node-type-rule"]
    if include_learned:
        results["task-level-router"] = executor.execute(
            task_level_router(task, registry, training_results),
            "task-level-router",
        )
        results["statistical-q"] = executor.execute(
            statistical_q(task, registry, training_results),
            "statistical-q",
        )
    return TaskStrategyBundle(results=results, single_results=singles, node_matrix=tuple(matrix), matrix_complete=matrix_complete, selection_decision=decision)


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
    training_nodes = sum(len(task.nodes) for task in train_tasks)
    test_nodes = sum(len(task.nodes) for task in test_tasks) * repeats
    training_calls = training_nodes * candidate_count
    strategies = 7 if include_learned else 5
    production_calls = training_calls + test_nodes * (2 * candidate_count + (4 if include_learned else 2))
    final_judge_calls = len(test_tasks) * repeats * strategies
    node_judge_calls = training_calls + test_nodes * candidate_count
    judge_calls = final_judge_calls + node_judge_calls
    return {
        "training_model_calls": training_calls,
        "production_model_calls": production_calls,
        "fixed_calls_per_candidate": training_nodes + 2 * test_nodes,
        "node_judge_model_calls": node_judge_calls,
        "final_judge_model_calls": final_judge_calls,
        "judge_model_calls": judge_calls,
        "total_model_calls": production_calls + judge_calls,
    }


def estimate_costs(
    plan: Mapping[str, int],
    manifest: ModelManifest,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, float]:
    prices = [input_tokens / 1000 * model.input_cost_per_1k
              + output_tokens / 1000 * model.output_cost_per_1k for model in manifest.candidates]
    fixed = int(plan.get("fixed_calls_per_candidate", 0))
    remaining = int(plan["production_model_calls"]) - fixed * len(prices)
    if fixed < 0 or remaining < 0:
        raise ValueError("Invalid fixed candidate call count")
    # Single-model runs and isolated sweeps have known model identities. Only
    # composed/learned routes need the most expensive possible per-call price.
    production = fixed * sum(prices) + remaining * max(prices)
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
    parser.add_argument("--selection-policy", choices=SELECTION_POLICIES, default=LEGACY_SELECTION_POLICY)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--max-production-cost", type=float)
    parser.add_argument("--max-evaluation-cost", type=float)
    parser.add_argument("--estimated-input-tokens", type=int, default=4000)
    parser.add_argument(
        "--estimated-output-tokens", type=int,
        help="Output estimate per call; defaults to the largest manifest output cap",
    )
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
    manifest_output_cap = max(model.max_output_tokens or 0 for model in manifest.models)
    if args.estimated_output_tokens is None:
        args.estimated_output_tokens = manifest_output_cap
    if args.estimated_input_tokens <= 0 or args.estimated_output_tokens <= 0:
        parser.error("token estimates must be positive")
    if args.estimated_output_tokens < manifest_output_cap:
        parser.error(
            "--estimated-output-tokens must cover the manifest request cap "
            f"{manifest_output_cap}"
        )
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
        "node_quality": {
            "rubric_version": NODE_RUBRIC_VERSION,
            "checks_version": NODE_CHECKS_VERSION, "rubric_sha256": _sha256(NODE_RUBRIC_PATH),
            "selection": "blinded-independent-node-judge-with-contract-caps",
            "tie_break": "observed-node-cost", "global_oracle": False,
            "selection_policy": args.selection_policy,
        },
        "node_output_contract": prompt_contract_snapshot(),
        "execution_policy": {
            "temperature": 0,
            "timeout_seconds": args.timeout_seconds,
            "max_retries": args.max_retries,
            "json_mode_by_model": {model.api_model: model.json_mode_strategy for model in manifest.models},
            "request_options_by_model": {
                model.api_model: dict(model.request_options)
                for model in manifest.models
            },
        },
        "call_plan": plan,
        "cost_estimate_assumptions": {
            "production_assignment_bound": "fixed candidate sweeps at each model's price; remaining calls at maximum per-call price",
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
    if args.execute_paid_run and args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Use a fresh output directory for a paid run; existing node evidence cannot be overwritten")
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

    node_judge = IndependentNodeJudge(client, manifest.judge)
    quality = NodeQualityRecorder(node_judge, ledger, args.output_dir, manifest.candidates, args.selection_policy)
    training_results: list[TaskResult] = []
    for task in train_tasks:
        executor = DeepAgentsGraphExecutor(task, adapter, registry)
        for model in registry.list():
            assignments = {node.node_id: model.model_id for node in task.nodes}
            training = executor.execute(assignments, f"train-single:{model.model_id}")
            context = {}
            scored = []
            for node_result in training.node_results:
                node = next(n for n in task.nodes if n.node_id == node_result.node_id)
                row = quality.record(task, node, node_result, context, repeat=0, stage="training")
                scored.append(replace(node_result, score=row["evaluation"].get("final_score") or 0))
                context[node.node_id] = node_result.output
            training_results.append(replace(training, node_results=tuple(scored)))


    judge = IndependentJudge(client, manifest.judge)
    observations: list[BenchmarkObservation] = []
    for task in test_tasks:
        for repeat_index in range(1, args.repeats + 1):
            single_dir = args.output_dir / "single-models" / task.task_id / f"repeat-{repeat_index}"
            single_dir.mkdir(parents=True, exist_ok=True)

            def checkpoint_single(model_id, result):
                (single_dir / f"{model_id}.json").write_text(json.dumps({
                    "result": asdict(result), "judge": None, "judge_error": "awaiting-evaluation",
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            bundle = build_task_strategy_bundle(
                task,
                registry,
                adapter,
                training_results,
                include_learned=include_learned,
                single_recorder=checkpoint_single,
                selection_policy=args.selection_policy,
                node_evaluator=lambda task, node, result, context: quality.record(
                    task, node, result, context, repeat=repeat_index, stage="probe"),
            )
            if bundle.selection_decision is not None:
                (args.output_dir / f"selection-{task.task_id}-{repeat_index}.json").write_text(
                    json.dumps(bundle.selection_decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
            single_dir = args.output_dir / "single-models" / task.task_id / f"repeat-{repeat_index}"
            single_dir.mkdir(parents=True, exist_ok=True)
            for model_id, single in bundle.single_results.items():
                (single_dir / f"{model_id}.json").write_text(json.dumps({
                    "result": asdict(single),
                    "judge": asdict(single_evaluations[model_id]) if single_evaluations[model_id] else None,
                    "judge_error": single_errors[model_id],
                }, ensure_ascii=False, indent=2) + "\n")
            task_oracle_complete = all(value is not None for value in single_evaluations.values())
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
                if strategy == "task-oracle" and not task_oracle_complete:
                    evaluation, judge_error = None, "incomplete-single-model-evaluations"
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

    quality.write_matrix()
    _write_outputs(args.output_dir, args, manifest, observations, ledger, preflight, quality.rows)
    return 0


def _evaluate_with_budget(
    judge: IndependentJudge,
    task: TaskDAG,
    result: TaskResult,
    ledger: CostLedger,
    error_recorder=None,
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
    except JudgeResponseError as exc:
        ledger.evaluation_spent += exc.telemetry["cost"]
        if error_recorder is not None:
            error_recorder({"error": exc.failure_type, **exc.telemetry})
        return None, exc.failure_type
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
    node_rows: Sequence[dict] = (),
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
    expected_blocks = [(task_id, repeat) for task_id in preflight["test_task_ids"]
                       for repeat in range(1, args.repeats + 1)]
    summary = aggregate_observations(observations, expected_blocks=expected_blocks)
    gate = oracle_gate(summary)
    comparisons = paired_comparisons(observations, expected_blocks=expected_blocks)
    failures = failure_taxonomy(observations)
    for row in node_rows:
        if row["node_result"]["status"] != "ok":
            error = "node-probe:" + str(row["node_result"]["failure_type"])
            failures[error] = failures.get(error, 0) + 1
        if row["evaluation"]["error"]:
            error = "node-judge:" + row["evaluation"]["error"]
            failures[error] = failures.get(error, 0) + 1
    expected_cells = preflight["call_plan"]["node_judge_model_calls"]
    if len(node_rows) != expected_cells:
        failures["node-matrix:missing-cells"] = abs(expected_cells - len(node_rows))
    availability = []
    for task_id, repeat in expected_blocks:
        block = [item for item in observations if (item.task_id, item.repeat) == (task_id, repeat)]
        nodes = sorted({node.node_id for item in block for node in item.result.node_results})
        rows = [row for row in node_rows if (row["task_id"], row["repeat"]) == (task_id, repeat)
                and row["stage"] == "probe"]
        state = matrix_availability(rows, node_ids=nodes,
                                    model_ids=[model.model_id for model in manifest.candidates])
        route = next((item for item in block if item.strategy == "node-oracle"), None)
        availability.append(dict(task_id=task_id, repeat=repeat, **state,
                                 route_executed=bool(route and route.result.model_assignments),
                                 route_judged=bool(route and route.judge and not route.judge_error)))
    selection_policy = preflight["node_quality"]["selection_policy"]
    blocking_failures = dict(failures)
    if selection_policy == REJECTION_SELECTION_POLICY:
        # Retain known rejections in the taxonomy and cost ledger, while allowing
        # alternatives only when every cell is known and each route is executable.
        for row in node_rows:
            if row["stage"] == "probe" and evaluation_state(row) == "contract-rejected":
                key = "node-probe:" + str(row["node_result"]["failure_type"])
                if key in blocking_failures:
                    blocking_failures[key] -= 1
                    if blocking_failures[key] == 0:
                        del blocking_failures[key]
        if any(not block["evaluations_available"] or block["nodes_without_eligible_candidates"]
               or not block["route_executed"] for block in availability):
            blocking_failures["node-selection:unavailable"] = 1
    model_run_complete = all(values["cohort"]["complete"] for values in summary.values()) and not blocking_failures
    comparison = comparisons["summaries"]["node-oracle vs task-oracle"]
    gate["routing_change_observed"] = comparison["pairs"] > comparison["identical_assignment_pairs"]
    gate["repeated"] = args.repeats >= 3
    gate["matrix_complete"] = model_run_complete
    if not model_run_complete or not gate["repeated"] or not gate["routing_change_observed"]:
        gate["decision"] = "Insufficient-evidence"
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
        "comparisons": comparisons["summaries"],
        "node_matrix": {"expected_cells": expected_cells, "recorded_cells": len(node_rows)},
        "selection_policy": selection_policy,
        "node_availability": availability,
        "blocking_failures": blocking_failures,
        "oracle_gate": gate,
        "failure_taxonomy": failures,
        "costs": {
            "node_evaluation": round(sum(row["evaluation"]["cost"] for row in node_rows), 8),
            "final_evaluation": round(ledger.evaluation_spent - sum(row["evaluation"]["cost"] for row in node_rows), 8),
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
    (output_dir / "strategy-comparisons.json").write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "strategy-comparisons.md").write_text(comparisons_markdown(comparisons), encoding="utf-8")
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
