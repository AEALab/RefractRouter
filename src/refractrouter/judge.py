from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Mapping

from .openai_compatible import OpenAICompatibleClient, model_response_cost
from .schemas import ModelSpec, TaskDAG, TaskResult
from .scoring import score_task_dimensions, source_trace_issues


JUDGE_RUBRIC_VERSION = "v0.1"
DIMENSION_LIMITS = {
    "requirement_coverage": 25.0,
    "evidence_accuracy": 25.0,
    "analysis_depth": 20.0,
    "structure_readability": 15.0,
    "html_validity": 15.0,
}


@dataclass(frozen=True, slots=True)
class JudgeEvaluation:
    rubric_version: str
    deterministic_dimensions: Mapping[str, float]
    judge_dimensions: Mapping[str, float]
    final_dimensions: Mapping[str, float]
    final_score: float
    claim_support: tuple[Mapping[str, object], ...]
    rationale: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    cost_usd: float
    latency_ms: int
    attempts: int
    request_id: str | None


class IndependentJudge:
    """Evaluate final reports with a model excluded from the candidate pool."""

    def __init__(self, client: OpenAICompatibleClient, judge_model: ModelSpec):
        if judge_model.role != "judge":
            raise ValueError("IndependentJudge requires a model with role=judge")
        self.client = client
        self.judge_model = judge_model

    def evaluate(self, task: TaskDAG, result: TaskResult) -> JudgeEvaluation:
        sources = [
            {
                "source_id": source.source_id,
                "title": source.title,
                "content_hash": source.content_hash,
                "content": source.content,
            }
            for source in task.source_documents
        ]
        payload = {
            "task_id": task.task_id,
            "domain": task.domain,
            "required_sections": task.required_sections,
            "expected_claims": task.expected_claims,
            "sources": sources,
            "report_html": result.final_output,
        }
        response = self.client.complete(
            self.judge_model,
            (
                {
                    "role": "system",
                    "content": (
                        "You are an independent evaluator and are not a routing candidate. "
                        "Use only the frozen sources. Return JSON with: scores, claim_support, "
                        "and rationale. scores must contain requirement_coverage (0-25), "
                        "evidence_accuracy (0-25), analysis_depth (0-20), "
                        "structure_readability (0-15), and html_validity (0-15). "
                        "For every expected claim, claim_support must state claim, source_ids, "
                        "supported, and explanation. Penalize unsupported or misattributed claims."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ),
            json_mode=True,
        )
        data = _parse_judge_response(response.content)
        judge_dimensions = _validate_dimensions(data.get("scores"))
        deterministic = score_task_dimensions(
            task, result.node_results, result.final_output
        )
        trace_issues = source_trace_issues(task, result.final_output)
        claim_support = _validate_claim_support(task, data.get("claim_support"))
        supported_claims = sum(item["supported"] is True for item in claim_support)
        semantic_evidence_cap = (
            25.0 * supported_claims / len(task.expected_claims)
            if task.expected_claims
            else 25.0
        )
        final_dimensions = {
            "requirement_coverage": min(
                deterministic["requirement_coverage"],
                judge_dimensions["requirement_coverage"],
            ),
            "evidence_accuracy": (
                0.0
                if trace_issues
                else min(
                    deterministic["evidence_accuracy"],
                    judge_dimensions["evidence_accuracy"],
                    semantic_evidence_cap,
                )
            ),
            "analysis_depth": judge_dimensions["analysis_depth"],
            "structure_readability": judge_dimensions["structure_readability"],
            "html_validity": min(
                deterministic["html_validity"], judge_dimensions["html_validity"]
            ),
        }
        return JudgeEvaluation(
            rubric_version=JUDGE_RUBRIC_VERSION,
            deterministic_dimensions=deterministic,
            judge_dimensions=judge_dimensions,
            final_dimensions=final_dimensions,
            final_score=round(sum(final_dimensions.values()), 3),
            claim_support=claim_support,
            rationale=str(data.get("rationale", "")),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_input_tokens=response.cached_input_tokens,
            reasoning_tokens=response.reasoning_tokens,
            cost_usd=model_response_cost(self.judge_model, response),
            latency_ms=response.latency_ms,
            attempts=response.attempts,
            request_id=response.request_id,
        )


def apply_judge_score(result: TaskResult, evaluation: JudgeEvaluation) -> TaskResult:
    return replace(result, task_score=evaluation.final_score)


def _parse_judge_response(content: str) -> dict[str, object]:
    stripped = content.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        stripped = stripped[7:-3].strip()
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise ValueError("Judge response must be a JSON object")
    return data


def _validate_dimensions(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError("Judge response scores must be an object")
    dimensions: dict[str, float] = {}
    for name, limit in DIMENSION_LIMITS.items():
        score = float(value[name])
        if score < 0 or score > limit:
            raise ValueError(f"Judge dimension out of range: {name}={score}")
        dimensions[name] = score
    return dimensions


def _validate_claim_support(
    task: TaskDAG,
    value: object,
) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Judge response claim_support must be an array of objects")
    records = tuple(value)
    claims = [item.get("claim") for item in records]
    if len(claims) != len(set(claims)):
        raise ValueError("Judge response contains duplicate claim_support records")
    if set(claims) != set(task.expected_claims):
        raise ValueError("Judge response must cover every expected claim exactly once")
    known_sources = {source.source_id for source in task.source_documents}
    for item in records:
        source_ids = item.get("source_ids")
        if not isinstance(source_ids, list) or not all(
            isinstance(source_id, str) and source_id in known_sources
            for source_id in source_ids
        ):
            raise ValueError("Judge response contains an unknown source ID")
        if not isinstance(item.get("supported"), bool):
            raise ValueError("Judge response supported must be boolean")
        if not isinstance(item.get("explanation"), str):
            raise ValueError("Judge response explanation must be a string")
    return records
