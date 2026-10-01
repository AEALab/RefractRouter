"""Jev 分动作实验门槛的无网络安全边界。"""

import json

import pytest

from experiments.calibrate_jev_choice_gate import load_cases, make_request, preflight, score
from refractrouter.jev_choice_gate import VERSION, evaluate_choice
from refractrouter.jev_decision import JEV_MODEL, JevDecisionAdapter


def answer(choice, probabilities, confidence):
    return {"type": "choice", "choice": choice,
            "probabilities": probabilities, "confidence": confidence}


def test_repair_can_pass_without_lowering_final_approval():
    redo = evaluate_choice(answer("REDO_EVIDENCE", {
        "REDO_EVIDENCE": .70, "REDO_REQUIREMENT": .26,
        "APPROVE": .03, "UNRESOLVED": .01}, .59), strategy="advisor")
    approval = evaluate_choice(answer("APPROVE", {
        "APPROVE": .70, "REDO_EVIDENCE": .20,
        "REDO_REQUIREMENT": .09, "UNRESOLVED": .01}, .60), strategy="advisor")
    assert redo["accepted"] is True
    assert redo["minimumProbability"] == .70
    assert approval["accepted"] is False
    assert approval["minimumProbability"] == .80


def test_tool_continuation_and_final_release_have_different_gates():
    raw = answer("PROCEED", {"PROCEED": .75, "DEFECT": .15,
                             "STALL": .07, "UNCERTAIN": .03}, .66)
    assert evaluate_choice(raw, strategy="escalation", finish_reason="tool_calls")["accepted"]
    assert not evaluate_choice(raw, strategy="escalation", finish_reason="stop")["accepted"]


def test_confidence_is_a_real_guard_and_explicit_abstention_is_preserved():
    raw = answer("DEFECT", {"DEFECT": .78, "PROCEED": .10,
                            "STALL": .08, "UNCERTAIN": .04}, .54)
    assert not evaluate_choice(raw, strategy="escalation")["accepted"]
    abstain = evaluate_choice(answer("UNRESOLVED", {"UNRESOLVED": .40,
        "APPROVE": .35, "REDO_EVIDENCE": .20, "REDO_REQUIREMENT": .05}, .10), strategy="advisor")
    assert abstain["accepted"] and abstain["reason"] == "explicit-abstain"


def test_one_global_seventy_percent_gate_would_approve_a_wrong_final_answer():
    # 新留出题 a-zh-wrong-sum 的原始回执：用户要 7+5，候选答 13。
    raw = answer("APPROVE", {"APPROVE": .77, "REDO_REQUIREMENT": .20,
                             "REDO_EVIDENCE": .02, "UNRESOLVED": .01}, .70)
    assert raw["confidence"] >= .55 and raw["probabilities"]["APPROVE"] >= .70
    assert not evaluate_choice(raw, strategy="advisor")["accepted"]


@pytest.mark.parametrize("raw", [
    answer("APPROVE", {"APPROVE": .6, "REDO_EVIDENCE": .5}, .7),
    answer("APPROVE", {"APPROVE": .4, "REDO_EVIDENCE": .6}, .7),
    answer("APPROVE", {"APPROVE": 1.0}, float("nan")),
])
def test_malformed_choice_fails_closed(raw):
    with pytest.raises(ValueError):
        evaluate_choice(raw, strategy="advisor")


def test_experimental_adapter_preserves_legacy_and_records_both_measures():
    raw = answer("REDO_EVIDENCE", {"REDO_EVIDENCE": .70,
        "REDO_REQUIREMENT": .26, "APPROVE": .03, "UNRESOLVED": .01}, .59)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self):
            return json.dumps({"model": JEV_MODEL, "answers": {"review": raw},
                               "usage": {"input_tokens": 100, "output_tokens": 20}}).encode()
    transport = lambda _request, timeout: Response()
    request = {"contract": "advisor-local-review-v2", "messages": [], "events": [],
               "candidate": {"content": "已完成", "toolCalls": []}, "threshold": .8}
    legacy = JevDecisionAdapter(api_key="test-only", transport=transport).decide_advisor(request)
    experimental = JevDecisionAdapter(api_key="test-only", transport=transport,
                                      action_gate=VERSION).decide_advisor(request)
    assert legacy.payload["verdict"] == "UNRESOLVED"
    assert experimental.payload["verdict"] == "REDO"
    assert experimental.payload["choiceConfidence"] == .59
    assert experimental.payload["selectedProbability"] == .70
    assert experimental.payload["choiceGate"]["ruleVersion"] == VERSION


def test_holdout_is_frozen_and_zero_call_preflight_has_bounded_usd():
    cases, suite_sha = load_cases()
    frozen = preflight(cases, suite_sha)
    assert len({case["id"] for case in cases}) == 24
    assert frozen["maximumRequests"] == 24
    assert frozen["maximumUsd"] == .064512
    assert frozen["httpRetries"] == 0
    for case in cases:
        request = make_request(case)
        assert request["candidate"] == case["candidate"]
        assert request["threshold"] == .8


def test_holdout_scoring_flags_wrong_delivery_even_when_gate_passes():
    case = {"strategy": "advisor", "expected": "REDO"}
    verdict = score(case, {"raw": answer("APPROVE", {
        "APPROVE": .83, "REDO_REQUIREMENT": .11,
        "REDO_EVIDENCE": .04, "UNRESOLVED": .02}, .57)})
    assert verdict["unsafeLegacy"] and verdict["unsafeProposed"]
