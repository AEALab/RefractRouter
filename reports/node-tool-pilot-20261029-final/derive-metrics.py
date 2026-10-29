"""从终态原始账本与提供方回执复现最终统计；不调用模型，不改变冻结分数。"""
from collections import Counter, defaultdict
from decimal import Decimal
import csv
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.audit_node_tool_pilot import terminal_receipt
from refractrouter.node_tool_study import validate

LIVE = ROOT / "reports/node-tool-pilot-20261029-live-05"
OUT = Path(__file__).parent
summary_bytes = (LIVE / "summary.json").read_bytes()
summary = json.loads(summary_bytes)
frozen = json.loads((LIVE / "frozen.json").read_text())
validate(frozen)
assert summary["status"] == "completed-development-pilot" and summary["simulated"] is False
assert len(summary["runs"]) == 45 and len(summary["pairs"]) == 18
comparison = [r for r in summary["runs"] if r["phase"] == "comparison"]
assert len(comparison) == 27 and len({r["runId"] for r in summary["runs"]}) == 45
assert {(r["taskId"], r["repeat"], r["arm"]) for r in comparison} == {
    (task, repeat, arm) for task in frozen["tasks"] for repeat in range(1, 4) for arm in frozen["arms"]}


def value_ok(row):
    values = [c for c in row.get("checks", []) if not c["check"].endswith(":sources")]
    return bool(values) and all(c["status"] == "pass" for c in values)


def stats(rows):
    times = [r["taskElapsedMs"] / 1000 for r in rows if r.get("taskElapsedMs") is not None]
    return {"samples": len(rows), "completed": sum(r["status"] == "completed" for r in rows),
            "jsonParsed": sum(r["status"] == "completed" and not r.get("qualityError") for r in rows),
            "valueChecksPassed": sum(value_ok(r) for r in rows),
            "frozenPrimaryPassed": sum(r["factStatus"] == "pass" for r in rows),
            "afp": float(sum(Decimal(str(r["chargedOrReserved"])) for r in rows)),
            "medianTaskSeconds": median(times) if times else None, "timedSamples": len(times),
            "modelRequests": sum(c["status"] != "cancelled-before-dispatch" for r in rows for c in r["calls"])}


routes = {arm: stats([r for r in comparison if r["arm"] == arm]) for arm in frozen["arms"]}
subsets = {}
for name, groups in (("原采样修订预定义五组", frozen["quoteAmendment"]["originalSamplingFreshGroups"]),
                     ("字段修订后全部新采集两组", frozen["samplingAmendment"]["freshGroups"])):
    keys = {(g["taskId"], g["repeat"]) for g in groups}
    subsets[name] = {arm: stats([r for r in comparison if r["arm"] == arm and (r["taskId"], r["repeat"]) in keys])
                     for arm in frozen["arms"]}
    if name == "字段修订后全部新采集两组":
        assert all(not r.get("importedFrom") for r in comparison if (r["taskId"], r["repeat"]) in keys)

tokens = defaultdict(lambda: {"requests": 0, "inputTokens": 0, "outputTokens": 0,
    "cachedInputTokensReported": 0, "cacheDetailsAvailableRequests": 0,
    "reasoningTokensReported": 0, "reasoningDetailsAvailableRequests": 0})
stages = defaultdict(lambda: {"requests": 0, "afp": Decimal(0), "inputTokens": 0, "outputTokens": 0})
models = Counter(); evidence = []; seen_paths = set(); intents = Counter(); shapes = []
for row in summary["runs"]:
    base = (ROOT / row["importedFrom"]["summary"]).parent if row.get("importedFrom") else LIVE
    directory = base / row["runId"]
    for index, call in enumerate(row["calls"], 1):
        assert call["status"] == "billed"
        if row["arm"] == "dag":
            prefix = directory / call["wire_evidence_prefix"]
            raw_path = Path(str(prefix) + "-response.json")
            reply = json.loads(raw_path.read_text())
        else:
            raw_path = directory / "wire" / f"{index:03}-response.txt"
            reply = terminal_receipt(raw_path)
        assert raw_path not in seen_paths; seen_paths.add(raw_path)
        usage = reply["usage"]; bucket = "baseline" if row["phase"] == "prompt-audit" else row["arm"]
        counter = tokens[bucket]; counter["requests"] += 1
        counter["inputTokens"] += usage["input_tokens"]; counter["outputTokens"] += usage["output_tokens"]
        for details, field, total, available in (("input_tokens_details", "cached_tokens", "cachedInputTokensReported", "cacheDetailsAvailableRequests"),
                                               ("output_tokens_details", "reasoning_tokens", "reasoningTokensReported", "reasoningDetailsAvailableRequests")):
            value = (usage.get(details) or {}).get(field)
            if value is not None:
                assert type(value) is int and value >= 0
                counter[total] += value; counter[available] += 1
        models[reply["model"]] += 1
        stage = "baseline" if bucket == "baseline" else row["arm"] + ":" + str(call.get("stage") or call.get("purpose"))
        stage_data = stages[stage]; stage_data["requests"] += 1; stage_data["afp"] += Decimal(str(call["charged"]))
        stage_data["inputTokens"] += usage["input_tokens"]; stage_data["outputTokens"] += usage["output_tokens"]
        if call.get("purpose") == "node-tool" and row["phase"] == "comparison":
            intents[call["node_intent"]] += 1
        evidence.append({"runId": row["runId"], "purpose": stage,
                         "response": str(raw_path.relative_to(ROOT)), "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()})
    if row["arm"] == "dag" and row["phase"] == "comparison":
        record = json.loads((directory / "dag.json").read_text())
        shapes.append({"runId": row["runId"], "nodes": row["graphNodes"],
                       "peakConcurrency": record["execution"]["peak_running_nodes"],
                       "edges": {n["node_id"]: n["parents"] for n in record["plan"]["nodes"]}})
for entry in stages.values():
    entry["afp"] = float(entry["afp"])
nodes = [r for r in comparison if r["arm"] == "node-as-tool"]
mechanisms = {"expertUsedSamples": sum(r.get("expertCalls", 0) > 0 for r in nodes),
              "expertUnusedSamples": [r["runId"] for r in nodes if r.get("expertCalls", 0) == 0],
              "expertIntents": dict(intents), "dagShapes": shapes,
              "multiNodeDagSamples": sum(s["nodes"] > 1 for s in shapes),
              "actuallyParallelDagSamples": sum(s["peakConcurrency"] > 1 for s in shapes)}
paired = {}
for arm in ("node-as-tool", "dag"):
    pairs = [p for p in summary["pairs"] if p["arm"] == arm]
    paired[arm] = {"transitions": dict(Counter(p["factTransition"] for p in pairs)),
                   "resourceOnlyCheaperThanOneShot": sum(p["afpDifference"] < 0 for p in pairs),
                   "resourceOnlyFasterThanOneShot": sum(p["elapsedDifferenceMs"] < 0 for p in pairs)}
expert_parsed = [r for r in nodes if r.get("expertCalls", 0) > 0 and not r.get("qualityError")]
paired["expertParsedSubset"] = {"samples": len(expert_parsed), "cheaperThanMatchedOneShot": sum(
    r["chargedOrReserved"] < next(a["chargedOrReserved"] for a in comparison if a["arm"] == "one-shot"
        and a["taskId"] == r["taskId"] and a["repeat"] == r["repeat"]) for r in expert_parsed),
    "note": "事后机制诊断，不是随机额外分组，不替代完整主比较。"}
primary_afp = sum(Decimal(str(r["chargedOrReserved"])) for r in summary["runs"])
metrics = {"scope": "三个构造开发任务、三路线、各三次重复；不代表总体因果或独立语义认证。",
    "summarySha256": hashlib.sha256(summary_bytes).hexdigest(), "protocolSha256": summary["protocolSha256"],
    "routes": routes, "subsets": subsets, "providerReportedModelsPrimaryCohort": dict(models),
    "rawProviderTokens": dict(tokens), "modelStages": dict(stages), "mechanisms": mechanisms, "paired": paired,
    "baseline": stats([r for r in summary["runs"] if r["phase"] == "prompt-audit"]),
    "comparisonAfp": float(sum(Decimal(str(r["chargedOrReserved"])) for r in comparison)),
    "primaryCohortAfp": float(primary_afp),
    "diagnosticAndUnknownReserveAfp": float(Decimal(str(summary["cumulativeActualOrReservedAfp"])) - primary_afp),
    "cumulativeRequests": summary["cumulativeRealModelCalls"], "cumulativeAfp": summary["cumulativeActualOrReservedAfp"],
    "unknownReserveAfp": .63, "confirmedUsageValuationAfp": summary["cumulativeActualOrReservedAfp"] - .63,
    "providerBillingConfirmed": False, "qualityVerdict": summary["qualityVerdict"], "receipts": evidence}
assert sum(t["requests"] for t in tokens.values()) == 85
assert models == {"deepseek-v4-flash-ga-260731": 85}
assert abs(float(primary_afp) + metrics["diagnosticAndUnknownReserveAfp"] - metrics["cumulativeAfp"]) < 1e-8
(OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
with (OUT / "paired-results.csv").open("w") as stream:
    writer = csv.writer(stream); writer.writerow(["任务", "轮次", "路线", "执行", "JSON可解析", "字段值正确", "冻结主判据", "AFP", "秒数", "实际专家调用", "规划执行节点数", "原始批次"])
    for row in sorted(comparison, key=lambda r: (r["taskId"], r["repeat"], r["arm"])):
        source = row.get("importedFrom", {}).get("summary", "reports/node-tool-pilot-20261029-live-05/summary.json")
        writer.writerow([row["taskId"], row["repeat"], row["arm"], row["status"], not bool(row.get("qualityError")),
                         value_ok(row) if row["checks"] else "未评", row["factStatus"], row["chargedOrReserved"],
                         row["taskElapsedMs"] / 1000 if row.get("taskElapsedMs") is not None else "",
                         row.get("expertCalls", 0), row.get("graphNodes", ""), source])
print(json.dumps({k: metrics[k] for k in ("routes", "subsets", "rawProviderTokens", "modelStages", "paired",
                                       "comparisonAfp", "primaryCohortAfp", "diagnosticAndUnknownReserveAfp")}, ensure_ascii=False))
