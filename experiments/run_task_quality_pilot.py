"""Task 小样本：默认只预检；付费执行要求冻结摘要和 AFP 上限。"""

import argparse
import json
import math
from pathlib import Path

from refractrouter.ark_plan import catalog
from refractrouter.planning_config import compile_config, preview
from refractrouter.stage_study import (_invoke_dsh, _metrics, _new_record,
                                       evaluate_code, evaluate_research)

from .preflight_task_quality_pilot import PROTOCOL, ROOT, preflight


MODEL_IDS = {"static-flash": "deepseek-v4-flash",
             "static-v4.1-flash": "deepseek-v4.1-flash"}


def _task_sources(protocol):
    return json.loads((ROOT / protocol["taskSource"]).read_text())


def _cards(calibration_rows):
    """只编码冻结任务的实际通过状态；相同证据让本地 Judge 安全备用。"""
    outcomes = {}
    for row in calibration_rows:
        if row["split"] != "calibration":
            continue
        if row.get("exitCode") != 0 or row.get("metrics", {}).get("modelCalls", 0) < 1:
            raise ValueError("校准任务未完整运行，不得写入模型质量证据")
        outcomes[(row["family"], row["arm"])] = row["evaluation"]["success"]
    if set(outcomes) != {(family, arm) for family in ("code", "research") for arm in MODEL_IDS}:
        raise ValueError("两条路线的代码与研究校准记录不完整")
    result = {}
    for arm, model in MODEL_IDS.items():
        summary = "；".join(f"{family}校准：{'通过' if outcomes[(family, arm)] else '未通过'}"
                           for family in ("code", "research"))
        result[model] = "文本和工具已接通；" + summary
    return result


def _config(protocol, arm, cards, cost_limit):
    limits = protocol["limits"]
    catalog_rows = {row["model_id"]: row for row in catalog()["models"]}
    models = []
    for role, model_id in (("efficient", MODEL_IDS["static-flash"]),
                           ("capable", MODEL_IDS["static-v4.1-flash"])):
        row = catalog_rows[model_id]
        price = row["pricing"]
        models.append({"id": role, "provider": "ark", "model": model_id,
                       "contextWindow": row["context_window_tokens"],
                       "maxOutputTokens": limits["maxOutputTokensPerCall"],
                       "inputPer1k": price["input_coefficient"] / 10,
                       "outputPer1k": price["output_coefficient"] / 10,
                       "cachedInputPer1k": price["input_coefficient"] / 10,
                       "billingUnit": "AFP", "reasoningEffort":
                       protocol["models"]["static-flash" if role == "efficient"
                                           else "static-v4.1-flash"]["reasoningEffort"],
                       "deployment": "trusted-cloud", "trustPolicy": "task-pilot-ark",
                       "capabilityCard": cards.get(model_id, "文本和工具已接通；任务质量待验收。"),
                       "capabilities": {"mainExecutor": True, "toolCalling": "connected",
                                        "modalities": {}}})
    task = protocol["models"]["task-choice-v2"]
    config = {"schemaVersion": "refractagent-planning-v3", "enabled": True,
              "defaultStrategy": "task" if arm == "task-choice-v2" else "static",
              "billingUnit": "AFP", "maxProductionCostByUnit": {"AFP": cost_limit},
              "timeoutMs": limits["timeoutMsPerRun"], "maxCalls": limits["maxCallsPerRun"],
              "models": models, "roles": {"efficient": "capable" if arm == "static-v4.1-flash"
                                          else "efficient", "capable": "capable"},
              "parameters": {"staticMode": "fixed"},
              "task": {"pool": ["efficient", "capable"], "fallback": "capable",
                       "threshold": task["threshold"], "maxInputChars": 12000,
                       "maxExecutionOutputTokens": limits["maxOutputTokensPerCall"],
                       "judge": {"type": "local-decision", "adapter": "laya-mlx",
                                 "modelPath": str(Path.home() / ".cache/refractrouter/models/laya-multilingual-mlx-f2b4faf5"),
                                 "sourceModel": task["judge"].split("@")[0],
                                 "revision": task["judge"].split("@")[1],
                                 "device": "gpu", "dtype": "float16", "method": task["method"]}},
              "trustPolicies": [{"id": "task-pilot-ark", "residency": "CN",
                                 "auditLogging": True, "allowsSensitiveData": True}],
              "compatiblePairs": [["efficient", "capable"], ["capable", "efficient"]],
              "security": {"maxPromptBytes": limits["maxRequestBytesPerCall"]}}
    compile_config(config)
    strategy = config["defaultStrategy"]
    available = next(item for item in preview(config)["strategies"] if item["id"] == strategy)
    if not available["available"]:
        raise ValueError("运行配置不可用：" + "；".join(available["issues"]))
    return config


def _patch(protocol, arm, cards, cost_limit):
    config = _config(protocol, arm, cards, cost_limit)
    limits = protocol["limits"]
    entries = [
        ("agent-default-model", {"provider": "refractagent", "model": "planning",
                                 "reasoningEffort": "rr:task" if arm == "task-choice-v2" else "rr:static"}, False),
        ("settings", {"path": ".refractagent/settings.yaml", "watch": False}, False),
        ("llm-pi-ai", {"providers": {"ark": {"apiKeyEnv": "ARK_API_KEY",
            "api": "openai-responses", "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "retryPolicy": {"mode": "normal", "maxRetries": limits["httpRetries"]},
            "models": [{"id": row["model"], "name": row["model"],
                        "contextWindow": row["contextWindow"],
                        "maxTokens": limits["maxOutputTokensPerCall"],
                        "reasoningEfforts": {"low": "low", "high": "high", "max": "max"}}
                       for row in config["models"]]}}}, False),
        ("refractagent", {"pythonExecutable": str(ROOT / ".venv/bin/refractagent"),
                          "runsDir": ".refractagent/runs", "planningRouting": config}, False),
        *( (name, None, True) for name in ("tool-subagent-control", "tool-subagent-list-agents",
            "tool-subagent", "tool-subagent-fork", "tool-ralph")),
    ]
    return "\n".join("- id: " + name + ("\n  disabled: true" if disabled else
        "\n  config: " + json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        for name, value, disabled in entries) + "\n"


def prepare(protocol, tasks, output):
    if output.exists():
        raise ValueError("输出目录已存在，拒绝覆盖历史批次")
    evidence = preflight(protocol, tasks, catalog())
    output.mkdir(parents=True)
    (output / "preflight.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    by_id = {item["id"]: item for item in tasks["tasks"]}
    for index, row in enumerate(evidence["runs"]):
        task = by_id[row["taskId"]]
        workspace = output / "workspaces" / f"{index:02d}-{row['taskId']}-{row['arm']}"
        workspace.mkdir(parents=True)
        settings = workspace / ".refractagent/settings.yaml"
        settings.parent.mkdir()
        settings.write_text("{}\n")
        payload = task["files"] if task["family"] == "code" else task["sources"]
        for name, content in payload.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("冻结任务文件路径越界")
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (workspace / "TASK.md").write_text(task["prompt"] + "\n")
    return evidence


def execute(protocol, tasks, output, approved_digest, approved_afp, *, profile="headless"):
    evidence = json.loads((output / "preflight.json").read_text())
    current = preflight(protocol, tasks, catalog())
    if evidence != current or approved_digest != current["preflightDigest"]:
        raise ValueError("协议或预检摘要不匹配，拒绝付费运行")
    if not math.isfinite(approved_afp) or approved_afp < current["maximumIncludingPriorAfp"]:
        raise ValueError("授权 AFP 上限低于本批次加历史已结算费用的冻结上界")
    records_path = output / "run-records.jsonl"
    if records_path.exists():
        raise ValueError("已有付费证据，拒绝自动重发或覆盖")
    by_id = {item["id"]: item for item in tasks["tasks"]}
    results = []
    for index, row in enumerate(current["runs"]):
        task = by_id[row["taskId"]]
        workspace = output / "workspaces" / f"{index:02d}-{row['taskId']}-{row['arm']}"
        cards = _cards(results) if row["arm"] == "task-choice-v2" else {}
        patch = output / f"{index:02d}.patch.yml"
        patch.write_text(_patch(protocol, row["arm"], cards, row["costUpperAfp"]))
        run_root = workspace / ".refractagent/runs"
        before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
        prompt = ("这是冻结的 Task 路由小样本验收；禁止委派，研究任务禁止访问网络。"
                  "只使用当前工作区材料，完成 TASK.md，并简述结果。\n\n" + task["prompt"])
        outcome, elapsed = _invoke_dsh(profile, patch, workspace, prompt,
                                       protocol["limits"]["timeoutMsPerRun"])
        (output / f"{index:02d}-stdout.log").write_text(outcome.stdout or "")
        (output / f"{index:02d}-stderr.log").write_text(outcome.stderr or "")
        record = _new_record(run_root, before)
        metrics = _metrics(record, capable_model=MODEL_IDS["static-v4.1-flash"],
                           efficient_model=MODEL_IDS["static-flash"])
        if not metrics["modelCalls"] and outcome.returncode != 0:
            raise RuntimeError("DSH 在模型调用前失败，停止批次检查宿主配置")
        if metrics["productionAfp"] > row["costUpperAfp"] + 1e-6:
            raise RuntimeError("实际 AFP 超过冻结上界，停止批次")
        evaluation = (evaluate_code(task["id"], workspace) if task["family"] == "code"
                      else evaluate_research(task, workspace))
        result = {**row, "family": task["family"], "exitCode": outcome.returncode,
                  "elapsedMs": elapsed, "metrics": metrics, "evaluation": evaluation,
                  "runId": record["runId"], "judgeDecision": record.get("state", {}).get("judge_decision")}
        with records_path.open("a") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    parser.add_argument("--profile", default="headless")
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text())
    tasks = _task_sources(protocol)
    if not args.execute_paid_run:
        print(json.dumps(prepare(protocol, tasks, args.output), ensure_ascii=False, indent=2))
        return
    if not args.approved_digest:
        raise ValueError("付费运行需要冻结预检摘要")
    result = execute(protocol, tasks, args.output, args.approved_digest, args.approved_afp,
                     profile=args.profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
