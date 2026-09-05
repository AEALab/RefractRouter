from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "validation" / "dsh" / "plugin"


class DSHPluginTests(unittest.TestCase):
    def test_bundle_manifest_and_safe_defaults(self) -> None:
        package = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
        patch = (PLUGIN / "cordis.patch.yml").read_text(encoding="utf-8")

        self.assertEqual(package["name"], "dsh-refractrouter-validation")
        self.assertEqual(
            package["dsh"]["bundle"]["patch"],
            "./cordis.patch.yml",
        )
        self.assertIn("name: dsh-refractrouter-validation", patch)
        self.assertIn("allowPaidRuns: false", patch)
        self.assertIn("maxProductionCostUsd: 2", patch)
        self.assertIn("maxEvaluationCostUsd: 1", patch)

    def test_plugin_is_valid_esm_and_uses_native_dsh_seams(self) -> None:
        source = (PLUGIN / "index.js").read_text(encoding="utf-8")
        completed = subprocess.run(
            ["node", "--check", str(PLUGIN / "index.js")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("ctx.tools.register", source)
        self.assertIn("export const Config", source)
        self.assertIn("'~standard'", source)
        self.assertIn("ctx.subprocess.spawn", source)
        self.assertIn("ctx.sandbox.confine", source)
        self.assertIn("ctx.credentials.resolve", source)
        self.assertNotIn("node:child_process", source)

    def test_plugin_config_schema_defaults_and_rejects_unknown_fields(self) -> None:
        program = """
import { Config } from './validation/dsh/plugin/index.js'
const valid = Config['~standard'].validate({})
if (!('value' in valid) || valid.value.allowPaidRuns !== false) process.exit(1)
const invalid = Config['~standard'].validate({ unexpected: true })
if (!('issues' in invalid) || invalid.issues.length !== 1) process.exit(2)
"""
        completed = subprocess.run(
            ["node", "--input-type=module", "--eval", program],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_real_runner_accepts_plugin_provenance(self) -> None:
        completed = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "validation/dsh/real_runner.py",
                "--dataset",
                "data/benchmarks/v0.1.json",
                "--manifest",
                "data/model-manifests/openai-gpt-5.4.json",
                "--phase",
                "dry-run",
                "--output-dir",
                "/tmp/refractrouter-plugin-test-output",
                "--evidence",
                "/tmp/refractrouter-plugin-test-evidence.json",
                "--invoked-by",
                "dsh-plugin",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        evidence = json.loads(
            Path("/tmp/refractrouter-plugin-test-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["invoked_by"], "dsh-plugin")
        self.assertEqual(evidence["mode"], "preflight")


if __name__ == "__main__":
    unittest.main()
