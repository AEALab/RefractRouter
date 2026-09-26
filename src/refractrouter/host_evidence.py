"""宿主中立的工具证据合同；策略只消费事实，不执行工具。"""
from copy import deepcopy

EVIDENCE_VERSION = "refract-tool-evidence-v1"
STATUSES = {"completed", "failed", "denied", "infrastructure", "unconfirmed", "unclassified-error", "unclassified"}


def validate_evidence(events):
    """按身份去重；同身份的矛盾事实必须停止，不能任选其一。"""
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("无效工具证据列表")
    unique = {}
    for event in events:
        if not isinstance(event, dict) or event.get("status") not in STATUSES:
            raise ValueError("无效工具证据状态")
        for key in ("id", "callId", "tool", "fingerprint"):
            if not isinstance(event.get(key), str) or not event[key]:
                raise ValueError("工具证据缺少身份或指纹")
        if event.get("kind") not in ("mutate", "observe", "plan", "unknown"):
            raise ValueError("无效工具类别")
        previous = unique.get(event["id"])
        if previous is not None and previous != event:
            raise ValueError("同一工具证据身份包含矛盾结果")
        unique[event["id"]] = deepcopy(event)
    return list(unique.values())
