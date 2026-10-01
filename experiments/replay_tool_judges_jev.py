"""用官方 Jev 重放已完成的 DSH Judge 请求；默认零调用预检。"""

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

from refractrouter.jev_decision import (JEV_INPUT_USD_PER_MILLION, JEV_MODEL,
                                        JevDecisionAdapter)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports/judge-tool-flow-20261001"
FLOWS = {
    "advisor-normal-v3": ["APPROVE"],
    "advisor-redo-v5": ["REDO", "APPROVE"],
    "escalation-normal-v4": ["PROCEED", "PROCEED"],
    "escalation-defect-v4": ["DEFECT"],
}
MAX_INPUT_TOKENS = 64000
PER_CALL_USD_UPPER = MAX_INPUT_TOKENS * JEV_INPUT_USD_PER_MILLION / 1_000_000


def load():
    rows = []
    fingerprints = {}
    for flow, labels in FLOWS.items():
        files = list((SOURCE / flow / "runs/planning").glob("*.json"))
        if len(files) != 1:
            raise ValueError(f"{flow} 缺少唯一的已完成任务记录")
        raw = files[0].read_bytes()
        record = json.loads(raw)
        if record.get("status") != "completed":
            raise ValueError(f"{flow} 未完成，不能作为此批重放输入")
        judges = [call for call in record["calls"]
                  if call.get("purpose") in ("advisor", "escalation")]
        if len(judges) != len(labels) or any(call.get("status") != "billed"
                                             for call in judges):
            raise ValueError(f"{flow} 的 Judge 次数或用量未确认")
        for index, (call, expected) in enumerate(zip(judges, labels, strict=True), 1):
            messages = call.get("request_messages")
            if not isinstance(messages, list) or len(messages) != 2:
                raise ValueError(f"{flow} 缺少 Judge 原始请求")
            request = json.loads(messages[1]["content"])
            # 本批只包含明确标记的合成任务，不转发宿主绝对路径或私人附件。
            if re.search(r"/(?:Users|home|private|tmp)/", json.dumps(request)):
                raise ValueError(f"{flow} 出现本机绝对路径，拒绝发送给 Jev")
            if call["purpose"] == "advisor":
                request["contract"] = "advisor-local-review-v2"
            rows.append({"id": f"{flow}:{index}", "flow": flow,
                         "kind": call["purpose"], "expected": expected,
                         "arkVerdict": json.loads(call["response_output"])["verdict"],
                         "request": request})
        fingerprints[flow] = hashlib.sha256(raw).hexdigest()
    return rows, fingerprints


def preflight(rows, fingerprints):
    return {"schemaVersion": "tool-judge-jev-replay-preflight-v1",
        "model": JEV_MODEL, "source": "已完成的 DSH 工具任务 Judge 输入",
        "questionMethod": "choice-v2", "caseCount": len(rows),
        "maximumRequests": len(rows), "httpRetries": 0,
        "maxInputTokensPerCall": MAX_INPUT_TOKENS,
        "maximumUsd": round(len(rows) * PER_CALL_USD_UPPER, 9),
        "sourceSha256": fingerprints,
        "contractSha256": hashlib.sha256((ROOT / "src/refractrouter/planning_decision.py")
                                        .read_bytes()).hexdigest(),
        "note": "事后重放只比较 Judge 判别；不会重新执行宿主工具，"
                "也不证明官方 Jev 已接入 Router 产品运行路径。"}


def run(rows, frozen, *, output, maximum):
    if output.exists():
        raise ValueError("重放目录已存在，拒绝覆盖或重发")
    if not math.isfinite(maximum) or maximum < frozen["maximumUsd"]:
        raise ValueError("授权上限不足以保护整批 Jev 调用")
    key = os.environ.get("TYPESAFE_API_KEY") or getpass("Jev API key（不回显）：")
    adapter = JevDecisionAdapter(api_key=key, method="choice-v2")
    output.mkdir(parents=True)
    (output / "preflight.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    spent = 0.0
    with (output / "calls.jsonl").open("x") as stream:
        for row in rows:
            if spent + PER_CALL_USD_UPPER > maximum:
                raise ValueError("剩余额度不足以保护下一次 Jev 调用")
            try:
                result = (adapter.decide_advisor(row["request"])
                          if row["kind"] == "advisor" else
                          adapter.decide_escalation(row["request"]))
                if result.model != JEV_MODEL or type(result.usage.get("input_tokens")) is not int:
                    raise ValueError("Jev 模型或用量未确认")
            except Exception as exc:
                stream.write(json.dumps({"id": row["id"], "status": "unconfirmed",
                    "errorType": type(exc).__name__, "reservedUsd": PER_CALL_USD_UPPER},
                    ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
                raise
            cost = result.usage["input_tokens"] * JEV_INPUT_USD_PER_MILLION / 1_000_000
            spent += cost
            receipt = {"id": row["id"], "kind": row["kind"], "expected": row["expected"],
                "arkVerdict": row["arkVerdict"], "jevVerdict": result.payload["verdict"],
                "jevRawVerdict": result.payload["rawVerdict"],
                "selectionProbability": result.payload["confidence"],
                "raw": result.payload.get("raw"), "model": result.model,
                "usage": result.usage, "latencyMs": result.latency_ms,
                "estimatedCostUsd": cost, "recordedAt": datetime.now(timezone.utc).isoformat()}
            stream.write(json.dumps(receipt, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {"completed": len(rows), "matched": sum(
        json.loads(line)["jevVerdict"] == json.loads(line)["expected"]
        for line in (output / "calls.jsonl").read_text().splitlines()),
        "estimatedCostUsd": spent, "output": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-usd", type=float, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rows, fingerprints = load()
    frozen = preflight(rows, fingerprints)
    if not args.run:
        print(json.dumps({"realCalls": 0, **frozen}, ensure_ascii=False, indent=2))
    else:
        if not args.output:
            parser.error("真实调用需要 --output")
        print(json.dumps(run(rows, frozen, output=args.output,
                             maximum=args.max_usd), ensure_ascii=False))


if __name__ == "__main__":
    main()
