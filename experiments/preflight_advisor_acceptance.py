"""Advisor Gate v2 有限真实验收的零调用预检。"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from refractrouter.advisor_decision import decision_request, llm_messages
from refractrouter.ark_plan import catalog


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "data/benchmarks/advisor-judge-v1.json"
PRIOR_AFP_WORST_CASE = 134.94255
AUTHORIZATION_AFP = 2000
JUDGE_MODEL = "deepseek-v4-flash"
EXECUTOR_MODEL = "deepseek-v4.1-flash"
JUDGE_OUTPUT_TOKENS = 1024
EXECUTION_OUTPUT_TOKENS = 2048
FLOW_INPUT_BYTES = 80000


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _price(rows, model_id, input_bound, output_bound):
    row = rows.get(model_id)
    if not row or row["pricing"]["unit"] != "afp-per-10000-tokens":
        raise ValueError(f"{model_id} 缺少可核对 AFP 价格")
    if input_bound + output_bound > row["context_window_tokens"]:
        raise ValueError(f"{model_id} 请求包络超过上下文容量")
    price = row["pricing"]
    return round((input_bound * price["input_coefficient"]
                  + output_bound * price["output_coefficient"]) / 10000, 6)


def preflight():
    suite = json.loads(SUITE.read_text())
    if suite.get("schemaVersion") != "advisor-judge-suite-v1" or len(suite.get("cases", [])) != 24:
        raise ValueError("Advisor Judge 必须冻结 24 条案例")
    counts = {category: sum(case["category"] == category for case in suite["cases"])
              for category in ("qualified", "defect", "insufficient", "recheck")}
    if set(counts.values()) != {6}:
        raise ValueError("Advisor 四类案例必须各六条")
    rows = {row["model_id"]: row for row in catalog()["models"]}
    judge_bounds = []
    for case in suite["cases"]:
        request = decision_request(case["messages"], case.get("events", []), case["candidate"],
            suite["threshold"], review_count=case["reviewCount"],
            previous_feedback=case.get("previousFeedback"))
        bound = len(json.dumps(llm_messages(request), ensure_ascii=False).encode()) + 256
        judge_bounds.append(_price(rows, JUDGE_MODEL, bound, JUDGE_OUTPUT_TOKENS))
    judge_total = round(sum(judge_bounds), 6)
    flow_input = FLOW_INPUT_BYTES + 256
    executor_call = _price(rows, EXECUTOR_MODEL, flow_input, EXECUTION_OUTPUT_TOKENS)
    judge_call = _price(rows, JUDGE_MODEL, flow_input, JUDGE_OUTPUT_TOKENS)
    # 每个客户端各一条直接通过和一条返工复审；最坏分别为 2 与 4 次调用。
    wiring_total = round(3 * (executor_call + judge_call
                              + 2 * executor_call + 2 * judge_call), 6)
    production = round(judge_total + wiring_total, 6)
    frozen = {"schemaVersion": "advisor-acceptance-preflight-v1",
        "status": "zero-call-preflight", "realModelCalls": 0,
        "suite": str(SUITE.relative_to(ROOT)), "suiteDigest": digest(suite),
        "judgeContractDigest": digest(llm_messages(decision_request(
            [{"role": "user", "content": "contract-digest-fixture"}], [],
            {"content": "fixture", "toolCalls": []}, suite["threshold"]))),
        "models": {"executor": EXECUTOR_MODEL, "judge": JUDGE_MODEL},
        "limits": {"judgeCases": 24, "clientFlows": 6, "clients": ["dsh", "codex", "hermes"],
            "maxCallsPerFlow": 4, "judgeOutputTokens": JUDGE_OUTPUT_TOKENS,
            "executionOutputTokens": EXECUTION_OUTPUT_TOKENS, "flowInputBytes": FLOW_INPUT_BYTES,
            "timeoutMsPerFlow": 300000, "httpRetries": 0, "delegation": False,
            "judgeThinking": "disabled"},
        "callPlan": {"judgeCases": 24, "clientFlowCallsUpper": 18,
                     "maximumModelCalls": 42},
        "costUpper": {"judgeCasesAfp": judge_total, "clientWiringAfp": wiring_total,
            "productionAfp": production, "priorAfpWorstCase": PRIOR_AFP_WORST_CASE,
            "maximumIncludingPriorAfp": round(PRIOR_AFP_WORST_CASE + production, 6),
            "authorizedCumulativeAfp": AUTHORIZATION_AFP},
        "perCallUpperAfp": {"executor": executor_call, "judge": judge_call},
        "credentialEnv": "CODEX_ARK_API_KEY",
        "credentialAvailable": bool(os.environ.get("CODEX_ARK_API_KEY")),
        "pricingSnapshot": catalog()["snapshot_date"], "pricingSource": catalog()["pricing_url"],
        "notes": ["本地 Laya 24 条案例无 API AFP，另记冷启动、暖机延迟和推论次数。",
                  "六条客户端流程含三条正常放行与三条受控返工复审，不用于证明自然任务收益。",
                  "预检不会下载权重、启动本地推论或派发真实模型调用。"]}
    if frozen["costUpper"]["maximumIncludingPriorAfp"] > AUTHORIZATION_AFP:
        raise ValueError("本批次上界超过累计 2000 AFP 授权")
    return {**frozen, "preflightDigest": digest(frozen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    content = json.dumps(preflight(), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise ValueError("预检输出已存在，拒绝覆盖")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
