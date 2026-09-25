"""纯策略与工具轨迹归一；不调用模型、不执行宿主工具。"""
import hashlib
import json
import math
import random

STAGE_RULE_VERSION = "stage-v2"


def text_of(message):
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def _structured_exit_code(meta):
    """只读取宿主的结构化退出码，不从工具正文猜测成败。"""
    if not isinstance(meta, dict):
        return None
    for key in ("exitCode", "exit_code"):
        value = meta.get(key)
        if type(value) is int:
            return value
    for key in ("result", "outcome", "process"):
        nested = meta.get(key)
        if isinstance(nested, dict):
            value = _structured_exit_code(nested)
            if value is not None:
                return value
    return None


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
    # 原生事件提供当前轮身份、结构化失败来源；正文没有权限扩大这些元数据。
    source = {}
    calls_from_events = {}
    for event in native or []:
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            calls_from_events[data.get("callId")] = data
        if event.get("type") == "tool/result":
            for block in data.get("message", {}).get("content", []):
                if block.get("type") == "tool-result":
                    source[block.get("toolCallId")] = data
    calls, events = dict(calls_from_events), []
    for message in messages:
        for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
            if block.get("type") == "tool-call":
                calls[block.get("id")] = block
            if block.get("type") != "tool-result":
                continue
            if native is not None and block.get("toolCallId") not in source:
                continue
            call = calls.get(block.get("toolCallId"), {})
            name = call.get("name", "unknown").lower().split(".")[-1]
            args = call.get("arguments", "")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            # 仅使用结构化错误；工具正文中的指令和成败措辞没有控制权。
            native_result = source.get(block.get("toolCallId"), {})
            error = native_result.get("error") or block.get("error") or {}
            code = str(error.get("code", "")) if isinstance(error, dict) else ""
            error_name = str(error.get("name", "")) if isinstance(error, dict) else ""
            host_result = native_result.get("hostResult", {})
            sandbox = host_result.get("sandbox", {}) if isinstance(host_result, dict) else {}
            exit_code = (_structured_exit_code(host_result) if host_result
                         else _structured_exit_code(native_result.get("meta")))
            status = ("unconfirmed" if code in (
                    "EXECUTION_UNCONFIRMED", "UNKNOWN_RESULT", "ABORTED", "TOOL_RESULT_UNKNOWN")
                or (isinstance(host_result, dict) and (host_result.get("aborted") is True
                    or host_result.get("signal") is not None))
                else "denied" if code in (
                    "PERMISSION_DENIED", "APPROVAL_REJECTED", "FS_PERMISSION_DENIED",
                    "ABORTED_BEFORE_DISPATCH", "TOOL_ABORTED_BEFORE_DISPATCH", "TOOL_NOT_STARTED")
                or (isinstance(sandbox, dict) and sandbox.get("denied") is True)
                else "infrastructure" if code in (
                    "AUTH", "AUTHENTICATION", "TRANSPORT", "TIMEOUT", "NETWORK")
                or (isinstance(host_result, dict) and host_result.get("timedOut") is True)
                or (isinstance(sandbox, dict) and sandbox.get("runnerFailed") is True)
                else "failed" if (exit_code is not None and exit_code != 0)
                  or (block.get("isError") is True and code) else
                  "unclassified-error" if block.get("isError") is True else "completed")
            kind = ("mutate" if name in ("write", "write_file", "edit", "apply_patch", "str_replace")
                else "observe" if name in ("read", "read_file", "search", "web_search", "web_fetch", "grep", "glob")
                else "plan" if name in ("todo", "todo_write", "update_plan") else "unknown")
            failure = {"name": error_name, "code": code, "exitCode": exit_code}
            fingerprint = hashlib.sha256(json.dumps(
                [name, args, failure if status == "failed" else None],
                sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            event_id = ":".join(str(value) for value in (
                native_result.get("turn", "history"), native_result.get("step", "history"),
                block.get("toolCallId")))
            events.append({"id": event_id, "callId": block.get("toolCallId"),
                           "turn": native_result.get("turn"), "step": native_result.get("step"),
                           "tool": name, "kind": kind, "status": status,
                           "fingerprint": fingerprint,
                           **({"failure": failure} if status == "failed" else {})})
    return events


def stage_decision(events, state, p, default):
    """计算一次 Stage 决策；保持轮数包含触发升级的当前调用。"""
    events = [{**event, "id": event.get("id") or
               f"legacy:{index}:{event.get('fingerprint', 'unknown')}"}
              for index, event in enumerate(events)]
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
        severity = len(failures) / len(window) if len(failures) >= 2 else 0
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
