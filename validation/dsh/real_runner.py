from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

try:
    from .runner import ROOT, _command_output, _package_version, _sha256, _tree_sha256
except ImportError:  # Direct execution: python validation/dsh/real_runner.py
    from runner import ROOT, _command_output, _package_version, _sha256, _tree_sha256


REAL_ARTIFACTS = (
    "preflight.json",
    "benchmark-summary.json",
    "baseline-table.md",
    "pareto-front.md",
    "oracle-gap.md",
    "failure-taxonomy.md",
    "evidence-index.json",
    "node-evaluations.ndjson",
    "node-quality-matrix.json",
    "node-quality-matrix.md",
    "strategy-comparisons.json",
    "strategy-comparisons.md",
)
DSH_BRIDGE_PROGRESS = "bridge-progress.ndjson"
MODEL_PROGRESS = "model-progress.ndjson"


def _expected_artifacts(
    execute_paid_run: bool, preflight: object
) -> tuple[str, ...]:
    if not execute_paid_run:
        return REAL_ARTIFACTS[:1]
    if isinstance(preflight, dict) and preflight.get("wire_api") == "dsh-llm":
        return (*REAL_ARTIFACTS, DSH_BRIDGE_PROGRESS)
    return (*REAL_ARTIFACTS, MODEL_PROGRESS)


def run_real_validation(
    *,
    dataset_path: Path,
    manifest_path: Path,
    output_dir: Path,
    evidence_path: Path,
    phase: str,
    repeats: int,
    execute_paid_run: bool = False,
    max_production_cost: float | None = None,
    max_evaluation_cost: float | None = None,
    max_retries: int = 2,
    invoked_by: str = "local",
) -> int:
    dataset_path = dataset_path.resolve()
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    evidence_path = evidence_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "experiments" / "run_real_v0_1.py"),
        "--dataset",
        str(dataset_path),
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir),
        "--phase",
        phase,
        "--repeats",
        str(repeats),
        "--max-retries",
        str(max_retries),
    ]
    if execute_paid_run:
        if max_production_cost is None or max_evaluation_cost is None:
            raise ValueError("Paid DSH validation requires both cost limits")
        command.extend(
            [
                "--execute-paid-run",
                "--max-production-cost",
                str(max_production_cost),
                "--max-evaluation-cost",
                str(max_evaluation_cost),
            ]
        )
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    issues: list[str] = []
    if completed.returncode != 0:
        issues.append(f"real-runner-exit:{completed.returncode}")
    preflight = None
    if (output_dir / "preflight.json").is_file():
        try:
            preflight = json.loads(
                (output_dir / "preflight.json").read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            issues.append("invalid-preflight")
    expected = _expected_artifacts(execute_paid_run, preflight)
    artifacts: dict[str, str | None] = {}
    for filename in expected:
        path = output_dir / filename
        artifacts[filename] = _sha256(path) if path.is_file() else None
        if not path.is_file():
            issues.append(f"missing-artifact:{filename}")
    summary = None
    if execute_paid_run and (output_dir / "benchmark-summary.json").is_file():
        try:
            summary = json.loads(
                (output_dir / "benchmark-summary.json").read_text(encoding="utf-8")
            )
            expected_status = "awaiting-human-audit" if phase == "final" else "complete"
            if summary.get("status") != expected_status:
                issues.append("benchmark-incomplete")
        except (json.JSONDecodeError, AttributeError):
            issues.append("invalid-benchmark-summary")
    git_status = _command_output(("git", "status", "--porcelain"))
    api_key_env = preflight.get("credential_env") if isinstance(preflight, dict) else None
    evidence = {
        "schema_version": "v0.2",
        "status": "pass" if not issues else "fail",
        "mode": "paid" if execute_paid_run else "preflight",
        "invoked_by": invoked_by,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "repeats": repeats,
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "issues": issues,
        "preflight": preflight,
        "summary": summary,
        "inputs": {
            "dataset": {"path": str(dataset_path), "sha256": _sha256(dataset_path)},
            "model_manifest": {
                "path": str(manifest_path),
                "sha256": _sha256(manifest_path),
            },
            "corpus": {
                "paths": ["data/tasks", "data/source_packs"],
                "sha256": _tree_sha256(
                    (ROOT / "data" / "tasks", ROOT / "data" / "source_packs")
                ),
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
        "artifacts": artifacts,
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
            "credential_env": api_key_env,
            "credential_available": bool(os.environ.get(str(api_key_env or ""))),
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": evidence["status"], "evidence": str(evidence_path)}))
    return 0 if not issues else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the real-model benchmark boundary")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--phase", choices=("dry-run", "pilot", "final"), default="dry-run")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--max-production-cost", type=float)
    parser.add_argument("--max-evaluation-cost", type=float)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument(
        "--invoked-by",
        choices=("local", "dsh", "dsh-plugin"),
        default="local",
    )
    args = parser.parse_args(argv)
    return run_real_validation(
        dataset_path=args.dataset,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        evidence_path=args.evidence,
        phase=args.phase,
        repeats=args.repeats,
        execute_paid_run=args.execute_paid_run,
        max_production_cost=args.max_production_cost,
        max_evaluation_cost=args.max_evaluation_cost,
        max_retries=args.max_retries,
        invoked_by=args.invoked_by,
    )


if __name__ == "__main__":
    raise SystemExit(main())
