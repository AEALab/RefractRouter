from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.dsh.runner import run_validation


ROOT = Path(__file__).resolve().parents[1]


class DSHRunnerTests(unittest.TestCase):
    def test_runner_captures_reproducibility_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.html"
            evidence = Path(tmp) / "evidence.json"

            exit_code = run_validation(
                task_path=ROOT / "data" / "tasks" / "report_001.json",
                strategy="strong-all",
                output_path=output,
                evidence_path=evidence,
            )
            payload = json.loads(evidence.read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["issues"], [])
            self.assertEqual(payload["source_trace_issues"], [])
            self.assertEqual(len(payload["inputs"]["source_pack"]), 8)
            self.assertEqual(len(payload["inputs"]["code"]["sha256"]), 64)
            self.assertEqual(len(payload["output"]["sha256"]), 64)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
