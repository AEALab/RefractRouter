from __future__ import annotations

import unittest

from tests.helpers import make_registry


class ModelRegistryTests(unittest.TestCase):
    def test_cheapest_and_strongest(self) -> None:
        registry = make_registry()
        self.assertEqual(registry.cheapest().model_id, "cheap-model")
        self.assertEqual(registry.strongest().model_id, "strong-model")

    def test_unknown_model_raises(self) -> None:
        registry = make_registry()
        with self.assertRaises(KeyError):
            registry.get("missing-model")


if __name__ == "__main__":
    unittest.main()
