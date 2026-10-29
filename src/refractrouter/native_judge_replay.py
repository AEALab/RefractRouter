"""使用现有四策略解析器重放已归档判词；不加载模型、不继承旧质量准入。"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from . import advisor_decision, escalation_decision, planning_decision, stage_hybrid
from .purpose_review import decode, digest, text_digest, wire


VERSION = "native-judge-replay-v1"
CONTRACTS = {
    "task-fit": planning_decision.DECISION_CONTRACT,
    "stage-progress": stage_hybrid.VERSION,
    "advisor-delivery": advisor_decision.VERSION,
    "escalation-takeover": escalation_decision.DECISION_CONTRACT,
}


def _threshold(value):
    if type(value) not in (int, float) or not 0 <= value <= 1:
        raise ValueError("原生评审阈值无效")
    return value


def parse_native(purpose, contract, payload, context, *, input_kind):
    """输入种类显式声明。旧归一化对象不是原始响应，不能为它生成假的原始字节摘要。"""
    if not isinstance(purpose, str) or CONTRACTS.get(purpose) != contract:
        raise ValueError("原生评审用途与合同不匹配")
    if input_kind not in ("raw-json", "archived-structured-answers", "archived-normalized-decision"):
        raise ValueError("原始记录类型无效")
    raw_hash = None
    try:
        if input_kind == "raw-json":
            raw_hash = text_digest(payload) if isinstance(payload, str) else None
            value = decode(payload)
        else:
            wire(payload)
            value = payload
        if not isinstance(context, dict):
            raise ValueError("原生评审上下文无效")
        wire(context)
        if purpose == "task-fit":
            if set(context) != {"candidateIds", "targetCandidateId", "threshold"}:
                raise ValueError("Task 重放上下文字段无效")
            ids = context["candidateIds"]
            if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not i for i in ids)
                    or len(set(ids)) != len(ids) or context["targetCandidateId"] not in ids):
                raise ValueError("Task 重放候选不完整或重复")
            rows = planning_decision.candidate_assessments(value, ids, _threshold(context["threshold"]))
            target = next(r for r in rows if r["candidateId"] == context["targetCandidateId"])
            native = {"perCandidate": rows, "targetCandidateId": target["candidateId"],
                      "qualified": target["qualified"]}
            prediction = "ALLOW" if target["qualified"] else "UNKNOWN"
        elif purpose == "stage-progress":
            if set(context) != {"upgradeThreshold", "downgradeThreshold"}:
                raise ValueError("Stage 重放上下文字段无效")
            for threshold in context.values():
                _threshold(threshold)
            native = stage_hybrid.parse_answers(value, context)
            prediction = {"EFFICIENT_OK": "ALLOW", "NEED_STRONG": "BLOCK", "UNCERTAIN": "UNKNOWN"}[native["verdict"]]
        elif purpose == "advisor-delivery":
            if context:
                raise ValueError("Advisor 重放不接受额外上下文字段")
            native = advisor_decision.parse_decision(value)
            prediction = {"APPROVE": "ALLOW", "REDO": "BLOCK", "UNRESOLVED": "UNKNOWN"}[native["verdict"]]
        else:
            if set(context) != {"evidenceIds", "threshold"}:
                raise ValueError("Escalation 重放上下文字段无效")
            ids = context["evidenceIds"]
            if (not isinstance(ids, list) or any(not isinstance(i, str) for i in ids)
                    or len(set(ids)) != len(ids)):
                raise ValueError("Escalation 重放证据身份无效")
            native = escalation_decision.parse_decision(value, ids, _threshold(context["threshold"]))
            prediction = {"PROCEED": "ALLOW", "DEFECT": "BLOCK", "STALL": "BLOCK", "UNCERTAIN": "UNKNOWN"}[native["verdict"]]
        return {"prediction": prediction, "nativeDecision": native, "contractStatus": "pass",
                "rawSha256": raw_hash, "payloadSha256": digest(value), "inputKind": input_kind,
                "wireStatus": "pass" if input_kind == "raw-json" else "unavailable",
                "quoteBindingStatus": "not-supported-by-this-contract", "semanticStatus": "unknown"}
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        return {"prediction": "FORMAT_REJECT", "nativeDecision": None, "contractStatus": "rejected",
                "rawSha256": raw_hash, "inputKind": input_kind,
                "wireStatus": "rejected" if input_kind == "raw-json" else "unavailable",
                "quoteBindingStatus": "unavailable", "semanticStatus": "unknown",
                "errorType": type(exc).__name__, "reason": str(exc)}


def replay_archives(repository, manifest):
    """仅重放固定报告及有出处的解析上下文；旧 expected 不成为新的金标。"""
    root = Path(repository).resolve()
    def pinned(relative, expected):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("原生评审归档越出仓库")
        raw = path.read_bytes()
        if len(raw) > 1024 * 1024 or text_digest(raw.decode()) != expected:
            raise ValueError("原生评审归档摘要漂移")
        return raw.decode()
    groups = []
    for spec in manifest["groups"]:
        raw = pinned(spec["report"], spec["reportSha256"])
        archive = ([decode(line) for line in raw.splitlines() if line]
                   if spec["format"] == "jsonl" else decode(raw)["cases"])
        source = decode(pinned(spec["contextSource"], spec["contextSourceSha256"]))
        source_cases = {c["id"]: c for c in source["cases"]}
        if len(source_cases) != len(source["cases"]) or set(source_cases) != {c["id"] for c in archive} or len(archive) != len(source_cases):
            raise ValueError("归档判词与固定案例缺失或重复")
        if "templateMetadataSource" in spec:
            metadata = decode(pinned(spec["templateMetadataSource"], spec["templateMetadataSha256"]))
            if spec["backend"]["templateSha256"] != metadata["judgeContractDigest"]:
                raise ValueError("原评审模板摘要与原预检不同")
        decisions = []
        for archived in archive:
            purpose = spec["purpose"]
            source_case = source_cases[archived["id"]]
            if source_case["expected"] != archived["expected"]:
                raise ValueError("原评审期望与固定案例不同；不得静默更换旧金标")
            if purpose == "task-fit":
                rows = archived["raw"]
                payload = {"rawPerCandidate": rows}
                context = {"candidateIds": [r["id"] for r in source_case["candidates"]],
                           "targetCandidateId": archived["selected"], "threshold": spec["threshold"]}
            elif purpose == "stage-progress":
                payload, context = archived["answers"], spec["thresholds"]
            elif purpose == "advisor-delivery":
                original = archived["decision"]
                payload = {"verdict": original["verdict"], "feedback": original.get("feedback")}
                context = {}
            else:
                original = archived["decision"]
                # 保留原生输入四字段；归一化对象中的其它审计字段不是新模型输出。
                payload = {key: original[key] for key in ("rawVerdict", "confidence", "evidenceIds", "reason")}
                payload["verdict"] = payload.pop("rawVerdict")
                case = [e["id"] for e in source_case.get("evidence", [])]
                if case != spec["evidenceIdsByCase"][archived["id"]]:
                    raise ValueError("Escalation 证据上下文与固定案例不符")
                context = {"evidenceIds": case, "threshold": spec["threshold"]}
            parsed = parse_native(purpose, spec["contract"], payload, context, input_kind=spec["inputKind"])
            if purpose == "task-fit":
                native_outcome = (context["targetCandidateId"] if parsed["nativeDecision"] is not None
                                  and parsed["nativeDecision"]["qualified"] else "insufficient")
            else:
                native_outcome = (parsed["nativeDecision"] or {}).get("verdict")
            decisions.append({"caseId": archived["id"], "originalOutcome": archived["outcome"],
                              "originalExpectedNotNewGold": archived["expected"],
                              "replayedOutcome": native_outcome,
                              "conversionMatchesArchive": native_outcome == archived["outcome"],
                              "archivedRecordSha256": digest(archived), **parsed})
        counts = Counter(d["prediction"] for d in decisions)
        groups.append({"purpose": spec["purpose"], "contract": spec["contract"],
                       "backend": spec["backend"], "identitySha256": digest({"purpose": spec["purpose"], "backend": spec["backend"]}),
                       "sourceReport": spec["report"], "sourceSha256": spec["reportSha256"],
                       "contextSource": spec["contextSource"], "contextSourceSha256": spec["contextSourceSha256"],
                       "inputKind": spec["inputKind"], "total": len(decisions),
                       "predictions": {k: counts[k] for k in ("ALLOW", "BLOCK", "UNKNOWN", "FORMAT_REJECT")},
                       "decisions": decisions, "semanticGoldAvailable": False,
                       "qualified": False, "reason": "archived-compatibility-is-not-independent-calibration"})
    return {"contract": VERSION, "groups": groups, "modelCalls": 0,
            "historicalScoresModified": False, "productionConfigurationChanged": False}
