"""Composite 规则＋本地 Laya 的零 API 费用接线验收。"""
import argparse
import json
from pathlib import Path
import tempfile
import time

from refractrouter.planning_runtime import PlanningRuntime


def config(model_path):
    model = {"provider": "fixture", "contextWindow": 32000, "maxOutputTokens": 1024,
        "inputPer1k": 0, "outputPer1k": 0, "billingUnit": "CNY", "deployment": "local",
        "reasoningEffort": "low", "capabilities": {"mainExecutor": True,
            "toolCalling": "verified", "modalities": {}}}
    judge = {"type": "local-decision", "adapter": "laya-mlx", "modelPath": str(model_path),
        "sourceModel": "aac6fef/laya-multilingual-mlx",
        "revision": "f2b4faf51023039425946074e2cf1361d2db11d5",
        "device": "gpu", "dtype": "float16"}
    return {"schemaVersion": "refractagent-planning-v6", "enabled": True,
        "defaultStrategy": "composite", "billingUnit": "CNY",
        "maxProductionCostByUnit": {"CNY": 0}, "timeoutMs": 120000, "maxCalls": 8,
        "models": [{"id": "small", "model": "small", "capabilityCard": "适合常规工具任务", **model},
            {"id": "large", "model": "large", "capabilityCard": "适合复杂推理和困难接管", **model},
            {"id": "judge", "model": "judge", "capabilityCard": "", **model,
             "capabilities": {"mainExecutor": False, "toolCalling": "unknown", "modalities": {}}}],
        "roles": {"efficient": "small", "capable": "large", "classifier": "judge"},
        "composite": {"pool": ["small", "large"], "takeover": "large",
            "judge": {"type": "llm", "modelId": "judge"}, "threshold": .8,
            "maxInputChars": 12000, "maxExecutionOutputTokens": 1024,
            "stage": {"mode": "hybrid", "allowExperimental": True, "judge": judge,
                "window": 3, "interval": 2, "maxJudgements": 4, "holdTurns": 2,
                "downgradeConfirmations": 2, "upgradeThreshold": .8,
                "downgradeThreshold": .9, "judgeTimeoutMs": 30000,
                "maxJudgeInputBytes": 65536}}}


def receipt(runtime, run_id, action, content="完成"):
    return runtime.handle({"op": "complete", "runId": run_id, "callId": action["callId"],
        "response": {"content": content, "inputTokens": 100, "outputTokens": 20,
            "finishReason": "stop", "usageAvailable": True, "latencyMs": 1}})


def run_case(runtime, cfg, name, status):
    begun = runtime.handle({"op": "begin", "identity": {"session": name, "agent": "fixture", "turn": 1},
        "strategy": "composite", "config": cfg})
    run_id = begun["runId"]
    messages = [{"role": "user", "content": "检查项目并完成任务"}]
    action = runtime.handle({"op": "step", "runId": run_id, "messages": messages, "tools": []})
    action = receipt(runtime, run_id, action, json.dumps({"answers": {"candidates": {
        "small": {"score": .95, "missingInformation": 0},
        "large": {"score": .2, "missingInformation": 0}}}}))
    receipt(runtime, run_id, action)
    evidence = [{"id": name + "-event", "callId": name + "-event", "tool": "read",
        "kind": "observe", "status": status, "fingerprint": name + "-fingerprint"}]
    action = runtime.handle({"op": "step", "runId": run_id, "messages": messages,
                             "tools": [], "toolEvidence": evidence})
    if action["action"] != "wait":
        raise RuntimeError("Composite 本地 Stage 未进入异步 Judge")
    started = time.monotonic()
    while action["action"] == "wait":
        time.sleep(action.get("pollAfterMs", 25) / 1000)
        action = runtime.handle({"op": "local-judge-poll", "runId": run_id,
                                 "jobId": action["jobId"]})
    elapsed = (time.monotonic() - started) * 1000
    receipt(runtime, run_id, action)
    run = runtime.runs[run_id]
    row = run["decisions"][-1]
    return {"case": name, "inputEvidence": status, "selectedModel": action["model"]["id"],
        "reason": row["reason"], "decision": row.get("decision"), "elapsedMs": elapsed,
        "localForwards": row.get("decision", {}).get("usage", {}).get("forwards"),
        "paidApiCalls": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cfg = config(args.model_path.expanduser().resolve())
    with tempfile.TemporaryDirectory(prefix="refract-composite-local-") as directory:
        runtime = PlanningRuntime(directory)
        try:
            loaded = runtime.handle({"op": "local-judge", "config": cfg, "action": "load",
                                     "target": "composite-stage"})
            if not loaded.get("loaded"):
                raise RuntimeError("本地 Laya 未加载")
            cases = [run_case(runtime, cfg, "normal-progress", "completed"),
                     run_case(runtime, cfg, "single-failure", "failed")]
        finally:
            runtime.local_service.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {"schemaVersion": "composite-local-acceptance-v1", "cases": cases,
              "allValid": all(case["localForwards"] for case in cases), "paidApiCalls": 0}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
