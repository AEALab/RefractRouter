"""独立 Task 资料研究保留题；默认零调用准备，付费派发需核对摘要与总额度。"""

import argparse
import hashlib
import json
import math
from pathlib import Path

from refractrouter.ark_plan import catalog
from refractrouter.stage_study import _invoke_dsh, _metrics, _new_record, evaluate_research

from .preflight_task_quality_pilot import ROOT, digest
from .run_task_quality_pilot import MODEL_IDS, _cards, _patch


PROTOCOL = ROOT / "data/benchmarks/task-research-holdout-v1.json"


def _inputs():
    protocol = json.loads(PROTOCOL.read_text())
    task_source = json.loads((ROOT / protocol["taskSource"]).read_text())
    record_path = ROOT / protocol["calibrationRecords"]
    if hashlib.sha256(record_path.read_bytes()).hexdigest() != protocol["calibrationSha256"]:
        raise ValueError("校准原始记录摘要不匹配")
    rows = [json.loads(line) for line in record_path.read_text().splitlines() if line]
    cards = _cards(rows)
    task = next((item for item in task_source["tasks"] if item["id"] == protocol["taskId"]), None)
    if task is None or task["family"] != "research":
        raise ValueError("保留题必须是冻结资料研究任务")
    return protocol, task, cards


def preflight(protocol, task, cards, pricing):
    if protocol.get("schemaVersion") != "task-research-holdout-v1":
        raise ValueError("保留题协议版本无效")
    limits = protocol["limits"]
    if limits["httpRetries"] != 0 or limits["delegation"] is not False:
        raise ValueError("保留题禁用 HTTP 自动重试和委派")
    models = {row["model_id"]: row for row in pricing["models"]}
    cost = {}
    for model_id in MODEL_IDS.values():
        row = models[model_id]
        price = row["pricing"]
        if price["unit"] != "afp-per-10000-tokens":
            raise ValueError("缺少 AFP 计价")
        input_bound = limits["maxRequestBytesPerCall"] + 256
        if input_bound + limits["maxOutputTokensPerCall"] > row["context_window_tokens"]:
            raise ValueError("冻结输入输出上界超过上下文")
        cost[model_id] = round((input_bound * price["input_coefficient"]
                               + limits["maxOutputTokensPerCall"] * price["output_coefficient"])
                               / 10000 * limits["maxCallsPerRun"], 6)
    rows = []
    for arm in protocol["arms"]:
        model = MODEL_IDS[arm] if arm in MODEL_IDS else max(cost, key=cost.get)
        rows.append({"arm": arm, "taskId": task["id"], "costUpperAfp": cost[model]})
    current = round(sum(row["costUpperAfp"] for row in rows), 6)
    frozen = {"schemaVersion": "task-research-holdout-preflight-v1", "realModelCalls": 0,
              "protocolDigest": digest(protocol), "taskDigest": digest(task),
              "calibrationSha256": protocol["calibrationSha256"], "cards": cards,
              "pricingSnapshot": pricing["snapshot_date"], "runs": rows,
              "maximumModelCalls": len(rows) * limits["maxCallsPerRun"],
              "maximumProductionAfp": current,
              "priorAfpWorstCase": protocol["priorAfpWorstCase"],
              "maximumIncludingPriorAfp": round(current + protocol["priorAfpWorstCase"], 6),
              "note": "先前未知用量按全额预留计入总授权；旧批次不并入本批次质量分母。"}
    return {**frozen, "preflightDigest": digest(frozen)}


def prepare(protocol, task, cards, output):
    if output.exists():
        raise ValueError("输出目录已存在，不覆盖旧批次")
    evidence = preflight(protocol, task, cards, catalog())
    output.mkdir(parents=True)
    (output / "preflight.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    for index, row in enumerate(evidence["runs"]):
        workspace = output / "workspaces" / f"{index:02d}-{row['arm']}"
        workspace.mkdir(parents=True)
        settings = workspace / ".refractagent/settings.yaml"
        settings.parent.mkdir()
        settings.write_text("{}\n")
        for name, content in task["sources"].items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("冻结来源路径越界")
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (workspace / "TASK.md").write_text(task["prompt"] + "\n")
        (output / f"{index:02d}.patch.yml").write_text(
            _patch(protocol, row["arm"], cards, row["costUpperAfp"]))
    return evidence


def execute(protocol, task, cards, output, approved_digest, approved_afp, *, profile="headless"):
    evidence = json.loads((output / "preflight.json").read_text())
    current = preflight(protocol, task, cards, catalog())
    if evidence != current or approved_digest != current["preflightDigest"]:
        raise ValueError("预检摘要或来源变化，拒绝派发")
    if not math.isfinite(approved_afp) or approved_afp < current["maximumIncludingPriorAfp"]:
        raise ValueError("累计授权 AFP 不足")
    records = output / "run-records.jsonl"
    if records.exists():
        raise ValueError("已有运行证据，拒绝自动重发")
    results = []
    for index, row in enumerate(current["runs"]):
        workspace = output / "workspaces" / f"{index:02d}-{row['arm']}"
        run_root = workspace / ".refractagent/runs"
        before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
        prompt = ("这是冻结的 Task 研究保留题；禁止委派和访问网络。只使用 sources/"
                  "材料完成 TASK.md，引用必须对应实际来源编号。\n\n" + task["prompt"])
        outcome, elapsed = _invoke_dsh(profile, output / f"{index:02d}.patch.yml",
                                       workspace, prompt, protocol["limits"]["timeoutMsPerRun"])
        (output / f"{index:02d}-stdout.log").write_text(outcome.stdout or "")
        (output / f"{index:02d}-stderr.log").write_text(outcome.stderr or "")
        record = _new_record(run_root, before)
        metrics = _metrics(record, capable_model=MODEL_IDS["static-v4.1-flash"],
                           efficient_model=MODEL_IDS["static-flash"])
        if metrics["productionAfp"] > row["costUpperAfp"] + 1e-6:
            raise RuntimeError("实际 AFP 超过冻结上界")
        evaluation = evaluate_research(task, workspace)
        result = {**row, "exitCode": outcome.returncode, "elapsedMs": elapsed,
                  "metrics": metrics, "evaluation": evaluation,
                  "runId": record["runId"],
                  "judgeDecision": record.get("state", {}).get("judge_decision")}
        with records.open("a") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    parser.add_argument("--profile", default="headless")
    args = parser.parse_args()
    protocol, task, cards = _inputs()
    if not args.execute_paid_run:
        result = prepare(protocol, task, cards, args.output)
    else:
        if not args.approved_digest:
            raise ValueError("付费运行需要预检摘要")
        result = execute(protocol, task, cards, args.output, args.approved_digest,
                         args.approved_afp, profile=args.profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
