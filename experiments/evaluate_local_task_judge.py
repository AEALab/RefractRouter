"""离线验收本地 Task Judge 的判别方向；候选能力为明确标注的模拟资料。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from refractrouter.planning_decision import (DECISION_CONTRACT, LayaDecisionAdapter,
                                            decision_request, parse_decision)


def evaluate(cases, adapter, threshold):
    results = []
    for case in cases:
        candidates = [
            {"id": item["id"], "provider": "offline-fixture", "model": item["id"],
             "capabilities": {"mainExecutor": True}, "capabilityCard": item["card"]}
            for item in case["candidates"]
        ]
        state = {"contract": DECISION_CONTRACT, "text": case["task"], "media": [],
                 "tools": [], "complete": True}
        response = adapter.decide(decision_request(state, candidates, threshold))
        parsed = parse_decision(response.payload, [item["id"] for item in candidates], threshold)
        outcome = "insufficient" if parsed["uncertain"] else parsed["candidateId"]
        results.append({"id": case["id"], "expected": case["expected"], "outcome": outcome,
                        "matched": outcome == case["expected"], "selected": parsed["candidateId"],
                        "score": parsed["score"], "missingInformation": parsed["missingInformation"],
                        "scoreKind": response.payload.get("scoreKind", "ordinal-suitability"),
                        "latencyMs": response.latency_ms, "usage": response.usage,
                        "raw": response.payload.get("rawPerCandidate", response.payload.get("rawChoice"))})
    return results


def evaluate_choice_probe(cases, adapter):
    """仅作离线对照；不替换生产 Task 的评分和备用规则。"""
    results = []
    for case in cases:
        criteria = {item["id"]: item["card"] for item in case["candidates"]}
        criteria["insufficient"] = "任务或候选能力资料不足，无法可靠选模"
        question = {"selection": {"type": "choice",
            "instructions": "根据用户任务与明确的候选能力，选择能完成任务的候选；信息不足时选择 insufficient。",
            "criteria": criteria}}
        adapter._ensure_complete(case["task"], question)
        response = adapter.agent.predict(case["task"], question)
        answer = response["answers"]["selection"]
        results.append({"id": case["id"], "expected": case["expected"],
                        "outcome": answer["choice"], "matched": answer["choice"] == case["expected"],
                        "probabilities": answer.get("probabilities"),
                        "confidence": answer.get("confidence"), "usage": response.get("usage")})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--mode", choices=("production", "choice-probe", "choice-v2"),
                        default="production")
    args = parser.parse_args()
    suite = json.loads(args.cases.read_text())
    adapter = LayaDecisionAdapter({"modelPath": str(args.model_path),
        "sourceModel": suite["checkpoint"], "revision": suite["revision"],
        "device": "gpu", "dtype": "float16",
        "method": "choice-v2" if args.mode == "choice-v2" else "ordinal-v1"})
    cold_start_ms = adapter.cold_start_ms
    cases = (evaluate_choice_probe(suite["cases"], adapter) if args.mode == "choice-probe"
             else evaluate(suite["cases"], adapter, args.threshold))
    report = {"schemaVersion": "task-judge-audit-result-v1",
              "recordedAt": datetime.now(timezone.utc).isoformat(),
              "suite": str(args.cases), "checkpoint": suite["checkpoint"],
              "revision": suite["revision"], "threshold": args.threshold,
              "mode": args.mode,
              "coldStartMs": cold_start_ms,
              "matched": sum(item["matched"] for item in cases), "total": len(cases),
              "cases": cases}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
