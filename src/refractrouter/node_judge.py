from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .openai_compatible import model_response_cost
from .scoring import node_contract_checks, traceable_source_ids


NODE_RUBRIC_VERSION = "v0.2"
NODE_RUBRIC_PATH = Path(__file__).resolve().parents[2] / "data/judges/node-v0.2.md"
NODE_LIMITS = {"correctness": 40, "grounding": 30, "completeness": 20, "downstream_utility": 10}


class NodeJudgeError(ValueError):
    def __init__(self, reason, telemetry):
        super().__init__(reason)
        self.failure_type = reason
        self.telemetry = telemetry


class IndependentNodeJudge:
    def __init__(self, client, model):
        if model.role != "judge":
            raise ValueError("Node quality evaluation requires an independent judge model")
        self.client = client
        self.judge_model = model
        self.rubric = NODE_RUBRIC_PATH.read_text(encoding="utf-8")
        self.rubric_sha256 = hashlib.sha256(self.rubric.encode()).hexdigest()

    def evaluate(self, task, node, result, context):
        checks = node_contract_checks(task, node, result.output, context)
        source_ids = checks["checks"].get("unique_sources", [])
        if node.node_type == "rendering":
            source_ids = sorted(traceable_source_ids(task, result.output))
        payload = {
            "task_id": task.task_id,
            "domain": task.domain,
            "required_sections": list(task.required_sections),
            "expected_claims": list(task.expected_claims),
            "constraints": list(task.output_constraints),
            "node_id": node.node_id,
            "node_type": node.node_type,
            "node_request": node.prompt_template,
            "upstream": {parent: context[parent] for parent in node.parents},
            "candidate_output": result.output,
            "assessed_source_ids": source_ids,
            "sources": [
                {"source_id": s.source_id, "title": s.title,
                 "content_hash": s.content_hash, "content": s.content}
                for s in task.source_documents
            ],
        }
        response = self.client.complete(
            self.judge_model,
            ({"role": "system", "content": self.rubric},
             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}),
            json_mode=True,
        )
        telemetry = {
            "cost": model_response_cost(self.judge_model, response),
            "billing_unit": self.judge_model.billing_unit,
            "input_tokens": response.input_tokens, "output_tokens": response.output_tokens,
            "cached_input_tokens": response.cached_input_tokens,
            "reasoning_tokens": response.reasoning_tokens,
            "latency_ms": response.latency_ms, "attempts": response.attempts,
            "request_id": response.request_id, "finish_reason": response.finish_reason,
            "response_content": response.content,
        }
        if response.finish_reason == "length":
            raise NodeJudgeError("node-judge-output-truncated", telemetry)
        try:
            data = json.loads(response.content)
            scores = data["scores"]
            if set(scores) != set(NODE_LIMITS):
                raise ValueError("wrong dimensions")
            for key, limit in NODE_LIMITS.items():
                score = scores[key]
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= limit:
                    raise ValueError("invalid score")
            rationale = data["rationale"]
            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError("missing rationale")
            assessments = data["source_assessments"]
            if not isinstance(assessments, list):
                raise ValueError("invalid source assessments")
            ids = []
            for item in assessments:
                if not isinstance(item, dict) or not isinstance(item.get("supported"), bool) or not isinstance(item.get("explanation"), str) or not item["explanation"].strip():
                    raise ValueError("invalid support assessment")
                ids.append(item["source_id"])
            if sorted(ids) != sorted(source_ids):
                raise ValueError("must assess every cited source exactly once")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise NodeJudgeError("invalid-node-judge-response", telemetry) from exc
        effective = dict(scores)
        if assessments:
            effective["grounding"] = min(scores["grounding"], 30 * sum(x["supported"] for x in assessments) / len(assessments))
        return {
            "rubric_version": NODE_RUBRIC_VERSION, "rubric_sha256": self.rubric_sha256,
            "checks": checks, "semantic_dimensions": scores, "effective_dimensions": effective,
            "final_score": round(min(checks["score_cap"], sum(effective.values())), 3),
            "source_assessments": assessments, "rationale": rationale, **telemetry,
        }
