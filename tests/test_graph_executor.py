from __future__ import annotations

import unittest

from refractrouter.adapters import FakeModelAdapter
from refractrouter.graph_executor import GraphExecutor
from refractrouter.routing import strong_all, weak_all
from refractrouter.schemas import NodeResult
from tests.helpers import make_registry, make_task


class GraphExecutorTests(unittest.TestCase):
    def test_weak_and_strong_runs(self) -> None:
        task = make_task()
        registry = make_registry()
        executor = GraphExecutor(task, FakeModelAdapter(registry), registry)

        weak = executor.execute(weak_all(task, registry), "weak-all")
        strong = executor.execute(strong_all(task, registry), "strong-all")

        self.assertGreater(strong.task_score, weak.task_score)
        self.assertGreater(strong.total_cost, weak.total_cost)
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

    def test_failed_parent_stops_downstream_paid_calls(self) -> None:
        task = make_task()
        registry = make_registry()

        class FailingAdapter:
            def __init__(self):
                self.calls = 0

            def invoke(self, task, node, prompt, context, model):
                self.calls += 1
                return NodeResult(
                    node_id=node.node_id,
                    node_type=node.node_type,
                    model_id=model.model_id,
                    output="",
                    input_tokens=1,
                    output_tokens=0,
                    cost=0.01,
                    latency_ms=5,
                    status="failed",
                    failure_type="timeout",
                )

        adapter = FailingAdapter()
        result = GraphExecutor(task, adapter, registry).execute(
            strong_all(task, registry), "strong-all"
        )

        self.assertEqual(adapter.calls, 1)
        self.assertEqual(result.node_results[0].failure_type, "timeout")
        self.assertTrue(
            all(
                node.failure_type == "upstream-failure"
                for node in result.node_results[1:]
            )
        )
        self.assertEqual(result.total_cost, 0.01)


if __name__ == "__main__":
    unittest.main()
