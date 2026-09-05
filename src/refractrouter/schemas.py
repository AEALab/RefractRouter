from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_id: str
    title: str
    content: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model_id: str
    provider: str
    input_cost_per_1k_usd: float
    output_cost_per_1k_usd: float
    capability: float
    tags: tuple[str, ...] = ()
    api_model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    cached_input_cost_per_1k_usd: float | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    snapshot_date: str | None = None
    role: str = "candidate"
    request_options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NodeSpec:
    node_id: str
    node_type: str
    prompt_template: str
    parents: tuple[str, ...] = ()
    expected_output: str | None = None


@dataclass(frozen=True, slots=True)
class TaskDAG:
    task_id: str
    domain: str
    nodes: tuple[NodeSpec, ...]
    required_sections: tuple[str, ...] = ()
    output_constraints: tuple[str, ...] = ()
    source_pack_id: str | None = None
    scoring_rubric_version: str = "v0.1"
    expected_claims: tuple[str, ...] = ()
    source_documents: tuple[SourceDocument, ...] = ()


@dataclass(frozen=True, slots=True)
class NodeResult:
    node_id: str
    node_type: str
    model_id: str
    output: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    score: float = 0.0
    status: str = "ok"
    failure_type: str | None = None
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    attempts: int = 1
    finish_reason: str | None = None
    request_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class TaskResult:
    task_id: str
    strategy: str
    model_assignments: Mapping[str, str]
    node_results: tuple[NodeResult, ...]
    final_output: str
    task_score: float
    total_cost_usd: float
    critical_path_latency_ms: int
    failure_types: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RunRecord:
    task_id: str
    strategy: str
    task_result: TaskResult
    metadata: Mapping[str, Any] = field(default_factory=dict)
