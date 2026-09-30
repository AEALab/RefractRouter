"""DSH 六策略稳定性验收的冻结任务、配置、上界与结果核验。"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from .ark_plan import catalog
from .planning_config import compile_config, preview


STRATEGY_COUNTS = {
    "static": 12,
    "stage": 24,
    "task": 20,
    "composite": 24,
    "advisor": 24,
    "escalation": 24,
}
AUTHORIZED_AFP = 5_000
INPUT_TOKENS_UPPER = 80_256
EXECUTION_OUTPUT_TOKENS = 2_048
JUDGE_OUTPUT_TOKENS = 1_024
TIMEOUT_MS = 300_000

MODEL_BINDINGS = {
    "efficient": ("deepseek-v4-flash", "low", "适合低成本完成常规文本与工具任务。"),
    "capable": ("deepseek-v4.1-flash", "high", "适合复杂推理、困难任务与接管。"),
    "judge": ("glm-5.3-flash", "high", "用于快速结构化任务选模。"),
}

ARITHMETIC = (
    ("17×19", "323"), ("48＋75", "123"), ("144÷12", "12"),
    ("81－37", "44"), ("13×14", "182"), ("225÷15", "15"),
    ("99＋101", "200"), ("64×8", "512"), ("1000－347", "653"),
    ("27×12", "324"), ("15×15", "225"), ("7×8＋9", "65"),
    ("360÷9", "40"), ("123＋456", "579"), ("19×21", "399"),
    ("625÷25", "25"), ("72－29", "43"), ("31×7", "217"),
    ("88＋17", "105"), ("14×16", "224"),
)


def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def frozen_tasks() -> list[dict[str, Any]]:
    """产生固定的 128 个独立任务；任务 ID 和提示内容均参与预检摘要。"""
    rows: list[dict[str, Any]] = []
    for index in range(1, STRATEGY_COUNTS["static"] + 1):
        marker = f"STATIC_{index:02d}_OK"
        rows.append({"id": f"static-{index:02d}", "strategy": "static",
            "prompt": f"只回复 {marker}，不要调用工具，也不要添加其他文字。",
            "expected": marker, "toolCalls": 0, "maximumModelCalls": 1})
    for index in range(1, STRATEGY_COUNTS["stage"] + 1):
        marker = f"STAGE_{index:02d}_OK"
        rows.append({"id": f"stage-{index:02d}", "strategy": "stage",
            "prompt": (f"只调用一次终端工具执行 printf %s {marker}，读取 stdout 后回复 {marker}。"
                       "不要调用其他工具。"),
            "expected": marker, "toolCalls": 1, "maximumModelCalls": 2})
    for index, (expression, answer) in enumerate(ARITHMETIC, 1):
        prompt = (f"计算 {expression}，只回复阿拉伯数字，不要调用工具。" if index % 2 else
                  f"Calculate {expression}. Reply with digits only and do not call tools.")
        rows.append({"id": f"task-{index:02d}", "strategy": "task",
            "prompt": prompt, "expected": answer, "toolCalls": 0,
            "maximumModelCalls": 2})
    for index in range(1, STRATEGY_COUNTS["composite"] + 1):
        marker = f"COMPOSITE_{index:02d}_OK"
        rows.append({"id": f"composite-{index:02d}", "strategy": "composite",
            "prompt": (f"只调用一次终端工具执行 printf %s {marker}，读取 stdout 后回复 {marker}。"
                       "不要调用其他工具。"),
            "expected": marker, "toolCalls": 1, "maximumModelCalls": 3})
    for index in range(1, STRATEGY_COUNTS["advisor"] + 1):
        marker = f"ADVISOR_{index:02d}_OK"
        rows.append({"id": f"advisor-{index:02d}", "strategy": "advisor",
            "prompt": f"只回复 {marker}，不要调用工具，也不要添加其他文字。",
            "expected": marker, "toolCalls": 0, "maximumModelCalls": 4})
    for index in range(1, STRATEGY_COUNTS["escalation"] + 1):
        marker = f"ESCALATION_{index:02d}_OK"
        rows.append({"id": f"escalation-{index:02d}", "strategy": "escalation",
            "prompt": f"只回复 {marker}，不要调用工具，也不要添加其他文字。",
            "expected": marker, "toolCalls": 0, "maximumModelCalls": 3})
    return rows


def _model(identity: str) -> dict[str, Any]:
    model_id, effort, card = MODEL_BINDINGS[identity]
    row = next(item for item in catalog()["models"] if item["model_id"] == model_id)
    price = row["pricing"]
    if price["unit"] != "afp-per-10000-tokens":
        raise ValueError(f"{model_id} 缺少可核对的 AFP 价格")
    return {"id": identity, "provider": "ark", "model": model_id,
        "contextWindow": row["context_window_tokens"],
        "maxOutputTokens": EXECUTION_OUTPUT_TOKENS,
        "inputPer1k": price["input_coefficient"] / 10,
        "outputPer1k": price["output_coefficient"] / 10,
        "cachedInputPer1k": price["input_coefficient"] / 10,
        "billingUnit": "AFP", "reasoningEffort": effort,
        "deployment": "trusted-cloud", "trustPolicy": "stability-ark",
        "capabilities": {"mainExecutor": identity != "judge",
                         "toolCalling": "verified", "modalities": {}},
        "capabilityCard": card}


def configuration() -> dict[str, Any]:
    config = {"schemaVersion": "refractagent-planning-v6", "enabled": True,
        "defaultStrategy": "stage", "billingUnit": "AFP",
        "maxProductionCostByUnit": {"AFP": 100}, "timeoutMs": TIMEOUT_MS,
        "maxCalls": 10, "models": [_model(name) for name in MODEL_BINDINGS],
        "roles": {"efficient": "efficient", "capable": "capable",
                  "classifier": "judge", "advisor": "efficient"},
        "parameters": {"window": 3, "threshold": .5, "holdTurns": 2,
            "staticMode": "random", "seed": 929,
            "efficientWeight": 1, "capableWeight": 1},
        "stage": {"mode": "rules"},
        "task": {"pool": ["efficient", "capable"], "fallback": "capable",
            "judge": {"type": "llm", "modelId": "judge"}, "threshold": .8,
            "maxInputChars": 12_000, "maxExecutionOutputTokens": EXECUTION_OUTPUT_TOKENS,
            "maxJudgeOutputTokens": JUDGE_OUTPUT_TOKENS},
        "composite": {"pool": ["efficient", "capable"], "takeover": "capable",
            "judge": {"type": "llm", "modelId": "judge"}, "threshold": .8,
            "maxInputChars": 12_000, "maxExecutionOutputTokens": EXECUTION_OUTPUT_TOKENS,
            "stage": {"mode": "rules", "window": 3, "threshold": .5, "holdTurns": 2}},
        "advisor": {"executor": "capable",
            "judge": {"type": "llm", "modelId": "efficient"}, "threshold": .8,
            "judgeTimeoutMs": 30_000, "maxJudgeInputBytes": 65_536,
            "maxExecutionOutputTokens": EXECUTION_OUTPUT_TOKENS,
            "maxJudgeOutputTokens": JUDGE_OUTPUT_TOKENS},
        "escalation": {"initial": "efficient", "takeover": "capable",
            "judge": {"type": "llm", "modelId": "judge"},
            "stallConfirmations": 2, "threshold": .8, "judgeTimeoutMs": 30_000,
            "maxJudgeInputBytes": 65_536,
            "maxExecutionOutputTokens": EXECUTION_OUTPUT_TOKENS,
            "maxJudgeOutputTokens": JUDGE_OUTPUT_TOKENS},
        "trustPolicies": [{"id": "stability-ark", "residency": "CN",
            "auditLogging": True, "allowsSensitiveData": True}],
        "compatiblePairs": [[left, right] for left in MODEL_BINDINGS
                              for right in MODEL_BINDINGS if left != right],
        "security": {"maxPromptBytes": 80_000}}
    compile_config(config)
    unavailable = [row for row in preview(config)["strategies"] if not row["available"]]
    if unavailable:
        raise ValueError("六策略零调用诊断失败：" + "；".join(
            f"{row['id']}：{'，'.join(row['issues'])}" for row in unavailable))
    return config


def _call_upper(model_id: str, output_tokens: int) -> float:
    row = next(item for item in catalog()["models"] if item["model_id"] == model_id)
    price = row["pricing"]
    return ((INPUT_TOKENS_UPPER * price["input_coefficient"]
             + output_tokens * price["output_coefficient"]) / 10_000)


def preflight() -> dict[str, Any]:
    tasks = frozen_tasks()
    counts = Counter(row["strategy"] for row in tasks)
    if dict(counts) != STRATEGY_COUNTS or len({row["id"] for row in tasks}) != len(tasks):
        raise ValueError("冻结任务数量或 ID 不合法")
    cheap_exec = _call_upper("deepseek-v4-flash", EXECUTION_OUTPUT_TOKENS)
    capable_exec = _call_upper("deepseek-v4.1-flash", EXECUTION_OUTPUT_TOKENS)
    judge = _call_upper("glm-5.3-flash", JUDGE_OUTPUT_TOKENS)
    cheap_judge = _call_upper("deepseek-v4-flash", JUDGE_OUTPUT_TOKENS)
    per_task = {
        "static": capable_exec,
        "stage": 2 * capable_exec,
        "task": judge + capable_exec,
        "composite": judge + 2 * capable_exec,
        "advisor": 2 * capable_exec + 2 * cheap_judge,
        "escalation": cheap_exec + cheap_judge + capable_exec,
    }
    per_strategy = {name: round(per_task[name] * amount, 6)
                    for name, amount in STRATEGY_COUNTS.items()}
    production_upper = round(sum(per_strategy.values()), 6)
    if production_upper > AUTHORIZED_AFP:
        raise ValueError("最坏路径上界超过 5000 AFP 授权")
    config = configuration()
    frozen = {"schemaVersion": "dsh-strategy-stability-preflight-v1",
        "status": "zero-call-preflight", "realModelCalls": 0,
        "taskCount": len(tasks), "strategyCounts": STRATEGY_COUNTS,
        "tasks": tasks, "tasksDigest": digest(tasks), "configDigest": digest(config),
        "patchDigests": {strategy: digest(patch_text(config, strategy))
                         for strategy in STRATEGY_COUNTS},
        "models": {name: {"model": values[0], "reasoningEffort": values[1]}
                   for name, values in MODEL_BINDINGS.items()},
        "limits": {"maximumProductionAfp": production_upper,
            "authorizedBatchAfp": AUTHORIZED_AFP,
            "maximumModelCalls": sum(row["maximumModelCalls"] for row in tasks),
            "timeoutMsPerTask": TIMEOUT_MS, "httpRetries": 0,
            "delegation": False, "media": False},
        "perStrategyAfpUpper": per_strategy,
        "acceptance": [
            "每个冻结任务的 DSH 进程退出码为 0，且输出包含唯一预期结果",
            "每次产生唯一 planning 记录，全部派发调用有确认用量并完成结算",
            "每个策略达到冻结成功数；任何任务失败则该批次不通过",
            "Static、Stage、Task、Composite、Advisor、Escalation 的轨迹符合各自合同",
            "所有失败尝试保留，不以补跑成功样本覆盖失败记录",
        ],
        "branchCoverage": {
            "realDsh": ["Static 随机选模", "Stage 高效模型与原生工具续接",
                "Task 单次判别后固定执行器", "Composite 单次 Task 判别与 Stage 续接",
                "Advisor 缓冲后审核放行或有界返工", "Escalation 缓冲后放行或接管"],
            "deterministic": ["Stage 重复失败升级、保持与降回",
                "Composite 接管、保持与降回", "Advisor REDO、复审与失败关闭",
                "Escalation DEFECT、STALL、UNCERTAIN 与强模型接管"]},
        "stopRules": ["认证失败", "模型用量未知", "账本或轨迹写入失败",
            "冻结配置摘要变化", "任一冻结任务失败", "5000 AFP 批次上限耗尽"]}
    return {**frozen, "preflightDigest": digest(frozen)}


def patch_text(config: dict[str, Any], strategy: str,
               *, python_executable: str = "refractagent") -> str:
    routed_config = deepcopy(config)
    # DSH Web 会从模型菜单传入 rr:*；headless 没有模型菜单，因此必须通过同一
    # planning 配置的 defaultStrategy 冻结本次任务所选模式。
    routed_config["defaultStrategy"] = strategy
    entries: list[tuple[str, Any, bool]] = [
        ("agent-default-model", {"provider": "refractagent", "model": "planning",
            "reasoningEffort": f"rr:{strategy}"}, False),
        ("settings", {"path": ".refractagent/settings.yaml", "watch": False}, False),
        ("llm-pi-ai", {"providers": {"ark": {"apiKeyEnv": "ARK_API_KEY",
            "api": "openai-responses",
            "baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
            "retryPolicy": {"mode": "normal", "maxRetries": 0},
            "models": [{"id": model["model"], "name": model["model"],
                "contextWindow": model["contextWindow"],
                "maxTokens": EXECUTION_OUTPUT_TOKENS,
                "reasoningEfforts": {"low": "low", "high": "high", "max": "max"}}
                for model in config["models"]]}}}, False),
        ("refractagent", {"pythonExecutable": python_executable,
            "runsDir": ".refractagent/runs", "planningRouting": routed_config}, False),
        *((name, None, True) for name in ("tool-subagent-control",
            "tool-subagent-list-agents", "tool-subagent", "tool-subagent-fork", "tool-ralph")),
    ]
    return "\n".join("- id: " + name + ("\n  disabled: true" if disabled else
        "\n  config: " + json.dumps(value, ensure_ascii=False, separators=(",", ":")))
        for name, value, disabled in entries) + "\n"


def verify_record(task: dict[str, Any], outcome_code: int, stdout: str,
                  record: dict[str, Any]) -> dict[str, Any]:
    """核验一条真实 DSH 运行，并返回可汇总且不含请求正文的结果。"""
    issues: list[str] = []
    if outcome_code != 0:
        issues.append(f"dsh-exit-{outcome_code}")
    if task["expected"] not in stdout.strip():
        issues.append("expected-output-missing")
    if record.get("status") != "completed" or record.get("strategy") != task["strategy"]:
        issues.append("planning-record-not-completed")
    calls = [row for row in record.get("calls", []) if row.get("status") != "local-inference"
             and row.get("purpose") != "compaction"]
    if len(calls) > task["maximumModelCalls"]:
        issues.append("model-call-limit-exceeded")
    if any(row.get("status") != "billed" for row in calls):
        issues.append("unconfirmed-model-usage")
    if any((row.get("response") or {}).get("attempts", 1) != 1 for row in calls):
        issues.append("http-retry-observed")
    purposes = Counter(row.get("purpose") for row in calls)
    reasons = [row.get("reason") for row in record.get("decisions", [])]
    state = record.get("state", {})
    strategy = task["strategy"]
    tool_calls = sum(len((row.get("response") or {}).get("tool_calls", [])) for row in calls)
    if tool_calls != task["toolCalls"]:
        issues.append("native-tool-call-count-mismatch")
    if strategy == "static":
        if purposes != Counter({"execute": 1}) or "static-random-selected" not in reasons:
            issues.append("static-route-mismatch")
    elif strategy == "stage":
        if purposes != Counter({"execute": 2}) or len(state.get("consumedEvidenceIds", [])) != 1:
            issues.append("stage-route-mismatch")
        if not reasons or reasons[0] != "no-signal":
            issues.append("stage-initial-reason-mismatch")
    elif strategy == "task":
        if purposes.get("task") != 1 or purposes.get("execute") != 1:
            issues.append("task-route-mismatch")
        if not state.get("classified") or state.get("selected_model") not in {"efficient", "capable"}:
            issues.append("task-selection-missing")
    elif strategy == "composite":
        if (purposes.get("task") != 1 or purposes.get("execute") != 2
                or len(state.get("consumedEvidenceIds", [])) != 1):
            issues.append("composite-route-mismatch")
        if not state.get("classified") or not state.get("selected_model"):
            issues.append("composite-selection-missing")
    elif strategy == "advisor":
        if purposes.get("advisor", 0) not in {1, 2} or state.get("advisorPhase") != "approved":
            issues.append("advisor-review-mismatch")
        if "advisor-approved" not in reasons and "advisor-reapproved" not in reasons:
            issues.append("advisor-approval-reason-missing")
    elif strategy == "escalation":
        if purposes.get("escalation") != 1:
            issues.append("escalation-review-mismatch")
        if not any(reason in {"escalation-proceed", "escalation-defect",
                              "escalation-stall-final", "escalation-uncertain"}
                   for reason in reasons):
            issues.append("escalation-decision-missing")
    costs = record.get("costsByUnit") or record.get("costs", {})
    afp = float(costs.get("AFP", {}).get("production", 0))
    return {"id": task["id"], "strategy": strategy, "success": not issues,
        "issues": issues, "runId": record.get("runId"), "modelCalls": len(calls),
        "productionAfp": afp, "models": [row.get("actual_model") for row in calls],
        "purposes": [row.get("purpose") for row in calls], "decisionReasons": reasons,
        "nativeToolCalls": tool_calls,
        "firstByteMs": next((row.get("ttft_ms") for row in calls
                             if row.get("ttft_ms") is not None), None),
        "latencyMs": sum(float(row.get("latency_ms") or 0) for row in calls)}


def write_preflight(output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("验收目录已存在，拒绝覆盖历史证据")
    output.mkdir(parents=True)
    config = configuration()
    frozen = preflight()
    (output / "preflight.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
    (output / "schedule.json").write_text(
        json.dumps(frozen_tasks(), ensure_ascii=False, indent=2) + "\n")
    patches = output / "patches"
    patches.mkdir()
    for strategy in STRATEGY_COUNTS:
        (patches / f"{strategy}.yml").write_text(patch_text(config, strategy))
    return frozen
