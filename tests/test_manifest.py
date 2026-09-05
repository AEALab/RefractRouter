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


if __name__ == "__main__":
    unittest.main()
