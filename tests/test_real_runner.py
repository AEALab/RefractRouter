from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

from experiments.run_real_v0_1 import CostLedger, _evaluate_with_budget, main
from refractrouter.schemas import ModelSpec


class RealRunnerPreflightTests(unittest.TestCase):
    def test_evaluation_budget_reserves_against_the_judge_model(self) -> None:
        judge_model = ModelSpec(
            model_id="judge",
            provider="test",
            input_cost_per_1k=0.1,
            output_cost_per_1k=0.1,
            capability=1.0,
            role="judge",
        )
        evaluation = SimpleNamespace(cost=0.4)
        judge = SimpleNamespace(
            judge_model=judge_model,
            evaluate=lambda task, result: evaluation,
        )
        ledger = CostLedger(
            billing_unit="AFP",
            production_limit=10,
            evaluation_limit=2,
            estimated_production_input_tokens=4_000,
            estimated_evaluation_input_tokens=8_000,
            estimated_output_tokens=1_200,
        )

        actual, error = _evaluate_with_budget(
            judge,
            SimpleNamespace(),
            SimpleNamespace(final_output="<html></html>"),
            ledger,
        )

        self.assertIs(actual, evaluation)
        self.assertIsNone(error)
        self.assertEqual(ledger.evaluation_spent, 0.4)

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
        self.assertEqual(preflight["call_plan"]["total_model_calls"], 700)
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
        self.assertEqual(preflight["cost_estimate_assumptions"]["output_tokens_per_call"], 8192)
        self.assertEqual(preflight["wire_api"], "chat-completions")
        self.assertEqual(
            preflight["base_url"],
            "https://ark.cn-beijing.volces.com/api/plan/v3",
        )
        self.assertEqual(preflight["provider"], "ark-plan")
        self.assertEqual(
            preflight["execution_policy"]["request_options_by_model"],
            {
                model: {"thinking": {"type": "disabled"}}
                for model in (
                    "deepseek-v4-flash",
                    "minimax-m3",
                    "deepseek-v4-pro",
                    "kimi-k3",
                )
            },
        )
        self.assertEqual(
            preflight["cost_estimate_assumptions"]["manifest_max_output_tokens"],
            8192,
        )
        self.assertEqual(
            preflight["cost_estimates"],
            {
                "billing_unit": "AFP",
                "production_upper_estimate": 238.96,
                "evaluation_upper_estimate": 420.99,
                "total_upper_estimate": 659.96,
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
            "must cover the preflight estimate 238.96 AFP", stderr.getvalue()
        )

    def test_paid_run_rejects_output_estimate_below_manifest_request_cap(self) -> None:
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
                        "--estimated-output-tokens",
                        "1199",
                        "--execute-paid-run",
                        "--max-production-cost",
                        "200",
                        "--max-evaluation-cost",
                        "60",
                        "--max-retries",
                        "0",
                    ]
                )

        self.assertIn(
            "must cover the manifest request cap 8192", stderr.getvalue()
        )

    def test_preflight_rejects_underestimate_without_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit):
                main(["--output-dir", directory, "--estimated-output-tokens", "1200"])
            self.assertFalse((Path(directory) / "preflight.json").exists())
        self.assertIn("must cover the manifest request cap 8192", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
