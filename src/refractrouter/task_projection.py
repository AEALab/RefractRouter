"""保留来源的当前任务投影；身份与任务边界来自接入层，不按提示相似度合并。"""
from copy import deepcopy
import hashlib
import json

VERSION = "current-task-projection-v1"
ENVIRONMENT = {"plugin", "skill-catalog", "compaction", "summary"}


def hashed(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def instruction(message):
    source = message.get("source") or {}
    if message.get("role") != "user" or source.get("kind", "user") != "user":
        return None
    blocks = message.get("content", [])
    if isinstance(blocks, str):
        blocks = [{"type": "text", "text": blocks}]
    # tool-result 内的文字不是新要求；原生 user 文本和附件才属于用户输入。
    blocks = [b for b in blocks if b.get("type") in {"text", "image", "video", "file"}]
    if not blocks:
        return None
    identifier = message.get("id")
    if identifier is not None and (not isinstance(identifier, str) or not identifier or len(identifier) > 256):
        raise ValueError("无效宿主用户消息身份")
    return {"messageId": identifier, "digest": hashed(blocks), "content": deepcopy(blocks)}


def public_blocks(blocks):
    return [{"type": b["type"], "source": "attachment-metadata"}
            if b.get("type") in {"image", "video", "file"} else deepcopy(b) for b in blocks]


def project(messages, previous=None):
    """首次取最后一条直接用户输入；后续保留初始要求，追加明确的新要求。

    有宿主 messageId 时按 ID 区分相同正文；无 ID 只去重连续同内容指导，
    不据此合并任务、预算或权限。宿主摘要只作背景，不能替换初始任务。
    """
    inputs = [value for m in messages if (value := instruction(m)) is not None]
    state = deepcopy(previous) if previous else {"version": VERSION, "initial": None, "guidance": [],
                                                "observedInputs": [], "seenMessageIds": {}}
    if not inputs:
        return state
    signatures = [{k: value[k] for k in ("messageId", "digest")} for value in inputs]
    seen = state.setdefault("seenMessageIds", {})
    validated = dict(seen)
    for value in inputs:
        identifier = value["messageId"]
        if identifier in validated and validated[identifier] != value["digest"]:
            raise ValueError("同一宿主用户消息身份的正文发生矛盾变化")
        if identifier is not None:
            validated[identifier] = value["digest"]
    if not state["initial"] and inputs:
        state["initial"] = inputs[-1]
    else:
        observed = state.get("observedInputs", [])
        overlap = next((n for n in range(min(len(observed), len(signatures)), 0, -1)
                        if observed[-n:] == signatures[:n]), 0)
        for value in inputs[overlap:]:
            if value["messageId"] is not None and value["messageId"] in seen:
                continue
            last = state["guidance"][-1] if state["guidance"] else state["initial"]
            if value["messageId"] is None and value["digest"] == last["digest"]:
                continue  # 仅连续正文重放去重；恢复更早的要求仍然追加。
            state["guidance"].append(value)
            if value["messageId"] is not None:
                seen[value["messageId"]] = value["digest"]
    seen.update(validated)
    if len(seen) > 10000 or len(signatures) > 10000 or len(state["guidance"]) > 10000:
        raise ValueError("任务指导超过技术容量，不能静默丢弃")
    state["observedInputs"] = signatures
    return state


def judge_view(messages, projection=None):
    projection = project(messages) if projection is None else projection
    history = []
    for message in messages:
        source = message.get("source") or {}
        kind = source.get("kind")
        if message.get("role") == "system" or kind in {"plugin", "skill-catalog"}:
            continue
        blocks = message.get("content", [])
        if isinstance(blocks, str):
            blocks = [{"type": "text", "text": blocks}]
        content = []
        for block in blocks:
            typ = block.get("type")
            if typ == "reasoning":
                continue
            if typ in {"image", "video", "file"}:
                # 二进制、URL 和私有 replay 不进入判别文本。
                content.append({"type": typ, "source": "attachment-metadata"})
            elif typ == "tool-result":
                content.append({"type": typ, "toolCallId": block.get("toolCallId"),
                                "source": "tool-text", "content": deepcopy(block.get("content", []))})
            else:
                content.append(deepcopy(block))
        history.append({"role": message["role"], "source": "host-summary" if kind in ENVIRONMENT
                        else "assistant-claim" if message["role"] == "assistant" else "request",
                        "content": content})
    current = projection["initial"]["content"] if projection.get("initial") else []
    latest = projection["guidance"][-1]["content"] if projection.get("guidance") else current
    return {"projectionVersion": VERSION, "task": public_blocks(current),
            "latestUserInstruction": public_blocks(latest), "guidance": [
                {**g, "content": public_blocks(g["content"])} for g in projection["guidance"]],
            "history": history}


def summary(projection):
    if not projection:
        return None
    return {"version": VERSION, "initialDigest": (projection.get("initial") or {}).get("digest"),
            "guidanceDigests": [g["digest"] for g in projection["guidance"]],
            "taskCategory": "unknown"}
