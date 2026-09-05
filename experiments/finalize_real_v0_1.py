from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def finalize(output_dir: Path, audit_path: Path) -> dict[str, object]:
    output_dir = output_dir.resolve()
    summary = json.loads(
        (output_dir / "benchmark-summary.json").read_text(encoding="utf-8")
    )
    if summary.get("phase") != "final":
        raise ValueError("Only a final-phase benchmark can be finalized")
    if summary.get("status") != "awaiting-human-audit":
        raise ValueError("Benchmark must be awaiting human audit")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("schema_version") != "v0.1":
        raise ValueError("Unsupported human-audit schema version")
    threshold = float(audit["agreement_threshold_points"])
    expected_tasks = set(summary["preflight"]["human_audit_task_ids"])
    expected_pairs = {
        (task_id, strategy)
        for task_id in expected_tasks
        for strategy in ("task-oracle", "node-oracle")
    }
    comparisons: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for record in audit.get("records", []):
        task_id = str(record["task_id"])
        strategy = str(record["strategy"])
        pair = (task_id, strategy)
        if pair not in expected_pairs or pair in seen:
            raise ValueError(f"Unexpected or duplicate audit record: {pair}")
        seen.add(pair)
        if record.get("human_score") is None or not record.get("reviewer"):
            raise ValueError(f"Incomplete audit record: {pair}")
        human_score = float(record["human_score"])
        if human_score < 0 or human_score > 100:
            raise ValueError(f"Human score out of range: {pair}")
        run_path = output_dir / "runs" / task_id / "repeat-1" / f"{strategy}.json"
        run = json.loads(run_path.read_text(encoding="utf-8"))
        judged_score = float(run["result"]["task_score"])
        delta = human_score - judged_score
        comparisons.append(
            {
                "task_id": task_id,
                "strategy": strategy,
                "human_score": human_score,
                "judged_score": judged_score,
                "delta": round(delta, 3),
                "within_threshold": abs(delta) <= threshold,
                "reviewer": str(record["reviewer"]),
                "notes": str(record.get("notes", "")),
            }
        )
    if seen != expected_pairs:
        raise ValueError("Human audit does not cover every frozen task/strategy pair")
    audit_pass = all(item["within_threshold"] for item in comparisons)
    oracle_decision = summary["oracle_gate"]["decision"]
    final_decision = "Go" if oracle_decision == "Go" and audit_pass else "No-go"
    result = {
        "schema_version": "v0.1",
        "status": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agreement_threshold_points": threshold,
        "audit_pass": audit_pass,
        "comparisons": comparisons,
        "oracle_decision": oracle_decision,
        "final_decision": final_decision,
    }
    (output_dir / "human-audit-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize v0.1 after frozen human audit")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args(argv)
    result = finalize(args.output_dir, args.audit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
