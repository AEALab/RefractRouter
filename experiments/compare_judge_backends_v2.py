"""在固定新版题集上比较 Jev 与轻量 LLM；默认只输出零调用预检。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median

from refractrouter.advisor_decision import (decision_request as advisor_request,
                                            llm_messages as advisor_messages,
                                            parse_decision as parse_advisor)
from refractrouter.escalation_decision import (decision_request as escalation_request,
                                               llm_messages as escalation_messages,
                                               parse_decision as parse_escalation)
from refractrouter.jev_decision import (JEV_INPUT_USD_PER_MILLION, JEV_MODEL,
                                        JevDecisionAdapter)
from refractrouter.openai_compatible import OpenAICompatibleClient, model_response_cost
from refractrouter.schemas import ModelSpec
from experiments.evaluate_advisor_judge import evaluate as evaluate_local_advisor
from experiments.evaluate_escalation_judge import evaluate as evaluate_local_escalation
from experiments.judge_case_audit import validate_suite


ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "advisor": ROOT / "data/benchmarks/advisor-judge-v2.json",
    "escalation": ROOT / "data/benchmarks/escalation-judge-v2.json",
}
LOCAL = {
    "advisor": ROOT / "reports/judge-question-audit-20261001/advisor-laya-v2.json",
    "escalation": ROOT / "reports/judge-question-audit-20261001/escalation-laya-v2.json",
}
EXCLUDED_FROM_SCORE = {"escalation": {"mix-stall-tool"}}
JUDGE_MODEL = "deepseek-v4-flash"
JUDGE_PRICE_AFP_PER_1K = .05
JUDGE_OUTPUT_LIMIT = 1024
INPUT_LIMIT_TOKENS = 64000
USD_UPPER_PER_JEV_CALL = INPUT_LIMIT_TOKENS * JEV_INPUT_USD_PER_MILLION / 1_000_000
AFP_UPPER_PER_LLM_CALL = ((INPUT_LIMIT_TOKENS + JUDGE_OUTPUT_LIMIT)
                          * JUDGE_PRICE_AFP_PER_1K / 1000)


def _json(path):
    return json.loads(path.read_text())


def load():
    suites = {}
    for name, path in SUITES.items():
        suite = _json(path)
        validate_suite(suite)
        local = _json(LOCAL[name])
        if {case["id"] for case in suite["cases"]} != {row["id"] for row in local["cases"]}:
            raise ValueError(f"{name} 本地对照题集不完整")
        suites[name] = suite
    return suites


def preflight(suites):
    count = sum(len(suite["cases"]) for suite in suites.values())
    return {"schemaVersion": "judge-backend-comparison-preflight-v1",
        "caseCount": count, "httpRequestsPerBackend": count, "httpRetries": 0,
        "excludedFromScore": {name: sorted(ids) for name, ids in EXCLUDED_FROM_SCORE.items()},
        "jev": {"model": JEV_MODEL, "priceUsdPerMillionInputTokens":
                 JEV_INPUT_USD_PER_MILLION,
                 "maximumUsd": round(count * USD_UPPER_PER_JEV_CALL, 9)},
        "llm": {"model": JUDGE_MODEL, "provider": "ark-plan",
                "maximumAfp": round(count * AFP_UPPER_PER_LLM_CALL, 6),
                "outputTokensPerCall": JUDGE_OUTPUT_LIMIT},
        "suites": {name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "cases": len(suites[name]["cases"])} for name, path in SUITES.items()},
        "contracts": {name: hashlib.sha256((ROOT / f"src/refractrouter/{name}_decision.py")
                                      .read_bytes()).hexdigest() for name in SUITES},
        "note": "含一条事先标记的歧义题；所有后端均执行，但不纳入符合率。"
                "费用上界按每请求 64k 输入和 LLM 1024 输出 tokens 计算；"
                "普通 LLM 使用此前核对的 Agent Plan AFP 路线价格。"}


def _model():
    return ModelSpec(model_id="judge-v2-comparison", provider="ark-plan",
        api_model=JUDGE_MODEL, base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        api_key_env="CODEX_ARK_API_KEY", input_cost_per_1k=JUDGE_PRICE_AFP_PER_1K,
        cached_input_cost_per_1k=JUDGE_PRICE_AFP_PER_1K,
        output_cost_per_1k=JUDGE_PRICE_AFP_PER_1K, capability=.5,
        billing_unit="AFP", context_window=1024000,
        max_output_tokens=JUDGE_OUTPUT_LIMIT, snapshot_date="2026-09-25",
        role="judge", wire_api="chat-completions",
        request_options={"thinking": {"type": "disabled"}},
        json_mode_strategy="json-object-hint")


def _request(name, case, suite):
    if name == "advisor":
        request = advisor_request(case["messages"], case.get("events", []),
            case["candidate"], suite["threshold"], review_count=case["reviewCount"],
            previous_feedback=case.get("previousFeedback"))
        request["contract"] = "advisor-local-review-v2"
    else:
        request = escalation_request(
            [{"role": "user", "content": case["task"]}, *case.get("history", [])],
            case.get("evidence", []), case["candidate"], case["finishReason"],
            suite["threshold"])
    return request


def _jev_case(name, case, suite, adapter):
    # 调用现有 Laya 评测函数，保证问题模板及阈值映射与本地结果相同。
    single = {**suite, "cases": [case]}
    row = (evaluate_local_advisor(single, adapter) if name == "advisor"
           else evaluate_local_escalation(single, adapter))[0]
    usage = row["usage"]
    if type(usage.get("input_tokens")) is not int:
        raise ValueError("Jev 用量未确认；停止本批")
    return {**row, "actualModel": adapter.model,
            "chargedUsd": usage["input_tokens"] * JEV_INPUT_USD_PER_MILLION / 1_000_000}


def _llm_case(name, case, suite, client, model):
    request = _request(name, case, suite)
    messages = advisor_messages(request) if name == "advisor" else escalation_messages(request)
    response = client.complete(model, messages, json_mode=True)
    if not response.usage_available:
        raise ValueError("LLM 用量未确认；停止本批")
    receipt = {"id": case["id"], "language": case["language"],
               "expected": case["expected"], "requestedModel": model.api_model,
               "modelIdentityVerified": False,
               "latencyMs": response.latency_ms, "requestId": response.request_id,
               "finishReason": response.finish_reason,
               "usage": {"inputTokens": response.input_tokens,
                         "outputTokens": response.output_tokens,
                         "cachedInputTokens": response.cached_input_tokens},
               "chargedAfp": model_response_cost(model, response),
               "rawResponse": response.content}
    raw = json.loads(response.content)
    if name == "advisor":
        parsed = parse_advisor(raw)
    else:
        parsed = parse_escalation(raw, {event["id"] for event in case.get("evidence", [])},
                                  suite["threshold"])
    return {**receipt, "outcome": parsed["verdict"], "rawVerdict": parsed["rawVerdict"],
            "matched": parsed["verdict"] == case["expected"], "decision": parsed}


def run(suites, *, backend, output, maximum):
    frozen = preflight(suites)
    upper = frozen[backend]["maximumUsd" if backend == "jev" else "maximumAfp"]
    if not math.isfinite(maximum) or maximum < upper:
        raise ValueError(f"{backend} 冻结上界为 {upper}；本次授权额度不足")
    if output.exists():
        raise ValueError("批次目录已经存在；拒绝覆盖或自动重发")
    if backend == "jev":
        key = os.environ.get("TYPESAFE_API_KEY") or getpass("Jev API key（不回显）：")
        adapter = JevDecisionAdapter(api_key=key, method="choice-v2")
        client = model = None
    else:
        if not os.environ.get("CODEX_ARK_API_KEY"):
            raise ValueError("Ark 凭证未就绪")
        adapter = None
        client = OpenAICompatibleClient(max_retries=0, timeout_seconds=30)
        model = _model()
    output.mkdir(parents=True)
    (output / "preflight.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    spent = 0.0
    completed = 0
    with (output / "calls.jsonl").open("x") as journal:
        for name, suite in suites.items():
            for case in suite["cases"]:
                if spent + (USD_UPPER_PER_JEV_CALL if backend == "jev"
                            else AFP_UPPER_PER_LLM_CALL) > maximum:
                    raise ValueError("剩余额度无法保护下一次调用；停止本批")
                try:
                    row = (_jev_case(name, case, suite, adapter) if backend == "jev"
                           else _llm_case(name, case, suite, client, model))
                except Exception as exc:
                    # 无法判断请求是否已计费，保留上界并且不自动重发。
                    journal.write(json.dumps({"suite": name, "caseId": case["id"],
                        "status": "unconfirmed", "errorType": type(exc).__name__,
                        "reservedUpper": (USD_UPPER_PER_JEV_CALL if backend == "jev"
                                          else AFP_UPPER_PER_LLM_CALL),
                        "recordedAt": datetime.now(timezone.utc).isoformat()},
                        ensure_ascii=False) + "\n")
                    journal.flush()
                    os.fsync(journal.fileno())
                    raise
                amount = row["chargedUsd" if backend == "jev" else "chargedAfp"]
                spent += amount
                journal.write(json.dumps({"suite": name, "case": row,
                    "recordedAt": datetime.now(timezone.utc).isoformat()},
                    ensure_ascii=False) + "\n")
                journal.flush()
                os.fsync(journal.fileno())
                completed += 1
    return {"backend": backend, "completed": completed, "charged": spent,
            "unit": "USD" if backend == "jev" else "AFP", "output": str(output)}


def compare(suites, *, jev_dir, llm_dir, output):
    if output.exists():
        raise ValueError("比较报告已存在，拒绝覆盖")
    expected = preflight(suites)
    for directory in (jev_dir, llm_dir):
        if _json(directory / "preflight.json") != expected:
            raise ValueError(f"{directory} 的预检与当前冻结题集不一致")
    def index(directory):
        entries = [json.loads(line) for line in (directory / "calls.jsonl").read_text().splitlines()]
        if any("case" not in entry for entry in entries):
            raise ValueError(f"{directory} 有未确认调用，不能汇总")
        return {(entry["suite"], entry["case"]["id"]): entry["case"] for entry in entries}
    jev, llm = index(jev_dir), index(llm_dir)
    rows = []
    for name, suite in suites.items():
        laya = {row["id"]: row for row in _json(LOCAL[name])["cases"]}
        for case in suite["cases"]:
            key = (name, case["id"])
            if key not in jev or key not in llm:
                raise ValueError(f"缺少相同案例：{key}")
            excluded = case["id"] in EXCLUDED_FROM_SCORE.get(name, set())
            rows.append({"suite": name, "id": case["id"], "expected": case["expected"],
                "excludedFromScore": excluded,
                **{backend: {"outcome": result["outcome"], "rawVerdict": result["rawVerdict"],
                             "matched": result["matched"], "latencyMs": result["latencyMs"]}
                   for backend, result in (("laya", laya[case["id"]]),
                                           ("jev", jev[key]), ("llm", llm[key]))}})
    summary = {}
    for name in suites:
        included = [row for row in rows if row["suite"] == name and not row["excludedFromScore"]]
        summary[name] = {"scored": len(included), "excluded":
                         len(suites[name]["cases"]) - len(included)}
        for backend in ("laya", "jev", "llm"):
            timings = [row[backend]["latencyMs"] for row in included]
            summary[name][backend] = {"matched": sum(row[backend]["matched"] for row in included),
                "medianLatencyMs": median(timings),
                "defectsReleased": sum(row["expected"] in ("DEFECT", "REDO")
                                       and row[backend]["outcome"] in ("PROCEED", "APPROVE")
                                       for row in included)}
    report = {"schemaVersion": "judge-backend-comparison-v2", "preflight": expected,
              "summary": summary, "cases": rows,
              "limitations": "人工小题集只比较判别结果；不代表完整 Agent 任务成功率。"
                             "Jev 与 Laya 共用 Choice 题目；普通 LLM 使用各策略 JSON 合同。"
                             "计费单位分列，不直接加总或换算。"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", choices=("jev", "llm"))
    parser.add_argument("--max-usd", type=float, default=0)
    parser.add_argument("--max-afp", type=float, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--jev-dir", type=Path)
    parser.add_argument("--llm-dir", type=Path)
    args = parser.parse_args()
    suites = load()
    if args.compare:
        if not args.output or not args.jev_dir or not args.llm_dir:
            parser.error("比较需要 --output、--jev-dir 和 --llm-dir")
        print(json.dumps(compare(suites, jev_dir=args.jev_dir,
                                  llm_dir=args.llm_dir, output=args.output), ensure_ascii=False))
    elif args.run:
        if not args.output:
            parser.error("真实运行需要 --output")
        maximum = args.max_usd if args.run == "jev" else args.max_afp
        print(json.dumps(run(suites, backend=args.run, output=args.output,
                             maximum=maximum), ensure_ascii=False))
    else:
        print(json.dumps(preflight(suites), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
