from __future__ import annotations

import json
import unittest

from refractrouter.adapters import FakeModelAdapter
from refractrouter.graph_executor import GraphExecutor
from refractrouter.judge import IndependentJudge, apply_judge_score
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse
from refractrouter.routing import strong_all
from refractrouter.schemas import ModelSpec
from tests.helpers import make_registry, make_task


class JudgeTransport:
    def __init__(self, supported: bool = True):
        self.supported = supported

    def post(self, url, headers, body, timeout_seconds):
        judge_output = {
            "scores": {
                "requirement_coverage": 24,
                "evidence_accuracy": 25,
                "analysis_depth": 18,
                "structure_readability": 14,
                "html_validity": 15,
            },
            "claim_support": [
                {
                    "claim": "Routing benchmarks report three objectives.",
                    "source_ids": ["source_003"],
                    "supported": self.supported,
                    "explanation": "Directly supported.",
                }
            ],
            "rationale": "The report is grounded and structurally complete.",
        }
        response = {
            "id": "judge-response",
            "choices": [
                {
                    "message": {"content": json.dumps(judge_output)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 200, "completion_tokens": 100},
        }
        return TransportResponse(200, {}, json.dumps(response).encode())


class IndependentJudgeTests(unittest.TestCase):
    def test_combines_deterministic_caps_with_independent_scores(self) -> None:
        task = make_task()
        registry = make_registry()
        result = GraphExecutor(task, FakeModelAdapter(registry), registry).execute(
            strong_all(task, registry), "strong-all"
        )
        judge_model = ModelSpec(
            model_id="judge",
            provider="test",
            input_cost_per_1k_usd=0.01,
            output_cost_per_1k_usd=0.02,
            capability=1.0,
            api_model="judge-snapshot",
            base_url="https://example.invalid/v1",
            api_key_env="TEST_API_KEY",
            role="judge",
            max_output_tokens=1024,
        )
        judge = IndependentJudge(
            OpenAICompatibleClient(
                transport=JudgeTransport(),
                environment={"TEST_API_KEY": "secret"},
                max_retries=0,
            ),
            judge_model,
        )

        evaluation = judge.evaluate(task, result)
        rescored = apply_judge_score(result, evaluation)

        self.assertEqual(evaluation.final_score, 96.0)
        self.assertEqual(evaluation.final_dimensions["requirement_coverage"], 24.0)
        self.assertEqual(evaluation.cost_usd, 0.004)
        self.assertEqual(rescored.task_score, 96.0)
        self.assertEqual(result.task_score, 100.0)

    def test_unsupported_expected_claim_caps_evidence_score_at_zero(self) -> None:
        task = make_task()
        registry = make_registry()
        result = GraphExecutor(task, FakeModelAdapter(registry), registry).execute(
            strong_all(task, registry), "strong-all"
        )
        judge_model = ModelSpec(
            model_id="judge",
            provider="test",
            input_cost_per_1k_usd=0.01,
            output_cost_per_1k_usd=0.02,
            capability=1.0,
            api_model="judge-snapshot",
            base_url="https://example.invalid/v1",
            api_key_env="TEST_API_KEY",
            role="judge",
            max_output_tokens=1024,
        )
        judge = IndependentJudge(
            OpenAICompatibleClient(
                transport=JudgeTransport(supported=False),
                environment={"TEST_API_KEY": "secret"},
                max_retries=0,
            ),
            judge_model,
        )

        evaluation = judge.evaluate(task, result)

        self.assertEqual(evaluation.final_dimensions["evidence_accuracy"], 0.0)
        self.assertEqual(evaluation.final_score, 71.0)


if __name__ == "__main__":
    unittest.main()
