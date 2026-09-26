"""Escalation 有限真实验收的零调用预检；默认不联系模型服务。"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from refractrouter.ark_plan import catalog
from refractrouter.escalation_decision import decision_request, llm_messages


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "data/benchmarks/escalation-judge-v1.json"
PRIOR_AFP_WORST_CASE = 134.94255
AUTHORIZATION_AFP = 2000
JUDGE_MODEL = "deepseek-v4-flash"
INITIAL_MODEL = "deepseek-v4-flash"
TAKEOVER_MODEL = "deepseek-v4.1-flash"
JUDGE_OUTPUT_TOKENS = 1024
EXECUTION_OUTPUT_TOKENS = 2048
FLOW_INPUT_BYTES = 80000
FLOW_MAX_CALLS = 6


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
    if (suite.get("schemaVersion") != "escalation-judge-suite-v1"
            or len(suite.get("cases", [])) != 24):
        raise ValueError("Escalation Judge 必须冻结 24 条案例")
    counts = {verdict: sum(case["expected"] == verdict for case in suite["cases"])
              for verdict in ("PROCEED", "DEFECT", "STALL", "UNCERTAIN")}
    if set(counts.values()) != {6}:
        raise ValueError("四类 Judge 案例必须各六条")
    rows = {row["model_id"]: row for row in catalog()["models"]}
    judge_bounds = []
    for case in suite["cases"]:
        request = decision_request([{"role": "user", "content": case["task"]},
                                    *case.get("history", [])], case.get("evidence", []),
                                   case["candidate"], case["finishReason"], suite["threshold"])
        messages = llm_messages(request)
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 256
        judge_bounds.append(_price(rows, JUDGE_MODEL, input_bound, JUDGE_OUTPUT_TOKENS))
    judge_total = round(sum(judge_bounds), 6)
    flow_input_bound = FLOW_INPUT_BYTES + 256
    per_call = {
        INITIAL_MODEL: _price(rows, INITIAL_MODEL, flow_input_bound, EXECUTION_OUTPUT_TOKENS),
        TAKEOVER_MODEL: _price(rows, TAKEOVER_MODEL, flow_input_bound, EXECUTION_OUTPUT_TOKENS),
        JUDGE_MODEL: _price(rows, JUDGE_MODEL, flow_input_bound, JUDGE_OUTPUT_TOKENS),
    }
    # 正常工具流程包含工具前后两轮起始 + Judge；受控接管流程再保护强模型三次续接上界。
    normal_flow = 2 * (per_call[INITIAL_MODEL] + per_call[JUDGE_MODEL])
    takeover_flow = normal_flow + per_call[TAKEOVER_MODEL] * 3
    wiring_total = round(2 * normal_flow + 2 * takeover_flow, 6)
    production = round(judge_total + wiring_total, 6)
    frozen = {"schemaVersion": "escalation-acceptance-preflight-v1",
              "status": "zero-call-preflight", "realModelCalls": 0,
              "suite": str(SUITE.relative_to(ROOT)), "suiteDigest": digest(suite),
              "judgeContractDigest": digest(llm_messages(decision_request(
                  [{"role": "user", "content": "contract-digest-fixture"}], [],
                  {"content": "fixture", "toolCalls": []}, "stop", suite["threshold"]))),
              "models": {"initial": INITIAL_MODEL, "takeover": TAKEOVER_MODEL,
                         "judge": JUDGE_MODEL},
              "limits": {"judgeCases": 24, "dshFlows": 4,
                         "maxCallsPerDshFlow": FLOW_MAX_CALLS,
                         "judgeOutputTokens": JUDGE_OUTPUT_TOKENS,
                         "executionOutputTokens": EXECUTION_OUTPUT_TOKENS,
                         "flowInputBytes": FLOW_INPUT_BYTES,
                         "timeoutMsPerFlow": 300000, "httpRetries": 0,
                         "delegation": False, "judgeThinking": "disabled"},
              "callPlan": {"judgeCases": 24, "normalDshFlowCallsUpper": 4,
                           "takeoverDshFlowCallsUpper": 5,
                           "maximumModelCalls": 42},
              "costUpper": {"judgeCasesAfp": judge_total,
                            "dshWiringAfp": wiring_total,
                            "productionAfp": production,
                            "priorAfpWorstCase": PRIOR_AFP_WORST_CASE,
                            "maximumIncludingPriorAfp": round(PRIOR_AFP_WORST_CASE + production, 6),
                            "authorizedCumulativeAfp": AUTHORIZATION_AFP},
              "perCallUpperAfp": per_call,
              "credentialEnv": "CODEX_ARK_API_KEY",
              "credentialAvailable": bool(os.environ.get("CODEX_ARK_API_KEY")),
              "pricingSnapshot": catalog()["snapshot_date"],
              "pricingSource": catalog()["pricing_url"],
              "notes": ["本地 Laya 24 条案例无 API AFP，另记冷启动、暖机延迟和推论次数。",
                        "四条 DSH 流程分为两个正常工具流程和两个明确标记的受控错误候选流程。",
                        "轻量 Judge 关闭思考，防止推理 token 占满结构化判别输出；该参数在批次内冻结。",
                        "预检不会下载权重、启动本地推论或派发任何真实模型调用。"]}
    if frozen["costUpper"]["maximumIncludingPriorAfp"] > AUTHORIZATION_AFP:
        raise ValueError("本批次上界超过累计 2000 AFP 授权")
    return {**frozen, "preflightDigest": digest(frozen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = preflight()
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise ValueError("预检输出已存在，拒绝覆盖")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
