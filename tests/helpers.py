from __future__ import annotations

from refractrouter.model_registry import ModelRegistry
from refractrouter.schemas import ModelSpec, NodeSpec, TaskDAG


def make_registry() -> ModelRegistry:
    return ModelRegistry(
        [
            ModelSpec("cheap-model", "fake", 0.001, 0.002, 0.35),
            ModelSpec("mid-model", "fake", 0.004, 0.008, 0.65),
            ModelSpec("strong-model", "fake", 0.012, 0.024, 0.95),
        ]
    )


def make_task() -> TaskDAG:
    return TaskDAG(
        task_id="report_001",
        domain="Enterprise LLM agent platform selection",
        nodes=(
            NodeSpec(
                node_id="parse_requirements",
                node_type="planning",
                prompt_template="Extract requirements.",
            ),
            NodeSpec(
                node_id="build_outline",
                node_type="planning",
                prompt_template="Build outline.",
                parents=("parse_requirements",),
            ),
            NodeSpec(
                node_id="extract_evidence",
                node_type="extraction",
                prompt_template="Extract evidence.",
                parents=("build_outline",),
            ),
            NodeSpec(
                node_id="synthesize_analysis",
                node_type="synthesis",
                prompt_template="Synthesize analysis.",
                parents=("extract_evidence",),
            ),
            NodeSpec(
                node_id="write_report",
                node_type="generation",
                prompt_template="Write report.",
                parents=("synthesize_analysis",),
            ),
            NodeSpec(
                node_id="render_html",
                node_type="rendering",
                prompt_template="Render HTML.",
                parents=("write_report",),
            ),
            NodeSpec(
                node_id="verify_report",
                node_type="verification",
                prompt_template="Verify report.",
                parents=("render_html",),
            ),
        ),
        required_sections=(
            "Executive Summary",
            "Background",
            "Selection Criteria",
            "Platform Comparison",
            "Risks",
            "Conclusion",
            "References",
        ),
        output_constraints=("standalone HTML",),
        source_pack_id="report_001",
    )
