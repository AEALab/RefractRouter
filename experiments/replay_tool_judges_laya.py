"""离线用固定 Laya 权重重放已完成的 DSH Judge 输入。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from experiments.replay_tool_judges_jev import load, preflight
from refractrouter.planning_decision import LayaDecisionAdapter, LocalDecisionCapacityError


MODEL = "aac6fef/laya-multilingual-mlx"
REVISION = "f2b4faf51023039425946074e2cf1361d2db11d5"


def run(rows, *, model_path, output):
    if output.exists():
        raise ValueError("本地重放证据已存在，拒绝覆盖")
    adapter = LayaDecisionAdapter({"modelPath": str(model_path),
        "sourceModel": MODEL, "revision": REVISION,
        "device": "gpu", "dtype": "float16", "method": "choice-v2"})
    cold_start_ms = adapter.cold_start_ms
    recorded = []
    for row in rows:
        try:
            result = (adapter.decide_advisor(row["request"])
                      if row["kind"] == "advisor" else
                      adapter.decide_escalation(row["request"]))
        except LocalDecisionCapacityError as exc:
            recorded.append({"id": row["id"], "status": "capacity-rejected",
                             "errorType": type(exc).__name__, "expected": row["expected"]})
            continue
        payload = result.payload
        recorded.append({"id": row["id"], "status": "completed",
            "expected": row["expected"], "arkVerdict": row["arkVerdict"],
            "layaVerdict": payload["verdict"], "layaRawVerdict": payload["rawVerdict"],
            "selectionProbability": payload["confidence"], "raw": payload.get("raw"),
            "latencyMs": result.latency_ms, "usage": result.usage})
    report = {"schemaVersion": "tool-judge-laya-replay-v1",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "model": MODEL, "revision": REVISION, "method": "choice-v2",
        "coldStartMs": cold_start_ms,
        "sourcePreflight": preflight(rows, load()[1]),
        "completed": sum(row["status"] == "completed" for row in recorded),
        "matched": sum(row.get("layaVerdict") == row["expected"] for row in recorded),
        "noApiCost": True, "cases": recorded}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return {"completed": report["completed"], "matched": report["matched"],
            "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, _ = load()
    print(json.dumps(run(rows, model_path=args.model_path,
                         output=args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
