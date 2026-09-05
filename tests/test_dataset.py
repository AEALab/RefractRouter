from __future__ import annotations

import unittest
from pathlib import Path

from refractrouter.dataset import load_benchmark_dataset


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkDatasetTests(unittest.TestCase):
    def test_loads_disjoint_twenty_task_dataset(self) -> None:
        dataset = load_benchmark_dataset(
            ROOT / "data" / "benchmarks" / "v0.1.json",
            ROOT / "data" / "tasks",
            ROOT / "data" / "source_packs",
        )

        self.assertEqual(len(dataset.train_tasks), 10)
        self.assertEqual(len(dataset.test_tasks), 10)
        self.assertEqual(len(dataset.all_tasks), 20)
        self.assertEqual(len({task.source_pack_id for task in dataset.all_tasks}), 20)
        self.assertTrue(all(len(task.source_documents) == 8 for task in dataset.all_tasks))
        self.assertEqual(len(dataset.human_audit_task_ids), 2)


if __name__ == "__main__":
    unittest.main()
