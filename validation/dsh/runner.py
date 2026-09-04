from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
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


ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for root in paths
        for path in (root.rglob("*") if root.is_dir() else (root,))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _command_output(command: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or completed.stderr.strip() or None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def run_validation(
    *,
    task_path: Path,
    strategy: str,
    output_path: Path,
    evidence_path: Path,
    source_pack_root: Path | None = None,
    invoked_by: str = "local",
) -> int:
    task_path = task_path.resolve()
    output_path = output_path.resolve()
    evidence_path = evidence_path.resolve()
    source_root = (source_pack_root or task_path.parent.parent / "source_packs").resolve()

    task = attach_source_pack(load_task(task_path), source_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "refractrouter.cli",
        "run",
        "--task",
        str(task_path),
        "--strategy",
        strategy,
        "--source-pack-root",
        str(source_root),
        "--output",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    issues: list[str] = []
    cli_result: dict[str, object] | None = None
    if completed.returncode != 0:
        issues.append(f"cli-exit:{completed.returncode}")
    else:
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            issues.append("invalid-cli-json")
        else:
            if isinstance(parsed, dict):
                cli_result = parsed
            else:
                issues.append("invalid-cli-json")

    html_hash: str | None = None
    trace_issues: tuple[str, ...] = ()
    if output_path.is_file():
        html = output_path.read_text(encoding="utf-8")
        html_hash = _sha256(output_path)
        trace_issues = source_trace_issues(task, html)
        issues.extend(f"source-trace:{issue}" for issue in trace_issues)
        lowered = html.lower()
        if not (
            lowered.startswith("<!doctype html>")
            and "<html" in lowered
            and "</html>" in lowered
        ):
            issues.append("invalid-html-envelope")
    else:
        issues.append("missing-output")

    if cli_result and cli_result.get("failure_types"):
        issues.append("cli-reported-failures")

    tracked_inputs = {
        "task": {"path": str(task_path), "sha256": _sha256(task_path)},
        "source_pack": {
            source.source_id: {
                "sha256": source.content_hash,
                "title": source.title,
            }
            for source in task.source_documents
        },
    }
    lockfile = ROOT / "uv.lock"
    if lockfile.is_file():
        tracked_inputs["lockfile"] = {"path": str(lockfile), "sha256": _sha256(lockfile)}
    tracked_inputs["code"] = {
        "paths": ["src/refractrouter", "validation/dsh/runner.py"],
        "sha256": _tree_sha256((ROOT / "src" / "refractrouter", Path(__file__).resolve())),
    }

    git_status = _command_output(("git", "status", "--porcelain"))

    evidence = {
        "schema_version": "v0.1",
        "status": "pass" if not issues else "fail",
        "invoked_by": invoked_by,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "task_id": task.task_id,
        "strategy": strategy,
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "cli_result": cli_result,
        "issues": issues,
        "source_trace_issues": trace_issues,
        "inputs": tracked_inputs,
        "output": {"path": str(output_path), "sha256": html_hash},
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
    parser = argparse.ArgumentParser(description="Run deterministic RefractRouter validation")
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--strategy", choices=("weak-all", "strong-all"), default="strong-all")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--source-pack-root", type=Path)
    parser.add_argument("--invoked-by", choices=("local", "dsh"), default="local")
    args = parser.parse_args(argv)
    return run_validation(
        task_path=args.task,
        strategy=args.strategy,
        output_path=args.output,
        evidence_path=args.evidence,
        source_pack_root=args.source_pack_root,
        invoked_by=args.invoked_by,
    )


if __name__ == "__main__":
    raise SystemExit(main())
