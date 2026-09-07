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
    if isinstance(preflight, dict) and preflight.get('phase') == 'k3-baseline':
        return ('preflight.json', 'private/state.json', 'evidence-index.json', 'README.md') + (
            ('benchmark-summary.json', 'production-results.ndjson', 'submitted-reviews.json',
             'input-evidence-index.json', MODEL_PROGRESS) if execute_paid_run else ())
    if isinstance(preflight, dict) and preflight.get("phase") == "contract-replay":
        if not execute_paid_run:
            return ("preflight.json", "replay-cases.json")
        return ("preflight.json", "replay-cases.json", "replay-results.ndjson",
                "benchmark-summary.json", "evidence-index.json", MODEL_PROGRESS)
    if isinstance(preflight, dict) and preflight.get("phase") == "execution-modes":
        if not execute_paid_run:
            return ("preflight.json",)
        return ("preflight.json", "benchmark-summary.json", "baseline-table.md",
                "failure-taxonomy.md", "evidence-index.json", "node-evaluations.ndjson",
                "node-quality-matrix.json", "node-quality-matrix.md", "strategy-comparisons.json",
                "strategy-comparisons.md", MODEL_PROGRESS)
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
    selection_policy: str | None = None,
    stage: str = 'prepare',
    input_dir: Path | None = None,
    reviews: Path | None = None,
) -> int:
    from refractrouter.node_availability import SELECTION_POLICIES, LEGACY_SELECTION_POLICY, REJECTION_SELECTION_POLICY
    selection_policy = selection_policy or (
        REJECTION_SELECTION_POLICY if phase == "execution-modes" else LEGACY_SELECTION_POLICY)
    if selection_policy not in SELECTION_POLICIES:
        raise ValueError("Unknown node selection policy")
    if phase == "contract-replay" and selection_policy != LEGACY_SELECTION_POLICY:
        raise ValueError("contract-replay does not select node candidates")
    dataset_path = dataset_path.resolve()
    manifest_path = manifest_path.resolve()
    output_dir = output_dir.resolve()
    evidence_path = evidence_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "experiments" / (
            "replay_node_contracts.py" if phase == "contract-replay" else
            "run_execution_modes.py" if phase == "execution-modes" else
            "run_k3_baseline.py" if phase == "k3-baseline" else "run_real_v0_1.py")),
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
    if phase == 'k3-baseline':
        command.extend(['--stage', stage])
        if input_dir: command.extend(['--input-dir', str(input_dir.resolve())])
        if reviews: command.extend(['--reviews', str(reviews.resolve())])
    elif phase != "contract-replay":
        command.extend(["--selection-policy", selection_policy])
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
    child_env = os.environ.copy()
    child_env.pop("REFRACTROUTER_EXECUTION_MODES_HOST", None)
    child_env.pop('REFRACTROUTER_K3_BASELINE_HOST', None)
    if phase == "execution-modes" and invoked_by == "dsh-plugin":
        child_env["REFRACTROUTER_EXECUTION_MODES_HOST"] = "dsh-plugin"
    if phase == 'k3-baseline' and invoked_by == 'dsh-plugin':
        child_env['REFRACTROUTER_K3_BASELINE_HOST'] = 'dsh-plugin'
    completed = subprocess.run(
        command,
        env=child_env,
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
            allowed_status = ({'baseline-ready'} if stage=='baseline' else {'node-review-ready'} if stage=='prepare' else {'final-review-ready'}) if phase=='k3-baseline' else {expected_status}
            if summary.get("status") not in allowed_status:
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
    parser.add_argument("--phase", choices=("dry-run", "pilot", "final", "contract-replay", "execution-modes", "k3-baseline"), default="dry-run")
    parser.add_argument('--stage', choices=['baseline','prepare','compose'], default='prepare')
    parser.add_argument('--input-dir', type=Path)
    parser.add_argument('--reviews', type=Path)
    parser.add_argument("--repeats", type=int, default=1)
    from refractrouter.node_availability import SELECTION_POLICIES, LEGACY_SELECTION_POLICY
    parser.add_argument("--selection-policy", choices=SELECTION_POLICIES)
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
        selection_policy=args.selection_policy,
        stage=args.stage, input_dir=args.input_dir, reviews=args.reviews,
    )


if __name__ == "__main__":
    raise SystemExit(main())
