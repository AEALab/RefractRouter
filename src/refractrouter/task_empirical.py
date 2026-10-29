"""整任务经验资格与完整计价费用的影子预测；不执行选路、调用模型或改账。"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import math
from statistics import mean, median

from .judge_qualification import interval
from .purpose_review import wire
from .task_cost_observation import observe
from .task_outcomes import digest


CONFIG = "task-expected-cost-shadow-v1"
CONTEXT = "task-cost-context-v1"
PROFILE = "task-empirical-profile-v1"


def _text(value, label, maximum=256):
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ValueError(label + " 无效")
    return value


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("经验材料摘要无效")
    return value


def _probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("经验质量门槛无效")
    return value


def compile_shadow(raw, *, schema, pool):
    if raw is None:
        return None
    if schema != "refractagent-planning-v8":
        raise ValueError("Task 经验影子需要 v8 配置")
    fields = {"schemaVersion", "profile", "profileSha256", "families", "routeVersion", "cacheCondition",
              "pricingDate", "expiresOn", "minSamples", "qualityMin"}
    if not isinstance(raw, dict) or set(raw) != fields or raw["schemaVersion"] != CONFIG:
        raise ValueError("Task 经验影子配置字段无效")
    wire(raw)
    validate_profile(raw["profile"])
    if _sha(raw["profileSha256"]) != digest(raw["profile"]):
        raise ValueError("经验 profile 与固定摘要不符")
    _text(raw["routeVersion"], "经验路线版本")
    if raw["cacheCondition"] not in ("cold", "warm", "observed-mixture", "unknown"):
        raise ValueError("缓存条件无效")
    start, end = date.fromisoformat(raw["pricingDate"]), date.fromisoformat(raw["expiresOn"])
    if end < start:
        raise ValueError("经验价格有效期无效")
    if type(raw["minSamples"]) is not int or not 3 <= raw["minSamples"] <= 10000:
        raise ValueError("经验最小样本数须为3至10000")
    _probability(raw["qualityMin"])
    families = raw["families"]
    if not isinstance(families, list) or not 1 <= len(families) <= 32:
        raise ValueError("必须固定任务类型目录")
    seen = set()
    for f in families:
        if not isinstance(f, dict) or set(f) != {"id", "description", "criteriaSha256", "criterionIds"}:
            raise ValueError("任务类型目录字段无效")
        key = _text(f["id"], "任务类型", 64)
        _text(f["description"], "任务类型说明", 1000)
        _sha(f["criteriaSha256"])
        ids = f["criterionIds"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 64:
            raise ValueError("必须固定完整验收项")
        for item in ids:
            _text(item, "验收项", 128)
        if key in seen or len(set(ids)) != len(ids):
            raise ValueError("任务类型或验收项重复")
        seen.add(key)
    if not pool:
        raise ValueError("经验影子需要 Task 模型池")
    return deepcopy(raw)


def make_context(compiled, family):
    shadow = compiled.get("task_shadow")
    if shadow is None:
        return None
    family_row = next((f for f in shadow["families"] if f["id"] == family), None)
    # profile 或统计门槛更新不会改变实际分类/执行路线，不能因此丢失同版本观测。
    raw = deepcopy(compiled["raw"])
    del raw["taskShadow"]
    binding = {"configuration": raw, "families": shadow["families"], "routeVersion": shadow["routeVersion"]}
    models = {}
    for m in raw["models"]:
        normalized = compiled["models"].get(m["id"])
        prices = ({k: getattr(normalized, k, None) for k in ("input_cost_per_1k", "output_cost_per_1k",
            "cached_input_cost_per_1k", "cache_write_cost_per_1k", "billing_unit", "conversion_rate",
            "conversion_source", "conversion_as_of")} if normalized is not None else None)
        models[m["id"]] = {"sha256": digest({"raw": m, "normalizedPrices": prices}), "provider": m["provider"],
                            "model": m["model"], "revision": m.get("revision")}
    from .deepseek_official_pricing import pricing
    active_prices = {m["id"]: pricing(m["model"]) for m in raw["models"] if m["provider"] == "deepseek-official"}
    return {"schemaVersion": CONTEXT, "family": family_row["id"] if family_row else None,
            "routeBinding": digest(binding), "routeVersion": shadow["routeVersion"], "modelBindings": models,
            "criteriaSha256": family_row["criteriaSha256"] if family_row else None,
            "criterionIds": family_row["criterionIds"] if family_row else [],
            "cacheCondition": shadow["cacheCondition"], "pricingDate": shadow["pricingDate"],
            "expiresOn": shadow["expiresOn"], "activePrices": active_prices}


def _context(ctx):
    fields = {"schemaVersion", "family", "routeBinding", "routeVersion", "modelBindings", "criteriaSha256",
              "criterionIds", "cacheCondition", "pricingDate", "expiresOn", "activePrices"}
    if not isinstance(ctx, dict) or set(ctx) != fields or ctx["schemaVersion"] != CONTEXT:
        raise ValueError("经验上下文合同无效")
    _sha(ctx["routeBinding"])
    _text(ctx["routeVersion"], "经验路线版本")
    if ctx["family"] is not None:
        _text(ctx["family"], "经验任务类型", 64)
        _sha(ctx["criteriaSha256"])
        if not isinstance(ctx["criterionIds"], list) or not ctx["criterionIds"]:
            raise ValueError("经验完整验收项缺失")
        for item in ctx["criterionIds"]:
            _text(item, "验收项", 128)
        if len(set(ctx["criterionIds"])) != len(ctx["criterionIds"]):
            raise ValueError("经验验收项重复")
    if ctx["cacheCondition"] not in ("cold", "warm", "observed-mixture", "unknown"):
        raise ValueError("经验缓存条件无效")
    if date.fromisoformat(ctx["expiresOn"]) < date.fromisoformat(ctx["pricingDate"]):
        raise ValueError("经验价格日期无效")
    if not isinstance(ctx["modelBindings"], dict) or not ctx["modelBindings"]:
        raise ValueError("经验模型绑定缺失")
    for key, value in ctx["modelBindings"].items():
        _text(key, "经验模型标识")
        if not isinstance(value, dict) or set(value) != {"sha256", "provider", "model", "revision"}:
            raise ValueError("经验模型绑定字段无效")
        _sha(value["sha256"])
        _text(value["provider"], "经验provider")
        _text(value["model"], "经验实际模型")
        if value["revision"] is not None:
            _text(value["revision"], "经验模型修订")
    if not isinstance(ctx["activePrices"], dict):
        raise ValueError("动态价格绑定无效")


def _money(value):
    if not isinstance(value, str) or len(value) > 128:
        raise ValueError("经验费用必须是有限非负金额字符串")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("经验费用金额无效") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("经验费用金额无效")
    return result


def _budget_available(bound, remaining):
    if not isinstance(bound, dict) or bound.get("unit") not in ("CNY", "USD", "AFP"):
        return False
    required = {bound["unit"]: bound.get("cashAmount", bound.get("amount"))}
    if "referenceAmount" in bound:
        required["REFERENCE_CNY"] = bound["referenceAmount"]
    for unit, value in required.items():
        limit = remaining.get(unit)
        if (type(value) not in (int, float) or not math.isfinite(value) or value < 0
                or type(limit) not in (int, float) or math.isnan(limit) or limit < 0 or value > limit):
            return False
    return True


def _quality(result, context, assessment):
    """只接收独立完整验收；普通用户点赞、未经准入的模型评审和局部字段不能代替。"""
    fields = {"schemaVersion", "candidateId", "candidateSha256", "criteriaSha256", "method", "scope",
              "independent", "familyCorrect", "checks"}
    if not isinstance(assessment, dict) or set(assessment) != fields:
        return "unknown", "missing-independent-full-assessment", None
    if (assessment["schemaVersion"] != "whole-task-acceptance-v1" or assessment["independent"] is not True
            or assessment["scope"] != "complete-delivery-and-requirements"
            or assessment["method"] not in ("frozen-full-task-oracle-v1", "human-adjudication-v1")
            or assessment["familyCorrect"] is not True or assessment["criteriaSha256"] != context["criteriaSha256"]):
        return "unknown", "unqualified-assessment-scope-or-source", digest(assessment)
    candidates = [c for c in result.get("candidates", []) if c["candidateId"] == assessment["candidateId"]
                  and c["candidateSha256"] == assessment["candidateSha256"] and c["routerDisposition"] == "accepted"]
    if len(candidates) != 1:
        return "unknown", "assessment-not-bound-to-delivered-candidate", digest(assessment)
    final = next((r for r in result["calls"] if r.get("call_id") == assessment["candidateId"]), {})
    if final.get("finish_reason") != "stop":
        return "unknown", "assessment-not-final-delivery", digest(assessment)
    accepted = {c["candidateId"] for c in result.get("candidates", []) if c["routerDisposition"] == "accepted"}
    final_calls = [r for r in result["calls"] if r.get("call_id") in accepted]
    if not final_calls or final_calls[-1]["call_id"] != assessment["candidateId"]:
        return "unknown", "assessment-bound-to-earlier-delivery", digest(assessment)
    checks = assessment["checks"]
    if (not isinstance(checks, list) or len(checks) != len(context["criterionIds"])
            or any(not isinstance(c, dict) or set(c) != {"id", "passed"} or
                   not isinstance(c["id"], str) or type(c["passed"]) not in (bool, type(None)) for c in checks)
            or len({c["id"] for c in checks}) != len(checks)
            or {c["id"] for c in checks} != set(context["criterionIds"])):
        return "unknown", "incomplete-full-task-checks", digest(assessment)
    states = [c["passed"] for c in checks]
    status = "fail" if False in states else "unknown" if None in states else "pass"
    if status == "pass" and result.get("status") != "completed":
        return "unknown", "unfinished-task-cannot-be-qualified", digest(assessment)
    # 独立裁定必须同时进入 W02 的独立评估通道，用户/模型反馈不能替代。
    events = [r["event"] for r in result.get("events", [])]
    replaced = {e.get("supersedes") for e in events if e.get("supersedes")}
    feedback_status = {"pass": "accepted", "fail": "rejected", "unknown": "unknown"}[status]
    witness = [e for e in events if e.get("kind") == "feedback" and e.get("source") == "hidden-evaluation"
               and e.get("eventId") not in replaced and e.get("candidateId") == assessment["candidateId"]
               and e.get("candidateSha256") == assessment["candidateSha256"]
               and e.get("criteriaVersion") == assessment["criteriaSha256"]]
    if (not witness or {e.get("status") for e in witness} != {feedback_status}
            or not any(digest(assessment) in e.get("artifactSha256", []) for e in witness)):
        return "unknown", "assessment-not-recorded-in-independent-channel", digest(assessment)
    return status, "independent-full-task-checks", digest(assessment)


def build_profile(samples, *, kind):
    """样本由受信离线导入方提供。验证身份/范围/算术，不认证人类或供应商签名。"""
    if kind not in ("empirical", "simulation") or not isinstance(samples, list) or len(samples) > 1000:
        raise ValueError("经验样本来源或数量无效")
    rows, seen = [], set()
    for sample in samples:
        if not isinstance(sample, dict) or set(sample) != {"result", "assessment", "sourceClusterId", "split"}:
            raise ValueError("经验样本字段无效")
        if sample["split"] != "calibration":
            raise ValueError("留出任务不得构建经验资格")
        result = sample["result"]
        costs = observe(result)
        token = result["runId"]
        if token in seen:
            raise ValueError("同一任务不能重复增加经验分母")
        seen.add(token)
        cluster = _text(sample["sourceClusterId"], "经验来源簇")
        context = result.get("costContext")
        if not isinstance(context, dict) or context.get("schemaVersion") != CONTEXT:
            rows.append({"runId": token, "excluded": "missing-versioned-task-context"})
            continue
        wire(context)
        _context(context)
        executions = [r for r in result["calls"] if r.get("purpose") in ("execute", "redo", "takeover")]
        model_ids = {r.get("model_id") for r in executions}
        if result.get("strategy") != "task" or len(model_ids) != 1:
            rows.append({"runId": token, "excluded": "not-a-fixed-whole-task-route"})
            continue
        model = next(iter(model_ids))
        binding = context["modelBindings"].get(model)
        identity_ok = binding and all(r.get("actual_model") == binding["model"] and r.get("provider") == binding["provider"]
                                      for r in executions)
        quality, reason, assessment_sha = _quality(result, context, sample["assessment"])
        if not identity_ok:
            quality, reason = "unknown", "actual-model-identity-mismatch"
        for call in result["calls"]:
            expected_model = context["modelBindings"].get(call.get("model_id"))
            if call.get("status") != "local-inference" and (not expected_model or
                    call.get("actual_model") != expected_model["model"] or call.get("provider") != expected_model["provider"]):
                quality, reason = "unknown", "unbound-managed-call-model"
        token_calls = [r for r in result["calls"] if r.get("status") in ("billed", "billed-failed", "billed-cancelled")
                       and r.get("usage_type") != "non-token"]
        hits = [r.get("cached_input_tokens") for r in token_calls]
        if ((context["cacheCondition"] == "cold" and any(type(h) is not int or h != 0 for h in hits))
                or (context["cacheCondition"] == "warm" and not any(type(h) is int and h > 0 for h in hits))):
            quality, reason = "unknown", "cache-condition-mismatch"
        task_input = digest(result.get("taskProjection"))
        if result.get("classificationTaskDigest") != task_input:
            quality, reason = "unknown", "task-instructions-changed"
        for call in result["calls"]:
            expected_price = context["activePrices"].get(call.get("model_id"))
            if call.get("model_id") in context["activePrices"]:
                actual = call.get("price_snapshot", {})
                if not expected_price or any(actual.get(k) != v for k, v in expected_price.items()):
                    quality, reason = "unknown", "pricing-changed-during-task"
        rows.append({"runId": token, "sourceClusterId": cluster, "sourceResultSha256": costs["sourceResultSha256"],
                     "taskInputSha256": task_input,
                     "context": deepcopy(context), "modelId": model, "quality": quality, "qualityReason": reason,
                     "assessmentSha256": assessment_sha, "costObservation": costs})
    profile = {"schemaVersion": PROFILE, "kind": kind, "observations": rows}
    validate_profile(profile)
    return profile


def validate_profile(profile):
    if (not isinstance(profile, dict) or set(profile) != {"schemaVersion", "kind", "observations"}
            or profile["schemaVersion"] != PROFILE or profile["kind"] not in ("empirical", "simulation")
            or not isinstance(profile["observations"], list) or len(profile["observations"]) > 1000):
        raise ValueError("经验 profile 合同无效")
    wire(profile)
    seen = set()
    for row in profile["observations"]:
        _text(row.get("runId"), "经验任务身份")
        if row["runId"] in seen:
            raise ValueError("经验 profile 重复任务")
        seen.add(row["runId"])
        if "excluded" in row:
            if set(row) != {"runId", "excluded"}:
                raise ValueError("经验排除记录字段无效")
            _text(row["excluded"], "经验排除原因")
            continue
        fields = {"runId", "sourceClusterId", "sourceResultSha256", "taskInputSha256", "context", "modelId", "quality",
                  "qualityReason", "assessmentSha256", "costObservation"}
        if set(row) != fields or row["quality"] not in ("pass", "fail", "unknown"):
            raise ValueError("经验观测字段无效")
        _text(row["sourceClusterId"], "经验来源簇")
        _sha(row["sourceResultSha256"])
        _sha(row["taskInputSha256"])
        if row["assessmentSha256"] is not None:
            _sha(row["assessmentSha256"])
        ctx, cost = row["context"], row["costObservation"]
        if not isinstance(ctx, dict) or ctx.get("schemaVersion") != CONTEXT or not isinstance(cost, dict):
            raise ValueError("经验上下文/费用缺失")
        if cost.get("sourceResultSha256") != row["sourceResultSha256"] or cost.get("runId") != row["runId"]:
            raise ValueError("经验费用与原任务身份不符")
        _context(ctx)
        if row["modelId"] not in ctx["modelBindings"]:
            raise ValueError("经验模型不在绑定中")
        if row["quality"] != "unknown" and row["assessmentSha256"] is None:
            raise ValueError("确定质量缺少独立裁定摘要")
        if row["quality"] != "unknown" and row["qualityReason"] != "independent-full-task-checks":
            raise ValueError("不能从非独立渠道推导确定质量")
        if (type(cost.get("pricedCallAmountsComplete")) is not bool or type(cost.get("cacheUsageComplete")) is not bool
                or not isinstance(cost.get("costs"), list)):
            raise ValueError("经验费用完整性字段无效")
        if cost["pricedCallAmountsComplete"] and (cost.get("unknownCallIds") or cost.get("pendingReservationCount")):
            raise ValueError("未知预留不能声明为完整费用")
        dimensions = set()
        for item in cost.get("costs", []):
            if (not isinstance(item, dict) or set(item) != {"lane", "unit", "knownCalculated", "unknownProtected"}
                    or item["lane"] not in ("metered-budget", "subscription-reference")
                    or item["unit"] not in ("CNY", "USD", "AFP")):
                raise ValueError("经验费用分账无效")
            identity = item["lane"], item["unit"]
            if identity in dimensions:
                raise ValueError("经验费用分账重复")
            dimensions.add(identity)
            _money(item["knownCalculated"])
            _money(item["unknownProtected"])
        reference = cost.get("referenceCostCny")
        if reference is not None:
            if set(reference) != {"knownCalculated", "unknownProtected"} or any(u != "CNY" for _, u in dimensions):
                raise ValueError("经验参考费用不能跨币种")
            for field in ("knownCalculated", "unknownProtected"):
                if _money(reference[field]) != sum(_money(i[field]) for i in cost["costs"]):
                    raise ValueError("经验参考费用与分账不符")


def predict(profile, context, *, candidate_ids, fallback, bounds, remaining, min_samples, quality_min, as_of):
    validate_profile(profile)
    day = date.fromisoformat(as_of)
    _probability(quality_min)
    if type(min_samples) is not int or min_samples < 3:
        raise ValueError("经验最小样本数无效")
    if (not isinstance(candidate_ids, list) or any(not isinstance(i, str) for i in candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)):
        raise ValueError("影子候选不能重复")
    allowed = set(candidate_ids)
    base = {"schemaVersion": CONFIG, "mode": "shadow", "actualSelectionChanged": False,
            "profileSha256": digest(profile), "corpusKind": profile["kind"], "rows": [],
            "candidateId": fallback if fallback in allowed and _budget_available(bounds.get(fallback), remaining) else None, "uncertain": True,
            "costBasis": "unavailable", "scope": "managed-agent-only", "outsideManagedCosts": "unknown",
            "productionQualificationClaimed": False}
    if not context or not context.get("family") or context.get("cacheCondition") == "unknown":
        return {**base, "reason": "unknown-task-family-or-cache-condition"}
    _context(context)
    if any("excluded" in r for r in profile["observations"]):
        return {**base, "reason": "profile-has-unresolved-observations"}
    if day < date.fromisoformat(context["pricingDate"]) or day > date.fromisoformat(context["expiresOn"]):
        return {**base, "reason": "pricing-expired-or-not-yet-valid"}
    grouped = defaultdict(list)
    for row in profile["observations"]:
        if "excluded" not in row and row["context"] == context and row["modelId"] in allowed:
            grouped[row["modelId"]].append(row)
    eligible = []
    qualified_without_cost = False
    for model in candidate_ids:
        rows = grouped[model]
        binding_reasons = []
        revisions = [b.get("revision") for b in context["modelBindings"].values()]
        if any(not isinstance(r, str) or r.strip().lower() in ("", "unknown", "unpinned", "unavailable") for r in revisions):
            binding_reasons.append("model-revision-unpinned")
        quality_reasons, cost_reasons = list(binding_reasons), list(binding_reasons)
        n, passed = len(rows), sum(r["quality"] == "pass" for r in rows)
        lower = 1 - interval(n - passed, n)["upper"] if n else None
        if n < min_samples:
            quality_reasons.append("insufficient-samples")
            cost_reasons.append("insufficient-samples")
        if len({r["sourceClusterId"] for r in rows}) != n:
            quality_reasons.append("reused-source-cluster")
        if len({r["taskInputSha256"] for r in rows}) != n:
            quality_reasons.append("reused-task-input")
        if any(r["quality"] == "unknown" for r in rows) or lower is None or lower < quality_min:
            quality_reasons.append("independent-quality-unproven")
        costs, dimensions = [], set()
        for row in rows:
            cost = row["costObservation"]
            reference = cost.get("referenceCostCny")
            if (cost.get("pricedCallAmountsComplete") is not True or cost.get("cacheUsageComplete") is not True
                    or reference is None and len(cost["costs"]) != 1):
                cost_reasons.append("incomplete-cost-or-incomparable-lanes")
                continue
            item = ({"lane": "reference-valuation", "unit": "CNY", **reference}
                    if reference is not None else cost["costs"][0])
            dimensions.add((item["lane"], item["unit"]))
            value = float(item["knownCalculated"])
            if not math.isfinite(value) or value < 0 or float(item["unknownProtected"]) != 0:
                cost_reasons.append("invalid-or-unknown-cost")
                continue
            costs.append(value)
        if len(dimensions) != 1:
            cost_reasons.append("incomparable-cost-dimensions")
        dimension = next(iter(dimensions)) if len(dimensions) == 1 else None
        bound = bounds.get(model)
        budget_ok = _budget_available(bound, remaining)
        estimate = None
        if costs and not cost_reasons:
            center = mean(costs)
            # 逐样本留一均值误差，仅为已知轨迹的描述，不是新任务的误差保证。
            exact_costs = [Decimal(str(v)) for v in costs]
            total_cost = sum(exact_costs)
            loo = float(mean(abs(v - (total_cost - v) / (len(costs) - 1)) for v in exact_costs))
            estimate = {"mean": center, "median": median(costs), "observedMin": min(costs), "observedMax": max(costs),
                        "leaveOneOutMae": loo, "sampleCount": len(costs), "dimension": list(dimension),
                        "rangeKind": "observed-not-guaranteed", "includesAllManagedCalls": True}
            base["costBasis"] = "empirical-full-managed-task"
            if not quality_reasons and budget_ok:
                eligible.append((center, candidate_ids.index(model), model, dimension))
        if not quality_reasons and estimate is None:
            qualified_without_cost = True
        reasons = quality_reasons + cost_reasons + ([] if budget_ok else ["hard-budget-unavailable"])
        base["rows"].append({"modelId": model, "samples": n, "independentPasses": passed,
                            "qualityLower95": lower, "qualified": not quality_reasons,
                            "qualityReasons": sorted(set(quality_reasons)), "costReasons": sorted(set(cost_reasons)),
                            "budgetAdmitted": budget_ok, "selectionAdmitted": not reasons,
                            "reasons": sorted(set(reasons)),
                            "estimate": estimate, "sourceRecordsSha256": digest(sorted(r["runId"] for r in rows))})
    if qualified_without_cost:
        return {**base, "reason": "qualified-candidate-cost-unavailable"}
    if not eligible:
        return {**base, "reason": "no-empirically-qualified-candidate"}
    if len({item[3] for item in eligible}) != 1:
        return {**base, "reason": "incomparable-cost-dimensions"}
    selected = min(eligible)[2]
    return {**base, "candidateId": selected, "uncertain": False, "costBasis": "empirical-full-managed-task",
            "reason": "quality-then-full-task-prediction", "productionQualificationClaimed": False}
