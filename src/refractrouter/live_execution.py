"""RefractAgent v4 单任务真实执行的零调用门禁与授权摘要。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from uuid import uuid4

from .decomposition_decision import RULE_VERSION, validate_evidence, trivial_workload
from .task_tool_evidence import tool_requirements


COMPLEXITY_POLICY_VERSION = "refractagent-complexity-gate-v3"
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
_NEGATED_TOOL_PREFIX = re.compile(
    r"(?:不要|不需要|无需|无须|不必|不得|请勿|禁止|避免|别)\s*(?:再|去|实际|直接|先)?\s*$"
    r"|\b(?:do not|don't|without|never)\s+(?:actually\s+)?$",
    re.IGNORECASE,
)
_ENUMERATED = re.compile(r"(?m)^\s*(?:[-*+]\s+|\d+[.)、]\s*)")
_SENTENCE_END = re.compile(r"[。！？!?](?:\s|$)")


def _requires_tools(task):
    if tool_requirements(task)['required']:
        return True
    for match in _TOOL_MARKERS.finditer(task):
        prefix = re.split(r"[，,。！？!?；;\n]", task[max(0, match.start()-24):match.start()])[-1]
        if not _NEGATED_TOOL_PREFIX.search(prefix):
            return True
    return False


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


def complexity_gate(payload, context, *, policy="auto", tools_allowed=False,
                    decomposition=None):
    """合并请求结构规则与宿主已取得的本地结构证据；本函数不调用模型。"""
    if policy not in {"auto", "direct", "dag"}:
        raise ValueError("complexityPolicy must be auto, direct or dag")
    task = payload.get("task")
    if not isinstance(task, str):
        raise ValueError("task requires nonempty text")
    if not isinstance(context, str):
        raise ValueError("context must be text")
    local = validate_evidence(decomposition, task, context) if decomposition is not None else None
    statistics = {
        "task_chars": len(task),
        "context_bytes": len(context.encode()),
        "enumerated_items": len(_ENUMERATED.findall(task)),
        "sentence_count": len(_SENTENCE_END.findall(task)),
    }
    requires_tools = _requires_tools(task)
    if requires_tools and not tools_allowed:
        return {"policy_version": COMPLEXITY_POLICY_VERSION, "policy": policy,
                "decision": "blocked-tools", "forced": policy != "auto",
                "reasons": ["explicit-tool-requirement"], "statistics": statistics,
                "local_decision": local}
    if policy != "auto":
        return {"policy_version": COMPLEXITY_POLICY_VERSION, "policy": policy,
                "decision": policy, "forced": True, "reasons": [f"forced-{policy}"],
                "statistics": statistics, "local_decision": local}
    reasons = []
    if statistics["task_chars"] > DIRECT_TASK_CHARS:
        reasons.append("task-too-long")
    # 宿主系统提示与历史长度不能证明工作可拆；容量检查仍由模型准入执行。
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
    if requires_tools:
        reasons.append("explicit-tool-requirement")
    trivial = trivial_workload(task) and not any(payload.get(k) for k in ("materials", "acceptanceCriteria", "outputConstraints"))
    if trivial:
        reasons = ["trivial-workload"]
    rule_decision = "dag" if reasons and not trivial else "direct"
    decision, combination = rule_decision, "rules-only"
    if local is not None:
        verdict = local["verdict"]
        # v3 区分分支依赖与最终汇总；工具和交付要求不是拆分证明。
        # 权限检查在此前完成，独立评审和模型准入继续保留。v2 保持历史语义。
        hard = {"multiple-materials", "acceptance-criteria-present",
                "strict-output-contract", "explicit-tool-requirement"}.intersection(reasons)
        if trivial:
            combination = "trivial-workload-no-planner"
        elif verdict == "SEPARABLE":
            decision, combination = "dag", "local-separable"
            if "local-separable" not in reasons:
                reasons.append("local-separable")
        elif verdict == "COUPLED" and local['ruleVersion'] == RULE_VERSION:
            decision, combination = "direct", "coupled-sequential-work"
            reasons.append("local-coupled")
        elif verdict == "COUPLED" and not hard:
            decision, combination = "direct", "local-coupled-overrode-weak-rules"
            reasons = ["local-coupled"]
        elif verdict == "COUPLED":
            combination = "hard-rules-preserved-over-local-coupled"
        else:
            combination = "local-unknown-rules-preserved"
    return {"policy_version": COMPLEXITY_POLICY_VERSION, "policy": policy,
            "decision": decision, "rule_decision": rule_decision, "combination": combination,
            "forced": False, "reasons": reasons or ["short-single-deliverable"],
            "statistics": statistics, "local_decision": local}


def review_decision(payload, gate, *, policy="adaptive", tools_allowed=False):
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
        if tools_allowed:
            reasons.append("host-tools-available")
    return {"policy": policy, "required": bool(reasons),
            "reason": ",".join(reasons) if reasons else "adaptive-low-risk-direct"}


def authorization_binding(payload, *, provider_config, catalog_snapshot, production_budget,
                          evaluation_budget, max_output_tokens, gate, review, data_mode, billing_unit,
                          tool_schemas=None, max_tool_calls=0):
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
        "canary": {"data_mode": data_mode, "billing_unit": billing_unit,
                   "tools_allowed": tool_schemas is not None,
                   "tool_schema_sha256": (hashlib.sha256(_canonical(tool_schemas).encode()).hexdigest()
                                          if tool_schemas is not None else None),
                   "max_tool_calls": max_tool_calls,
                   "max_plan_repairs": 0, "max_dynamic_splits": 0,
                   "max_node_fallbacks": 0, "max_concurrency": 1,
                   "max_dag_nodes": 6},
    }


def create_authorization_preview(binding, *, billing_unit, production_estimate,
                                 evaluation_estimate, ready=True, now=None):
    now = now or datetime.now(timezone.utc)
    authorization_id = uuid4().hex
    issued_at = now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(seconds=AUTHORIZATION_TTL_SECONDS)).isoformat().replace("+00:00", "Z")
    gate, review = binding["complexity"], binding["review"]
    maximum_calls = ((1 + int(review["required"])) if gate["decision"] == "direct" else 8)
    tool_limit = binding["canary"]["max_tool_calls"]
    maximum_calls = None if tool_limit == 'unlimited' else maximum_calls + tool_limit
    digest_input = {"authorization_id": authorization_id, "issued_at": issued_at,
                    "expires_at": expires_at, "binding": binding}
    preview_sha256 = hashlib.sha256(_canonical(digest_input).encode()).hexdigest()
    mixed = billing_unit == 'MIXED'
    if mixed:
        if (not isinstance(production_estimate, dict) or set(production_estimate) != {'AFP', 'CNY'}
                or not isinstance(evaluation_estimate, dict) or set(evaluation_estimate) != {'AFP', 'CNY'}):
            raise ValueError('mixed authorization requires AFP and CNY estimates')
        costs = {'billing_unit': 'MIXED',
            'estimate_kind': 'native-unit-route-reserve',
            'production_estimate_by_unit': dict(production_estimate),
            'evaluation_estimate_by_unit': dict(evaluation_estimate),
            'production_hard_limit_by_unit': dict(binding['production_budget']),
            'evaluation_hard_limit_by_unit': dict(binding['evaluation_budget'])}
    else:
        costs = {
            'billing_unit': billing_unit,
            'estimate_kind': ('base-route-only-tool-continuations-unestimated'
                              if binding['canary']['tools_allowed'] else
                              'conservative-route-reserve' if gate['decision'] == 'direct' else 'bounded-range'),
            'production_estimate': production_estimate,
            'evaluation_estimate': evaluation_estimate,
            'production_hard_limit': (None if binding['production_budget'] == 'unlimited'
                                      else binding['production_budget']),
            'evaluation_hard_limit': (None if binding['evaluation_budget'] == 'unlimited'
                                      else binding['evaluation_budget']),
            'production_unlimited': binding['production_budget'] == 'unlimited',
            'evaluation_unlimited': binding['evaluation_budget'] == 'unlimited',
            **({'production_estimate_range': {
                'minimum': production_estimate,
                'maximum': (None if binding['production_budget'] == 'unlimited'
                            else binding['production_budget']),
            }} if gate['decision'] == 'dag' or binding['canary']['tools_allowed'] else {}),
        }
    return {
        "schema_version": AUTHORIZATION_SCHEMA,
        "authorization_id": authorization_id,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "preview_sha256": preview_sha256,
        "complexity": gate,
        "review": review,
        "calls": {"maximum": maximum_calls,
                  "estimate": maximum_calls if gate["decision"] == "direct"
                  and not binding["canary"]["tools_allowed"] else None},
        "costs": costs,
        "ready": (ready and binding["canary"]["data_mode"] in {"synthetic", "desensitized", "live"}
                  and binding["canary"]["billing_unit"] in {"USD", "CNY", "AFP", "MIXED"}),
        "data_mode": binding["canary"]["data_mode"],
        "tools_allowed": binding["canary"]["tools_allowed"],
        "tools": {"maximum_calls": binding["canary"]["max_tool_calls"],
                  "schema_sha256": binding["canary"]["tool_schema_sha256"]},
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
