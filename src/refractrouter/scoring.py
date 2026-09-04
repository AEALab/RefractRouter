from __future__ import annotations

import re

from .schemas import NodeResult, NodeSpec, TaskDAG


_CITATION_PATTERN = re.compile(r"source_\d+", re.IGNORECASE)


def _count_citations(text: str) -> int:
    return len(_CITATION_PATTERN.findall(text))


def score_task(task: TaskDAG, node_results: tuple[NodeResult, ...], final_output: str) -> float:
    sections = sum(1 for section in task.required_sections if section.lower() in final_output.lower())
    section_score = sections / max(1, len(task.required_sections))
    citations = sum(_count_citations(result.output) for result in node_results)
    citation_score = min(1.0, citations / 3)
    html_valid = (
        final_output.lower().startswith("<!doctype html>")
        and "<html" in final_output.lower()
        and "</html>" in final_output.lower()
    )
    analysis_depth = 1.0 if any("analysis:" in result.output.lower() for result in node_results) else 0.5
    readability = 1.0 if "<h1>" in final_output.lower() or "<h2>" in final_output.lower() else 0.5
    score = (
        section_score * 25
        + citation_score * 25
        + analysis_depth * 20
        + readability * 15
        + (1.0 if html_valid else 0.0) * 15
    )
    return round(score, 3)


def score_node(task: TaskDAG, node: NodeSpec, output: str) -> float:
    if node.node_type == "planning":
        covered = sum(1 for section in task.required_sections if section.lower() in output.lower())
        return round(covered / max(1, len(task.required_sections)) * 100, 3)
    if node.node_type == "extraction":
        citations = _count_citations(output)
        return round(min(1.0, citations / 3) * 100, 3)
    if node.node_type == "synthesis":
        markers = ("comparison", "tradeoff", "recommendation")
        return round(sum(marker in output.lower() for marker in markers) / len(markers) * 100, 3)
    if node.node_type == "generation":
        covered = sum(1 for section in task.required_sections if section.lower() in output.lower())
        return round(covered / max(1, len(task.required_sections)) * 100, 3)
    if node.node_type == "rendering":
        valid = output.lower().startswith("<!doctype html>") and "</html>" in output.lower()
        covered = sum(1 for section in task.required_sections if section.lower() in output.lower())
        section_score = covered / max(1, len(task.required_sections))
        return round(section_score * 70 + (1.0 if valid else 0.0) * 30, 3)
    if node.node_type == "verification":
        return 100.0 if "verification:" in output.lower() else 0.0
    return 0.0
