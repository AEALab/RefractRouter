"""冻结新题后对官方 Jev 分动作门槛做有限留出验证；默认零调用。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re

from refractrouter.advisor_decision import decision_request as advisor_request
from refractrouter.escalation_decision import decision_request as escalation_request
from refractrouter.jev_choice_gate import VERSION, evaluate_choice
from refractrouter.jev_decision import (JEV_INPUT_USD_PER_MILLION, JEV_MODEL,
                                        JevDecisionAdapter)


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "data/benchmarks/jev-choice-action-gate-holdout-v1.json"
MAX_INPUT_TOKENS = 64000
PER_CALL_USD_UPPER = MAX_INPUT_TOKENS * JEV_INPUT_USD_PER_MILLION / 1_000_000
EXPECTED = {"advisor": {"APPROVE", "REDO", "UNRESOLVED"},
            "escalation": {"PROCEED", "DEFECT", "STALL", "UNCERTAIN"}}


def load_cases(path=SUITE):
    raw = path.read_bytes()
    suite = json.loads(raw)
    if suite.get("schemaVersion") != "jev-choice-action-gate-holdout-v1":
        raise ValueError("留出题合同不兼容")
    cases, ids = suite.get("cases"), set()
    if not isinstance(cases, list) or len(cases) != 24:
        raise ValueError("留出题数量应冻结为 24")
    for case in cases:
        if (not isinstance(case, dict) or case.get("strategy") not in EXPECTED
                or case.get("expected") not in EXPECTED[case["strategy"]]
                or not isinstance(case.get("id"), str) or case["id"] in ids
                or not isinstance(case.get("task"), str)
                or not isinstance(case.get("candidate"), dict)):
            raise ValueError("留出题身份、标签或候选无效")
        ids.add(case["id"])
        if re.search(r"/(?:Users|home|private|tmp)/", json.dumps(case, ensure_ascii=False)):
            raise ValueError("留出题含本机绝对路径，拒绝发送")
        if case["strategy"] == "escalation":
            tool_calls = case["candidate"].get("toolCalls", [])
            if (case.get("finishReason") == "tool_calls") != bool(tool_calls):
                raise ValueError("Escalation 结束状态和工具调用不配对")
    return cases, hashlib.sha256(raw).hexdigest()


def make_request(case):
    messages = [{"role": "user", "content": case["task"]}, *case.get("history", [])]
    if case["strategy"] == "advisor":
        request = advisor_request(messages, case.get("events", []), case["candidate"], .8,
                                  review_count=case.get("reviewCount", 1),
                                  previous_feedback=case.get("previousFeedback"))
        request["contract"] = "advisor-local-review-v2"
        return request
    return escalation_request(messages, case.get("events", []), case["candidate"],
                              case["finishReason"], .8)


def preflight(cases, suite_sha):
    return {"schemaVersion": "jev-choice-action-gate-preflight-v1",
            "model": JEV_MODEL, "gateVersion": VERSION, "caseCount": len(cases),
            "suiteSha256": suite_sha, "maximumRequests": len(cases),
            "maxInputTokensPerCall": MAX_INPUT_TOKENS,
            "maximumUsd": round(len(cases) * PER_CALL_USD_UPPER, 9),
            "httpRetries": 0, "currency": "USD",
            "note": "新题首次调用前冻结；动作门槛仅供实验，不修改产品默认配置。"}


def score(case, answer):
    raw = answer["raw"]
    gate = evaluate_choice(raw, strategy=case["strategy"],
                           finish_reason=case.get("finishReason"))
    fallback = "UNRESOLVED" if case["strategy"] == "advisor" else "UNCERTAIN"
    choice = raw["choice"]
    legacy = choice if raw["probabilities"][choice] >= .8 else fallback
    proposed = choice if gate["accepted"] else fallback
    if case["strategy"] == "advisor":
        legacy = "REDO" if legacy.startswith("REDO") else legacy
        proposed = "REDO" if proposed.startswith("REDO") else proposed
    return {"legacy": legacy, "proposed": proposed, "gate": gate,
            "unsafeLegacy": legacy in ("APPROVE", "PROCEED") and legacy != case["expected"],
            "unsafeProposed": proposed in ("APPROVE", "PROCEED") and proposed != case["expected"]}


def run(cases, frozen, *, output, max_usd):
    if output.exists():
        raise ValueError("输出目录已存在；拒绝覆盖或重发留出题")
    if not math.isfinite(max_usd) or max_usd < frozen["maximumUsd"]:
        raise ValueError("授权上限不足以覆盖冻结的整批调用")
    key = os.environ.get("TYPESAFE_API_KEY") or getpass("Jev API key（不回显）：")
    adapter = JevDecisionAdapter(api_key=key, method="choice-v2", action_gate=VERSION)
    output.mkdir(parents=True)
    (output / "preflight.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    spent = 0.0
    with (output / "calls.jsonl").open("x") as stream:
        for case in cases:
            if spent + PER_CALL_USD_UPPER > max_usd:
                raise ValueError("剩余额度不足以保护下一次 Jev 调用")
            request = make_request(case)
            try:
                result = (adapter.decide_advisor(request) if case["strategy"] == "advisor"
                          else adapter.decide_escalation(request))
                tokens = result.usage.get("input_tokens")
                if result.model != JEV_MODEL or type(tokens) is not int or tokens < 0:
                    raise ValueError("模型或用量未确认")
                assessed = score(case, result.payload)
            except Exception as exc:
                stream.write(json.dumps({"id": case["id"], "status": "unconfirmed",
                    "errorType": type(exc).__name__, "reservedUsd": PER_CALL_USD_UPPER}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                raise
            charge = tokens * JEV_INPUT_USD_PER_MILLION / 1_000_000
            spent += charge
            receipt = {"id": case["id"], "strategy": case["strategy"],
                       "group": case["group"], "expected": case["expected"],
                       "rawChoice": result.payload["rawVerdict"],
                       "raw": result.payload["raw"], **assessed,
                       "actualModel": result.model, "usage": result.usage,
                       "latencyMs": result.latency_ms, "estimatedCostUsd": charge,
                       "recordedAt": datetime.now(timezone.utc).isoformat()}
            stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    rows = [json.loads(line) for line in (output / "calls.jsonl").read_text().splitlines()]
    summary = {"completed": len(rows), "legacyMatched": sum(r["legacy"] == r["expected"] for r in rows),
               "proposedMatched": sum(r["proposed"] == r["expected"] for r in rows),
               "legacyUnsafeDelivery": [r["id"] for r in rows if r["unsafeLegacy"]],
               "proposedUnsafeDelivery": [r["id"] for r in rows if r["unsafeProposed"]],
               "estimatedCostUsd": spent, "output": str(output)}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-usd", type=float, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases, suite_sha = load_cases()
    frozen = preflight(cases, suite_sha)
    if args.run:
        if args.output is None:
            parser.error("真实调用需要新的 --output 路径")
        print(json.dumps(run(cases, frozen, output=args.output, max_usd=args.max_usd), ensure_ascii=False))
    else:
        print(json.dumps({"realCalls": 0, **frozen}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
