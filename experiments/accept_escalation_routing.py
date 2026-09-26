"""Escalation DSH 正常工具接线验收；默认只生成零调用预检。"""

import argparse
import hashlib
import json
import math
from pathlib import Path

from refractrouter.ark_plan import catalog
from refractrouter.planning_config import compile_config, preview
from refractrouter.stage_study import _invoke_dsh, _new_record


ROOT = Path(__file__).resolve().parents[1]
PROMPT = "只使用终端工具执行 pwd，然后只报告工具实际返回的绝对路径。不要访问网络或修改文件。"
PRIOR_AFP_WORST_CASE = 135.52625


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _model(model_id, identity, effort):
    row = next(item for item in catalog()["models"] if item["model_id"] == model_id)
    price = row["pricing"]
    return {"id": identity, "provider": "ark", "model": model_id,
            "contextWindow": row["context_window_tokens"], "maxOutputTokens": 2048,
            "inputPer1k": price["input_coefficient"] / 10,
            "outputPer1k": price["output_coefficient"] / 10,
            "cachedInputPer1k": price["input_coefficient"] / 10,
            "billingUnit": "AFP", "reasoningEffort": effort,
            "deployment": "trusted-cloud", "trustPolicy": "escalation-ark",
            "capabilities": {"mainExecutor": True, "toolCalling": "verified",
                             "modalities": {}},
            "capabilityCard": "文本与 DSH 原生工具接口已接通。"}


def configuration():
    config = {"schemaVersion": "refractagent-planning-v4", "enabled": True,
        "defaultStrategy": "escalation", "billingUnit": "AFP",
        "maxProductionCostByUnit": {"AFP": 80}, "timeoutMs": 300000, "maxCalls": 6,
        "models": [_model("deepseek-v4-flash", "initial", "low"),
                   _model("deepseek-v4.1-flash", "takeover", "high")],
        "roles": {"efficient": "initial", "capable": "takeover", "classifier": "initial"},
        "parameters": {},
        "escalation": {"initial": "initial", "takeover": "takeover",
                       "judge": {"type": "llm", "modelId": "initial"},
                       "stallConfirmations": 2, "threshold": .8,
                       "judgeTimeoutMs": 30000, "maxJudgeInputBytes": 65536,
                       "maxExecutionOutputTokens": 2048, "maxJudgeOutputTokens": 1024},
        "trustPolicies": [{"id": "escalation-ark", "residency": "CN",
                           "auditLogging": True, "allowsSensitiveData": True}],
        "compatiblePairs": [["initial", "takeover"], ["takeover", "initial"]],
        "security": {"maxPromptBytes": 80000}}
    compile_config(config)
    row = next(item for item in preview(config)["strategies"] if item["id"] == "escalation")
    if not row["available"]:
        raise ValueError("Escalation 零调用诊断失败：" + "；".join(row["issues"]))
    return config


def patch(config):
    entries = [
        ("agent-default-model", {"provider": "refractagent", "model": "planning",
                                 "reasoningEffort": "rr:escalation"}, False),
        ("settings", {"path": ".refractagent/settings.yaml", "watch": False}, False),
        ("llm-pi-ai", {"providers": {"ark": {"apiKeyEnv": "CODEX_ARK_API_KEY",
            "api": "openai-responses", "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "retryPolicy": {"mode": "normal", "maxRetries": 0},
            "models": [{"id": item["model"], "name": item["model"],
                        "contextWindow": item["contextWindow"], "maxTokens": 2048,
                        "reasoningEfforts": {"low": "low", "high": "high", "max": "max"}}
                       for item in config["models"]]}}}, False),
        ("refractagent", {"pythonExecutable": str(ROOT / ".venv/bin/refractagent"),
                          "runsDir": ".refractagent/runs", "planningRouting": config}, False),
        *((name, None, True) for name in ("tool-subagent-control", "tool-subagent-list-agents",
            "tool-subagent", "tool-subagent-fork", "tool-ralph")),
    ]
    return "\n".join("- id: " + name + ("\n  disabled: true" if disabled else
        "\n  config: " + json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        for name, value, disabled in entries) + "\n"


def plan():
    config = configuration()
    # 两轮工具循环各含一次起始执行与一次 Judge；按 80 KiB 输入包络计算。
    input_bound = 80256
    price = .05
    per_call = input_bound / 1000 * price + 2048 / 1000 * price
    upper = round(per_call * 4, 6)
    frozen = {"schemaVersion": "escalation-dsh-acceptance-v1", "realModelCalls": 0,
              "prompt": PROMPT, "configDigest": digest(config),
              "profile": "headless", "models": {"initial": "deepseek-v4-flash",
                  "judge": "deepseek-v4-flash", "takeover": "deepseek-v4.1-flash"},
              "maximumModelCalls": 6, "expectedCalls": 4,
              "maximumProductionAfp": upper,
              "priorAfpWorstCase": PRIOR_AFP_WORST_CASE,
              "maximumIncludingPriorAfp": round(PRIOR_AFP_WORST_CASE + upper, 6),
              "authorizedCumulativeAfp": 2000, "httpRetries": 0, "delegation": False,
              "acceptance": ["宿主执行一次原生 pwd 工具", "两个高效候选均由 Judge 放行",
                             "不创建 DAG", "真实来源、用量和 AFP 可核对"]}
    return config, {**frozen, "preflightDigest": digest(frozen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    parser.add_argument("--profile", default="headless")
    args = parser.parse_args()
    output = args.output.resolve()
    config, preflight = plan()
    if not args.execute_paid_run:
        if output.exists():
            raise ValueError("验收目录已存在，拒绝覆盖")
        workspace = output / "workspace"
        (workspace / ".refractagent").mkdir(parents=True)
        (workspace / ".refractagent/settings.yaml").write_text("{}\n")
        (output / "patch.yml").write_text(patch(config))
        (output / "preflight.json").write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return
    if (json.loads((output / "preflight.json").read_text()) != preflight
            or args.approved_digest != preflight["preflightDigest"]
            or not math.isfinite(args.approved_afp)
            or args.approved_afp < preflight["maximumIncludingPriorAfp"]):
        raise ValueError("预检摘要或累计 AFP 授权不一致")
    if any((output / name).exists() for name in ("dispatch.started", "result.json", "stdout.log")):
        raise ValueError("已有派发证据，拒绝覆盖或自动重发")
    run_root = output / "workspace/.refractagent/runs"
    before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
    (output / "dispatch.started").write_text(preflight["preflightDigest"] + "\n")
    outcome, elapsed = _invoke_dsh(args.profile, output / "patch.yml", output / "workspace",
                                   PROMPT, 300000)
    (output / "stdout.log").write_text(outcome.stdout or "")
    (output / "stderr.log").write_text(outcome.stderr or "")
    record = _new_record(run_root, before)
    calls = [row for row in record["calls"] if row.get("status") != "local-inference"]
    charged = round(sum(row.get("charged", 0) for row in calls), 8)
    if charged > preflight["maximumProductionAfp"] + 1e-6:
        raise RuntimeError("实际 AFP 超过冻结上界")
    reasons = [row.get("reason") for row in record.get("decisions", [])]
    result = {"exitCode": outcome.returncode, "elapsedMs": elapsed,
              "runId": record["runId"], "status": record["status"],
              "modelCalls": len(calls), "productionAfp": charged,
              "toolEvents": len(record.get("state", {}).get("consumedEvidenceIds", [])),
              "decisionReasons": reasons,
              "acceptedCalls": sum(row.get("disposition") == "accepted" for row in calls),
              "discardedCalls": sum(row.get("disposition") == "discarded" for row in calls)}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
