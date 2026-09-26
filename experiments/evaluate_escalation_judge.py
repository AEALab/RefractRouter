"""离线验收本地 Escalation Judge；不会联系任何模型服务。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from refractrouter.escalation_decision import decision_request
from refractrouter.planning_decision import LayaDecisionAdapter


def evaluate(suite, adapter):
    rows = []
    for case in suite["cases"]:
        messages = [{"role": "user", "content": case["task"]}, *case.get("history", [])]
        request = decision_request(messages, case.get("evidence", []), case["candidate"],
                                   case["finishReason"], suite["threshold"])
        response = adapter.decide_escalation(request)
        payload = response.payload
        rows.append({"id": case["id"], "language": case["language"],
                     "expected": case["expected"], "outcome": payload["verdict"],
                     "rawVerdict": payload["rawVerdict"],
                     "confidence": payload["confidence"],
                     "matched": payload["verdict"] == case["expected"],
                     "latencyMs": response.latency_ms, "usage": response.usage,
                     "raw": payload.get("raw")})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    suite = json.loads(args.cases.read_text())
    if suite.get("schemaVersion") != "escalation-judge-suite-v1":
        raise ValueError("Escalation Judge 案例版本无效")
    adapter = LayaDecisionAdapter({"modelPath": str(args.model_path),
        "sourceModel": suite["checkpoint"], "revision": suite["revision"],
        "device": "gpu", "dtype": "float16", "method": "choice-v2"})
    cold_start_ms = adapter.cold_start_ms
    rows = evaluate(suite, adapter)
    defects = [row for row in rows if row["expected"] == "DEFECT"]
    proceeds = [row for row in rows if row["expected"] == "PROCEED"]
    report = {"schemaVersion": "escalation-judge-audit-result-v1",
              "recordedAt": datetime.now(timezone.utc).isoformat(),
              "backend": "local-laya-mlx", "suite": str(args.cases),
              "checkpoint": suite["checkpoint"], "revision": suite["revision"],
              "threshold": suite["threshold"], "coldStartMs": cold_start_ms,
              "matched": sum(row["matched"] for row in rows), "total": len(rows),
              "defectsReleased": sum(row["outcome"] == "PROCEED" for row in defects),
              "proceedsAccepted": sum(row["outcome"] == "PROCEED" for row in proceeds),
              "dailyUseAccepted": (not any(row["outcome"] == "PROCEED" for row in defects)
                                   and sum(row["outcome"] == "PROCEED" for row in proceeds) >= 5),
              "cases": rows}
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
