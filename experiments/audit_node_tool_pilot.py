"""只读核对 node-as-tool 先导原始用量、费用与接续来源；不改变冻结主判据。"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def terminal_receipt(path):
    """只提取终态和用量，不复制模型思考或正文，不另发网络请求。"""
    found = []
    with Path(path).open() as stream:
        for line in stream:
            if not line.startswith("data: ") or not any(
                name in line for name in ('"response.completed"', '"response.incomplete"', '"response.failed"')
            ):
                continue
            event = json.loads(line[6:])
            if event.get("type") not in {"response.completed", "response.incomplete", "response.failed"}:
                continue
            response = event["response"]
            found.append({k: response.get(k) for k in ("id", "model", "status", "usage", "incomplete_details")})
    if len(found) != 1:
        raise ValueError("原始响应须恰有一个终态回执")
    return found[0]


def expected_afp(usage, model):
    incoming, outgoing = usage["input_tokens"], usage["output_tokens"]
    cached = usage.get("input_tokens_details", {}).get("cached_tokens", 0)
    if any(type(value) is not int or value < 0 for value in (incoming, outgoing, cached)) or cached > incoming:
        raise ValueError("提供方用量字段无效")
    cached_rate = model.get("cached_input_cost_per_1k")
    if cached_rate is None:
        cached_rate = model["input_cost_per_1k"]
    cost = ((incoming - cached) * Decimal(str(model["input_cost_per_1k"]))
            + cached * Decimal(str(cached_rate))
            + outgoing * Decimal(str(model["output_cost_per_1k"]))) / 1000
    # output_tokens 已含思考，不能把 reasoning_tokens 再加一次。
    return float(cost)


def check_wire_controls(request, frozen, errors):
    if request.get("max_output_tokens") != frozen["model"]["max_output_tokens"]:
        errors.append("真实请求未使用冻结的完整模型输出容量")
    if request.get("model") != frozen["model"]["api_model"]:
        errors.append("真实请求模型与冻结清单不符")
    if frozen.get("sampling", {}).get("temperature") == 0:
        if type(request.get("temperature")) not in (int, float) or request.get("temperature") != 0:
            errors.append("实际请求 temperature 与同采样控制不符")


def audit_case(row, directory, frozen):
    errors, notes, receipts = [], [], []
    calls = [c for c in row["calls"] if c["status"] != "cancelled-before-dispatch"]
    if row["arm"] != "dag" and len(list((directory / "wire").glob("*-request.json"))) != len(calls):
        errors.append("宿主请求归档数量与已派发账本行数不同")
    for index, call in enumerate(calls, 1):
        item = {"ledgerCallId": call.get("call_id"), "ledgerStatus": call["status"], "chargedAfp": call["charged"]}
        try:
            if row["arm"] == "dag":
                path = directory / "calls" / (hashlib.sha256(call["label"].encode()).hexdigest() + ".json")
                response = read(path)
                usage = response["raw_usage"]
                observed_model = None  # 此路径保留解析回执，未保留 HTTP 返回的精确模型版本。
                item.update(evidence=str(path), evidenceSha256=sha(path), attempts=response["attempts"])
                if response["attempts"] != 1:
                    errors.append("DAG 回执尝试次数不是一")
                wire = call.get("wire_evidence_prefix")
                if wire:
                    prefix = directory / wire
                    request = read(Path(str(prefix) + "-request.json"))
                    response_path = Path(str(prefix) + "-response.json")
                    original = read(response_path)
                    receipt = read(Path(str(prefix) + "-receipt.json"))
                    check_wire_controls(request, frozen, errors)
                    if original.get("usage") != usage:
                        errors.append("DAG 原始 HTTP 用量与解析回执不一致")
                    request_id = receipt.get("requestId") or original.get("id")
                    if request_id != call.get("request_id"):
                        errors.append("DAG 并发调用与原始 HTTP 关联不符")
                    observed_model = original.get("model")
                    item.update(wireEvidence=str(response_path), wireEvidenceSha256=sha(response_path),
                                requestedTemperature=request.get("temperature"),
                                requestedOutputTokens=request.get("max_output_tokens"))
                elif frozen.get("sampling", {}).get("temperature") == 0:
                    errors.append("同采样 DAG 缺少原始 HTTP 证据")
            else:
                prefix = directory / "wire" / str(index).zfill(3)
                path = Path(str(prefix) + "-response.txt")
                response = terminal_receipt(path)
                usage, observed_model = response["usage"], response["model"]
                request = read(Path(str(prefix) + "-request.json"))
                item.update(evidence=str(path), evidenceSha256=sha(path), responseStatus=response["status"],
                            providerResponseId=response["id"], requestedOutputTokens=request["max_output_tokens"],
                            requestedTemperature=request.get("temperature"))
                check_wire_controls(request, frozen, errors)
                tool_names = [tool.get("name") for tool in request.get("tools", [])]
                item.update(providedToolNames=tool_names, purpose=call.get("purpose"),
                            nodeIntent=call.get("node_intent"))
                if row["arm"] == "one-shot" and tool_names:
                    errors.append("一次性回答请求意外提供了工具")
                if row["arm"] == "node-as-tool":
                    if index == 1 and "refract_expert" not in tool_names:
                        errors.append("工具可用路线的首请求未实际提供专家工具")
                    if any(name != "refract_expert" for name in tool_names):
                        errors.append("工具可用路线提供了未冻结工具")
                    if call.get("purpose") == "node-tool" and tool_names:
                        errors.append("专家子请求不应提供内部工具循环")
            raw_cost = expected_afp(usage, frozen["model"])
            reasoning = usage.get("output_tokens_details", {}).get("reasoning_tokens")
            item.update(providerReportedModel=observed_model, providerInputTokens=usage["input_tokens"],
                        providerOutputTokens=usage["output_tokens"], providerReasoningTokens=reasoning,
                        ledgerReasoningTokens=call.get("reasoning_tokens"), recalculatedAfp=raw_cost)
            if call["status"] != "billed":
                errors.append("已归档回执的调用尚未结算")
            if call.get("input_tokens") != usage["input_tokens"] or call.get("output_tokens") != usage["output_tokens"]:
                errors.append("提供方原始输入或总输出用量与账本不一致")
            if abs(raw_cost - call["charged"]) > 1e-8:
                errors.append("原始总用量重新计算的 AFP 与账本不一致")
            if reasoning is not None and reasoning != call.get("reasoning_tokens"):
                notes.append("原始响应与宿主的思考细项不同；按原始细项展示，总输出计费另行核对")
            if observed_model is None:
                notes.append("DAG 路径没有独立保存提供方精确版本；只能核对冻结请求模型和解析回执")
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append("回执证据不足：" + str(error))
        receipts.append(item)
    if abs(sum(c["charged"] for c in row["calls"]) - row["chargedOrReserved"]) > 1e-8:
        errors.append("个案汇总与调用账本费用不同")
    if row.get("qualityError"):
        notes.append("原交付未通过冻结解析合同；空字段检查列表不表示字段全部正确")
    failures = [c for c in row.get("checks", []) if c["status"] == "fail"]
    return {"runId": row["runId"], "phase": row["phase"], "arm": row["arm"], "status": row["status"],
            "factStatus": row["factStatus"], "deliveryParseError": row.get("qualityError"),
            "fieldChecksAvailable": bool(row.get("checks")),
            "failedValueChecks": [c for c in failures if not c["check"].endswith(":sources")],
            "failedCitationChecks": [c for c in failures if c["check"].endswith(":sources")],
            "chargedOrReservedAfp": row["chargedOrReserved"], "importedFrom": row.get("importedFrom"),
            "reportedExpertInvocations": row.get("expertCalls"),
            "dispatchedExpertRequests": sum(c.get("purpose") == "node-tool" for c in calls),
            "receipts": receipts, "errors": errors, "notes": sorted(set(notes))}


def audit(result_dir, *, root=ROOT, snapshot_path=None, summary_path=None):
    result_dir = Path(result_dir).resolve()
    snapshot = Path(summary_path or result_dir / "summary.json").read_bytes()
    summary, frozen = json.loads(snapshot), read(result_dir / "frozen.json")
    if snapshot_path is not None:
        Path(snapshot_path).write_bytes(snapshot)
    if summary.get("simulated") is not False:
        raise ValueError("真实用量审计不接受模拟批次")
    errors, cases = [], []
    if summary["protocolSha256"] != frozen["protocolSha256"]:
        errors.append("汇总与冻结协议摘要不符")
    for row in summary["runs"]:
        imported = row.get("importedFrom")
        if imported:
            source = root / imported["summary"]
            binding = next((b for b in frozen["priorResults"] if b["path"] == imported["summary"]), None)
            if binding is None or binding["sha256"] != sha(source):
                errors.append("接续来源未绑定累计账本，或来源摘要变化")
            directory = source.parent / row["runId"]
        else:
            directory = result_dir / row["runId"]
        cases.append(audit_case(row, directory, frozen))
    ids = [r["runId"] for r in summary["runs"]]
    if len(set(ids)) != len(ids):
        errors.append("样本身份重复")
    new_rows = [r for r in summary["runs"] if not r.get("importedFrom")]
    direct_calls = sum(c["status"] != "cancelled-before-dispatch" for r in new_rows for c in r["calls"])
    direct_cost = sum(r["chargedOrReserved"] for r in new_rows)
    prior_cost = sum(r["actualOrReservedAfp"] for r in frozen["priorResults"])
    prior_calls = sum(r["realModelCalls"] for r in frozen["priorResults"])
    if direct_calls != summary["realModelCalls"] or abs(direct_cost - summary["actualOrReservedAfp"]) > 1e-8:
        errors.append("本目录新增费用或请求与账本不同")
    if direct_calls + prior_calls != summary["cumulativeRealModelCalls"] or abs(direct_cost + prior_cost - summary["cumulativeActualOrReservedAfp"]) > 1e-8:
        errors.append("跨批累计费用或请求不一致")
    if summary["cumulativeRealModelCalls"] > frozen["cumulativeModelCallLimit"] or summary["cumulativeActualOrReservedAfp"] > frozen["productionAfpUpperBound"] + 1e-8:
        errors.append("超过人类批准的累计额度")
    errors += [row["runId"] + "：" + problem for row in cases for problem in row["errors"]]
    comparison = Counter(r["arm"] for r in summary["runs"] if r["phase"] == "comparison")
    complete = summary["status"] == "completed-development-pilot" and len(cases) == 45 and all(comparison[a] == 9 for a in ("one-shot", "node-as-tool", "dag"))
    return {"schema": "node-tool-pilot-evidence-audit-v1", "batchStatus": summary["status"],
            "scope": "核对原始用量、费用与证据绑定，不代表交付质量通过",
            "summarySha256": hashlib.sha256(snapshot).hexdigest(), "protocolSha256": summary["protocolSha256"],
            "integrityStatus": "fail" if errors else "pass", "completeness": "complete" if complete else "pending",
            "cohortSamples": len(cases), "comparisonSamples": dict(comparison),
            "newRequests": direct_calls, "cumulativeRequests": direct_calls + prior_calls,
            "settledOrHistoricalReservedAfp": direct_cost + prior_cost,
            "budgetNote": "运行中数值只覆盖已收录样本及历史预留；在途预留另由当前个案核心账本保护。",
            "providerBillingConfirmed": False, "errors": errors, "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summary-snapshot", type=Path,
                        help="只读复核已归档的阶段快照，不受主实验继续追加样本影响")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    result = audit(args.result_dir, snapshot_path=args.output_dir / "summary.snapshot.json",
                   summary_path=args.summary_snapshot)
    (args.output_dir / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("integrityStatus", "completeness", "cohortSamples", "cumulativeRequests", "errors")}, ensure_ascii=False))
    return 0 if result["integrityStatus"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
