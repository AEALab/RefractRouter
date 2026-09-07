"""Describe frozen candidate evidence without changing node selection policy."""
from __future__ import annotations

from collections import Counter
from math import isfinite

from .node_contracts import CONTRACT_FAILURES


def evaluation_state(row):
    """Known contract rejection is evaluated evidence; unknown quality is never zero."""
    result = row.get("node_result", {})
    evaluation = row.get("evaluation", {})
    failure = result.get("failure_type")
    if failure == "invalid-reference-context":
        return "invalid-reference-context"
    if evaluation.get("error") or (result.get("status") != "ok" and failure not in CONTRACT_FAILURES):
        return "unavailable"
    score = evaluation.get("final_score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score):
        return "unavailable"
    if (evaluation.get("method") == "deterministic-rejection" and score == 0
            and (failure in CONTRACT_FAILURES or evaluation.get("checks", {}).get("score_cap") == 0)):
        return "contract-rejected"
    if (evaluation.get("method") == "independent-node-judge" and result.get("status") == "ok"
            and row.get("eligible") is True and 0 <= score <= 100):
        return "judged"
    return "unavailable"


def matrix_availability(rows, *, node_ids, model_ids):
    """Assess one task/repeat matrix against explicit expected nodes and models.

    The legacy selection readiness retains its all-executions-required condition.
    A complete record set does not imply available evaluations or an executable route.
    """
    node_ids, model_ids = tuple(node_ids), tuple(model_ids)
    if not node_ids or not model_ids:
        raise ValueError("Expected nodes and models must be nonempty")
    expected = {(node, model) for node in node_ids for model in model_ids}
    counts = Counter((row["node_id"], row["model_id"]) for row in rows)
    missing = sorted(expected - counts.keys())
    unexpected = sorted(counts.keys() - expected)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    states = [evaluation_state(row) for row in rows]
    inconsistent_contexts = [node for node in node_ids
                             if len({row.get("upstream_sha256") for row in rows
                                     if row["node_id"] == node}) > 1]
    records_complete = not (missing or unexpected or duplicates)
    context_valid = not inconsistent_contexts and "invalid-reference-context" not in states
    evaluations_available = records_complete and context_valid and "unavailable" not in states
    eligible_by_node = {
        node: sorted(row["model_id"] for row, state in zip(rows, states)
                     if row["node_id"] == node and state == "judged") for node in node_ids
    }
    return {
        "expected_cells": len(expected), "recorded_cells": len(rows),
        "records_complete": records_complete,
        "evaluations_available": evaluations_available,
        "reference_context_valid": context_valid,
        "evaluation_states": dict(sorted(Counter(states).items())),
        "eligible_by_node": eligible_by_node,
        "nodes_without_eligible_candidates": [node for node, models in eligible_by_node.items() if not models],
        "missing_cells": [list(key) for key in missing],
        "unexpected_cells": [list(key) for key in unexpected],
        "duplicate_cells": [list(key) for key in duplicates],
        "inconsistent_context_nodes": inconsistent_contexts,
        "legacy_policy": "all-candidates-required-v1",
        "legacy_route_executable": (evaluations_available and all(eligible_by_node.values())
                                    and all(row["node_result"]["status"] == "ok" for row in rows)),
    }


LEGACY_SELECTION_POLICY = "all-candidates-required-v1"
REJECTION_SELECTION_POLICY = "exclude-known-contract-rejections-v2"
SELECTION_POLICIES = (LEGACY_SELECTION_POLICY, REJECTION_SELECTION_POLICY)


def select_available_candidates(rows, *, task, model_ids, policy=REJECTION_SELECTION_POLICY):
    """Select a composed-route assignment from complete frozen evidence, without calls.

    Rejections have known zero contract scores. Unknown execution, judging, or context
    stops the entire selection. The resulting assignment still needs a fresh DAG run.
    """
    import hashlib
    import json

    if policy not in SELECTION_POLICIES:
        raise ValueError(f"Unknown node selection policy: {policy}")
    state = matrix_availability(rows, node_ids=[node.node_id for node in task.nodes], model_ids=model_ids)
    errors = []
    for field in ("missing_cells", "unexpected_cells", "duplicate_cells", "inconsistent_context_nodes"):
        if state[field]:
            errors.append(field.replace("_", "-"))
    if not state["evaluations_available"]:
        errors.append("node-evaluation-unavailable")
    if state["nodes_without_eligible_candidates"]:
        errors.append("no-eligible-candidate")
    if policy == LEGACY_SELECTION_POLICY and not state["legacy_route_executable"]:
        errors.append("legacy-all-executions-required")
    nodes = {node.node_id: node for node in task.nodes}
    if len({(row.get("task_id"), row.get("repeat"), row.get("stage")) for row in rows}) != 1:
        errors.append("mixed-matrix-blocks")
    for row in rows:
        result = row.get("node_result", {})
        node = nodes.get(row["node_id"])
        if (node is None or row.get("task_id") != task.task_id or row.get("stage") != "probe"
                or result.get("node_id") != row["node_id"] or result.get("model_id") != row["model_id"]):
            errors.append("invalid-candidate-identity")
            continue
        upstream = row.get("upstream")
        if not isinstance(upstream, dict) or set(upstream) != set(node.parents):
            errors.append("invalid-reference-context")
            continue
        upstream_hash = hashlib.sha256(json.dumps(upstream, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        output = result.get("output")
        if (row.get("upstream_sha256") != upstream_hash or not isinstance(output, str)
                or hashlib.sha256(output.encode()).hexdigest() != row.get("output_sha256")):
            errors.append("invalid-evidence-hash")
        # Recheck each reference parent's actual contract, not just a reported status.
        from .scoring import node_contract_checks
        for parent in node.parents:
            if not isinstance(upstream[parent], str) or node_contract_checks(
                task, nodes[parent], upstream[parent], upstream
            )["score_cap"] == 0:
                errors.append("invalid-reference-context")
        cost = result.get("cost")
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not isfinite(cost) or cost < 0:
            errors.append("invalid-candidate-cost")
    assignments = {}
    if not errors:
        for node in task.nodes:
            eligible = [row for row in rows if row["node_id"] == node.node_id and evaluation_state(row) == "judged"]
            chosen = min(eligible, key=lambda row: (-row["evaluation"]["final_score"],
                                                   row["node_result"]["cost"], row["model_id"]))
            assignments[node.node_id] = chosen["model_id"]
    return {"selection_policy": policy, "route_executable": not errors,
            "blocking_reasons": sorted(set(errors)), "assignments": assignments, "availability": state}
