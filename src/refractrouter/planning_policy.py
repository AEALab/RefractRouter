"""纯策略与工具轨迹归一；不调用模型、不执行宿主工具。"""
import hashlib
import json
import math
import random

STAGE_RULE_VERSION = "stage-v4"


def text_of(message):
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def _evidence_summary(events):
    labels = {
        "completed": "完成",
        "failed": "任务失败",
        "denied": "权限拒绝",
        "infrastructure": "基础设施故障",
        "unconfirmed": "结果未确认",
        "unclassified-error": "无法分类",
    }
    counts = {}
    for event in events:
        label = labels.get(event["status"], event["status"])
        counts[label] = counts.get(label, 0) + 1
    return "，".join(f"{label} {count}" for label, count in counts.items()) if counts else "无新有效证据"


def tool_events(messages, native=None):
    """兼容旧插件；DSH 字段解析与策略评分分离。"""
    from .dsh_evidence import tool_events as decode
    return decode(messages, native)


def stage_decision(events, state, p, default):
    """计算一次 Stage 决策；保持轮数包含触发升级的当前调用。"""
    events = [{**event, "id": event.get("id") or
               f"legacy:{index}:{event.get('fingerprint', 'unknown')}"}
              for index, event in enumerate(events)]
    # 重放同一事件不能构成两次失败。
    events = list({e["id"]: e for e in events}.values())
    if any(e["status"] == "unconfirmed" for e in events):
        raise ValueError("工具结果未确认，停止续接")
    eligible = [e for e in events if e["status"] in ("completed", "failed")]
    window = eligible[-p["window"]:]
    consumed = set(state.get("consumedEvidenceIds", []))
    new_events = [e for e in events if e["id"] not in consumed]
    new_window = [e for e in window if e["id"] not in consumed]
    evidence_ids = [e["id"] for e in new_events]
    failures = [e for e in window if e["status"] == "failed"]
    repeated = (len(failures) >= 2
                and failures[-1]["fingerprint"] == failures[-2]["fingerprint"]
                and failures[-1]["id"] in evidence_ids)
    hold_before = state.get("hold", 0)
    if repeated:
        role, reason, hold, score = "capable", "repeated-failure", max(0, p["holdTurns"] - 1), 1.0
    elif hold_before > 0:
        role, reason, hold, score = "capable", "capable-hold", hold_before - 1, None
    elif not new_window:
        role, reason, hold, score = default, "no-signal", 0, 0.0
    else:
        # 借鉴有符号 tanh 信号；持续检索本身不视为空转，未知工具不假定成功。
        severity = (len(failures) / len(window) if len(failures) >= 2
                    and any(e["status"] == "failed" for e in new_window) else 0)
        spinning = float(repeated)
        production = sum(e["kind"] == "mutate" and e["status"] == "completed" for e in window) / len(window)
        score = math.tanh(.5 * (severity / .7 + spinning - production / .7))
        if abs(score) <= p["threshold"]:
            role, reason, hold = default, "ambiguous", 0
        else:
            role = "capable" if score > 0 else "efficient"
            reason = "tool-signal"
            hold = max(0, p["holdTurns"] - 1) if role == "capable" else 0
    return {"role": role, "reason": reason, "hold": hold, "score": score,
            "holdBefore": hold_before, "holdAfter": hold,
            "evidenceIds": evidence_ids, "evidenceSummary": _evidence_summary(new_events),
            "ruleVersion": STAGE_RULE_VERSION}


def stage(events, state, p, default):
    decision = stage_decision(events, state, p, default)
    return decision["role"], decision["reason"], decision["hold"], decision["score"]


def static_choice(p, identity, step):
    if p["staticMode"] == "fixed":
        return "efficient"
    seed = hashlib.sha256(f'{p["seed"]}:{identity}:{step}'.encode()).hexdigest()
    return random.Random(seed).choices(["efficient", "capable"],
        [p["efficientWeight"], p["capableWeight"]])[0]
