"""官方 Jev Choice 的实验性分动作门槛；不改变现有在线 Judge 配置。"""

from __future__ import annotations

import math


VERSION = "jev-choice-action-gate-v1-experimental"

# 返工、接管与工具探索可恢复；最终批准和最终放行要求更高的所选项概率。
# 这些值仅是待独立留出题校准的候选规则，不代表概率已校准为正确率。
THRESHOLDS = {
    "advisor:APPROVE": (0.55, 0.80),
    "advisor:REDO_REQUIREMENT": (0.55, 0.70),
    "advisor:REDO_EVIDENCE": (0.55, 0.70),
    "escalation:PROCEED:tool": (0.55, 0.70),
    "escalation:PROCEED:final": (0.55, 0.80),
    "escalation:DEFECT": (0.55, 0.70),
    "escalation:STALL": (0.55, 0.70),
}


def evaluate_choice(answer: dict, *, strategy: str, finish_reason: str | None = None) -> dict:
    """校验原始分布后决定是否采用首选类别；门槛不覆盖明确弃权。"""
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        raise ValueError("Jev Choice 答案类型不符")
    choice, probabilities = answer.get("choice"), answer.get("probabilities")
    confidence = answer.get("confidence")
    if (not isinstance(probabilities, dict) or not probabilities
            or choice not in probabilities
            or type(confidence) not in (int, float) or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
            or any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
                   for p in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > .02
            or probabilities[choice] < max(probabilities.values())):
        raise ValueError("Jev Choice 概率或 confidence 无效")
    key = f"{strategy}:{choice}"
    if key == "escalation:PROCEED":
        key += ":tool" if finish_reason == "tool_calls" else ":final"
    if (strategy == "advisor" and choice == "UNRESOLVED") or (
            strategy == "escalation" and choice == "UNCERTAIN"):
        accepted, reason, minimum_confidence, minimum_probability = True, "explicit-abstain", None, None
    else:
        if key not in THRESHOLDS:
            raise ValueError("Jev Choice 返回未知动作")
        minimum_confidence, minimum_probability = THRESHOLDS[key]
        accepted = confidence >= minimum_confidence and probabilities[choice] >= minimum_probability
        reason = "threshold-passed" if accepted else "threshold-not-met"
    return {"ruleVersion": VERSION, "rawChoice": choice,
            "choiceConfidence": float(confidence),
            "selectedProbability": float(probabilities[choice]),
            "minimumConfidence": minimum_confidence,
            "minimumProbability": minimum_probability,
            "accepted": accepted, "reason": reason}
