from __future__ import annotations

import html
import json
import re
from typing import Protocol

from .model_registry import ModelRegistry
from .openai_compatible import ModelInvocationError, OpenAICompatibleClient, model_response_cost
from .schemas import ModelSpec, NodeResult, NodeSpec, TaskDAG
from .scoring import source_trace_issues


class ModelAdapter(Protocol):
    def invoke(
        self,
        task: TaskDAG,
        node: NodeSpec,
        prompt: str,
        context: dict[str, str],
        model: ModelSpec,
    ) -> NodeResult:
        """Execute one node with one candidate model."""


class FakeModelAdapter:
    """Deterministic adapter for offline dry runs and unit tests."""

    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def invoke(
        self,
        task: TaskDAG,
        node: NodeSpec,
        prompt: str,
        context: dict[str, str],
        model: ModelSpec,
    ) -> NodeResult:
        quality = self._quality(node.node_type, model.capability)
        output = self._render_output(node.node_type, quality, task, context)
        input_tokens = max(64, len(prompt) // 4)
        output_tokens = max(32, len(output) // 4)
        cost = (
            input_tokens / 1000 * model.input_cost_per_1k
            + output_tokens / 1000 * model.output_cost_per_1k
        )
        latency_ms = int(400 + (1 - model.capability) * 1600 + len(output) // 16)
        trace_issues = (
            source_trace_issues(task, context.get("render_html", ""))
            if node.node_type == "verification"
            else ()
        )
        return NodeResult(
            node_id=node.node_id,
            node_type=node.node_type,
            model_id=model.model_id,
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=round(cost, 6),
            billing_unit=model.billing_unit,
            latency_ms=latency_ms,
            score=quality,
            status="failed" if trace_issues else "ok",
            failure_type="source-trace" if trace_issues else None,
        )

    @staticmethod
    def _quality(node_type: str, capability: float) -> float:
        base = {
            "planning": 0.40,
            "extraction": 0.40,
            "synthesis": 0.30,
            "generation": 0.32,
            "rendering": 0.55,
            "verification": 0.38,
        }.get(node_type, 0.70)
        adjusted = base + capability * 0.55
        return round(min(1.0, adjusted), 3)

    @classmethod
    def _render_output(
        cls,
        node_type: str,
        quality: float,
        task: TaskDAG,
        context: dict[str, str],
    ) -> str:
        if node_type == "planning":
            sections = "; ".join(task.required_sections)
            constraints = "; ".join(task.output_constraints)
            return (
                f"requirements: {task.domain}; sections: {sections}; "
                f"constraints: {constraints}"
            )
        if node_type == "extraction":
            count = 3 if quality >= 0.82 else 2 if quality >= 0.68 else 1
            if not task.source_documents:
                raise ValueError(
                    f"Task {task.task_id} requires a loaded source pack before evidence extraction"
                )
            evidence = [
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "claim": source.content.splitlines()[0].strip(),
                    "content_hash": source.content_hash,
                }
                for source in task.source_documents[:count]
            ]
            return json.dumps({"evidence": evidence}, ensure_ascii=False, sort_keys=True)
        if node_type == "synthesis":
            evidence = cls._evidence_from_context(context)
            return json.dumps(
                {
                    "analysis": "comparison table; tradeoff summary; recommendation",
                    "evidence": evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        if node_type == "generation":
            evidence = cls._evidence_from_context(context)
            sections = []
            for index, section in enumerate(task.required_sections):
                if evidence:
                    item = evidence[index % len(evidence)]
                    paragraph = f"{item['claim']} [{item['source_id']}]"
                else:
                    paragraph = f"No traceable evidence is available for {section}."
                sections.append({"heading": section, "paragraph": paragraph})
            return json.dumps(
                {
                    "title": task.domain,
                    "sections": sections,
                    "evidence": evidence,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        if node_type == "rendering":
            if quality < 0.70:
                visible_sections = task.required_sections[:4]
            elif quality < 0.85:
                visible_sections = task.required_sections[:6]
            else:
                visible_sections = task.required_sections
            report = cls._json_from_context(context, "write_report")
            section_data = {
                item["heading"]: item["paragraph"] for item in report.get("sections", [])
            }
            sections = "".join(
                "<section><h2>"
                + html.escape(section)
                + "</h2><p>"
                + cls._render_citations(section_data.get(section, ""))
                + "</p></section>"
                for section in visible_sections
            )
            evidence = report.get("evidence", [])
            source_trace = "".join(
                f'<li id="source-{html.escape(item["source_id"])}" '
                f'data-source-id="{html.escape(item["source_id"])}" '
                f'data-content-hash="{html.escape(item["content_hash"])}">'
                f'<strong>{html.escape(item["title"])}</strong>: '
                f'{html.escape(item["claim"])}</li>'
                for item in evidence
            )
            return (
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                f"<title>{html.escape(task.task_id)}</title></head><body>"
                f"<h1>{html.escape(task.domain)}</h1>{sections}"
                f'<aside aria-label="Source trace"><h3>Source trace</h3><ol>{source_trace}</ol></aside>'
                "</body></html>"
            )
        if node_type == "verification":
            rendered = context.get("render_html", "")
            issues = source_trace_issues(task, rendered)
            status = "valid" if not issues else "invalid"
            details = ",".join(issues) if issues else "none"
            return f"verification: source_trace={status}; issues={details}; html=checked"
        return "generic output"

    @staticmethod
    def _json_from_context(context: dict[str, str], node_id: str) -> dict[str, object]:
        raw = context.get(node_id, "{}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @classmethod
    def _evidence_from_context(cls, context: dict[str, str]) -> list[dict[str, str]]:
        for node_id in ("synthesize_analysis", "extract_evidence"):
            value = cls._json_from_context(context, node_id).get("evidence", [])
            if isinstance(value, list) and value:
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _render_citations(text: str) -> str:
        escaped = html.escape(text)
        return re.sub(
            r"\[(source_\d{3})\]",
            lambda match: (
                f'<a href="#source-{match.group(1)}" '
                f'data-cite-source-id="{match.group(1)}">[{match.group(1)}]</a>'
            ),
            escaped,
        )


class OpenAICompatibleAdapter:
    """Execute fixed DAG nodes through a non-streaming Chat Completions endpoint."""

    def __init__(self, client: OpenAICompatibleClient):
        self.client = client

    def invoke(
        self,
        task: TaskDAG,
        node: NodeSpec,
        prompt: str,
        context: dict[str, str],
        model: ModelSpec,
    ) -> NodeResult:
        messages = (
            {"role": "system", "content": self._system_prompt(node)},
            {"role": "user", "content": self._user_prompt(task, node, prompt)},
        )
        try:
            response = self.client.complete(
                model,
                messages,
                json_mode=node.node_type != "rendering",
            )
        except ModelInvocationError as exc:
            return NodeResult(
                node_id=node.node_id,
                node_type=node.node_type,
                model_id=model.model_id,
                output="",
                input_tokens=0,
                output_tokens=0,
                cost=0.0,
                billing_unit=model.billing_unit,
                latency_ms=exc.latency_ms,
                status="failed",
                failure_type=exc.failure_type,
                attempts=exc.attempts,
                error_message=str(exc),
            )
        output = _strip_code_fence(response.content)
        failure_type = self._output_failure(task, node, output, context)
        return NodeResult(
            node_id=node.node_id,
            node_type=node.node_type,
            model_id=model.model_id,
            output=output,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_input_tokens=response.cached_input_tokens,
            reasoning_tokens=response.reasoning_tokens,
            cost=model_response_cost(model, response),
            billing_unit=model.billing_unit,
            latency_ms=response.latency_ms,
            attempts=response.attempts,
            finish_reason=response.finish_reason,
            request_id=response.request_id,
            status="failed" if failure_type else "ok",
            failure_type=failure_type,
        )

    @staticmethod
    def _system_prompt(node: NodeSpec) -> str:
        common = (
            "You are one node in a frozen research-report DAG. Follow only the requested "
            "node contract. Preserve source_id and content_hash exactly; do not invent sources. "
            "Do not use web search or outside knowledge. "
        )
        contracts = {
            "planning": (
                'Return one JSON object with "requirements", "sections", "constraints", '
                'and "analysis" keys.'
            ),
            "extraction": (
                'Return one JSON object with an "evidence" array. Every item must contain '
                '"source_id", "title", "claim", and "content_hash" copied from the supplied sources.'
            ),
            "synthesis": (
                'Return one JSON object with a substantive "analysis" string and an "evidence" '
                "array copied from upstream evidence. Compare alternatives and explain tradeoffs."
            ),
            "generation": (
                'Return one JSON object with "title", "sections", and "evidence". Each section '
                'must have "heading" and "paragraph"; cite claims as [source_###].'
            ),
            "rendering": (
                "Return only a complete standalone HTML document. Convert every [source_###] "
                'citation to <a href="#source-source_###" data-cite-source-id="source_###">. '
                "Add a source trace list whose entries carry data-source-id and data-content-hash "
                "copied exactly from upstream evidence. Do not add external CSS or JavaScript."
            ),
            "verification": (
                'Return one JSON object with "valid", "issues", and "summary". Do not repair output.'
            ),
        }
        return common + contracts.get(node.node_type, "Return only the requested output.")

    @staticmethod
    def _user_prompt(task: TaskDAG, node: NodeSpec, prompt: str) -> str:
        task_context = {
            "task_id": task.task_id,
            "domain": task.domain,
            "required_sections": task.required_sections,
            "output_constraints": task.output_constraints,
            "expected_claims": task.expected_claims,
        }
        parts = [
            "TASK\n" + json.dumps(task_context, ensure_ascii=False),
            "NODE REQUEST\n" + prompt,
        ]
        if node.node_type == "extraction":
            sources = [
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "content_hash": source.content_hash,
                    "content": source.content,
                }
                for source in task.source_documents
            ]
            parts.append("FROZEN SOURCE PACK\n" + json.dumps(sources, ensure_ascii=False))
        return "\n\n".join(parts)

    @staticmethod
    def _output_failure(
        task: TaskDAG,
        node: NodeSpec,
        output: str,
        context: dict[str, str],
    ) -> str | None:
        if not output.strip():
            return "empty-output"
        if node.node_type == "rendering":
            lowered = output.lower()
            if not lowered.startswith("<!doctype html>") or "</html>" not in lowered:
                return "invalid-html"
        else:
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError:
                return "invalid-json"
            if not isinstance(parsed, dict):
                return "invalid-json"
            contract_failure = _structured_output_failure(task, node.node_type, parsed)
            if contract_failure:
                return contract_failure
            if node.node_type == "verification" and source_trace_issues(
                task, context.get("render_html", "")
            ):
                return "source-trace"
        return None


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    match = re.fullmatch(
        r"```(?:json|html)?\s*(.*?)\s*```",
        stripped,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else stripped


def _structured_output_failure(
    task: TaskDAG,
    node_type: str,
    value: dict[str, object],
) -> str | None:
    if node_type == "planning":
        if not value.get("sections") and not value.get("requirements"):
            return "invalid-node-contract"
    if node_type == "synthesis" and not value.get("analysis"):
        return "invalid-node-contract"
    if node_type == "generation":
        sections = value.get("sections")
        if not isinstance(sections, list) or not sections:
            return "invalid-node-contract"
    if node_type in {"extraction", "synthesis", "generation"}:
        evidence = value.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return "invalid-evidence"
        known = {source.source_id: source.content_hash for source in task.source_documents}
        for item in evidence:
            if not isinstance(item, dict):
                return "invalid-evidence"
            source_id = item.get("source_id")
            if (
                not isinstance(source_id, str)
                or source_id not in known
                or item.get("content_hash") != known[source_id]
                or not isinstance(item.get("claim"), str)
                or not item.get("claim")
            ):
                return "invalid-evidence"
    if node_type == "verification":
        if not isinstance(value.get("valid"), bool) or not isinstance(
            value.get("issues"), list
        ):
            return "invalid-node-contract"
    return None
