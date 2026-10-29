"""从任务结果读取完整逐调用费用；不推断质量、不把计价或预留冒充实付。"""
from collections import defaultdict
from decimal import Decimal
import math

from .task_outcomes import digest


VERSION = "whole-task-cost-observation-v1"


def amount(value):
    if (type(value) not in (int, float) or type(value) is int and value.bit_length() > 4096
            or type(value) is float and not math.isfinite(value) or value < 0):
        raise ValueError("任务费用必须是有限非负数")
    return Decimal(str(value))


def observe(result):
    """只消费 #203 原账本投影。失败和丢弃候选照计费，未知保留，币种/订阅分账。"""
    if (not isinstance(result, dict) or result.get("schemaVersion") != "task-result-v1"
            or result.get("financialAuthority") != "original-call-ledger"
            or result.get("coverage") != "managed-agent-only"
            or not isinstance(result.get("status"), str) or not result["status"]):
        raise ValueError("需要原逐调用账本的任务结果投影")
    calls = result.get("calls")
    if not isinstance(calls, list) or not isinstance(result.get("costsByUnit"), dict):
        raise ValueError("任务逐调用费用或总账缺失")
    ledger, known, unknown, purposes = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    seen, unresolved, local_calls = set(), [], []
    reference_total = Decimal(0)
    cache_known = True
    for row in calls:
        if not isinstance(row, dict):
            raise ValueError("逐调用费用记录无效")
        status, token = row.get("status"), row.get("call_id")
        if token is not None:
            if not isinstance(token, str) or not token or token in seen:
                raise ValueError("已派发调用标识缺失或重复")
            seen.add(token)
        elif status not in ("reserved", "cancelled-before-dispatch"):
            raise ValueError("已派发调用标识缺失")
        if status == "local-inference":
            if (row.get("provider") != "local" or row.get("usage_type") != "local-decision"
                    or amount(row.get("charged")) != 0):
                raise ValueError("本地推论记录不能伪装现金调用")
            local_calls.append(token)
            continue
        unit, mode, purpose = row.get("billing_unit"), row.get("billing_mode"), row.get("purpose")
        if (unit not in ("CNY", "USD", "AFP") or mode not in ("metered", "subscription")
                or not isinstance(purpose, str) or not purpose):
            raise ValueError("费用单位、计费模式或用途无效")
        charged, reserved = amount(row.get("charged")), amount(row.get("reserved"))
        if status == "cancelled-before-dispatch" and charged != 0:
            raise ValueError("派发前取消记录不能有费用")
        lane = ("subscription-reference" if mode == "subscription" else "metered-budget", unit)
        if mode == "metered":
            ledger[unit] += charged
        reference_total += charged
        purposes[(*lane, purpose)] += charged
        if status in ("billed", "billed-failed", "billed-cancelled", "cancelled-before-dispatch"):
            known[lane] += charged
        else:
            unknown[lane] += max(charged, reserved)
            unresolved.append(token)
        if row.get("usage_type") != "non-token" and status != "cancelled-before-dispatch":
            read, total = row.get("cached_input_tokens"), row.get("input_tokens")
            cache_known = (cache_known and row.get("cache_usage_available") is True
                           and isinstance(row.get("cache_usage_source"), str) and bool(row["cache_usage_source"])
                           and type(read) is int and type(total) is int and 0 <= read <= total)
    for unit in set(ledger) | set(result["costsByUnit"]):
        if unit not in ("CNY", "USD", "AFP"):
            raise ValueError("任务总账单位无效")
        balance = result["costsByUnit"].get(unit, {})
        if not isinstance(balance, dict):
            raise ValueError("任务总账类型错误")
        expected = amount(balance.get("production", 0)) + amount(balance.get("evaluation", 0))
        if abs(ledger[unit] - expected) > max(Decimal("1e-10"), expected * Decimal("1e-9")):
            raise ValueError("逐调用费用与原总账不一致，禁止遗漏失败或审核费")
    reference = result.get("referenceCosts")
    if any(row.get("billing_mode") == "subscription" for row in calls) and reference is None:
        raise ValueError("订阅参考调用缺少原参考总账")
    if reference is not None:
        if (not isinstance(reference, dict) or reference.get("currency") != "CNY"
                or reference.get("includesCashCalls") is not True
                or any(row.get("billing_unit") != "CNY" for row in calls if row.get("status") != "local-inference")):
            raise ValueError("参考成本不能跨币种相加")
        expected = amount(reference.get("occupied"))
        if abs(reference_total - expected) > max(Decimal("1e-10"), expected * Decimal("1e-9")):
            raise ValueError("参考成本与逐调用费用不一致")
    lanes = sorted(set(known) | set(unknown))
    return {"schemaVersion": VERSION, "sourceResultSha256": digest(result), "runId": result["runId"],
            "taskStatus": result["status"], "coverage": "managed-agent-only",
            "outsideManagedCalls": result.get("outsideManagedCalls", "unknown"),
            "pricedCallAmountsComplete": not unresolved and result["status"] != "running",
            "costs": [{"lane": lane, "unit": unit, "knownCalculated": str(known[lane, unit]),
                       "unknownProtected": str(unknown[lane, unit])} for lane, unit in lanes],
            "byPurpose": [{"lane": lane, "unit": unit, "purpose": purpose, "ledgerOccupied": str(value)}
                          for (lane, unit, purpose), value in sorted(purposes.items())],
            "callIds": sorted(seen), "unknownCallIds": [i for i in unresolved if i is not None],
            "pendingReservationCount": sum(i is None for i in unresolved), "localInferenceCallIds": local_calls,
            "referenceCostCny": ({"knownCalculated": str(sum(known.values())),
                                  "unknownProtected": str(sum(unknown.values()))} if reference is not None else None),
            "cacheUsageComplete": bool(calls) and cache_known,
            "actualProviderDebit": "not-established-by-this-view", "wholeTaskQuality": "unknown",
            "financialLedgerChanged": False, "modelCalls": 0}
