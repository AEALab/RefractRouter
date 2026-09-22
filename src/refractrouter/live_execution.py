"""RefractAgent v4 单任务真实执行的零调用门禁与授权摘要。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from uuid import uuid4


COMPLEXITY_POLICY_VERSION = "refractagent-complexity-gate-v1"
AUTHORIZATION_SCHEMA = "refractagent-live-authorization-v1"
AUTHORIZATION_TTL_SECONDS = 600
DIRECT_TASK_CHARS = 600
DIRECT_CONTEXT_BYTES = 12_000

_COMPLEX_MARKERS = re.compile(
    r"(?:比较|对比|分别|然后|同时|步骤|方案|多阶段|汇总|"
    r"\bcompare\b|\bversus\b|\bseparately\b|\bthen\b|\bsteps?\b|\bplan\b)",
    re.IGNORECASE,
)
_TOOL_MARKERS = re.compile(
    r"(?:搜索(?:网页|网络|互联网)?|查找(?:最新|实时)|读取(?:文件|仓库)|"
    r"写入文件|修改代码|运行(?:命令|测试|脚本)|执行(?:命令|终端)|调用(?:工具|API)|发送(?:消息|邮件)|"
    r"\bsearch (?:the )?(?:web|internet)\b|\bread (?:the )?(?:file|repository)\b|"
    r"\brun (?:the )?(?:command|tests?|script)\b|\bcall (?:a )?(?:tool|api)\b)",
    re.IGNORECASE,
)
_ENUMERATED = re.compile(r"(?m)^\s*(?:[-*+]\s+|\d+[.)、]\s*)")
_SENTENCE_END = re.compile(r"[。！？!?](?:\s|$)")


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{field} must be an ISO timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def complexity_gate(payload, context, *, policy="auto"):
    """只消费请求结构与文本特征，不调用模型。"""
    if policy not in {"auto", "direct", "dag"}:
        raise ValueError("complexityPolicy must be auto, direct or dag")
    task = payload.get("task")
    if not isinstance(task, str):
        raise ValueError("task requires nonempty text")
    if not isinstance(context, str):
        raise ValueError("context must be text")
    statistics = {
        "task_chars": len(task),
        "context_bytes": len(context.encode()),
        "enumerated_items": len(_ENUMERATED.findall(task)),
        "sentence_count": len(_SENTENCE_END.findall(task)),
    }
    if _TOOL_MARKERS.search(task):
        return {"policy_version": COMPLEXITY_POLICY_VERSION, "policy": policy,
                "decision": "blocked-tools", "forced": policy != "auto",
                "reasons": ["explicit-tool-requirement"], "statistics": statistics}
    if policy != "auto":
        return {"policy_version": COMPLEXITY_POLICY_VERSION, "policy": policy,
                "decision": policy, "forced": True, "reasons": [f"forced-{policy}"],
                "statistics": statistics}
    reasons = []
    if statistics["task_chars"] > DIRECT_TASK_CHARS:
        reasons.append("task-too-long")
    if statistics["context_bytes"] > DIRECT_CONTEXT_BYTES:
        reasons.append("context-too-long")
    if statistics["enumerated_items"] >= 2:
        reasons.append("multiple-enumerated-requirements")
    if "```" in task:
        reasons.append("code-fence")
    if len(payload.get("materials") or []) > 1:
        reasons.append("multiple-materials")
    if payload.get("acceptanceCriteria"):
        reasons.append("acceptance-criteria-present")
    if payload.get("outputConstraints"):
        reasons.append("strict-output-contract")
    if _COMPLEX_MARKERS.search(task):
        reasons.append("complex-task-marker")
    return {"policy_version": COMPLEXITY_POLICY_VERSION, "policy": policy,
            "decision": "dag" if reasons else "direct", "forced": False,
            "reasons": reasons or ["short-single-deliverable"], "statistics": statistics}


def review_decision(payload, gate, *, policy="adaptive"):
    if policy not in {"adaptive", "always"}:
        raise ValueError("reviewPolicy must be adaptive or always")
    reasons = []
    if policy == "always":
        reasons.append("always-review")
    else:
        if gate["decision"] != "direct":
            reasons.append("dag-or-blocked")
        if gate["forced"]:
            reasons.append("forced-routing-policy")
        if payload.get("materials"):
            reasons.append("materials-present")
        if payload.get("acceptanceCriteria"):
            reasons.append("acceptance-criteria-present")
        if payload.get("outputConstraints"):
            reasons.append("strict-output-contract")
    return {"policy": policy, "required": bool(reasons),
            "reason": ",".join(reasons) if reasons else "adaptive-low-risk-direct"}


def authorization_binding(payload, *, provider_config, catalog_snapshot, production_budget,
                          evaluation_budget, max_output_tokens, gate, review, data_mode, billing_unit):
    clean = deepcopy(payload)
    clean.pop("authorization", None)
    return {
        "payload": clean,
        "provider_config": provider_config,
        "catalog_snapshot": catalog_snapshot,
        "production_budget": production_budget,
        "evaluation_budget": evaluation_budget,
        "max_output_tokens": max_output_tokens,
        "complexity": gate,
        "review": review,
        "canary": {"data_mode": data_mode, "billing_unit": billing_unit, "tools_allowed": False,
                   "max_plan_repairs": 0, "max_dynamic_splits": 0,
                   "max_node_fallbacks": 0, "max_concurrency": 1,
                   "max_dag_nodes": 6},
    }


def create_authorization_preview(binding, *, billing_unit, production_estimate,
                                 evaluation_estimate, now=None):
    now = now or datetime.now(timezone.utc)
    authorization_id = uuid4().hex
    issued_at = now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(seconds=AUTHORIZATION_TTL_SECONDS)).isoformat().replace("+00:00", "Z")
    gate, review = binding["complexity"], binding["review"]
    maximum_calls = ((1 + int(review["required"])) if gate["decision"] == "direct" else 8)
    digest_input = {"authorization_id": authorization_id, "issued_at": issued_at,
                    "expires_at": expires_at, "binding": binding}
    preview_sha256 = hashlib.sha256(_canonical(digest_input).encode()).hexdigest()
    return {
        "schema_version": AUTHORIZATION_SCHEMA,
        "authorization_id": authorization_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "preview_sha256": preview_sha256,
        "complexity": gate,
        "review": review,
        "calls": {"maximum": maximum_calls,
                  "estimate": maximum_calls if gate["decision"] == "direct" else None},
        "costs": {
            "billing_unit": billing_unit,
            "estimate_kind": "conservative-route-reserve" if gate["decision"] == "direct" else "bounded-range",
            "production_estimate": production_estimate,
            "evaluation_estimate": evaluation_estimate,
            "production_hard_limit": binding["production_budget"],
            "evaluation_hard_limit": binding["evaluation_budget"],
        },
        "ready": (binding["canary"]["data_mode"] == "synthetic"
                  and binding["canary"]["billing_unit"] == "USD"),
        "data_mode": binding["canary"]["data_mode"],
        "tools_allowed": False,
    }


def validate_authorization(raw, expected_binding, *, now=None):
    if not isinstance(raw, dict) or raw.get("schema_version") != AUTHORIZATION_SCHEMA:
        raise ValueError("REFRACTAGENT_PREVIEW_MISMATCH: live execution requires an authorization preview")
    expected_fields = {"schema_version", "authorization_id", "issued_at", "expires_at", "preview_sha256"}
    if set(raw) != expected_fields:
        raise ValueError("REFRACTAGENT_PREVIEW_MISMATCH: invalid authorization fields")
    if not isinstance(raw.get("authorization_id"), str) or not raw["authorization_id"]:
        raise ValueError("REFRACTAGENT_PREVIEW_MISMATCH: invalid authorization id")
    issued = _timestamp(raw.get("issued_at"), "issued_at")
    expires = _timestamp(raw.get("expires_at"), "expires_at")
    current = now or datetime.now(timezone.utc)
    if expires <= issued or expires - issued > timedelta(seconds=AUTHORIZATION_TTL_SECONDS) or current > expires:
        raise ValueError("REFRACTAGENT_PREVIEW_MISMATCH: authorization preview expired")
    digest_input = {"authorization_id": raw["authorization_id"], "issued_at": raw["issued_at"],
                    "expires_at": raw["expires_at"], "binding": expected_binding}
    expected = hashlib.sha256(_canonical(digest_input).encode()).hexdigest()
    if raw.get("preview_sha256") != expected:
        raise ValueError("REFRACTAGENT_PREVIEW_MISMATCH: request or configuration changed after preview")
    return {key: raw[key] for key in expected_fields}
