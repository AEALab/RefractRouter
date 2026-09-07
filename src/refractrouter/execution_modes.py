"""Explicit one-shot versus fixed-DAG experimental modes; no online routing claim."""
from dataclasses import replace

from .deepagents_executor import DeepAgentsGraphExecutor
from .schemas import NodeSpec


def one_shot_task(task):
    if not task.source_documents:
        raise ValueError("One-shot reports require a frozen source pack")
    return replace(task, output_contract_version="v0.4", execution_mode="one-shot", nodes=(
        NodeSpec("render_html", "rendering",
                 "Generate the complete research report directly from the frozen sources. "
                 "Cover every required section with substantive analysis, comparisons, risks, "
                 "and supported conclusions. Return only standalone HTML with source trace."),))


def run_one_shot(task, model_id, adapter, registry):
    task = one_shot_task(task)
    return DeepAgentsGraphExecutor(task, adapter, registry).execute(
        {"render_html": model_id}, f"one-shot:{model_id}")


def execution_mode_call_plan(task, candidate_count, repeats):
    if candidate_count < 1 or repeats < 1:
        raise ValueError("Candidate and repeat counts must be positive")
    nodes = len(task.nodes)
    return {
        "training_model_calls": 0,
        "one_shot_model_calls": candidate_count * repeats,
        "single_dag_model_calls": nodes * candidate_count * repeats,
        "probe_model_calls": nodes * candidate_count * repeats,
        "composed_model_calls": nodes * repeats,
        "fixed_calls_per_candidate": (1 + 2 * nodes) * repeats,
        "production_model_calls": (candidate_count * (1 + 2 * nodes) + nodes) * repeats,
        "node_judge_model_calls": nodes * candidate_count * repeats,
        "final_judge_model_calls": (2 * candidate_count + 1) * repeats,
        "judge_model_calls": (nodes * candidate_count + 2 * candidate_count + 1) * repeats,
        "total_model_calls": (candidate_count * (3 * nodes + 3) + nodes + 1) * repeats,
    }


def execution_mode_pairs(model_ids):
    return tuple(
        [(f"dag:{m}", f"one-shot:{m}") for m in model_ids]
        + [("node-mixed", f"dag:{m}") for m in model_ids]
        + [("node-mixed", f"one-shot:{m}") for m in model_ids]
        + [("node-mixed", "dag-oracle"), ("node-mixed", "one-shot-oracle")])
