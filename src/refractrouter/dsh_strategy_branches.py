"""DSH 复杂策略关键分支的冻结配置、预算上界和结果核验。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from .ark_plan import catalog
from .dsh_strategy_stability import configuration as stability_configuration
from .planning_config import compile_config, preview


STRATEGY_COUNTS = {"stage": 6, "composite": 6, "advisor": 6, "escalation": 6}
AUTHORIZED_AFP = 5_000
PRIOR_CONFIRMED_AFP = 237.52915
PRIOR_PENDING_AFP = 0.23485
INPUT_TOKENS_UPPER = 100_000
EXECUTION_OUTPUT_TOKENS = 256
JUDGE_OUTPUT_TOKENS = 4_096


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()


def implementation_digest() -> str:
    root = Path(__file__).resolve().parents[2]
    paths = [Path(__file__), root / "experiments/run_dsh_strategy_branches.py",
             root / "validation/dsh/plugin/scripts/check-gateway-branch-tools.ts"]
    return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()


def _fixture_model(identity: str) -> dict[str, Any]:
    return {"id": identity, "provider": "controlled-fixture", "model": identity,
        "contextWindow": 100_000, "maxOutputTokens": EXECUTION_OUTPUT_TOKENS,
        "inputPer1k": .000001, "outputPer1k": .000001,
        "cachedInputPer1k": .000001, "billingUnit": "AFP",
        "deployment": "local", "trustPolicy": "branch-local",
        "capabilities": {"mainExecutor": True, "toolCalling": "verified", "modalities": {}},
        "capabilityCard": "仅用于稳定构造错误候选；不作为真实模型质量或费用证据。"}


def _fixture_judge_model(identity: str) -> dict[str, Any]:
    model = _fixture_model(identity)
    model["capabilities"] = {"mainExecutor": False, "toolCalling": "unknown", "modalities": {}}
    model["capabilityCard"] = "仅冻结关键分支的初始选择；不作为 Judge 质量证据。"
    return model


def configuration(strategy: str) -> dict[str, Any]:
    if strategy not in STRATEGY_COUNTS:
        raise ValueError("未知关键分支策略")
    config = deepcopy(stability_configuration())
    config["defaultStrategy"] = strategy
    config["maxCalls"] = 10
    config["maxProductionCostByUnit"] = {"AFP": 100}
    config["timeoutMs"] = 300_000
    if strategy == "composite":
        config["models"].append(_fixture_judge_model("composite-task-judge-fixture"))
        config["composite"]["judge"] = {"type": "llm", "modelId": "composite-task-judge-fixture"}
    elif strategy == "advisor":
        config["models"].append(_fixture_model("advisor-executor-fixture"))
        config["advisor"] = {"executor": "advisor-executor-fixture",
            "judge": {"type": "llm", "modelId": "efficient"}, "threshold": .8,
            "judgeTimeoutMs": 30_000, "maxJudgeInputBytes": 65_536,
            "maxExecutionOutputTokens": EXECUTION_OUTPUT_TOKENS,
            "maxJudgeOutputTokens": 1_024}
    elif strategy == "escalation":
        config["models"].append(_fixture_model("escalation-initial-fixture"))
        config["escalation"] = {"initial": "escalation-initial-fixture", "takeover": "capable",
            "judge": {"type": "llm", "modelId": "efficient"},
            "stallConfirmations": 2, "threshold": .8, "judgeTimeoutMs": 30_000,
            "maxJudgeInputBytes": 65_536,
            "maxExecutionOutputTokens": EXECUTION_OUTPUT_TOKENS,
            "maxJudgeOutputTokens": 1_024}
    config["trustPolicies"].append({"id": "branch-local", "residency": "local",
        "auditLogging": True, "allowsSensitiveData": True})
    config["compatiblePairs"] = [[left["id"], right["id"]]
        for left in config["models"] for right in config["models"] if left["id"] != right["id"]]
    compile_config(config)
    status = next(row for row in preview(config)["strategies"] if row["id"] == strategy)
    if not status["available"]:
        raise ValueError(f"{strategy} 零调用诊断失败：" + "；".join(status["issues"]))
    return config


def _call_upper(model_id: str, output_tokens: int) -> float:
    row = next(item for item in catalog()["models"] if item["model_id"] == model_id)
    price = row["pricing"]
    if price["unit"] != "afp-per-10000-tokens":
        raise ValueError(f"{model_id} 缺少 AFP 价格")
    return ((INPUT_TOKENS_UPPER * price["input_coefficient"]
             + output_tokens * price["output_coefficient"]) / 10_000)


def preflight() -> dict[str, Any]:
    efficient = _call_upper("deepseek-v4-flash", JUDGE_OUTPUT_TOKENS)
    capable = _call_upper("deepseek-v4.1-flash", EXECUTION_OUTPUT_TOKENS)
    per_flow = {"stage": 5 * capable,
        "composite": 5 * capable,
        "advisor": 2 * efficient,
        "escalation": efficient + 2 * capable}
    per_strategy = {key: round(value * STRATEGY_COUNTS[key], 6)
                    for key, value in per_flow.items()}
    production = round(sum(per_strategy.values()), 6)
    cumulative = round(PRIOR_CONFIRMED_AFP + PRIOR_PENDING_AFP + production, 6)
    if cumulative > AUTHORIZED_AFP:
        raise ValueError("关键分支批次最坏上界超过累计 5000 AFP 授权")
    configs = {strategy: configuration(strategy) for strategy in STRATEGY_COUNTS}
    frozen = {"schemaVersion": "dsh-strategy-branch-preflight-v1",
        "status": "zero-call-preflight", "realModelCalls": 0,
        "implementationDigest": implementation_digest(),
        "strategyCounts": STRATEGY_COUNTS,
        "configDigests": {key: digest(value) for key, value in configs.items()},
        "models": {"efficient": "deepseek-v4-flash",
            "capable": "deepseek-v4.1-flash",
            "controlledFixtures": ["composite-task-judge-fixture",
                "advisor-executor-fixture", "escalation-initial-fixture"]},
        "limits": {"maximumProductionAfp": production,
            "priorConfirmedAfp": PRIOR_CONFIRMED_AFP, "priorPendingAfp": PRIOR_PENDING_AFP,
            "maximumIncludingPriorAfp": cumulative, "authorizedCumulativeAfp": AUTHORIZED_AFP,
            "maximumRealModelCalls": 90, "timeoutMsPerStrategy": 900_000,
            "httpRetries": 0, "delegation": False, "media": False},
        "perStrategyAfpUpper": per_strategy,
        "acceptance": {
            "stage": "高效→高效→强执行→强执行保持→高效恢复",
            "composite": "Task 判别一次后，高效→高效→接管→接管保持→常用模型恢复",
            "advisor": "受控错误候选→真实 Judge REDO→DSH 工具→真实 Judge 复审通过",
            "escalation": "受控错误候选→真实 Judge 接管判定→真实强模型工具续接并锁定"},
        "evidenceBoundary": [
            "Stage／Composite 的执行、选模和 DSH 工具均为真实路径；失败状态由受控宿主事实提供。",
            "Composite 的 Task 初选使用受控 Judge 固定为高效模型；上一批 24 条正常路径保留真实 Task Judge 证据。",
            "Advisor 的执行器为明确标记夹具，两个审核调用为真实模型。",
            "Escalation 的起始候选为明确标记夹具，Judge 与接管执行为真实模型。",
            "受控候选不用于证明自然任务收益或执行模型质量。"],
        "stopRules": ["任一流程失败", "认证失败", "模型用量未知",
            "账本或证据写入失败", "配置摘要改变", "累计 5000 AFP 上限耗尽"]}
    return {**frozen, "preflightDigest": digest(frozen)}


def verify_runs(strategy: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(runs) != STRATEGY_COUNTS[strategy]:
        raise ValueError(f"{strategy} 任务数不符合冻结范围")
    compact = []
    for run in runs:
        calls = [row for row in run["budget"].records if row.get("purpose") != "compaction"]
        if any(row.get("status") != "billed" for row in calls):
            raise ValueError(f"{strategy} 存在未确认用量")
        reasons = [row.get("reason") for row in run.get("decisions", [])]
        real_calls = [row for row in calls if row.get("provider") == "ark"]
        models = [row.get("actual_model") for row in calls]
        purposes = [row.get("purpose") for row in calls]
        issues = []
        if strategy == "stage":
            expected = ["deepseek-v4-flash", "deepseek-v4-flash",
                        "deepseek-v4.1-flash", "deepseek-v4.1-flash", "deepseek-v4-flash"]
            if models != expected or not {"repeated-failure", "capable-hold"}.issubset(reasons):
                issues.append("stage-cycle-mismatch")
        elif strategy == "composite":
            execution = [row.get("actual_model") for row in calls if row.get("purpose") == "execute"]
            expected = ["deepseek-v4-flash", "deepseek-v4-flash",
                        "deepseek-v4.1-flash", "deepseek-v4.1-flash", "deepseek-v4-flash"]
            required = {"composite-repeated-failure", "composite-takeover-hold",
                        "composite-return-base"}
            if purposes.count("task") != 1 or execution != expected or not required.issubset(reasons):
                issues.append("composite-cycle-mismatch")
        elif strategy == "advisor":
            if (purposes.count("advisor") != 2 or "advisor-redo-required" not in reasons
                    or "advisor-reapproved" not in reasons
                    or run["state"].get("advisorPhase") != "approved"):
                issues.append("advisor-redo-mismatch")
        elif strategy == "escalation":
            if (purposes.count("escalation") != 1 or purposes.count("takeover") != 1
                    or not run["state"].get("latched")
                    or not any(reason in {"escalation-defect", "escalation-uncertain",
                                         "escalation-final-stall"} for reason in reasons)):
                issues.append("escalation-takeover-mismatch")
        if issues:
            raise ValueError(f"{strategy} 关键分支不匹配：{','.join(issues)}")
        compact.append({"runId": run["id"], "strategy": strategy,
            "models": models, "purposes": purposes, "decisionReasons": reasons,
            "realModelCalls": len(real_calls),
            "fixtureCalls": len(calls) - len(real_calls),
            "productionAfp": round(sum(float(row.get("charged") or 0)
                                        for row in real_calls), 8),
            "status": run.get("status"), "state": {key: run["state"].get(key)
                for key in ("selected_model", "hold", "latched", "advisorPhase", "reviews", "redos")}})
    return compact
