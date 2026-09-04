from __future__ import annotations

import unittest

from refractrouter.schemas import NodeResult
from refractrouter.scoring import score_node, score_task
from tests.helpers import make_task


class ScoringTests(unittest.TestCase):
    def test_score_task_rewards_sections_citations_and_html(self) -> None:
        task = make_task()
        results = (
            NodeResult(
                node_id="extract_evidence",
                node_type="extraction",
                model_id="strong-model",
                output="source_001: claim; source_002: claim; source_003: claim",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.001,
                latency_ms=100,
                score=100,
            ),
            NodeResult(
                node_id="synthesize_analysis",
                node_type="synthesis",
                model_id="strong-model",
                output="analysis: comparison; tradeoff; recommendation",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.001,
                latency_ms=100,
                score=100,
            ),
        )
        final_output = (
            "<!doctype html><html><body>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + "</body></html>"
        )
        score = score_task(task, results, final_output)
        self.assertGreater(score, 80)

    def test_placeholder_source_id_is_not_a_citation(self) -> None:
        task = make_task()
        results = (
            NodeResult(
                node_id="parse_requirements",
                node_type="planning",
                model_id="cheap-model",
                output="requirements: all claims cite source_id; analysis: none",
                input_tokens=10,
                output_tokens=10,
                cost_usd=0.001,
                latency_ms=10,
            ),
        )
        final_output = (
            "<!doctype html><html><body><h1>title</h1>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + "</body></html>"
        )

        self.assertEqual(score_task(task, results, final_output), 75.0)
        self.assertEqual(
            score_node(task, task.nodes[2], "Preserve source_id; found source_001."),
            33.333,
        )


if __name__ == "__main__":
    unittest.main()
