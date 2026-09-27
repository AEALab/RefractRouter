"""旧 DSH 事件合同兼容适配；新增宿主传递 host_evidence 事实。"""
import hashlib
import json

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


def _fingerprint_args(name, args):
    """移除不影响执行的宿主展示参数，保留其余工具实参。"""
    if not isinstance(args, dict):
        return args
    if name in ("bash", "pwsh", "shell"):
        return {key: value for key, value in args.items() if key != "description"}
    return args


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
                [name, _fingerprint_args(name, args), failure if status == "failed" else None],
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
