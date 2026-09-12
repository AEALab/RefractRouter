from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "validation" / "dsh" / "plugin"


class DSHPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Never install from the test suite: clean checkouts install the locked dev tools first.
        completed = subprocess.run(
            ["npm", "run", "--prefix", str(PLUGIN), "build"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Build the TypeScript plugin after npm ci --prefix validation/dsh/plugin.\n"
                f"{completed.stdout}\n{completed.stderr}"
            )

    def test_settings_examples_match_python_configuration_and_compile(self) -> None:
        from refractrouter.agent_cli import example_configuration
        from refractrouter.ark_plan import afp_metadata
        from refractrouter.application_config import compile_configuration

        examples = json.loads((PLUGIN / "src" / "provider-examples.json").read_text())
        self.assertEqual(json.loads((PLUGIN / "src" / "afp-metadata.json").read_text()), afp_metadata())
        for kind, config in examples.items():
            self.assertEqual(config, example_configuration(kind))
            config["defaultReasoningEffort"] = "medium"
            config["strategies"] = {"quality": {"reasoningEffort": "high"}}
            for strategy, effort in [("economy", "medium"), ("quality", "high")]:
                compiled = compile_configuration(config, strategy=strategy)
                self.assertTrue(all(m.request_options["reasoning_effort"] == effort
                                    for m in compiled.manifest.models))
                if kind == "ark-agent-plan":
                    self.assertTrue(all(m.request_options["thinking"]["type"] in {"auto", "enabled"}
                                        for m in compiled.manifest.models))

    def test_bundle_manifest_and_safe_defaults(self) -> None:
        package = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
        patch = (PLUGIN / "cordis.patch.yml").read_text(encoding="utf-8")

        self.assertEqual(package["name"], "dsh-refractrouter-validation")
        self.assertEqual(package["version"], "0.14.0")
        self.assertTrue(package["private"])
        self.assertEqual(package["engines"]["node"], ">=22.19.0 <23")
        self.assertEqual(package["packageManager"], "pnpm@10.15.0")
        self.assertEqual(
            package["dsh"]["bundle"]["patch"],
            "./cordis.patch.yml",
        )
        self.assertEqual(
            package["dsh"]["compatibility"]["cli"],
            "0.1.1-rc.2",
        )
        self.assertEqual(package["exports"]["./client"]["default"], "./dist/client.js")
        self.assertEqual(package["dsh"]["client"]["platform"], "web")
        self.assertIn("@deepseek-ai/dsh-client-ui-settings", package["dsh"]["client"]["inject"])
        self.assertIn("name: dsh-refractrouter-validation", patch)
        self.assertIn("allowPaidRuns: false", patch)
        self.assertIn("maxProductionCost: 2", patch)
        self.assertIn("maxEvaluationCost: 1", patch)
        self.assertIn("maxRetries: 0", patch)

    def test_plugin_is_valid_esm_and_uses_native_dsh_seams(self) -> None:
        source = (PLUGIN / "src" / "index.ts").read_text(encoding="utf-8")
        completed = subprocess.run(
            ["node", "--check", str(PLUGIN / "dist" / "index.js")],
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

    def test_node_service_contract(self) -> None:
        completed = subprocess.run(
            ["npm", "run", "--prefix", str(PLUGIN), "test:contracts"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            completed.returncode,
            0,
            f"{completed.stdout}\n{completed.stderr}",
        )

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
