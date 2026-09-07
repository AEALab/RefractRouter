"""C -> A -> B sensitivity analysis of frozen evidence, with zero model calls."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from refractrouter.model_selection import (
    Constraints, Weights, build_candidates, pareto_model_ids, quality_baseline, select_model,
)
from experiments.review_node_quality_evidence import observation


def analyze(root: Path, constraints: Constraints, weights: Weights) -> dict:
    root = root.resolve()
    index_bytes = (root / "evidence-index.json").read_bytes()
    index = json.loads(index_bytes)["artifacts"]
    hashes = {"evidence-index.json": hashlib.sha256(index_bytes).hexdigest()}
    for name, expected in index.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Artifact escapes evidence directory: {name}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Evidence hash mismatch: {name}")
        hashes[name] = actual
    if "preflight.json" not in index:
        raise ValueError("Preflight must be covered by the evidence index")
    preflight = json.loads((root / "preflight.json").read_text())
    blocks = [(task, repeat) for task in preflight["test_task_ids"]
              for repeat in range(1, preflight["repeats"] + 1)]
    paths = sorted((root / "single-models").rglob("*.json"))
    indexed_paths = {name for name in index if name.startswith("single-models/") and name.endswith(".json")}
    if {str(path.relative_to(root)) for path in paths} != indexed_paths:
        raise ValueError("Single-model files do not match frozen evidence index")
    # Aliases are encoded by the archived single-model paths, not today's model registry.
    model_ids = sorted({Path(name).stem for name in indexed_paths})
    if len(model_ids) != len(preflight["candidate_models"]):
        raise ValueError("Single-model candidate count differs from frozen preflight")
    observations, run_rows = [], []
    for path in paths:
        record = json.loads(path.read_text())
        repeat = int(path.parent.name.removeprefix("repeat-"))
        item = observation(record, repeat=repeat, strategy=path.stem)
        if item.task_id != path.parent.parent.name:
            raise ValueError(f"Task ID differs from archive path: {path}")
        observations.append(item)
        run_rows.append({
            "task_id": item.task_id, "repeat": repeat, "model_id": path.stem,
            "quality": item.judge.final_score if item.judge and not item.judge_error else None,
            "cost_afp": item.result.total_cost,
            "latency_ms": item.result.critical_path_latency_ms,
            "failure_types": list(item.result.failure_types), "judge_error": item.judge_error,
            "source": str(path.relative_to(root)),
        })
    candidates = build_candidates(observations, expected_model_ids=model_ids, expected_blocks=blocks)
    a_grid = [select_model(candidates, method="A", constraints=Constraints(q, cost, latency))
              for cost in (.7, 6.0, 10.0)
              for q in (85.0, 88.0, 90.0, 92.0)
              for latency in (50000, 55000, 60000, 80000, 90000)]
    profiles = {
        "balanced-example": Weights(.5, .25, .25),
        "quality-priority": Weights(.8, .1, .1),
        "cost-priority": Weights(.2, .7, .1),
        "latency-priority": Weights(.25, .15, .6),
    }
    b_grid = {name: select_model(candidates, method="B", weights=w) for name, w in profiles.items()}
    return {
        "schema_version": "single-model-selection-report-v1", "model_calls": 0,
        "source_directory": root.name, "source_hashes": hashes,
        "task_count": len(preflight["test_task_ids"]), "expected_blocks": blocks,
        "candidate_models_from_preflight": preflight["candidate_models"],
        "interpretation": "Within-sample offline single-model selection. Repeats are nested within tasks. "
        "Critical-path p95 is descriptive, not end-to-end response-time SLA. "
        "Mean production AFP excludes historical probes and judges. "
        "Mixed-route predictions require actual composed execution and independent final judging.",
        "quality_baseline": quality_baseline(candidates),
        "candidates": [asdict(c) for c in candidates], "runs": run_rows,
        "pareto_model_ids": pareto_model_ids(candidates),
        "A": select_model(candidates, method="A", constraints=constraints),
        "B": select_model(candidates, method="B", weights=weights),
        "B_with_constraints": select_model(candidates, method="B", weights=weights, constraints=constraints),
        "A_sensitivity": a_grid, "B_sensitivity": b_grid,
    }


def markdown(report):
    lines = ["# 三指标单模型离线选择", "",
             f"模型调用：0。任务数：{report['task_count']}；任务与轮次块数：{len(report['expected_blocks'])}。",
             "`cheap` = Flash，`mid` = M3，`strong` = Pro（本次归档的别名）。", "",
             "质量为独立最终评审均值；成本为整条路线平均生产 AFP；时延为关键路径样本 p95。",
             "三项指标来自相同完整轮次。失败或缺评审的候选整体排除；每项排除原因保存在 JSON。", "",
             "## C：观测数据", "",
             "| 单模型 | 质量均值 ± sd | AFP 均值 | p50 / p95 秒 | 已记录轮次 | 合格 |",
             "|---|---:|---:|---:|---:|---|"]
    for c in report["candidates"]:
        if c["exclusions"]:
            lines.append(f"| {c['model_id']} | N/A | N/A | N/A | {c['runs']} | {', '.join(c['exclusions'])} |")
        else:
            lines.append(f"| {c['model_id']} | {c['quality_mean']:.3f} ± {c['quality_stddev']:.3f} | "
                         f"{c['cost_afp_mean']:.8f} | {c['latency_p50_ms']/1000:.3f} / "
                         f"{c['latency_p95_ms']/1000:.3f} | {c['runs']} | 是 |")
    lines.extend(["", f"质量基准：`{report['quality_baseline']}`。三指标 Pareto 集："
                  + ", ".join(f"`{mid}`" for mid in report["pareto_model_ids"]) + "。", "",
                  "## A：约束式选择", "",
                  "无解表示没有同时满足三项条件的候选；约束不自动放宽。表中数值均为示例场景。", ""])
    for budget in (.7, 6.0, 10.0):
        lines.extend([f"平均生产成本上限：{budget:g} AFP。", "",
                      "| 质量底线 / p95 上限 | 50 秒 | 55 秒 | 60 秒 | 80 秒 | 90 秒 |",
                      "|---|---|---|---|---|---|"])
        for q in (85, 88, 90, 92):
            selections = [row["selected_model"] or "无解" for row in report["A_sensitivity"]
                          if row["constraints"]["cost_afp_max"] == budget
                          and row["constraints"]["quality_min"] == q]
            lines.append(f"| {q} | " + " | ".join(selections) + " |")
        lines.append("")
    lines.extend(["## B：加权敏感性", "",
                  "在全部合格候选上固定 min/max；质量效用递增，成本与时延效用递减。",
                  "这些权重仅用于敏感性分析，没有设为生产默认值。", "",
                  "| 场景 | 质量 / 成本 / 时延权重 | 选择 | 各模型加权分数 |",
                  "|---|---|---|---|"])
    for name, result in report["B_sensitivity"].items():
        w = result["normalized_weights"]
        scores = "; ".join(f"{mid}: {c['score']:.6f}" if c["score"] is not None else f"{mid}: N/A"
                           for mid, c in result["candidates"].items())
        lines.append(f"| {name} | {w['quality']:g} / {w['cost']:g} / {w['latency']:g} | "
                     f"{result['selected_model'] or '无解'} | {scores} |")
    lines.extend(["", "## 本次显式配置", "",
                  f"A 约束：`{json.dumps(report['A']['constraints'])}`。",
                  f"B 权重：`{json.dumps(report['B']['weights'])}`。", "",
                  "| 决策 | 质量基准 | 综合选择 | 状态 |", "|---|---|---|---|"])
    for name in ("A", "B", "B_with_constraints"):
        r = report[name]
        lines.append(f"| {name} | {r['quality_baseline']} | {r['selected_model'] or '无解'} | {r['status']} |")
    lines.extend(["", "## 边界与复现", "",
                  "本结果来自同一任务的三次重复，只描述样本内取舍，不能证明跨任务泛化。",
                  "p95 来自极小样本的线性插值；关键路径时间不等于用户端到端等待时间。",
                  "平均质量底线不保证每次质量，平均成本预算也不是单次费用硬上限。",
                  "`task-oracle` 仍表示每轮事后质量最优的单模型；本报告质量基准是固定单模型均值最优者。",
                  "新混合路线的离线结果只能作为预测，必须实际组合执行并独立评审后再判断。",
                  "本入口只分析单模型，不改变冻结运行记录、oracle gate 或付费执行策略。", "",
                  "[机器可读结果、逐轮数据、排除原因及原始文件 SHA-256](selection-analysis.json)", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--quality-min", type=float, required=True)
    parser.add_argument("--cost-afp-max", type=float, required=True)
    parser.add_argument("--latency-p95-ms-max", type=float, required=True)
    parser.add_argument("--weights", type=float, nargs=3, metavar=("QUALITY", "COST", "LATENCY"), required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    source = args.directory.resolve()
    if output == source or output.is_relative_to(source):
        parser.error("Output must be outside the historical evidence directory")
    if output.exists():
        parser.error("Output directory must be fresh")
    report = analyze(source, Constraints(args.quality_min, args.cost_afp_max, args.latency_p95_ms_max),
                     Weights(*args.weights))
    rendered = markdown(report)
    output.mkdir(parents=True)
    (output / "selection-analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (output / "selection-analysis.md").write_text(rendered)
    print(f"Wrote zero-call selection report to {output}")


if __name__ == "__main__":
    main()
