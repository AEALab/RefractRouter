"""运行冻结的 24 条轻量 LLM Advisor Judge 案例；默认只生成零调用预检。"""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from refractrouter.advisor_decision import decision_request, llm_messages, parse_decision
from refractrouter.openai_compatible import (ModelInvocationError, OpenAICompatibleClient,
                                             model_response_cost)
from refractrouter.schemas import ModelSpec

from .preflight_advisor_acceptance import (JUDGE_MODEL, JUDGE_OUTPUT_TOKENS, SUITE, preflight)


def judge_model():
    evidence = preflight()
    return ModelSpec(model_id="advisor-judge", provider="ark-plan", api_model=JUDGE_MODEL,
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        api_key_env="CODEX_ARK_API_KEY", input_cost_per_1k=.05,
        cached_input_cost_per_1k=.05, output_cost_per_1k=.05, capability=.5,
        billing_unit="AFP", context_window=1024000, max_output_tokens=JUDGE_OUTPUT_TOKENS,
        snapshot_date=evidence["pricingSnapshot"], role="judge", wire_api="chat-completions",
        request_options={"thinking": {"type": "disabled"}},
        json_mode_strategy="json-object-hint")


def execute(output, approved_digest, approved_afp):
    frozen = preflight()
    saved = json.loads((output / "preflight.json").read_text())
    if saved != frozen or approved_digest != frozen["preflightDigest"]:
        raise ValueError("预检摘要或冻结资料不一致，拒绝真实派发")
    if (not math.isfinite(approved_afp)
            or approved_afp < frozen["costUpper"]["maximumIncludingPriorAfp"]):
        raise ValueError("累计 AFP 授权不足以覆盖冻结上界")
    if any((output / name).exists() for name in ("judge-results.jsonl", "judge-summary.json")):
        raise ValueError("已有真实调用证据，拒绝覆盖或自动重发")
    if not os.environ.get("CODEX_ARK_API_KEY"):
        raise ValueError("缺少 CODEX_ARK_API_KEY")
    suite = json.loads(SUITE.read_text())
    model = judge_model()
    client = OpenAICompatibleClient(max_retries=0, timeout_seconds=30,
        environment={**os.environ,
                     "REFRACTROUTER_MODEL_PROGRESS": str(output / "model-progress.ndjson")})
    rows, charged = [], 0.0
    for case in suite["cases"]:
        request = decision_request(case["messages"], case.get("events", []), case["candidate"],
            suite["threshold"], review_count=case["reviewCount"],
            previous_feedback=case.get("previousFeedback"))
        try:
            response = client.complete(model, llm_messages(request), json_mode=True)
        except ModelInvocationError as exc:
            failed = {"id": case["id"], "category": case["category"],
                "language": case["language"], "expected": case["expected"], "model": JUDGE_MODEL,
                "status": "model-invocation-failed", "failureType": exc.failure_type,
                "attempts": exc.attempts, "latencyMs": exc.latency_ms,
                "diagnostics": exc.diagnostics}
            with (output / "judge-results.jsonl").open("a") as stream:
                stream.write(json.dumps(failed, ensure_ascii=False) + "\n")
                stream.flush()
            raise RuntimeError("Advisor Judge 调用失败；停止批次且不会自动重试") from exc
        if not response.usage_available:
            raise RuntimeError("Judge 用量未知；停止批次并保留在途证据")
        cost = model_response_cost(model, response)
        charged += cost
        receipt = {"id": case["id"], "category": case["category"],
            "language": case["language"], "expected": case["expected"], "model": JUDGE_MODEL,
            "requestId": response.request_id, "latencyMs": response.latency_ms,
            "attempts": response.attempts, "finishReason": response.finish_reason,
            "usage": {"inputTokens": response.input_tokens, "outputTokens": response.output_tokens,
                "cachedInputTokens": response.cached_input_tokens,
                "reasoningTokens": response.reasoning_tokens}, "chargedAfp": cost}
        try:
            parsed = parse_decision(json.loads(response.content))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            with (output / "judge-results.jsonl").open("a") as stream:
                stream.write(json.dumps({**receipt, "status": "invalid-judge-output",
                    "response": response.content, "errorType": type(exc).__name__},
                    ensure_ascii=False) + "\n")
                stream.flush()
            raise ValueError("Advisor Judge 输出无效；停止批次且不会自动修复或重试") from exc
        row = {**receipt, "outcome": parsed["verdict"],
               "matched": parsed["verdict"] == case["expected"], "decision": parsed}
        with (output / "judge-results.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
        rows.append(row)
    defects = [row for row in rows if row["category"] == "defect"]
    qualified = [row for row in rows if row["category"] == "qualified"]
    insufficient = [row for row in rows if row["category"] == "insufficient"]
    rechecks = [row for row in rows if row["category"] == "recheck"]
    summary = {"schemaVersion": "advisor-judge-audit-result-v1",
        "recordedAt": datetime.now(timezone.utc).isoformat(), "backend": "llm",
        "model": JUDGE_MODEL, "threshold": suite["threshold"],
        "matched": sum(row["matched"] for row in rows), "total": len(rows),
        "defectsApproved": sum(row["outcome"] == "APPROVE" for row in defects),
        "qualifiedApproved": sum(row["outcome"] == "APPROVE" for row in qualified),
        "insufficientApproved": sum(row["outcome"] == "APPROVE" for row in insufficient),
        "rechecksMatched": sum(row["matched"] for row in rechecks),
        "dailyUseAccepted": (not any(row["outcome"] == "APPROVE" for row in defects + insufficient)
                             and sum(row["outcome"] == "APPROVE" for row in qualified) >= 5
                             and all(row["matched"] for row in rechecks)),
        "productionAfp": round(charged, 8), "httpRetries": 0, "cases": rows}
    (output / "judge-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    args = parser.parse_args()
    output = args.output.resolve()
    if not args.execute_paid_run:
        if output.exists():
            raise ValueError("验收目录已存在，拒绝覆盖")
        output.mkdir(parents=True)
        (output / "preflight.json").write_text(
            json.dumps(preflight(), ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(preflight(), ensure_ascii=False, indent=2))
        return
    if not args.approved_digest:
        raise ValueError("真实调用需要冻结预检摘要")
    print(json.dumps(execute(output, args.approved_digest, args.approved_afp),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
