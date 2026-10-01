"""拆分前本地 Laya 有限案例验收；零网络、零 API 费用。"""
import argparse
import json
from pathlib import Path
import statistics
import time

from refractrouter.decomposition_decision import build_request
from refractrouter.planning_decision import LayaDecisionAdapter


def percentile(values, ratio):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--cases", type=Path,
                        default=Path("data/benchmarks/decomposition-judge-v1.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=.65)
    args = parser.parse_args()
    case_set = json.loads(args.cases.read_text())
    config = {"modelPath": str(args.model_path.expanduser().resolve()),
              "sourceModel": case_set["checkpoint"], "revision": case_set["revision"],
              "device": "gpu", "dtype": "float16", "method": "choice-v2"}
    adapter = LayaDecisionAdapter(config)
    rows = []
    for case in case_set["cases"]:
        started = time.perf_counter()
        result = adapter.decide_decomposition(build_request(
            case["task"], "", threshold=args.threshold))
        elapsed = (time.perf_counter() - started) * 1000
        rows.append({"id": case["id"], "expected": case["expected"],
                     "verdict": result.payload["verdict"],
                     "rawVerdict": result.payload["rawVerdict"],
                     "confidence": result.payload["confidence"],
                     "probabilities": result.payload["probabilities"],
                     "signals": result.payload.get("signals"),
                     "correct": result.payload["verdict"] == case["expected"],
                     "latencyMs": result.latency_ms, "wallMs": elapsed,
                     "usage": result.usage})
    warm = [row["wallMs"] for row in rows[1:]]
    counts = {choice: sum(row["verdict"] == choice for row in rows)
              for choice in ("SEPARABLE", "COUPLED", "UNKNOWN")}
    report = {"schemaVersion": "decomposition-local-acceptance-v1",
              "checkpoint": case_set["checkpoint"], "revision": case_set["revision"],
              "threshold": args.threshold, "cases": len(rows),
              "correct": sum(row["correct"] for row in rows), "verdictCounts": counts,
              "warmLatencyMs": {"median": statistics.median(warm), "p95": percentile(warm, .95)},
              "paidApiCalls": 0, "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
