"""纯策略与工具轨迹归一；不调用模型、不执行宿主工具。"""
import hashlib
import json
import math
import random


def text_of(message):
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


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
            error = source.get(block.get("toolCallId"), {}).get("error") or block.get("error") or {}
            code = str(error.get("code", "")) if isinstance(error, dict) else ""
            status = ("unconfirmed" if code in ("EXECUTION_UNCONFIRMED", "UNKNOWN_RESULT", "ABORTED")
                else "denied" if code in ("PERMISSION_DENIED", "APPROVAL_REJECTED", "FS_PERMISSION_DENIED", "ABORTED_BEFORE_DISPATCH")
                else "infrastructure" if code in ("AUTH", "TRANSPORT", "TIMEOUT")
                else "failed" if block.get("isError") is True and code else
                  "unclassified-error" if block.get("isError") is True else "completed")
            kind = ("mutate" if name in ("write", "write_file", "edit", "apply_patch", "str_replace")
                else "observe" if name in ("read", "read_file", "search", "web_search", "web_fetch", "grep", "glob")
                else "plan" if name in ("todo", "todo_write", "update_plan") else "unknown")
            fingerprint = hashlib.sha256(json.dumps([name, args, code], sort_keys=True).encode()).hexdigest()
            events.append({"id": block.get("toolCallId"), "kind": kind, "status": status,
                           "fingerprint": fingerprint})
    return events


def stage(events, state, p, default):
    window = events[-p["window"]:]
    if any(e["status"] == "unconfirmed" for e in window):
        raise ValueError("工具结果未确认，停止续接")
    failures = [e for e in window if e["status"] == "failed"]
    repeated = len(failures) >= 2 and failures[-1]["fingerprint"] == failures[-2]["fingerprint"]
    if repeated:
        return "capable", "repeated-failure", p["holdTurns"], 1.0
    if state["hold"] > 0:
        return "capable", "capable-hold", state["hold"] - 1, None
    if not window:
        return default, "no-signal", 0, 0.0
    # 借鉴有符号 tanh 信号；持续检索本身不视为空转，未知工具不假定成功。
    severity = len(failures) / len(window) if len(failures) >= 2 else 0
    spinning = float(repeated)
    production = sum(e["kind"] == "mutate" and e["status"] == "completed" for e in window) / len(window)
    score = math.tanh(.5 * (severity / .7 + spinning - production / .7))
    if abs(score) <= p["threshold"]:
        return default, "ambiguous", 0, score
    target = "capable" if score > 0 else "efficient"
    return target, "tool-signal", p["holdTurns"] if target == "capable" else 0, score


def static_choice(p, identity, step):
    if p["staticMode"] == "fixed":
        return "efficient"
    seed = hashlib.sha256(f'{p["seed"]}:{identity}:{step}'.encode()).hexdigest()
    return random.Random(seed).choices(["efficient", "capable"],
        [p["efficientWeight"], p["capableWeight"]])[0]
