from __future__ import annotations

import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
