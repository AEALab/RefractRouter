from __future__ import annotations

import unittest

from refractrouter.adapters import FakeModelAdapter
from refractrouter.deepagents_executor import DeepAgentsGraphExecutor
from refractrouter.graph_executor import GraphExecutor
from refractrouter.routing import node_oracle, task_oracle
from experiments.run_v0_1 import probe_node_candidates
from tests.helpers import make_registry, make_task


class OracleTests(unittest.TestCase):
    def test_task_and_node_oracles(self) -> None:
        task = make_task()
        registry = make_registry()
        executor = GraphExecutor(task, FakeModelAdapter(registry), registry)
        results = [
            executor.execute(
                {node.node_id: model.model_id for node in task.nodes},
                f"single:{model.model_id}",
            )
            for model in registry.list()
        ]

        task_assignment = task_oracle(task, registry, results)
        node_assignment = node_oracle(task, registry, results)

        self.assertEqual(set(task_assignment.values()), {"strong-model"})
        self.assertGreater(len(set(node_assignment.values())), 1)
        self.assertEqual(node_assignment["extract_evidence"], "strong-model")
        self.assertEqual(node_assignment["render_html"], "mid-model")

    def test_node_probes_execute_only_the_target_node(self) -> None:
        task = make_task()
        registry = make_registry()
        adapter = FakeModelAdapter(registry)
        reference = GraphExecutor(task, adapter, registry).execute(
            {node.node_id: registry.strongest().model_id for node in task.nodes},
            "reference",
        )
        executor = DeepAgentsGraphExecutor(task, adapter, registry)

        probes = probe_node_candidates(task, registry, executor, reference)

        self.assertEqual(len(probes), len(task.nodes) * len(registry.list()))
        self.assertTrue(all(len(probe.node_results) == 1 for probe in probes))
        self.assertTrue(
            all(len(probe.model_assignments) == 1 for probe in probes)
        )


if __name__ == "__main__":
    unittest.main()
