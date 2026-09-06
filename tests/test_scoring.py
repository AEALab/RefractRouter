from __future__ import annotations

import unittest

from refractrouter.schemas import NodeResult
from refractrouter.scoring import source_trace_issues, score_node, score_task
from tests.helpers import make_task


class ScoringTests(unittest.TestCase):
    def test_score_task_rewards_traceable_final_html_citations(self) -> None:
        task = make_task()
        results = (
            NodeResult(
                node_id="extract_evidence",
                node_type="extraction",
                model_id="strong-model",
                output="source_001: claim; source_002: claim; source_003: claim",
                input_tokens=100,
                output_tokens=50,
                cost=0.001,
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
                cost=0.001,
                latency_ms=100,
                score=100,
            ),
        )
        final_output = (
            "<!doctype html><html><body>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + "".join(
                f'<a data-cite-source-id="source_00{i}" href="#source-source_00{i}">citation</a>'
                f'<li data-source-id="source_00{i}" data-content-hash="hash-00{i}" '
                f'id="source-source_00{i}">source</li>'
                for i in range(1, 4)
            )
            + "</body></html>"
        )
        score = score_task(task, results, final_output)
        self.assertEqual(score, 100.0)
        self.assertEqual(source_trace_issues(task, final_output), ())

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
                cost=0.001,
                latency_ms=10,
            ),
        )
        final_output = (
            "<!doctype html><html><body><h1>title</h1>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + "</body></html>"
        )

        self.assertEqual(score_task(task, results, final_output), 65.0)
        self.assertEqual(
            score_node(task, task.nodes[2], "Preserve source_id; found source_001."),
            33.333,
        )

    def test_intermediate_citations_do_not_increase_task_score(self) -> None:
        task = make_task()
        results = (
            NodeResult(
                node_id="extract_evidence",
                node_type="extraction",
                model_id="strong-model",
                output="source_001 source_002 source_003",
                input_tokens=10,
                output_tokens=10,
                cost=0.001,
                latency_ms=10,
            ),
        )
        final_output = (
            "<!doctype html><html><body><h1>title</h1>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + "</body></html>"
        )

        self.assertEqual(score_task(task, results, final_output), 65.0)
        self.assertEqual(source_trace_issues(task, final_output), ("missing-citations",))

    def test_unknown_or_unresolved_sources_do_not_receive_credit(self) -> None:
        task = make_task()
        final_output = (
            "<!doctype html><html><body><h1>title</h1>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + '<a data-cite-source-id="source_001">known but unresolved</a>'
            + '<a data-cite-source-id="source_999">unknown</a>'
            + '<li data-source-id="source_999" data-content-hash="unknown">unknown source</li>'
            + "</body></html>"
        )

        self.assertEqual(score_task(task, (), final_output), 65.0)
        self.assertEqual(
            source_trace_issues(task, final_output),
            ("unknown-source:source_999", "missing-reference:source_001"),
        )

    def test_source_hash_mismatch_does_not_receive_credit(self) -> None:
        task = make_task()
        final_output = (
            "<!doctype html><html><body><h1>title</h1>"
            + "".join(f"<h2>{section}</h2>" for section in task.required_sections)
            + '<a data-cite-source-id="source_001">citation</a>'
            + '<li data-source-id="source_001" data-content-hash="stale-hash">source</li>'
            + "</body></html>"
        )

        self.assertEqual(score_task(task, (), final_output), 65.0)
        self.assertEqual(
            source_trace_issues(task, final_output),
            ("source-hash-mismatch:source_001",),
        )


if __name__ == "__main__":
    unittest.main()
