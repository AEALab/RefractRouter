"""Stage 日常使用验收：冻结两个真实任务、DSH 配置与 AFP 调用包络。"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .ark_plan import catalog
from .planning_policy import STAGE_RULE_VERSION
from .stage_study import (_invoke_dsh, _metrics, _new_record, canonical_digest,
                          evaluate_code, evaluate_research)


SCHEMA = "stage-daily-acceptance-v1"
TASK_IDS = ("code-tdd-slug", "research-compare-search")
MAX_CALLS_PER_TASK = 8
TIMEOUT_MS = 300000
MAX_INPUT_TOKENS = 32768
MAX_OUTPUT_TOKENS = 4096
EFFICIENT_MODEL = "deepseek-v4-flash"
CAPABLE_MODEL = "deepseek-v4.1-flash"
EFFICIENT_REASONING_EFFORT = "low"

COMMON_GUIDANCE = (
    "不要读取或修改 .refractagent；它只包含运行时元数据，不属于任务材料。"
    "在安全且相互独立时批量读取文件，并在完成文件修改后运行必要检查。"
)
CODE_GUIDANCE = (
    "Unicode 规范化必须保留拉丁重音字符；例如分解形式 Cafe\\u0301 应输出 café，"
    "不能删除组合标记得到 cafe。"
)
RESEARCH_GUIDANCE = (
    "引用格式说明：TASK.md 中的 [S1] 是格式示例；事实必须引用实际来源编号，"
    "即分别使用 [S1]、[S2] 或 [S3]，不得把其他来源标成 [S1]。"
)


def _model(model_id: str) -> dict:
    row = next((item for item in catalog()["models"] if item["model_id"] == model_id), None)
    if row is None:
        raise ValueError(f"Ark 目录缺少模型：{model_id}")
    pricing = row.get("pricing", {})
    if pricing.get("unit") != "afp-per-10000-tokens":
        raise ValueError(f"{model_id} 缺少可核对的 AFP 价格")
    model = {
        "id": "efficient" if model_id == EFFICIENT_MODEL else "capable",
        "provider": "ark",
        "model": model_id,
        "contextWindow": row["context_window_tokens"],
        "maxOutputTokens": MAX_OUTPUT_TOKENS,
        "inputPer1k": pricing["input_coefficient"] / 10,
        "outputPer1k": pricing["output_coefficient"] / 10,
        "cachedInputPer1k": pricing["input_coefficient"] / 10,
        "billingUnit": "AFP",
        "deployment": "trusted-cloud",
        "trustPolicy": "ark-stage-daily",
    }
    if model_id == EFFICIENT_MODEL:
        model["reasoningEffort"] = EFFICIENT_REASONING_EFFORT
    return model


def _call_upper(model: dict) -> float:
    return ((MAX_INPUT_TOKENS / 1000) * model["inputPer1k"]
            + (MAX_OUTPUT_TOKENS / 1000) * model["outputPer1k"])


def planning_config() -> dict:
    efficient, capable = _model(EFFICIENT_MODEL), _model(CAPABLE_MODEL)
    # Stage 首轮必用高效角色；后续既可能继续高效，也可能升级到强角色。
    # 因此首轮按 efficient 覆盖，其余轮次按两条路线中较贵者覆盖。
    per_task = (_call_upper(efficient)
                + (MAX_CALLS_PER_TASK - 1)
                * max(_call_upper(efficient), _call_upper(capable)))
    return {
        "schemaVersion": "refractagent-planning-v2",
        "enabled": True,
        "defaultStrategy": "stage",
        "maxProductionCostByUnit": {"AFP": round(per_task, 6)},
        "timeoutMs": TIMEOUT_MS,
        "maxCalls": MAX_CALLS_PER_TASK,
        "models": [efficient, capable],
        "roles": {"efficient": "efficient", "capable": "capable"},
        "parameters": {"window": 3, "threshold": 0.5, "holdTurns": 2},
        "trustPolicies": [{"id": "ark-stage-daily", "residency": "CN",
                           "auditLogging": True, "allowsSensitiveData": True}],
        "compatiblePairs": [["efficient", "capable"], ["capable", "efficient"]],
        # 与冻结输入 token 上限使用同一保守 4 bytes/token 包络，避免预算
        # 预检声称 32K 输入、实际却允许更大的请求进入派发。
        "security": {"maxPromptBytes": 4 * MAX_INPUT_TOKENS},
    }


def render_patch(runs_dir: str = ".refractagent/runs") -> str:
    config = planning_config()
    provider = {
        "apiKeyEnv": "ARK_API_KEY",
        "api": "openai-responses",
        "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "retryPolicy": {"mode": "normal", "maxRetries": 0},
        "models": [{"id": row["model"], "name": row["model"],
                    "contextWindow": row["contextWindow"],
                    "maxTokens": row["maxOutputTokens"],
                    **({"reasoningEfforts": {"low": "low", "high": "high", "max": "max"}}
                       if row["model"] == EFFICIENT_MODEL else {})}
                   for row in config["models"]],
    }
    entries = [
        ("agent-default-model", {"provider": "refractagent", "model": "planning"}, False),
        ("settings", {"path": ".refractagent/settings.yaml", "watch": False}, False),
        ("llm-pi-ai", {"providers": {"ark": provider}}, False),
        ("refractagent", {"pythonExecutable": "refractagent", "runsDir": runs_dir,
                          "planningRouting": config}, False),
        ("tool-subagent-control", None, True),
        ("tool-subagent-list-agents", None, True),
        ("tool-subagent", None, True),
        ("tool-subagent-fork", None, True),
        ("tool-ralph", None, True),
    ]
    lines = []
    for plugin_id, value, disabled in entries:
        lines.append(f"- id: {plugin_id}")
        if disabled:
            lines.append("  disabled: true")
        else:
            lines.append("  config: " + json.dumps(value, ensure_ascii=False,
                                                       separators=(",", ":")))
    return "\n".join(lines) + "\n"


def _selected_tasks(protocol: dict, task_ids=TASK_IDS) -> list[dict]:
    by_id = {task["id"]: task for task in protocol["tasks"]}
    task_ids = tuple(task_ids)
    if not task_ids or len(set(task_ids)) != len(task_ids):
        raise ValueError("日常验收任务必须非空且唯一")
    if any(task_id not in by_id for task_id in task_ids):
        raise ValueError("Stage 协议缺少日常验收任务")
    return [deepcopy(by_id[task_id]) for task_id in task_ids]


def task_prompt(task: dict) -> str:
    guidance = COMMON_GUIDANCE
    if task["family"] == "code":
        guidance += CODE_GUIDANCE
    elif task["family"] == "research":
        guidance += RESEARCH_GUIDANCE
    return task["prompt"] + "\n\n日常验收补充说明：" + guidance


def preflight(protocol: dict, task_ids=TASK_IDS) -> dict:
    tasks = _selected_tasks(protocol, task_ids)
    config = planning_config()
    per_task = config["maxProductionCostByUnit"]["AFP"]
    frozen = {
        "schemaVersion": SCHEMA,
        "strategy": "stage",
        "stageRuleVersion": STAGE_RULE_VERSION,
        "profile": "headless",
        "tasks": [{"id": task["id"], "family": task["family"],
                   "sha256": canonical_digest({"task": task,
                                                "dailyPrompt": task_prompt(task)})}
                  for task in tasks],
        "models": {"efficient": {"id": EFFICIENT_MODEL,
                                  "reasoningEffort": EFFICIENT_REASONING_EFFORT},
                   "capable": {"id": CAPABLE_MODEL,
                               "reasoningEffort": "provider-default"}},
        "limits": {"maxCallsPerTask": MAX_CALLS_PER_TASK,
                   "timeoutMsPerTask": TIMEOUT_MS,
                   "maxInputTokensPerCall": MAX_INPUT_TOKENS,
                   "maxOutputTokensPerCall": MAX_OUTPUT_TOKENS,
                   "maxProductionAfpPerTask": per_task,
                   "maxProductionAfpTotal": round(per_task * len(tasks), 6)},
        "evaluationAfp": 0,
        "httpRetries": 0,
        "delegation": False,
        "patchSha256": hashlib.sha256(render_patch().encode()).hexdigest(),
        "notes": [
            "代码任务由确定性隐藏检查验收，研究任务只做确定性引用与关键事实检查。",
            "本批次验证日常可用性，不比较 Static，也不用于证明 Stage 的收益。",
            "AFP 上限按首轮高效模型、其余轮次中较贵的路线和冻结 token 上限计算。",
            "Stage 不调用 classifier；当前判断模型的价格不进入本批次账本。",
            "日常提示忽略 .refractagent 运行元数据，并澄清研究引用须对应实际来源。",
            "代码规格明确要求 Unicode 规范化保留拉丁重音字符。",
        ],
    }
    return {**frozen, "acceptanceSha256": canonical_digest(frozen)}


def prepare(protocol: dict, output_dir: Path, task_ids=TASK_IDS) -> Path:
    output = Path(output_dir)
    if output.exists():
        raise ValueError("验收输出目录已存在，拒绝覆盖")
    output.mkdir(parents=True)
    (output / "preflight.json").write_text(
        json.dumps(preflight(protocol, task_ids), ensure_ascii=False, indent=2) + "\n")
    (output / "stage.patch.yml").write_text(render_patch())
    for task in _selected_tasks(protocol, task_ids):
        workspace = output / "workspaces" / task["id"]
        workspace.mkdir(parents=True)
        settings = workspace / ".refractagent" / "settings.yaml"
        settings.parent.mkdir()
        settings.write_text("{}\n")
        payload = task["files"] if task["family"] == "code" else task["sources"]
        for name, content in payload.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("任务文件路径越界")
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (workspace / "TASK.md").write_text(task_prompt(task) + "\n")
    return output


def run(protocol: dict, output_dir: Path, *, profile: str = "headless",
        task_ids=TASK_IDS) -> dict:
    """顺序执行两个已授权任务；任一账本异常都会停止，不自动重发。"""
    output = Path(output_dir)
    preview = preflight(protocol, task_ids)
    results = []
    for task in _selected_tasks(protocol, task_ids):
        workspace = output / "workspaces" / task["id"]
        run_root = workspace / ".refractagent" / "runs"
        before = set(run_root.glob("planning/*.json")) if run_root.exists() else set()
        prompt = ("这是 Stage 日常功能验收。禁止委派或启动子 Agent；严格遵守 TASK.md。"
                  "研究任务禁止访问网络。完成任务后给出简短结果。\n\n"
                  + task_prompt(task))
        outcome, elapsed = _invoke_dsh(profile, output / "stage.patch.yml",
                                       workspace, prompt, TIMEOUT_MS)
        (output / f"{task['id']}-stdout.log").write_text(outcome.stdout or "")
        (output / f"{task['id']}-stderr.log").write_text(outcome.stderr or "")
        record = _new_record(run_root, before)
        try:
            metrics = _metrics(record, capable_model=CAPABLE_MODEL,
                               efficient_model=EFFICIENT_MODEL)
        except RuntimeError as exc:
            calls = [call for call in record.get("calls", [])
                     if call.get("purpose") != "compaction"]
            costs = record.get("costsByUnit", {}).get("AFP", {})
            results.append({
                "taskId": task["id"], "family": task["family"],
                "elapsedMs": elapsed, "dshExitCode": outcome.returncode,
                "modelCalls": sum(call.get("purpose") in ("execute", "redo", "takeover")
                                  for call in calls),
                "productionAfp": float(costs.get("production", 0)),
                "usageConfirmed": False,
                "error": str(exc), "success": False,
            })
            total = sum(row.get("productionAfp", 0) for row in results)
            summary = {
                "schemaVersion": "stage-daily-acceptance-summary-v1",
                "acceptanceSha256": preview["acceptanceSha256"],
                "profile": profile, "tasks": results,
                "productionAfp": total,
                "withinTotalAfpLimit": total
                <= preview["limits"]["maxProductionAfpTotal"],
                "automaticRetryCount": 0,
                "stoppedReason": str(exc),
                "success": False,
            }
            (output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
            return summary
        evaluation = (evaluate_code(task["id"], workspace) if task["family"] == "code"
                      else evaluate_research(task, workspace))
        checks = {
            "dshCompleted": outcome.returncode == 0 and record.get("status") == "completed",
            "taskPassed": evaluation["success"],
            "withinCallLimit": metrics["modelCalls"] <= MAX_CALLS_PER_TASK,
            "withinAfpLimit": metrics["productionAfp"]
            <= preview["limits"]["maxProductionAfpPerTask"],
        }
        results.append({"taskId": task["id"], "family": task["family"],
                        "elapsedMs": elapsed, "dshExitCode": outcome.returncode,
                        **metrics, "evaluation": evaluation, "checks": checks,
                        "success": all(checks.values())})
    total_afp = sum(row["productionAfp"] for row in results)
    summary = {
        "schemaVersion": "stage-daily-acceptance-summary-v1",
        "acceptanceSha256": preview["acceptanceSha256"],
        "profile": profile,
        "tasks": results,
        "productionAfp": total_afp,
        "withinTotalAfpLimit": total_afp <= preview["limits"]["maxProductionAfpTotal"],
        "automaticRetryCount": 0,
    }
    summary["success"] = (summary["withinTotalAfpLimit"]
                          and all(row["success"] for row in results))
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary
