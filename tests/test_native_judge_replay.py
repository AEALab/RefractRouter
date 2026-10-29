"""当前业务解析器对历史结构化记录的无模型重放，不继承旧期望为金标。"""
import json
from pathlib import Path

import pytest

from refractrouter.native_judge_replay import CONTRACTS, parse_native, replay_archives
from refractrouter.stage_hybrid import QUESTIONS


ROOT = Path(__file__).resolve().parents[1]


def test_all_four_existing_contracts_replay_real_archives_without_inventing_raw_responses():
    manifest = json.loads((ROOT / "data/judge-regression-v1/native-archives.json").read_text())
    result = replay_archives(ROOT, manifest)
    groups = {g["purpose"]: g for g in result["groups"]}
    assert {p: g["total"] for p, g in groups.items()} == {
        "task-fit": 8, "stage-progress": 16, "advisor-delivery": 24, "escalation-takeover": 24}
    assert result["modelCalls"] == 0
    assert result["historicalScoresModified"] is False
    for group in groups.values():
        assert group["qualified"] is False
        assert group["semanticGoldAvailable"] is False
        assert group["predictions"]["FORMAT_REJECT"] == 0
        for row in group["decisions"]:
            assert row["conversionMatchesArchive"] is True
            assert row["rawSha256"] is None
            assert row["wireStatus"] == "unavailable"
            assert row["semanticStatus"] == "unknown"


def stage(progress, route):
    choices = {"progress": progress, "route": route}
    return {key: {"choice": choice, "probabilities": {option: 1. if option == choice else 0.
            for option in QUESTIONS[key]["criteria"]}} for key, choice in choices.items()}


@pytest.mark.parametrize("purpose,payload,context,expected", [
    ("task-fit", {"rawPerCandidate": [{"candidateId": "a", "score": .9, "missingInformation": 0.}]},
     {"candidateIds": ["a"], "targetCandidateId": "a", "threshold": .8}, "ALLOW"),
    ("task-fit", {"rawPerCandidate": [{"candidateId": "a", "score": .9, "missingInformation": .8}]},
     {"candidateIds": ["a"], "targetCandidateId": "a", "threshold": .8}, "UNKNOWN"),
    ("stage-progress", stage("NORMAL_EXPLORATION", "EFFICIENT"),
     {"upgradeThreshold": .8, "downgradeThreshold": .9}, "ALLOW"),
    ("stage-progress", stage("STALLED", "CAPABLE"),
     {"upgradeThreshold": .8, "downgradeThreshold": .9}, "BLOCK"),
    ("advisor-delivery", {"verdict": "REDO", "feedback": "候选说退出码0，实际为2，请纠正。"}, {}, "BLOCK"),
    ("advisor-delivery", {"verdict": "UNRESOLVED"}, {}, "UNKNOWN"),
    ("escalation-takeover", {"verdict": "DEFECT", "confidence": .95, "evidenceIds": ["e"], "reason": "候选与事件矛盾。"},
     {"evidenceIds": ["e"], "threshold": .8}, "BLOCK"),
    ("escalation-takeover", {"verdict": "DEFECT", "confidence": .6, "evidenceIds": ["e"], "reason": "低把握判别。"},
     {"evidenceIds": ["e"], "threshold": .8}, "UNKNOWN"),
])
def test_native_meanings_and_unknowns_use_current_business_parsers(purpose, payload, context, expected):
    raw = json.dumps(payload, ensure_ascii=False)
    result = parse_native(purpose, CONTRACTS[purpose], raw, context, input_kind="raw-json")
    assert result["prediction"] == expected
    assert result["rawSha256"] is not None
    assert result["wireStatus"] == "pass"
    assert result["semanticStatus"] == "unknown"


@pytest.mark.parametrize("raw,context", [
    ('{"verdict":"APPROVE","verdict":"REDO"}', {}),
    ('{"verdict":"APPROVE","confidence":NaN}', {}),
    ('{"verdict":"REDO"}', {}),
    ('{"verdict":"APPROVE"}', {"unexpected": 1}),
])
def test_malformed_native_response_is_format_rejection_not_semantic_failure(raw, context):
    result = parse_native("advisor-delivery", "advisor-review-v2", raw, context, input_kind="raw-json")
    assert result["prediction"] == "FORMAT_REJECT"
    assert result["semanticStatus"] == "unknown"


def test_forged_evidence_and_missing_candidate_cannot_be_replayed_as_pass():
    bad = {"verdict": "PROCEED", "confidence": 1., "evidenceIds": ["invented"], "reason": "不可信。"}
    result = parse_native("escalation-takeover", "escalation-decision-v1", bad,
                          {"evidenceIds": [], "threshold": .8}, input_kind="archived-normalized-decision")
    assert result["prediction"] == "FORMAT_REJECT"
    result = parse_native("task-fit", "task-decision-v2", {"rawPerCandidate": []},
                          {"candidateIds": ["a"], "targetCandidateId": "a", "threshold": .8},
                          input_kind="archived-normalized-decision")
    assert result["prediction"] == "FORMAT_REJECT"
    with pytest.raises(ValueError, match="合同不匹配"):
        parse_native("advisor-delivery", "stage-decision-v2", {}, {}, input_kind="raw-json")


def test_unknown_purpose_and_empty_contract_cannot_fall_through_to_escalation():
    with pytest.raises(ValueError, match="合同不匹配"):
        parse_native("unregistered-purpose", None,
                     {"verdict": "PROCEED", "confidence": 1., "evidenceIds": [], "reason": "允许"},
                     {"evidenceIds": [], "threshold": .8}, input_kind="archived-normalized-decision")


@pytest.mark.parametrize("purpose,payload,context", [
    ("task-fit", {}, {"candidateIds": ["a"], "targetCandidateId": "a", "threshold": .8}),
    ("stage-progress", {}, {"upgradeThreshold": .8, "downgradeThreshold": .9}),
    ("advisor-delivery", {"verdict": "REDO"}, {}),
    ("escalation-takeover", {}, {"evidenceIds": [], "threshold": .8}),
])
def test_valid_json_contract_rejection_preserves_wire_success(purpose, payload, context):
    result = parse_native(purpose, CONTRACTS[purpose], json.dumps(payload), context, input_kind="raw-json")
    assert result["wireStatus"] == "pass"
    assert result["contractStatus"] == "rejected"
    assert result["prediction"] == "FORMAT_REJECT"
