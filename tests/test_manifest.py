from __future__ import annotations

import unittest
from pathlib import Path

from refractrouter.manifest import load_model_manifest


ROOT = Path(__file__).resolve().parents[1]


class ModelManifestTests(unittest.TestCase):
    def test_loads_frozen_candidate_pool_and_independent_judge(self) -> None:
        manifest = load_model_manifest(
            ROOT / "data" / "model-manifests" / "openai-gpt-5.4.json"
        )

        self.assertEqual(len(manifest.candidates), 3)
        self.assertEqual(manifest.judge.role, "judge")
        candidate_ids = {model.model_id for model in manifest.candidate_registry().list()}
        self.assertNotIn(manifest.judge.model_id, candidate_ids)
        self.assertTrue(all(model.snapshot_date for model in manifest.models))
        self.assertTrue(all(model.api_key_env == "OPENAI_API_KEY" for model in manifest.models))
        self.assertEqual(manifest.billing_unit, "USD")

    def test_loads_agent_plan_afp_rates_and_direct_plan_transport(self) -> None:
        manifest = load_model_manifest(
            ROOT / "data" / "model-manifests" / "volcengine-agent-plan.json"
        )

        self.assertEqual(manifest.billing_unit, "AFP")
        self.assertEqual(
            [model.api_model for model in manifest.candidates],
            ["deepseek-v4-flash", "minimax-m3", "deepseek-v4-pro"],
        )
        self.assertEqual(manifest.judge.api_model, "kimi-k3")
        self.assertEqual(manifest.judge.input_cost_per_1k, 1.0)
        self.assertTrue(
            all(model.wire_api == "chat-completions" for model in manifest.models)
        )
        self.assertTrue(
            all(
                model.base_url == "https://ark.cn-beijing.volces.com/api/plan/v3"
                for model in manifest.models
            )
        )
        self.assertTrue(
            all(model.api_key_env == "CODEX_ARK_API_KEY" for model in manifest.models)
        )
        self.assertTrue(all(model.max_output_tokens == 1200 for model in manifest.models))
        self.assertTrue(
            all(
                model.request_options == {"thinking": {"type": "disabled"}}
                for model in manifest.models
            )
        )


if __name__ == "__main__":
    unittest.main()
