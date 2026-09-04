from __future__ import annotations

import unittest

from refractrouter.adapters import FakeModelAdapter
from refractrouter.deepagents_executor import DeepAgentsGraphExecutor
from refractrouter.routing import strong_all
from tests.helpers import make_registry, make_task


class DeepAgentsGraphExecutorTests(unittest.TestCase):
    def test_langgraph_execution_returns_task_result(self) -> None:
        task = make_task()
        registry = make_registry()
        executor = DeepAgentsGraphExecutor(task, FakeModelAdapter(registry), registry)
        result = executor.execute(strong_all(task, registry), "strong-all")
        self.assertEqual(result.task_id, "report_001")
        self.assertGreater(result.task_score, 0)
        self.assertGreater(result.total_cost_usd, 0)


if __name__ == "__main__":
    unittest.main()
