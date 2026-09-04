from __future__ import annotations

import unittest

from refractrouter.adapters import FakeModelAdapter
from refractrouter.graph_executor import GraphExecutor
from refractrouter.routing import strong_all, weak_all
from tests.helpers import make_registry, make_task


class GraphExecutorTests(unittest.TestCase):
    def test_weak_and_strong_runs(self) -> None:
        task = make_task()
        registry = make_registry()
        executor = GraphExecutor(task, FakeModelAdapter(registry), registry)

        weak = executor.execute(weak_all(task, registry), "weak-all")
        strong = executor.execute(strong_all(task, registry), "strong-all")

        self.assertGreater(strong.task_score, weak.task_score)
        self.assertGreater(strong.total_cost_usd, weak.total_cost_usd)
        self.assertGreater(strong.critical_path_latency_ms, 0)
        self.assertTrue(strong.final_output.startswith("<!doctype html>"))
        self.assertIn('data-cite-source-id="source_001"', strong.final_output)
        self.assertIn('data-source-id="source_001"', strong.final_output)
        self.assertIn("DeepAgents provides a fixed-DAG execution harness.", strong.final_output)
        self.assertEqual(strong.failure_types, ())

    def test_missing_assignment_raises(self) -> None:
        task = make_task()
        registry = make_registry()
        executor = GraphExecutor(task, FakeModelAdapter(registry), registry)
        with self.assertRaises(ValueError):
            executor.execute({}, "missing")


if __name__ == "__main__":
    unittest.main()
