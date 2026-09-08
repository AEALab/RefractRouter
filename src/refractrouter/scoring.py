from __future__ import annotations

import json
import re
from html.parser import HTMLParser

from .schemas import NodeResult, NodeSpec, TaskDAG
from .evidence_state import evidence_artifact, uses_evidence_state, validate_evidence


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


def score_task_dimensions(
    task: TaskDAG,
    node_results: tuple[NodeResult, ...],
    final_output: str,
) -> dict[str, float]:
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
    return {
        "requirement_coverage": round(section_score * 25, 3),
        "evidence_accuracy": round(citation_score * 25, 3),
        "analysis_depth": round(analysis_depth * 20, 3),
        "structure_readability": round(readability * 15, 3),
        "html_validity": 15.0 if html_valid else 0.0,
    }


def score_task(task: TaskDAG, node_results: tuple[NodeResult, ...], final_output: str) -> float:
    dimensions = score_task_dimensions(task, node_results, final_output)
    return round(sum(dimensions.values()), 3)


NODE_CHECKS_VERSION = "v0.3"


class _HeadingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headings: list[str] = []
        self.current: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self.current is not None:
            self.headings.append("".join(self.current).strip())
            self.current = None


def node_contract_checks(task: TaskDAG, node: NodeSpec, output: str, context=None) -> dict:
    """Deterministic validity/coverage caps, never a claim of semantic quality."""
    context = context or {}
    version = task.output_contract_version
    owned = uses_evidence_state(task) and node.node_type in {
        "synthesis", "generation", "rendering", "verification"}
    artifact = None
    if owned:
        try:
            artifact = evidence_artifact(task, context)
        except ValueError:
            return {"version": version, "score_cap": 0.0, "checks": {},
                    "issues": ["invalid-reference-context"]}
    issues: list[str] = []
    checks: dict[str, object] = {}
    cap = 100.0
    value = None
    if node.node_type != "rendering":
        try:
            value = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            value = None
        if not isinstance(value, dict):
            return {"version": version, "score_cap": 0.0,
                    "checks": {"json_object": False}, "issues": ["invalid-json"]}
        checks["json_object"] = True

    headings = None
    if node.node_type == "planning":
        raw = value.get("sections")
        headings = raw if isinstance(raw, list) and all(isinstance(x, str) for x in raw) else []
        checks["planning_contract"] = bool(value.get("requirements")) and isinstance(value.get("constraints"), list) and isinstance(value.get("analysis"), str) and bool(value["analysis"].strip()) and bool(headings)
        if not checks["planning_contract"]:
            issues.append("invalid-planning-contract")
            cap = 0.0
    elif node.node_type == "generation":
        sections = value.get("sections")
        valid = isinstance(sections, list) and bool(sections) and all(
            isinstance(x, dict) and isinstance(x.get("heading"), str) and bool(x["heading"].strip())
            and isinstance(x.get("paragraph"), str) and bool(x["paragraph"].strip()) for x in sections
        )
        checks["generation_contract"] = valid and isinstance(value.get("title"), str) and bool(value["title"].strip())
        headings = [x["heading"] for x in sections] if valid else []
        if not checks["generation_contract"]:
            issues.append("invalid-generation-contract")
            cap = 0.0
    elif node.node_type == "synthesis":
        checks["analysis_present"] = isinstance(value.get("analysis"), str) and bool(value["analysis"].strip())
        if not checks["analysis_present"]:
            issues.append("missing-analysis")
            cap = 0.0
    elif node.node_type == "rendering":
        lowered = output.strip().lower()
        checks["html_envelope"] = lowered.startswith("<!doctype html>") and "<html" in lowered and lowered.endswith("</html>")
        trace = source_trace_issues(task, output)
        checks["source_trace"] = not trace
        parser = _HeadingParser()
        parser.feed(output)
        headings = parser.headings
        issues.extend(trace)
        if not checks["html_envelope"]:
            issues.append("invalid-html")
        if issues:
            cap = 0.0
        if artifact and not traceable_source_ids(task, output) <= {x.source_id for x in artifact.items}:
            issues.append("unresolved-citations")
            cap = 0.0
    elif node.node_type == "verification":
        rendered = context.get("render_html", "")
        lowered = rendered.strip().lower()
        expected_issues = list(source_trace_issues(task, rendered))
        if not (lowered.startswith("<!doctype html>") and "<html" in lowered and lowered.endswith("</html>")):
            expected_issues.append("invalid-html")
        valid = isinstance(value.get("valid"), bool) and isinstance(value.get("issues"), list) and isinstance(value.get("summary"), str) and bool(value["summary"].strip())
        checks["verification_contract"] = valid
        checks["known_defects"] = expected_issues
        # Passing mechanical checks does not prove semantic validity. A rejection may
        # identify unsupported claims; the independent judge must assess that finding.
        checks["verdict_matches_checks"] = valid and (not expected_issues or not value["valid"])
        checks["issues_consistent"] = valid and bool(value["issues"]) == (not value["valid"])
        if not rendered or not all(checks[k] for k in ["verification_contract", "verdict_matches_checks", "issues_consistent"]):
            issues.append("incorrect-verification")
            cap = 0.0

    if headings is not None:
        normalized = [x.strip().casefold() for x in headings]
        required = {x.strip().casefold() for x in task.required_sections}
        missing = sorted(required - set(normalized))
        checks["missing_sections"] = missing
        if missing:
            issues.append("missing-sections")
        cap = min(cap, 100 * (len(required) - len(missing)) / len(required)) if required else cap

    if node.node_type in {"extraction", "synthesis", "generation"}:
        if artifact:
            valid, valid_ids = True, {item.source_id for item in artifact.items}
            checks["evidence_artifact"] = artifact.snapshot()
            if "evidence" in value:
                issues.append("unexpected-evidence")
                cap = 0.0
        else:
            valid, valid_ids = validate_evidence(task, value.get("evidence"))
        checks["evidence_identity"] = valid
        checks["unique_sources"] = sorted(valid_ids)
        if not valid:
            issues.append("invalid-evidence")
            cap = 0.0
        # Literal source IDs must resolve; repetition never raises the score.
        if node.node_type == "generation" or (artifact and node.node_type == "synthesis"):
            raw_sections = value.get("sections")
            paragraphs = (value.get("analysis", "") if node.node_type == "synthesis" else
                " ".join(x["paragraph"] for x in (raw_sections if isinstance(raw_sections, list) else []) if isinstance(x, dict) and isinstance(x.get("paragraph"), str)))
            paragraphs = paragraphs if isinstance(paragraphs, str) else ""
            citations = set(re.findall(r"\[(source_\d+)\]", paragraphs))
            checks["citations_resolve"] = bool(citations) and citations <= valid_ids
            if not checks["citations_resolve"]:
                issues.append("unresolved-citations")
                cap = 0.0
    return {"version": version, "score_cap": round(cap, 3), "checks": checks, "issues": issues}


def score_node(task: TaskDAG, node: NodeSpec, output: str, context=None) -> float:
    return node_contract_checks(task, node, output, context)["score_cap"]
