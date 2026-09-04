from __future__ import annotations

import unittest

from refractrouter.routing import node_type_rule, statistical_q, strong_all, weak_all
from tests.helpers import make_registry, make_task


class RoutingTests(unittest.TestCase):
    def test_weak_and_strong_assignments(self) -> None:
        task = make_task()
        registry = make_registry()
        weak = weak_all(task, registry)
        strong = strong_all(task, registry)
        self.assertEqual(set(weak.values()), {"cheap-model"})
        self.assertEqual(set(strong.values()), {"strong-model"})

    def test_node_type_rule(self) -> None:
        task = make_task()
        registry = make_registry()
        rules = {
            "planning": "mid-model",
            "extraction": "cheap-model",
            "synthesis": "strong-model",
            "generation": "strong-model",
            "rendering": "mid-model",
            "verification": "cheap-model",
        }
        assignments = node_type_rule(task, registry, rules)
        self.assertEqual(assignments["parse_requirements"], "mid-model")
        self.assertEqual(assignments["extract_evidence"], "cheap-model")
        self.assertEqual(assignments["synthesize_analysis"], "strong-model")

    def test_statistical_q_without_training_data_falls_back_to_cheapest(self) -> None:
        task = make_task()
        registry = make_registry()
        assignments = statistical_q(task, registry, [])
        self.assertEqual(set(assignments.values()), {"cheap-model"})


if __name__ == "__main__":
    unittest.main()
