"""Task 产品接线验收：默认零调用预检；派发仅限一次冻结的原生工具任务。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from refractrouter.ark_plan import catalog
from refractrouter.planning_config import preview
from refractrouter.stage_study import _invoke_dsh, _metrics, _new_record

from .preflight_task_quality_pilot import ROOT, digest
from .run_task_quality_pilot import _config


SOURCE_PROTOCOL = ROOT / "data/benchmarks/task-quality-pilot-v3.json"
PRIOR_WORST_AFP = 133.86975
PROMPT = "只使用终端工具执行 pwd，然后报告工具实际返回的绝对路径。不要访问网络或修改文件。"


def plan():
    original = json.loads(SOURCE_PROTOCOL.read_text())
    protocol = deepcopy(original)
    protocol["limits"].update(maxCallsPerRun=3, maxRequestBytesPerCall=80000,
                              maxOutputTokensPerCall=2048, timeoutMsPerRun=300000)
    cards = {"deepseek-v4-flash": "文本和终端工具已接通；短指令任务质量待验收",
             "deepseek-v4.1-flash": "文本和终端工具已接通；短指令任务质量待验收"}
    rows = {row["model_id"]: row for row in catalog()["models"]}
    limits = protocol["limits"]
    bounds = {}
    for model_id in cards:
        row = rows[model_id]
        price = row["pricing"]
        if price["unit"] != "afp-per-10000-tokens":
            raise ValueError("实际路线缺少 AFP 定价")
        input_bound = limits["maxRequestBytesPerCall"] + 256
        if input_bound + limits["maxOutputTokensPerCall"] > row["context_window_tokens"]:
            raise ValueError("冻结调用上界超过模型上下文")
        bounds[model_id] = (input_bound * price["input_coefficient"]
                            + limits["maxOutputTokensPerCall"] * price["output_coefficient"]) / 10000
    maximum = round(3 * max(bounds.values()), 6)
    config = _config(protocol, "task-choice-v2", cards, maximum)
    config["task"]["judge"] = {"type": "llm", "modelId": "efficient"}
    config["task"]["threshold"] = .8
    available = next(row for row in preview(config)["strategies"] if row["id"] == "task")
    if not available["available"]:
        raise ValueError("Task 零调用诊断失败：" + "；".join(available["issues"]))
    frozen = {"schemaVersion": "task-product-acceptance-v1", "status": "zero-call-preflight",
              "prompt": PROMPT, "configDigest": digest(config),
              "pricingSnapshot": catalog()["snapshot_date"],
              "models": [{"id": item["id"], "provider": item["provider"],
                          "model": item["model"], "reasoningEffort": item["reasoningEffort"]}
                         for item in config["models"]],
              "judge": "ark/deepseek-v4-flash", "maximumModelCalls": 3,
              "maximumProductionAfp": maximum, "priorAfpWorstCase": PRIOR_WORST_AFP,
              "maximumIncludingPriorAfp": round(PRIOR_WORST_AFP + maximum, 6),
              "zeroHttpRetries": True, "delegation": False,
              "note": "首次执行调用真实选择前，不把多个互斥候选相加；整轮授权上界按最贵路线计算。"}
    return config, {**frozen, "preflightDigest": digest(frozen)}


def patch(config):
    limits = {"maxOutputTokensPerCall": config["task"]["maxExecutionOutputTokens"]}
    entries = [
        ("agent-default-model", {"provider": "refractagent", "model": "planning",
                                 "reasoningEffort": "rr:task"}, False),
        ("settings", {"path": ".refractagent/settings.yaml", "watch": False}, False),
        ("llm-pi-ai", {"providers": {"ark": {"apiKeyEnv": "ARK_API_KEY",
            "api": "openai-responses", "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "retryPolicy": {"mode": "normal", "maxRetries": 0},
            "models": [{"id": item["model"], "name": item["model"],
                        "contextWindow": item["contextWindow"],
                        "maxTokens": limits["maxOutputTokensPerCall"],
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    args = parser.parse_args()
    config, preflight = plan()
    output = args.output.resolve()
    if not args.execute_paid_run:
        if output.exists():
            raise ValueError("验收目录已存在，不覆盖历史证据")
        output.mkdir(parents=True)
        workspace = output / "workspace"
        workspace.mkdir()
        (workspace / ".refractagent").mkdir()
        (workspace / ".refractagent/settings.yaml").write_text("{}\n")
        (output / "patch.yml").write_text(patch(config))
        (output / "preflight.json").write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return
    if (not (output / "preflight.json").exists()
            or json.loads((output / "preflight.json").read_text()) != preflight
            or args.approved_digest != preflight["preflightDigest"]
            or args.approved_afp < preflight["maximumIncludingPriorAfp"]):
        raise ValueError("预检摘要、上界或累计授权不一致，拒绝真实派发")
    if any((output / name).exists() for name in ("dispatch.started", "result.json", "stdout.log")):
        raise ValueError("已有派发证据，不自动重发")
    workspace = output / "workspace"
    run_root = workspace / ".refractagent/runs"
    before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
    (output / "dispatch.started").write_text(preflight["preflightDigest"] + "\n")
    outcome, elapsed = _invoke_dsh("headless", output / "patch.yml", workspace, PROMPT, 300000)
    (output / "stdout.log").write_text(outcome.stdout or "")
    (output / "stderr.log").write_text(outcome.stderr or "")
    record = _new_record(run_root, before)
    metrics = _metrics(record, capable_model="deepseek-v4.1-flash",
                       efficient_model="deepseek-v4-flash")
    if metrics["productionAfp"] > preflight["maximumProductionAfp"] + 1e-6:
        raise RuntimeError("实际 AFP 超过冻结上界")
    result = {"exitCode": outcome.returncode, "elapsedMs": elapsed,
              "metrics": metrics, "runId": record["runId"],
              "judgeDecision": record.get("state", {}).get("judge_decision"),
              "toolEvidence": record.get("decisions", [])}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
