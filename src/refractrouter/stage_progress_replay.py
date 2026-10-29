"""同一合成工具轨迹下重放新旧 Stage 规则；重定价不证明真实收益。"""
from decimal import Decimal, InvalidOperation

from .planning_policy import STAGE_RULE_VERSION, stage_decision
from .purpose_review import digest, wire
from .stage_progress import VERSION, compile_shadow, decide

CORPUS = "stage-progress-corpus-v1"


def _amount(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("模拟价格必须是有界十进制字符串")
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0 or not -12 <= result.as_tuple().exponent <= 12:
            raise ValueError("模拟价格无效")
        return result
    except InvalidOperation as exc:
        raise ValueError("模拟价格无效") from exc


def compare(corpus):
    wire(corpus)
    if (not isinstance(corpus, dict) or set(corpus) != {
        "schemaVersion", "kind", "description", "config", "legacyParameters", "simulatedPrices", "cases"
    } or corpus["schemaVersion"] != CORPUS or corpus["kind"] != "constructed"):
        raise ValueError("必须使用明确标注的合成进展回归合同")
    config = compile_shadow(corpus["config"])
    parameters = corpus["legacyParameters"]
    if (not isinstance(parameters, dict) or set(parameters) != {"window", "threshold", "holdTurns"}
            or any(type(parameters[k]) is not int or not 1 <= parameters[k] <= 100 for k in ("window", "holdTurns"))
            or type(parameters["threshold"]) not in (float, int) or not 0 <= parameters["threshold"] <= 1):
        raise ValueError("旧规则参数无效")
    prices = corpus["simulatedPrices"]
    if not isinstance(prices, dict) or set(prices) != {"unit", "efficient", "capable", "commonCalls"} or prices["unit"] != "CNY":
        raise ValueError("模拟重定价只比较同一 CNY 包络")
    execution = {key: _amount(prices[key]) for key in ("efficient", "capable")}
    if not isinstance(prices["commonCalls"], list) or len(prices["commonCalls"]) > 100:
        raise ValueError("模拟共同调用无效")
    for call in prices["commonCalls"]:
        if (not isinstance(call, dict) or set(call) != {"purpose", "amount"}
                or call["purpose"] not in ("classification", "review", "failed", "discarded", "takeover")):
            raise ValueError("模拟共同费用须逐调用列出用途")
        _amount(call["amount"])
    cases = corpus["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("回归案例数量无效")
    case_ids, output = set(), []
    totals = {arm: {"boundaries": 0, "strongCalls": 0, "switches": 0, "falseUpgrades": 0,
        "prematureRestores": 0, "unscoredBoundaries": 0, "simulatedCompleteCostCny": Decimal(0)}
        for arm in ("fixed-hold", "new-evidence")}
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {"id", "description", "taskSha256", "steps"}
                or not isinstance(case["id"], str) or not case["id"] or case["id"] in case_ids
                or not isinstance(case["steps"], list) or not 1 <= len(case["steps"]) <= 100):
            raise ValueError("回归案例身份或边界无效")
        case_ids.add(case["id"])
        legacy, proposed, previous = {}, None, {arm: "efficient" for arm in totals}
        traces = {arm: [] for arm in totals}
        fees = {arm: sum((_amount(c["amount"]) for c in prices["commonCalls"]), Decimal(0)) for arm in totals}
        for step in case["steps"]:
            if (not isinstance(step, dict) or set(step) != {"events", "expectedRole"}
                    or step["expectedRole"] not in ("efficient", "capable", "unknown")):
                raise ValueError("回归边界须冻结事件及判定预期")
            old = stage_decision(step["events"], legacy, parameters, "efficient")
            legacy.update(hold=old["hold"], consumedEvidenceIds=list(dict.fromkeys(
                legacy.get("consumedEvidenceIds", []) + [e["id"] for e in step["events"]]))[-128:])
            proposed, new = decide(step["events"], proposed, config, case["taskSha256"])
            for arm, result in (("fixed-hold", old), ("new-evidence", new)):
                role, before = result["role"], previous[arm]
                row = totals[arm]
                row["boundaries"] += 1
                row["strongCalls"] += role == "capable"
                row["switches"] += role != before
                row["falseUpgrades"] += before == "efficient" and role == "capable" and step["expectedRole"] == "efficient"
                row["prematureRestores"] += before == "capable" and role == "efficient" and step["expectedRole"] == "capable"
                row["unscoredBoundaries"] += step["expectedRole"] == "unknown"
                fees[arm] += execution[role]
                traces[arm].append({"role": role, "reason": result["reason"], "expectedRole": step["expectedRole"],
                                    "progress": result.get("progress"), "evidenceIds": result["evidenceIds"]})
                previous[arm] = role
        for arm in totals:
            totals[arm]["simulatedCompleteCostCny"] += fees[arm]
        output.append({"id": case["id"], "sourceSha256": digest(case), "traces": traces,
                       "simulatedCompleteCostCny": {arm: str(amount) for arm, amount in fees.items()}})
    for row in totals.values():
        row["strongShare"] = row["strongCalls"] / row["boundaries"]
        row["simulatedCompleteCostCny"] = str(row["simulatedCompleteCostCny"])
    return {"schemaVersion": "stage-progress-replay-result-v1", "corpusSha256": digest(corpus),
        "kind": "constructed", "modelCalls": 0, "actualSelectionChanged": False,
        "rules": {"fixed-hold": STAGE_RULE_VERSION, "new-evidence": VERSION}, "metrics": totals, "cases": output,
        "additionalStrongCalls": totals["new-evidence"]["strongCalls"] - totals["fixed-hold"]["strongCalls"],
        "costBasis": "simulated-complete-managed-call-envelope", "actualCompleteCostComparison": "unknown",
        "wholeTaskQualityProven": False, "actualModelBenefitProven": False,
        "hybrid": {"mode": "unchanged", "existingDowngradeConfirmations": True, "newQualificationGranted": False}}
