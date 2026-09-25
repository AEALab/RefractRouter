"""规划路由配置：独立角色绑定、零调用预检与宿主无关合同。"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import math

from .schemas import ModelSpec
from .application_config import compile_privacy, SCHEMA_V2 as PRIVACY_SCHEMA_V2
from .dsh_model_pool import frozen_usd_cny_rate

SCHEMA = "refractagent-planning-v1"
SCHEMA_V2 = "refractagent-planning-v2"
PROTOCOL = "refractagent-planning/2"
STRATEGIES = ("stage", "task", "composite", "advisor", "escalation", "static")
NAMES = dict(zip(STRATEGIES, ("阶段", "任务", "组合", "审核", "升级", "静态")))
REQUIRED = {
    "static": ("efficient",), "stage": ("efficient", "capable"),
    "task": ("efficient", "capable", "classifier"),
    "composite": ("efficient", "capable", "classifier"),
    "advisor": ("efficient", "advisor"),
    "escalation": ("efficient", "capable", "classifier"),
}
DEFAULTS = {"window": 3, "threshold": .5, "holdTurns": 2, "baseThreshold": .5,
            "thresholdStep": .1, "maxReviews": 1, "maxRedos": 1, "stallTurns": 0,
            "confirmations": 2, "staticMode": "fixed", "seed": 0,
            "efficientWeight": 1, "capableWeight": 1}


def number(value, name, minimum=0, maximum=float("inf"), integer=False):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} 数值不合法")
    if integer and type(value) is not int:
        raise ValueError(f"{name} 必须是整数")
    return value


def obj(value, allowed, name):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f"{name} 字段不合法")
    return value


@dataclass(frozen=True)
class PlanningModel(ModelSpec):
    deployment: str = "external-cloud"
    trust_policy: str | None = None
    cache_write_cost_per_1k: float | None = None
    source_billing_unit: str | None = None
    conversion_rate: float | None = None
    conversion_source: str | None = None
    conversion_as_of: str | None = None


def compile_config(raw):
    raw = deepcopy(obj(raw, ("schemaVersion", "enabled", "defaultStrategy", "billingUnit",
        "maxProductionCost", "maxProductionCostByUnit", "timeoutMs", "maxCalls", "models", "roles", "parameters",
        "security", "trustPolicies", "compatiblePairs"), "planningRouting"))
    if raw.get("schemaVersion") not in (SCHEMA, SCHEMA_V2) or type(raw.get("enabled")) is not bool:
        raise ValueError("需要版本化 planningRouting 配置和 enabled")
    if raw["schemaVersion"] == SCHEMA and ("maxProductionCostByUnit" in raw or any(
            isinstance(model, dict) and "billingUnit" in model for model in raw.get("models", []))):
        raise ValueError(f"多计费单位配置需要 {SCHEMA_V2}")
    strategy = raw.get("defaultStrategy", "stage")
    if strategy not in STRATEGIES:
        raise ValueError("未知规划路由策略")
    unit = raw.get("billingUnit", "USD" if raw["schemaVersion"] == SCHEMA else "CNY")
    if unit not in ("USD", "AFP", "CNY"):
        raise ValueError("不支持的计费单位")
    fx_rate, fx_snapshot = frozen_usd_cny_rate()
    source_unit = unit
    if unit == "USD":
        unit = "CNY"
    # 未启用时仍允许保存未完成的设置；执行前必须通过完整预检。
    budget = raw.get("maxProductionCost")
    if budget is not None:
        number(budget, "maxProductionCost")
    unit_budgets = obj(raw.get("maxProductionCostByUnit", {}), ("USD", "AFP", "CNY"), "maxProductionCostByUnit")
    budgets = {}
    for name in ("AFP", "CNY"):
        if name in unit_budgets:
            budgets[name] = number(unit_budgets[name], f"{name} 生产预算")
    if "USD" in unit_budgets and "CNY" not in budgets:
        budgets["CNY"] = number(unit_budgets["USD"], "USD 生产预算") * fx_rate
    if budget is not None:
        amount = number(budget, "maxProductionCost")
        target = "CNY" if source_unit == "USD" else source_unit
        budgets.setdefault(target, amount * (fx_rate if source_unit == "USD" else 1))
    timeout = number(raw.get("timeoutMs", 300000), "timeoutMs", 0, 7200000, True)
    max_calls = number(raw.get("maxCalls", 128), "maxCalls", 0, 4096, True)
    policies = {}
    for item in raw.get("trustPolicies", []):
        p = obj(item, ("id", "residency", "auditLogging", "allowsSensitiveData", "expiresOn"), "trustPolicy")
        if not p.get("id") or p["id"] in policies or not p.get("residency"):
            raise ValueError("信任策略需要唯一 id 与 residency")
        if p.get("auditLogging") is not True or p.get("allowsSensitiveData") is not True:
            raise ValueError("信任策略必须明确允许敏感数据和审计")
        if p.get("expiresOn") and date.fromisoformat(p["expiresOn"]) < date.today():
            raise ValueError("信任策略已过期")
        policies[p["id"]] = p
    models = {}
    model_issues = {}
    declared_ids = set()
    for item in raw.get("models", []):
        m = obj(item, ("id", "provider", "model", "contextWindow", "maxOutputTokens",
            "inputPer1k", "outputPer1k", "cachedInputPer1k", "cacheWritePer1k", "reasoningEffort",
            "deployment", "trustPolicy", "capabilityCard", "billingUnit"), "model")
        model_id = m.get("id")
        if not isinstance(model_id, str) or not model_id.strip() or len(model_id) > 256:
            raise ValueError("model.id 无效")
        if model_id in declared_ids:
            raise ValueError("重复模型")
        declared_ids.add(model_id)
        if m.get("provider") == "refractagent":
            raise ValueError("重复模型或递归路由")
        try:
            for field in ("provider", "model"):
                if not isinstance(m.get(field), str) or not m[field].strip() or len(m[field]) > 256:
                    raise ValueError(f"model.{field} 无效")
            deployment = m.get("deployment", "external-cloud")
            model_unit = m.get("billingUnit", source_unit)
            if model_unit not in ("USD", "AFP", "CNY"):
                raise ValueError("model.billingUnit 无效")
            if deployment not in ("local", "external-cloud", "trusted-cloud"):
                raise ValueError("规划路由需要真实部署域")
            if deployment == "trusted-cloud" and m.get("trustPolicy") not in policies:
                raise ValueError("可信云需要有效的信任策略")
            context = number(m.get("contextWindow"), "contextWindow", 512, 10000000, True)
            output = number(m.get("maxOutputTokens"), "maxOutputTokens", 1, context - 1, True)
            input_price = number(m.get("inputPer1k"), "inputPer1k")
            output_price = number(m.get("outputPer1k"), "outputPer1k")
            cached = number(m.get("cachedInputPer1k", input_price), "cachedInputPer1k", 0, input_price)
            cache_write = m.get("cacheWritePer1k")
            if cache_write is not None:
                number(cache_write, "cacheWritePer1k")
            effort = m.get("reasoningEffort")
            if effort is not None and (not isinstance(effort, str) or not effort or effort.startswith("rr:")):
                raise ValueError("角色推理等级不能使用虚拟策略标识")
            card = m.get("capabilityCard", "")
            if not isinstance(card, str) or len(card) > 16000:
                raise ValueError("capabilityCard 无效")
            converted = model_unit == "USD"
            models[model_id] = PlanningModel(model_id, m["provider"],
                input_price * (fx_rate if converted else 1), output_price * (fx_rate if converted else 1), 0,
                billing_unit="CNY" if converted else model_unit, api_model=m["model"],
                cached_input_cost_per_1k=cached * (fx_rate if converted else 1),
                context_window=context, max_output_tokens=output, wire_api="dsh-llm",
                request_options=({"reasoning_effort": effort} if effort else {}),
                deployment=deployment, trust_policy=m.get("trustPolicy"),
                cache_write_cost_per_1k=cache_write * (fx_rate if converted and cache_write is not None else 1)
                    if cache_write is not None else None,
                source_billing_unit="USD" if converted else None,
                conversion_rate=fx_rate if converted else None,
                conversion_source=fx_snapshot["source"] if converted else None,
                conversion_as_of=fx_snapshot["as_of"] if converted else None)
        except (ValueError, TypeError, KeyError) as exc:
            model_issues[model_id] = str(exc)
    roles = obj(raw.get("roles", {}), ("efficient", "capable", "classifier", "advisor"), "roles")
    for value in roles.values():
        if not isinstance(value, str) or value not in declared_ids:
            raise ValueError("角色引用不存在的模型")
    parameters = {**DEFAULTS, **obj(raw.get("parameters", {}), DEFAULTS, "parameters")}
    for key in ("window", "holdTurns", "maxReviews", "maxRedos", "stallTurns", "confirmations", "seed"):
        number(parameters[key], key, 1 if key in ("window", "confirmations") else 0, 10000, True)
    for key in ("threshold", "baseThreshold", "thresholdStep"):
        number(parameters[key], key, 0, 1)
    if parameters["baseThreshold"] + 2 * parameters["thresholdStep"] > 1:
        raise ValueError("能力边界阈值超过 1")
    for key in ("efficientWeight", "capableWeight"):
        number(parameters[key], key)
    if parameters["staticMode"] not in ("fixed", "random") or parameters["efficientWeight"] + parameters["capableWeight"] <= 0:
        raise ValueError("静态策略参数无效")
    security_raw = obj(raw.get("security", {}), ("sensitiveTerms", "maxPromptBytes"), "security")
    security = compile_privacy({"enabled": True, **security_raw}, models=tuple(models.values()),
        schema_version=PRIVACY_SCHEMA_V2, require_local_candidate=False, enforce_zero_cost_classifier=False)
    pairs = raw.get("compatiblePairs", [])
    if not isinstance(pairs, list) or any(not isinstance(p, list) or len(p) != 2
            or any(v not in declared_ids for v in p) for p in pairs):
        raise ValueError("compatiblePairs 必须引用两个已配置模型")
    return {"raw": raw, "enabled": raw["enabled"], "strategy": strategy, "unit": unit, "budget": budget,
        "timeout": timeout, "max_calls": max_calls, "models": models, "roles": roles,
        "parameters": parameters, "security": security, "pairs": pairs, "budgets": budgets,
        "model_issues": model_issues}


def preview(raw, host_issues=None):
    try:
        c = compile_config(raw)
    except (ValueError, TypeError, KeyError) as exc:
        return {"valid": False, "issues": [str(exc)], "strategies": []}
    rows = []
    for strategy in STRATEGIES:
        required = list(REQUIRED[strategy])
        if strategy == "static" and c["parameters"]["staticMode"] == "random":
            required.append("capable")
        issues = [f"缺少 {r} 模型" for r in required if r not in c["roles"]]
        for role in required:
            model_id = c["roles"].get(role)
            if model_id in c["model_issues"]:
                reason = (host_issues or {}).get(model_id, c["model_issues"][model_id])
                issues.append(f"{role}：{model_id} 配置未完成（{reason}）")
            elif model_id in (host_issues or {}):
                issues.append(f"{role}：模型资料不可用（{host_issues[model_id]}）")
        for role in required:
            model_id = c["roles"].get(role)
            if model_id in c["models"]:
                model_unit = c["models"][model_id].billing_unit
                if model_unit not in c["budgets"]:
                    issues.append(f"缺少 {model_unit} 生产预算")
        if not c["enabled"]:
            issues.append("尚未启用规划路由")
        rows.append({"id": strategy, "name": NAMES[strategy], "available": not issues, "issues": issues})
    config_issues = [f"{model_id} 配置未完成（{(host_issues or {}).get(model_id, reason)}）"
                     for model_id, reason in c["model_issues"].items()]
    return {"valid": True, "issues": config_issues, "strategies": rows, "defaultStrategy": c["strategy"],
            "coverage": "仅受管模型调用；宿主工具和独立子 Agent 费用不在主任务硬预算内"}
