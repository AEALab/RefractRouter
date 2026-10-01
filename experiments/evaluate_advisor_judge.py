"""离线验收本地 Advisor Judge；不会联系任何模型服务。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from refractrouter.advisor_decision import decision_request
from refractrouter.planning_decision import LayaDecisionAdapter


def evaluate(suite, adapter):
    rows = []
    for case in suite["cases"]:
        request = decision_request(case["messages"], case.get("events", []), case["candidate"],
            suite["threshold"], review_count=case["reviewCount"],
            previous_feedback=case.get("previousFeedback"))
        request["contract"] = "advisor-local-review-v2"
        response = adapter.decide_advisor(request)
        payload = response.payload
        rows.append({"id": case["id"], "category": case["category"],
            "language": case["language"], "expected": case["expected"],
            "outcome": payload["verdict"], "rawVerdict": payload["rawVerdict"],
            "confidence": payload["confidence"], "matched": payload["verdict"] == case["expected"],
            "latencyMs": response.latency_ms, "usage": response.usage, "raw": payload.get("raw")})
    return rows


def summarize(suite, rows, *, cases, cold_start_ms):
    defects = [row for row in rows if row["category"] == "defect"]
    qualified = [row for row in rows if row["category"] == "qualified"]
    insufficient = [row for row in rows if row["category"] == "insufficient"]
    rechecks = [row for row in rows if row["category"] == "recheck"]
    return {"schemaVersion": "advisor-judge-audit-result-v1",
        "recordedAt": datetime.now(timezone.utc).isoformat(), "backend": "local-laya-mlx",
        "suite": str(cases), "checkpoint": suite["checkpoint"], "revision": suite["revision"],
        "threshold": suite["threshold"], "coldStartMs": cold_start_ms,
        "matched": sum(row["matched"] for row in rows), "total": len(rows),
        "defectsApproved": sum(row["outcome"] == "APPROVE" for row in defects),
        "qualifiedApproved": sum(row["outcome"] == "APPROVE" for row in qualified),
        "insufficientApproved": sum(row["outcome"] == "APPROVE" for row in insufficient),
        "rechecksMatched": sum(row["matched"] for row in rechecks),
        "dailyUseAccepted": ((not any(row["outcome"] == "APPROVE" for row in defects + insufficient)
                              and sum(row["outcome"] == "APPROVE" for row in qualified) >= 5
                              and all(row["matched"] for row in rechecks))
                             if suite.get("schemaVersion", "advisor-judge-suite-v1") == "advisor-judge-suite-v1" else None),
        "cases": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    suite = json.loads(args.cases.read_text())
    if suite.get("schemaVersion") == "advisor-judge-suite-v1":
        if len(suite.get("cases", [])) != 24:
            raise ValueError("Advisor Judge v1 必须使用冻结的 24 条案例")
    elif suite.get("schemaVersion") == "advisor-judge-suite-v2":
        from experiments.judge_case_audit import validate_suite
        validate_suite(suite)
    else:
        raise ValueError("Advisor Judge 案例版本无效")
    adapter = LayaDecisionAdapter({"modelPath": str(args.model_path),
        "sourceModel": suite["checkpoint"], "revision": suite["revision"],
        "device": "gpu", "dtype": "float16", "method": "choice-v2"})
    cold_start_ms = adapter.cold_start_ms
    report = summarize(suite, evaluate(suite, adapter), cases=args.cases,
                       cold_start_ms=cold_start_ms)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise ValueError("验收输出已存在，拒绝覆盖")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
