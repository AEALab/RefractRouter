from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from experiments.finalize_real_v0_1 import finalize


class FinalizeRealBenchmarkTests(unittest.TestCase):
    def test_requires_and_reconciles_frozen_human_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            summary = {
                "phase": "final",
                "status": "awaiting-human-audit",
                "preflight": {"human_audit_task_ids": ["report_011", "report_020"]},
                "oracle_gate": {"decision": "Go"},
            }
            (output / "benchmark-summary.json").write_text(json.dumps(summary))
            records = []
            for task_id in ("report_011", "report_020"):
                for strategy in ("task-oracle", "node-oracle"):
                    run_dir = output / "runs" / task_id / "repeat-1"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    (run_dir / f"{strategy}.json").write_text(
                        json.dumps({"result": {"task_score": 90}})
                    )
                    records.append(
                        {
                            "task_id": task_id,
                            "strategy": strategy,
                            "human_score": 88,
                            "reviewer": "reviewer-1",
                            "notes": "Reviewed against the frozen rubric.",
                        }
                    )
            audit_path = output / "audit.json"
            audit_path.write_text(
                json.dumps(
                    {
                        "schema_version": "v0.1",
                        "agreement_threshold_points": 10,
                        "records": records,
                    }
                )
            )

            result = finalize(output, audit_path)

        self.assertTrue(result["audit_pass"])
        self.assertEqual(result["final_decision"], "Go")
        self.assertTrue(all(item["delta"] == -2 for item in result["comparisons"]))


if __name__ == "__main__":
    unittest.main()
