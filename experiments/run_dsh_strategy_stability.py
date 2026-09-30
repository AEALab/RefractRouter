"""运行 DSH 六策略稳定性验收；默认只生成零调用预检。"""

import argparse
import json
import math
import os
from pathlib import Path

from refractrouter.dsh_strategy_stability import (
    AUTHORIZED_AFP, STRATEGY_COUNTS, frozen_tasks, preflight, verify_record,
    write_preflight,
)
from refractrouter.stage_study import _invoke_dsh, _new_record


def _append(path: Path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _ordered_tasks():
    rows = frozen_tasks()
    # 第一波先各跑一项，尽早发现某个策略的接线问题；其后保持冻结顺序。
    first = []
    remaining = []
    seen = set()
    for row in rows:
        if row["strategy"] not in seen:
            first.append(row)
            seen.add(row["strategy"])
        else:
            remaining.append(row)
    return first + remaining


def _summary(records):
    by_strategy = {}
    for strategy, expected in STRATEGY_COUNTS.items():
        rows = [row for row in records if row["strategy"] == strategy]
        by_strategy[strategy] = {"expected": expected, "attempted": len(rows),
            "successful": sum(row.get("success") is True for row in rows),
            "productionAfp": round(sum(row.get("productionAfp", 0) for row in rows), 8),
            "modelCalls": sum(row.get("modelCalls", 0) for row in rows)}
    complete = all(row["attempted"] == row["expected"]
                   and row["successful"] == row["expected"] for row in by_strategy.values())
    return {"schemaVersion": "dsh-strategy-stability-summary-v1", "complete": complete,
        "attempts": len(records), "successes": sum(row.get("success") is True for row in records),
        "productionAfp": round(sum(row.get("productionAfp", 0) for row in records), 8),
        "modelCalls": sum(row.get("modelCalls", 0) for row in records),
        "strategies": by_strategy}


def run(output: Path, profile: str):
    frozen = preflight()
    saved = json.loads((output / "preflight.json").read_text())
    if saved != frozen:
        raise ValueError("冻结预检已改变，拒绝派发")
    records_path = output / "records.jsonl"
    records = ([json.loads(line) for line in records_path.read_text().splitlines() if line]
               if records_path.exists() else [])
    completed = {row["id"] for row in records}
    if any(not row.get("success") for row in records):
        raise RuntimeError("批次已有失败任务，拒绝补跑以掩盖失败")
    for index, task in enumerate(_ordered_tasks(), 1):
        if task["id"] in completed:
            continue
        case = output / "cases" / task["id"]
        if (case / "dispatch.started").exists():
            raise RuntimeError(f"{task['id']} 已派发但没有确认结果，拒绝自动重发")
        workspace = case / "workspace"
        (workspace / ".refractagent").mkdir(parents=True)
        (workspace / ".refractagent/settings.yaml").write_text("{}\n")
        patch = output / "patches" / f"{task['strategy']}.yml"
        run_root = workspace / ".refractagent/runs"
        before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
        (case / "dispatch.started").write_text(frozen["preflightDigest"] + "\n")
        outcome, elapsed = _invoke_dsh(profile, patch, workspace, task["prompt"], 300_000)
        (case / "stdout.log").write_text(outcome.stdout or "")
        (case / "stderr.log").write_text(outcome.stderr or "")
        try:
            record = _new_record(run_root, before)
            result = verify_record(task, outcome.returncode, outcome.stdout or "", record)
            evidence = run_root / "planning" / f"{record['runId']}.json"
            result.update(elapsedMs=elapsed,
                evidencePath=str(evidence.relative_to(output)),
                evidenceSha256=__import__("hashlib").sha256(evidence.read_bytes()).hexdigest())
        except Exception as exc:
            result = {"id": task["id"], "strategy": task["strategy"], "success": False,
                "issues": [f"evidence-error:{type(exc).__name__}:{exc}"],
                "exitCode": outcome.returncode, "elapsedMs": elapsed,
                "productionAfp": 0, "modelCalls": 0}
        _append(records_path, result)
        records.append(result)
        print(json.dumps({"progress": f"{len(records)}/{len(frozen_tasks())}", **result},
                         ensure_ascii=False), flush=True)
        if sum(row.get("productionAfp", 0) for row in records) > AUTHORIZED_AFP:
            raise RuntimeError("5000 AFP 批次上限耗尽")
        if not result["success"]:
            summary = _summary(records)
            (output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
            raise RuntimeError(f"冻结任务 {task['id']} 失败，整批停止")
    summary = _summary(records)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    parser.add_argument("--profile", default="headless")
    args = parser.parse_args()
    output = args.output.resolve()
    if not args.execute_paid_run:
        result = write_preflight(output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    frozen = preflight()
    if (not math.isfinite(args.approved_afp)
            or args.approved_afp < frozen["limits"]["maximumProductionAfp"]
            or args.approved_digest != frozen["preflightDigest"]):
        raise ValueError("预检摘要或 AFP 授权上限不匹配")
    marker = output / "batch-dispatch.started"
    if not marker.exists():
        marker.write_text(frozen["preflightDigest"] + "\n")
    elif marker.read_text().strip() != frozen["preflightDigest"]:
        raise ValueError("批次派发摘要不匹配")
    print(json.dumps(run(output, args.profile), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
