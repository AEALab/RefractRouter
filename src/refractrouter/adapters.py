from __future__ import annotations

from typing import Protocol

from .model_registry import ModelRegistry
from .schemas import ModelSpec, NodeResult, NodeSpec, TaskDAG


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
        cost_usd = (
            input_tokens / 1000 * model.input_cost_per_1k_usd
            + output_tokens / 1000 * model.output_cost_per_1k_usd
        )
        latency_ms = int(400 + (1 - model.capability) * 1600 + len(output) // 16)
        return NodeResult(
            node_id=node.node_id,
            node_type=node.node_type,
            model_id=model.model_id,
            output=output,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 6),
            latency_ms=latency_ms,
            score=quality,
            status="ok",
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

    @staticmethod
    def _render_output(
        node_type: str,
        quality: float,
        task: TaskDAG,
        context: dict[str, str],
    ) -> str:
        if node_type == "planning":
            sections = "; ".join(task.required_sections)
            return f"requirements: {task.domain}; sections: {sections}; constraints: {'; '.join(task.output_constraints)}"
        if node_type == "extraction":
            count = 3 if quality >= 0.82 else 2 if quality >= 0.68 else 1
            return "; ".join(f"source_{i:03d}: claim_{i}" for i in range(1, count + 1))
        if node_type == "synthesis":
            return "analysis: comparison table; tradeoff summary; recommendation"
        if node_type == "generation":
            return "report: " + "; ".join(task.required_sections)
        if node_type == "rendering":
            if quality < 0.70:
                visible_sections = task.required_sections[:4]
            elif quality < 0.85:
                visible_sections = task.required_sections[:6]
            else:
                visible_sections = task.required_sections
            sections = "".join(
                f"<section><h2>{section}</h2><p>{section} content.</p></section>"
                for section in visible_sections
            )
            return f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{task.task_id}</title></head><body><h1>{task.domain}</h1>{sections}</body></html>"
        if node_type == "verification":
            return "verification: sections=cited; sources=traced; html=valid"
        return "generic output"
