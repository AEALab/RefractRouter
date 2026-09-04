from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from refractrouter.cli import load_task
from refractrouter.scoring import source_trace_issues
from refractrouter.source_pack import attach_source_pack

try:
    from .runner import ROOT, _command_output, _package_version, _sha256, _tree_sha256
except ImportError:  # Direct execution: python validation/dsh/canonical_runner.py
    from runner import ROOT, _command_output, _package_version, _sha256, _tree_sha256


EXPECTED_ARTIFACTS = (
    "baseline-table.md",
    "pareto-front.md",
    "oracle-gap.md",
    "experiment-summary.json",
    "run-record.json",
    "report_001.html",
)


def _oracle_metrics(summary: dict[str, object]) -> dict[str, float | str]:
    strategies = summary.get("strategies")
    if not isinstance(strategies, dict):
        raise ValueError("Experiment summary has no strategies object")
    task = strategies.get("task-oracle")
    node = strategies.get("node-oracle")
    if not isinstance(task, dict) or not isinstance(node, dict):
        raise ValueError("Experiment summary is missing oracle results")

    task_score = float(task["task_score"])
    node_score = float(node["task_score"])
    task_cost = float(task["total_cost_usd"])
    node_cost = float(node["total_cost_usd"])
    task_latency = float(task["critical_path_latency_ms"])
    node_latency = float(node["critical_path_latency_ms"])
    quality_delta = node_score - task_score
    cost_reduction = (task_cost - node_cost) / task_cost * 100
    latency_ratio = node_latency / task_latency
    gate = (
        "Go"
        if abs(quality_delta) < 2 and cost_reduction >= 20 and latency_ratio <= 1.2
        else "No-go"
    )
    return {
        "quality_delta": round(quality_delta, 6),
        "cost_reduction_percent": round(cost_reduction, 6),
        "latency_ratio": round(latency_ratio, 6),
        "gate": gate,
    }


def run_canonical_validation(
    *,
    task_path: Path,
    output_dir: Path,
    evidence_path: Path,
    source_pack_root: Path | None = None,
    invoked_by: str = "local",
) -> int:
    task_path = task_path.resolve()
    output_dir = output_dir.resolve()
    evidence_path = evidence_path.resolve()
    source_root = (source_pack_root or task_path.parent.parent / "source_packs").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    task = attach_source_pack(load_task(task_path), source_root)
    command = [
        sys.executable,
        str(ROOT / "experiments" / "run_v0_1.py"),
        "--task",
        str(task_path),
        "--source-pack-root",
        str(source_root),
        "--output-dir",
        str(output_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    issues: list[str] = []
    if completed.returncode != 0:
        issues.append(f"experiment-exit:{completed.returncode}")

    artifact_hashes: dict[str, str | None] = {}
    for filename in EXPECTED_ARTIFACTS:
        path = output_dir / filename
        if path.is_file():
            artifact_hashes[filename] = _sha256(path)
        else:
            artifact_hashes[filename] = None
            issues.append(f"missing-artifact:{filename}")

    summary: dict[str, object] | None = None
    oracle_metrics: dict[str, float | str] | None = None
    summary_path = output_dir / "experiment-summary.json"
    if summary_path.is_file():
        try:
            parsed = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("Summary root must be an object")
            summary = parsed
            oracle_metrics = _oracle_metrics(summary)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            issues.append(f"invalid-summary:{type(exc).__name__}")

    trace_issues: tuple[str, ...] = ()
    html_path = output_dir / "report_001.html"
    if html_path.is_file():
        trace_issues = source_trace_issues(task, html_path.read_text(encoding="utf-8"))
        issues.extend(f"source-trace:{issue}" for issue in trace_issues)

    run_record_path = output_dir / "run-record.json"
    if run_record_path.is_file() and summary is not None:
        try:
            record = json.loads(run_record_path.read_text(encoding="utf-8"))
            node_summary = summary["strategies"]["node-oracle"]
            node_record = record["task_result"]
            for field in ("task_score", "total_cost_usd", "critical_path_latency_ms"):
                if node_summary[field] != node_record[field]:
                    issues.append(f"run-record-mismatch:{field}")
            if record["strategy"] != "node-oracle":
                issues.append("run-record-mismatch:strategy")
        except (json.JSONDecodeError, KeyError, TypeError):
            issues.append("invalid-run-record")

    git_status = _command_output(("git", "status", "--porcelain"))
    evidence = {
        "schema_version": "v0.1",
        "status": "pass" if not issues else "fail",
        "invoked_by": invoked_by,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task.task_id,
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "issues": issues,
        "source_trace_issues": trace_issues,
        "oracle_metrics": oracle_metrics,
        "summary": summary,
        "inputs": {
            "task": {"path": str(task_path), "sha256": _sha256(task_path)},
            "source_pack": {
                source.source_id: {"title": source.title, "sha256": source.content_hash}
                for source in task.source_documents
            },
            "code": {
                "paths": ["src/refractrouter", "experiments", "validation/dsh"],
                "sha256": _tree_sha256(
                    (
                        ROOT / "src" / "refractrouter",
                        ROOT / "experiments",
                        ROOT / "validation" / "dsh",
                    )
                ),
            },
        },
        "artifacts": artifact_hashes,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "git_commit": _command_output(("git", "rev-parse", "HEAD")),
            "git_dirty": bool(git_status),
            "git_status": git_status or "",
            "dsh": _command_output(("dsh", "--version")),
            "deepagents": _package_version("deepagents"),
            "langgraph": _package_version("langgraph"),
            "refractrouter": _package_version("refractrouter"),
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": evidence["status"], "evidence": str(evidence_path)}))
    return 0 if not issues else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the canonical v0.1 experiment")
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-pack-root", type=Path)
    parser.add_argument("--invoked-by", choices=("local", "dsh"), default="local")
    args = parser.parse_args(argv)
    return run_canonical_validation(
        task_path=args.task,
        output_dir=args.output_dir,
        evidence_path=args.evidence,
        source_pack_root=args.source_pack_root,
        invoked_by=args.invoked_by,
    )


if __name__ == "__main__":
    raise SystemExit(main())
