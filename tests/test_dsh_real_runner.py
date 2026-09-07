from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validation.dsh.real_runner import _expected_artifacts, run_real_validation


ROOT = Path(__file__).resolve().parents[1]


class DSHRealRunnerTests(unittest.TestCase):
    def test_execution_modes_preflight_uses_versioned_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = run_real_validation(
                dataset_path=ROOT / 'data/benchmarks/v0.1.json',
                manifest_path=ROOT / 'data/model-manifests/volcengine-agent-plan.json',
                output_dir=root / 'output', evidence_path=root / 'evidence.json',
                phase='execution-modes', repeats=1, max_retries=0, invoked_by='dsh-plugin')
            evidence = json.loads((root / 'evidence.json').read_text())
        self.assertEqual(code, 0)
        self.assertEqual(evidence['status'], 'pass')
        self.assertTrue(evidence['command'][1].endswith('run_execution_modes.py'))
        self.assertEqual(evidence['preflight']['call_plan']['total_model_calls'], 80)
        self.assertEqual(evidence['preflight']['selection_policy'], 'exclude-known-contract-rejections-v2')

    def test_contract_replay_preflight_selects_bounded_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            code = run_real_validation(
                dataset_path=ROOT / 'data/benchmarks/v0.1.json',
                manifest_path=ROOT / 'data/model-manifests/volcengine-agent-plan.json',
                output_dir=root / 'output', evidence_path=root / 'evidence.json',
                phase='contract-replay', repeats=1, max_retries=0, invoked_by='dsh-plugin')
            evidence = json.loads((root / 'evidence.json').read_text())
        self.assertEqual(code, 0)
        self.assertTrue(evidence['command'][1].endswith('replay_node_contracts.py'))
        self.assertEqual(evidence['preflight']['call_plan']['total_model_calls'], 7)
        self.assertIn('replay-cases.json', evidence['artifacts'])
        self.assertNotIn('baseline-table.md', _expected_artifacts(True, {'phase': 'contract-replay'}))

    def test_request_progress_is_required_only_for_paid_runs(self) -> None:
        self.assertEqual(
            _expected_artifacts(False, {"wire_api": "dsh-llm"}),
            ("preflight.json",),
        )
        direct_artifacts = _expected_artifacts(
            True, {"wire_api": "chat-completions"}
        )
        self.assertIn("model-progress.ndjson", direct_artifacts)
        for artifact in ("node-quality-matrix.json", "node-quality-matrix.md",
                         "node-evaluations.ndjson", "strategy-comparisons.json", "strategy-comparisons.md"):
            self.assertIn(artifact, direct_artifacts)
        self.assertNotIn("bridge-progress.ndjson", direct_artifacts)
        bridge_artifacts = _expected_artifacts(True, {"wire_api": "dsh-llm"})
        self.assertIn(
            "bridge-progress.ndjson",
            bridge_artifacts,
        )
        self.assertNotIn("model-progress.ndjson", bridge_artifacts)

    def test_preflight_captures_hashes_without_paid_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence_path = root / "evidence.json"
            exit_code = run_real_validation(
                dataset_path=ROOT / "data" / "benchmarks" / "v0.1.json",
                manifest_path=ROOT
                / "data"
                / "model-manifests"
                / "openai-gpt-5.4.json",
                output_dir=root / "output",
                evidence_path=evidence_path,
                phase="dry-run",
                repeats=1,
                invoked_by="dsh",
            )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(evidence["status"], "pass")
        self.assertEqual(evidence["mode"], "preflight")
        self.assertEqual(evidence["invoked_by"], "dsh")
        self.assertEqual(evidence["preflight"]["call_plan"]["total_model_calls"], 82)
        self.assertTrue(evidence["inputs"]["corpus"]["sha256"])

    def test_direct_script_entrypoint(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "validation" / "dsh" / "real_runner.py"), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--execute-paid-run", completed.stdout)


if __name__ == "__main__":
    unittest.main()
