from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validation.dsh.canonical_runner import run_canonical_validation


ROOT = Path(__file__).resolve().parents[1]


class DSHCanonicalRunnerTests(unittest.TestCase):
    def test_direct_script_entrypoint_loads(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "validation" / "dsh" / "canonical_runner.py"),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Validate the canonical v0.1 experiment", completed.stdout)

    def test_runner_recomputes_oracle_gate_and_hashes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "reports"
            evidence = Path(tmp) / "canonical-evidence.json"

            exit_code = run_canonical_validation(
                task_path=ROOT / "data" / "tasks" / "report_001.json",
                output_dir=output_dir,
                evidence_path=evidence,
            )
            payload = json.loads(evidence.read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["issues"], [])
            self.assertEqual(payload["oracle_metrics"]["gate"], "No-go")
            self.assertGreater(payload["oracle_metrics"]["cost_reduction_percent"], 20)
            self.assertGreater(payload["oracle_metrics"]["latency_ratio"], 1.2)
            self.assertTrue(all(payload["artifacts"].values()))


if __name__ == "__main__":
    unittest.main()
