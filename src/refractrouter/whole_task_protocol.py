"""整任务评测的隔离、完整费用和停止合同；只校验冻结材料，不调用模型。"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


VERSION = "whole-task-evaluation-v1"
HASH = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")
KINDS = {"extraction", "cross-file-code", "evidence-analysis"}
RULES = {
    "unit": "independent-task",
    "failureDenominator": "all-frozen-tasks",
    "unknownQuality": "not-passed",
    "outputLimit": "model-native",
    "httpRetries": 0,
    "costComponents": ["all-execution-attempts", "all-routing-calls", "all-online-reviews"],
    "researchEvaluation": "separate-and-report-total",
    "billing": "cash-reference-and-historical-afp-separate",
    "unknownUsage": "retain-reservation-stop-batch-settle-inflight",
    "criticalRegression": "stop-configuration",
    "infrastructureFailure": "stop-batch-settle-inflight",
    "hiddenEvaluation": "outside-model-tools-cache-and-readable-logs",
    "repeatedObservation": "not-new-independent-task",
    "insufficientEvidence": "keep-current-default-no-auto-expansion",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _object(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f"{name} 字段不完整或存在未知字段")


def _id(value):
    if type(value) is not str or ID.fullmatch(value) is None:
        raise ValueError("身份必须为明确且受限的字符串")


def _hash(value):
    if type(value) is not str or HASH.fullmatch(value) is None:
        raise ValueError("必须提供完整 SHA-256")


def validate_contract(contract):
    _object(contract, ("schemaVersion", "rules", "acceptance"), "评测合同")
    if contract["schemaVersion"] != VERSION:
        raise ValueError("未知整任务评测合同版本")
    if (type(contract["rules"]) is not dict or contract["rules"] != RULES
            or type(contract["rules"].get("httpRetries")) is not int):
        raise ValueError("完整费用、质量、隔离或停止规则不符合合同")
    acceptance = contract["acceptance"]
    _object(acceptance, ("qualityMargin", "confidence", "minimumSavings", "criticalErrorsAllowed",
                         "positiveSavingsInBothHalves", "intervalUnit"), "验收条件")
    for key in ("qualityMargin", "confidence", "minimumSavings"):
        text = acceptance[key]
        if type(text) is not str or re.fullmatch(r"0\.[0-9]+", text) is None:
            raise ValueError("验收数值使用有限十进制字符串")
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("验收数值无效") from exc
        if not 0 < amount < 1:
            raise ValueError("验收数值必须在0与1之间")
        if (key == "qualityMargin" and amount > Decimal("0.03")
                or key == "confidence" and amount < Decimal("0.95")
                or key == "minimumSavings" and amount < Decimal("0.20")):
            raise ValueError("不得放宽既定质量、确定水平或节省门槛")
    if (acceptance["criticalErrorsAllowed"] != 0
            or type(acceptance["criticalErrorsAllowed"]) is not int
            or acceptance["positiveSavingsInBothHalves"] is not True
            or acceptance["intervalUnit"] != "independent-task"):
        raise ValueError("不得允许关键错误或把重跑作为独立统计单位")
    return deepcopy(contract)


def freeze_study(contract, tasks, arms, comparisons, *, exposed_materials=()):
    """冻结声明及摘要；不证明材料真实、近重复审查完成或付费准入通过。"""
    validate_contract(contract)
    if type(tasks) is not list or not tasks or type(arms) is not list or len(arms) < 2:
        raise ValueError("需要非空任务和至少两个实验臂")
    ids, materials, source_splits, split_counts = set(), set(), {}, {}
    for task in tasks:
        _object(task, ("taskId", "sourceGroup", "kind", "split", "materialSha256", "criteriaSha256"), "任务")
        _id(task["taskId"])
        _id(task["sourceGroup"])
        for key in ("materialSha256", "criteriaSha256"):
            _hash(task[key])
        if (type(task["kind"]) is not str or task["kind"] not in KINDS
                or type(task["split"]) is not str or task["split"] not in ("development", "holdout")):
            raise ValueError("未知任务类别或数据划分")
        if task["taskId"] in ids or task["materialSha256"] in materials:
            raise ValueError("重复任务身份或重复材料")
        if task["split"] == "holdout" and task["materialSha256"] in exposed_materials:
            raise ValueError("已暴露材料不能作为独立留出")
        prior_split = source_splits.setdefault(task["sourceGroup"], task["split"])
        if prior_split != task["split"]:
            raise ValueError("同一来源组不能跨开发和留出集")
        ids.add(task["taskId"])
        materials.add(task["materialSha256"])
        split_counts[task["split"]] = split_counts.get(task["split"], 0) + 1
    arm_ids, by_arm = set(), {}
    for arm in arms:
        _object(arm, ("armId", "routeSnapshotSha256", "toolsSha256", "hostSnapshotSha256",
                      "deliveryContractSha256"), "实验臂")
        _id(arm["armId"])
        if arm["armId"] in arm_ids:
            raise ValueError("实验臂身份重复")
        for key in set(arm) - {"armId"}:
            _hash(arm[key])
        arm_ids.add(arm["armId"])
        by_arm[arm["armId"]] = arm
    if type(comparisons) is not list or not comparisons:
        raise ValueError("必须预先声明主要比较")
    seen_pairs = set()
    for pair in comparisons:
        _object(pair, ("baseline", "candidate", "factor"), "配对比较")
        names = (pair["baseline"], pair["candidate"])
        if (any(type(name) is not str or name not in arm_ids for name in names)
                or names[0] == names[1] or frozenset(names) in seen_pairs):
            raise ValueError("配对引用缺失、相同或重复实验臂")
        seen_pairs.add(frozenset(names))
        a, b = (by_arm[name] for name in names)
        if any(a[key] != b[key] for key in ("hostSnapshotSha256", "deliveryContractSha256")):
            raise ValueError("主要配对须使用相同宿主和交付要求")
        if pair["factor"] == "routing":
            if a["toolsSha256"] != b["toolsSha256"]:
                raise ValueError("选模收益比较必须使用相同工具")
        elif pair["factor"] == "tools":
            if a["routeSnapshotSha256"] != b["routeSnapshotSha256"]:
                raise ValueError("工具收益比较必须使用相同模型路线")
        else:
            raise ValueError("每组主要比较只能改变路由或工具一个因素")
    payload = {"contract": contract, "tasks": tasks, "arms": arms, "comparisons": comparisons}
    return {"schemaVersion": "whole-task-freeze-v1", "snapshot": deepcopy(payload),
            "sha256": digest(payload), "splitCounts": split_counts,
            "modelCalls": 0, "liveExecutionReady": False,
            "blockingRequirements": ["实际材料及近重复审查", "隐藏评估隔离验收", "精确模型与费用包络预检",
                                     "独立任务精度与停止观察点冻结"],
            "historicalResultsChanged": False}
