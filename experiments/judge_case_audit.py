"""冻结 Judge 题集的宿主协议与证据来源检查；不调用模型。"""


def validate_escalation_case(case):
    candidate = case["candidate"]
    calls = candidate.get("toolCalls", [])
    if not isinstance(calls, list) or any(not isinstance(call, dict) or not call.get("id")
                                           or not call.get("name") for call in calls):
        raise ValueError(f"{case['id']} 的候选工具调用无效")
    if len({call["id"] for call in calls}) != len(calls):
        raise ValueError(f"{case['id']} 的工具调用 ID 重复")
    if (case["finishReason"] == "tool_calls") != bool(calls):
        raise ValueError(f"{case['id']} 的 finishReason 与工具调用不一致")
    if case["finishReason"] not in ("tool_calls", "stop"):
        raise ValueError(f"{case['id']} 的结束原因未经题集验收")
    if case["expected"] not in ("PROCEED", "DEFECT", "STALL", "UNCERTAIN"):
        raise ValueError(f"{case['id']} 的标签无效")
    if case.get("evidence"):
        prior_calls, results = set(), set()
        for message in case.get("history", []):
            for block in message["content"] if isinstance(message["content"], list) else []:
                if block.get("type") == "tool-call" and message["role"] == "assistant":
                    prior_calls.add(block.get("id"))
                if block.get("type") == "tool-result" and message["role"] == "user":
                    results.add(block.get("toolCallId"))
        if not results or not results <= prior_calls or None in results:
            raise ValueError(f"{case['id']} 的历史工具结果未经配对")
        if any(event.get("callId") not in results for event in case["evidence"]):
            raise ValueError(f"{case['id']} 的工具证据未关联已完成调用")


def validate_advisor_case(case):
    if case["expected"] not in ("APPROVE", "REDO", "UNRESOLVED"):
        raise ValueError(f"{case['id']} 的标签无效")
    if not case.get("requiresTrustedToolResult"):
        return
    calls, results = set(), set()
    for message in case["messages"]:
        for block in message["content"] if isinstance(message["content"], list) else []:
            if block.get("type") == "tool-call" and message["role"] == "assistant":
                calls.add(block.get("id"))
            if block.get("type") == "tool-result" and message["role"] == "user":
                results.add(block.get("toolCallId"))
    if not results or not results <= calls or None in results:
        raise ValueError(f"{case['id']} 缺少成对的宿主工具结果")
    event_calls = {event.get("callId") for event in case.get("events", [])}
    if not results <= event_calls:
        raise ValueError(f"{case['id']} 的工具事件未关联到已完成调用")


def validate_suite(suite):
    kind = suite["schemaVersion"]
    validator = {"escalation-judge-suite-v2": validate_escalation_case,
                 "advisor-judge-suite-v2": validate_advisor_case}.get(kind)
    if validator is None:
        raise ValueError("只检查新版题集，历史原始题集不追改")
    cases = suite["cases"]
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("题集案例 ID 重复")
    for case in cases:
        validator(case)
