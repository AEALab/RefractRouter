from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from experiments.run_real_v0_1 import main


class RealRunnerPreflightTests(unittest.TestCase):
    def test_preflight_never_requires_a_key_or_calls_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            exit_code = main(
                ["--phase", "pilot", "--output-dir", str(output_dir)]
            )
            preflight = json.loads(
                (output_dir / "preflight.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertFalse(preflight["credential_available"])
        self.assertEqual(preflight["call_plan"]["total_model_calls"], 490)
        self.assertEqual(len(preflight["train_task_ids"]), 5)
        self.assertEqual(len(preflight["test_task_ids"]), 5)

    def test_agent_plan_preflight_estimates_afp_without_model_calls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            exit_code = main(
                [
                    "--phase",
                    "dry-run",
                    "--manifest",
                    str(root / "data" / "model-manifests" / "volcengine-agent-plan.json"),
                    "--output-dir",
                    str(output_dir),
                ]
            )
            preflight = json.loads(
                (output_dir / "preflight.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(preflight["billing_unit"], "AFP")
        self.assertEqual(preflight["wire_api"], "dsh-llm")
        self.assertEqual(preflight["provider"], "ark-plan")
        self.assertEqual(
            preflight["cost_estimates"],
            {
                "billing_unit": "AFP",
                "production_upper_estimate": 160.16,
                "evaluation_upper_estimate": 46.0,
                "total_upper_estimate": 206.16,
            },
        )

    def test_paid_run_rejects_a_ceiling_below_preflight_before_model_calls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit):
                main(
                    [
                        "--phase",
                        "dry-run",
                        "--manifest",
                        str(
                            root
                            / "data"
                            / "model-manifests"
                            / "volcengine-agent-plan.json"
                        ),
                        "--output-dir",
                        temp_dir,
                        "--execute-paid-run",
                        "--max-production-cost",
                        "160",
                        "--max-evaluation-cost",
                        "60",
                        "--max-retries",
                        "0",
                    ]
                )

        self.assertIn(
            "must cover the preflight estimate 160.16 AFP", stderr.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
