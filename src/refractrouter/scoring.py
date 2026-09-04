from __future__ import annotations

import json
import re
from html.parser import HTMLParser

from .schemas import NodeResult, NodeSpec, TaskDAG


_CITATION_PATTERN = re.compile(r"source_\d+", re.IGNORECASE)


class _SourceTraceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cited_ids: list[str] = []
        self.reference_ids: set[str] = set()
        self.reference_hashes: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        cited_id = attributes.get("data-cite-source-id")
        if cited_id:
            self.cited_ids.append(cited_id)
        source_id = attributes.get("data-source-id")
        if source_id:
            self.reference_ids.add(source_id)
            content_hash = attributes.get("data-content-hash")
            if content_hash:
                self.reference_hashes[source_id] = content_hash


def traceable_source_ids(task: TaskDAG, final_output: str) -> set[str]:
    parser = _SourceTraceParser()
    parser.feed(final_output)
    known_hashes = {source.source_id: source.content_hash for source in task.source_documents}
    return {
        source_id
        for source_id in set(parser.cited_ids) & parser.reference_ids & set(known_hashes)
        if parser.reference_hashes.get(source_id) == known_hashes[source_id]
    }


def source_trace_issues(task: TaskDAG, final_output: str) -> tuple[str, ...]:
    parser = _SourceTraceParser()
    parser.feed(final_output)
    cited_ids = set(parser.cited_ids)
    known_hashes = {source.source_id: source.content_hash for source in task.source_documents}
    known_ids = set(known_hashes)
    issues: list[str] = []
    if not cited_ids:
        issues.append("missing-citations")
    for source_id in sorted(cited_ids - known_ids):
        issues.append(f"unknown-source:{source_id}")
    for source_id in sorted(cited_ids - parser.reference_ids):
        issues.append(f"missing-reference:{source_id}")
    for source_id in sorted(cited_ids & parser.reference_ids & known_ids):
        if parser.reference_hashes.get(source_id) != known_hashes[source_id]:
            issues.append(f"source-hash-mismatch:{source_id}")
    return tuple(issues)


def _count_citations(text: str) -> int:
    return len(_CITATION_PATTERN.findall(text))


def _contains_analysis(result: NodeResult) -> bool:
    if result.node_type != "synthesis":
        return False
    try:
        value = json.loads(result.output)
    except json.JSONDecodeError:
        return "analysis:" in result.output.lower()
    return isinstance(value, dict) and bool(value.get("analysis"))


def score_task(task: TaskDAG, node_results: tuple[NodeResult, ...], final_output: str) -> float:
    sections = sum(1 for section in task.required_sections if section.lower() in final_output.lower())
    section_score = sections / max(1, len(task.required_sections))
    traceable_ids = traceable_source_ids(task, final_output)
    citation_target = min(3, len(task.source_documents))
    citation_score = min(1.0, len(traceable_ids) / citation_target) if citation_target else 0.0
    html_valid = (
        final_output.lower().startswith("<!doctype html>")
        and "<html" in final_output.lower()
        and "</html>" in final_output.lower()
    )
    analysis_depth = 1.0 if any(_contains_analysis(result) for result in node_results) else 0.5
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
