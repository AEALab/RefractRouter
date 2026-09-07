"""Paired, descriptive comparisons; repeated tasks are not independent new tasks."""
from collections import defaultdict
from statistics import mean, pstdev

from .benchmark import comparison_exclusions


def paired_comparisons(observations, *, expected_blocks=None):
    indexed = {}
    for item in observations:
        key = (item.task_id, item.repeat, item.strategy)
        if key in indexed:
            raise ValueError(f"Duplicate observation: {key}")
        indexed[key] = item
    observed_blocks = {key[:2] for key in indexed}
    blocks = sorted(set(expected_blocks) if expected_blocks is not None else observed_blocks)
    if observed_blocks - set(blocks):
        raise ValueError("Observation outside expected task/repeat blocks")
    pairs = []
    summaries = {}
    for candidate in ("node-oracle", "node-type-rule"):
        for baseline in ("strong-all", "task-oracle"):
            rows = []
            for task_id, repeat in blocks:
                left = indexed.get((task_id, repeat, candidate))
                right = indexed.get((task_id, repeat, baseline))
                errors = []
                for label, item in ((candidate, left), (baseline, right)):
                    if item is None:
                        errors.append(f"{label}:missing-run")
                    else:
                        errors.extend(f"{label}:{reason}" for reason in comparison_exclusions(item))
                row = dict(task_id=task_id, repeat=repeat, candidate=candidate,
                           baseline=baseline, included=not errors, exclusion_reasons=errors)
                if left and right:
                    a, b = left.result, right.result
                    if a.billing_unit != b.billing_unit:
                        raise ValueError("Paired observations contain mixed billing units")
                    row.update(
                        billing_unit=a.billing_unit,
                        candidate_quality=left.judge.final_score if left.judge and not left.judge_error else None,
                        baseline_quality=right.judge.final_score if right.judge and not right.judge_error else None,
                        quality_delta=left.judge.final_score - right.judge.final_score if not errors else None,
                        candidate_cost=a.total_cost, baseline_cost=b.total_cost,
                        cost_delta=a.total_cost - b.total_cost if not errors else None,
                        cost_reduction_percent=(b.total_cost-a.total_cost)/b.total_cost*100 if not errors and b.total_cost else None,
                        latency_delta_ms=a.critical_path_latency_ms-b.critical_path_latency_ms if not errors else None,
                        identical_assignments=dict(a.model_assignments) == dict(b.model_assignments),
                        candidate_is_mixed=len(set(a.model_assignments.values())) > 1,
                        identical_output=a.final_output == b.final_output,
                        candidate_assignments=dict(a.model_assignments), baseline_assignments=dict(b.model_assignments),
                    )
                rows.append(row)
            valid = [row for row in rows if row["included"]]
            stats = dict(pairs=len(valid), excluded_pairs=len(rows)-len(valid),
                         included_blocks=[dict(task_id=r["task_id"], repeat=r["repeat"]) for r in valid],
                         excluded_blocks=[dict(task_id=r["task_id"], repeat=r["repeat"],
                                               reasons=r["exclusion_reasons"]) for r in rows if not r["included"]],
                         task_count=len({r["task_id"] for r in valid}),
                         repeats=sorted({r["repeat"] for r in valid}),
                         identical_assignment_pairs=sum(r["identical_assignments"] for r in valid),
                         mixed_candidate_pairs=sum(r["candidate_is_mixed"] for r in valid))
            by_task = defaultdict(list)
            for row in valid:
                by_task[row["task_id"]].append(row["quality_delta"])
            stats["per_task_quality_delta"] = {
                task: {"repeats": len(values), "mean": round(mean(values), 6),
                       "stddev": round(pstdev(values), 6)} for task, values in by_task.items()}
            for metric in ("quality_delta", "cost_delta", "cost_reduction_percent", "latency_delta_ms"):
                values = [row[metric] for row in valid if row[metric] is not None]
                stats[metric + "_mean"] = round(mean(values), 8) if values else None
                stats[metric + "_stddev"] = round(pstdev(values), 8) if values else None
            summaries[f"{candidate} vs {baseline}"] = stats
            pairs.extend(rows)
    return {
        "pairing": "task_id + repeat", "summaries": summaries, "pairs": pairs,
        "interpretation": "Descriptive paired differences; repeats are nested within tasks. "
        "Identical assignments measure generation/judge variation, not a routing change. "
        "Task-oracle is the post-hoc best of all three judged single-model runs in that block. "
        "Node-oracle is a local greedy selection on fixed upstream probes, not a global upper bound.",
    }


def comparisons_markdown(report):
    lines = ["# Paired strategy comparisons", "", report["interpretation"], "",
             "| Comparison | Pairs / excluded | Tasks | Repeats | Quality Δ mean ± sd | Cost Δ mean ± sd | Identical assignments | Mixed |",
             "|---|---:|---:|---|---:|---:|---:|---:|"]
    for name, s in report["summaries"].items():
        lines.append(f"| {name} | {s['pairs']} / {s['excluded_pairs']} | {s['task_count']} | {s['repeats']} | "
                     f"{s['quality_delta_mean']} ± {s['quality_delta_stddev']} | "
                     f"{s['cost_delta_mean']} ± {s['cost_delta_stddev']} | {s['identical_assignment_pairs']} | {s['mixed_candidate_pairs']} |")
    lines.extend(["", "Included cohorts (identical for every displayed delta):"])
    for name, stats in report["summaries"].items():
        blocks = ", ".join(f"{r['task_id']}/{r['repeat']}" for r in stats["included_blocks"]) or "none"
        lines.append(f"- {name}: {blocks}.")
        for row in stats["excluded_blocks"]:
            lines.append(f"  Excluded {row['task_id']}/{row['repeat']}: {', '.join(row['reasons'])}.")
    lines.extend(["", "Positive quality Δ favors the candidate. Negative cost Δ means lower production cost.",
                  "Probe and judge expenses are reported separately in the run ledger.", ""])
    return "\n".join(lines)
