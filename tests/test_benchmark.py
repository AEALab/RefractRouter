from __future__ import annotations

import unittest

from refractrouter.adapters import FakeModelAdapter
from refractrouter.benchmark import (
    BenchmarkObservation,
    aggregate_observations,
    oracle_gate,
    pareto_front_markdown,
)
from dataclasses import replace

from experiments.run_real_v0_1 import (
    call_plan,
    run_task_strategies,
    select_judged_task_oracle,
)
from refractrouter.judge import JudgeEvaluation
from tests.helpers import make_registry, make_task


class BenchmarkTests(unittest.TestCase):
    def test_real_runner_strategy_shape_uses_isolated_probes(self) -> None:
        task = make_task()
        registry = make_registry()

        results = run_task_strategies(
            task,
            registry,
            FakeModelAdapter(registry),
            include_learned=False,
        )

        self.assertEqual(
            set(results),
            {"weak-all", "strong-all", "node-type-rule", "task-oracle", "node-oracle"},
        )
        self.assertTrue(all(len(result.node_results) == 7 for result in results.values()))

    def test_aggregate_and_gate_require_complete_judge_coverage(self) -> None:
        task = make_task()
        registry = make_registry()
        results = run_task_strategies(
            task,
            registry,
            FakeModelAdapter(registry),
            include_learned=False,
        )
        observations = [
            BenchmarkObservation(task.task_id, 1, name, result)
            for name, result in results.items()
        ]

        summary = aggregate_observations(observations)
        gate = oracle_gate(summary)

        self.assertEqual(summary["node-oracle"]["judge_coverage"], 0.0)
        self.assertEqual(summary["node-oracle"]["quality_stddev"], 0.0)
        self.assertFalse(gate["judge_complete"])
        self.assertEqual(gate["decision"], "No-go")

    def test_pareto_report_uses_quality_and_production_cost(self) -> None:
        summary = {
            "expensive": {
                "quality_mean": 90.0,
                "production_cost_mean_usd": 1.0,
                "critical_path_p95_ms": 100,
            },
            "efficient": {
                "quality_mean": 90.0,
                "production_cost_mean_usd": 0.5,
                "critical_path_p95_ms": 150,
            },
        }

        report = pareto_front_markdown(summary)

        self.assertIn("| `expensive` | 90.000 | 1.00000000 | 100 | No |", report)
        self.assertIn("| `efficient` | 90.000 | 0.50000000 | 150 | Yes |", report)

    def test_call_plan_counts_dry_run_calls(self) -> None:
        task = make_task()
        plan = call_plan((), (task,), 3, 1, False)

        self.assertEqual(plan["production_model_calls"], 56)
        self.assertEqual(plan["judge_model_calls"], 5)
        self.assertEqual(plan["total_model_calls"], 61)

    def test_oracle_gate_accepts_same_cost_quality_gain(self) -> None:
        summary = {
            "task-oracle": {
                "quality_mean": 80,
                "production_cost_mean_usd": 1,
                "critical_path_p95_ms": 100,
                "success_rate": 1,
                "judge_coverage": 1,
            },
            "node-oracle": {
                "quality_mean": 86,
                "production_cost_mean_usd": 1.04,
                "critical_path_p95_ms": 120,
                "success_rate": 1,
                "judge_coverage": 1,
            },
        }

        gate = oracle_gate(summary)

        self.assertTrue(gate["quality_path_pass"])
        self.assertFalse(gate["cost_path_pass"])
        self.assertEqual(gate["decision"], "Go")

    def test_oracle_gate_rejects_latency_regression(self) -> None:
        summary = {
            "task-oracle": {
                "quality_mean": 90,
                "production_cost_mean_usd": 1,
                "critical_path_p95_ms": 100,
                "success_rate": 1,
                "judge_coverage": 1,
            },
            "node-oracle": {
                "quality_mean": 90,
                "production_cost_mean_usd": 0.7,
                "critical_path_p95_ms": 121,
                "success_rate": 1,
                "judge_coverage": 1,
            },
        }

        gate = oracle_gate(summary)

        self.assertTrue(gate["cost_path_pass"])
        self.assertFalse(gate["latency_pass"])
        self.assertEqual(gate["decision"], "No-go")

    def test_task_oracle_uses_independent_judge_score(self) -> None:
        task = make_task()
        registry = make_registry()
        results = run_task_strategies(
            task, registry, FakeModelAdapter(registry), include_learned=False
        )
        singles = {
            "cheap-model": replace(results["weak-all"], total_cost_usd=0.01),
            "mid-model": replace(results["strong-all"], total_cost_usd=0.02),
            "strong-model": replace(results["strong-all"], total_cost_usd=0.03),
        }

        def evaluation(score: float) -> JudgeEvaluation:
            return JudgeEvaluation(
                rubric_version="v0.1",
                deterministic_dimensions={},
                judge_dimensions={},
                final_dimensions={},
                final_score=score,
                claim_support=(),
                rationale="",
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=0,
                latency_ms=0,
                attempts=1,
                request_id=None,
            )

        selected = select_judged_task_oracle(
            singles,
            {
                "cheap-model": evaluation(70),
                "mid-model": evaluation(95),
                "strong-model": evaluation(90),
            },
        )

        self.assertEqual(selected, "mid-model")


if __name__ == "__main__":
    unittest.main()
