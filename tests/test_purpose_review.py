"""分用途候选合同回归：仅证明机械约束，不模拟真实评审准确率。"""
from copy import deepcopy
import json

import pytest

from refractrouter.purpose_review import (
    PURPOSES, decode, inspect_review, llm_messages, packet, parse_review, span, wire,
)


def fixture(purpose="advisor-delivery"):
    value = packet(purpose, "据材料回答并保留限制。",
                   [{"id": "facts", "text": "事实与来源相符。"},
                    {"id": "scope", "text": "每条引用支持对应主张。"}],
                   "中文😀\r\n事实与限制。", [{"id": "source", "text": "来源😀\r\n原文。"}])
    result = {"contract": value["contract"], "purpose": purpose,
              "packetSha256": value["packetSha256"],
              "coverage": {"candidate": "full", "requirements": ["facts", "scope"]},
              "checks": [{"requirementId": key, "status": "PASS", "reason": "本例只是协议探针。",
                          "candidateRefs": [span(value["candidate"], 2, 3)],
                          "sourceRefs": [span(value["sources"][0]["text"], 2, 3, source_id="source")]}
                         for key in ("facts", "scope")], "verdict": "ALLOW"}
    return value, result


@pytest.mark.parametrize("purpose", PURPOSES)
def test_purposes_have_separate_hashed_contracts_and_no_quality_claim(purpose):
    value, result = fixture(purpose)
    messages = llm_messages(value)
    assert PURPOSES[purpose] in messages[0]["content"]
    assert json.loads(messages[1]["content"]) == value
    parsed = parse_review(wire(result), value)
    assert parsed["verdict"] == "ALLOW"
    assert parsed["mechanicallyValid"] is True
    assert parsed["semanticValidityProven"] is False
    assert parsed["coverageIsSelfReported"] is True
    assert value["packetSha256"] != fixture(next(p for p in PURPOSES if p != purpose))[0]["packetSha256"]


@pytest.mark.parametrize("mutation", [
    lambda r: r["checks"].pop(),
    lambda r: r["checks"].append(deepcopy(r["checks"][0])),
    lambda r: r["checks"][1].update(requirementId="facts"),
    lambda r: r["coverage"].update(candidate="selected-fields"),
    lambda r: r["coverage"].update(requirements=["facts"]),
    lambda r: r.update(purpose="task-fit"),
    lambda r: r.update(packetSha256="0" * 64),
    lambda r: r["checks"][0]["candidateRefs"][0].update(quote="😀误"),
    lambda r: r["checks"][0]["candidateRefs"][0].update(start=3, end=7),
    lambda r: r["checks"][0]["sourceRefs"][0].update(sourceId="hidden-answer"),
    lambda r: r["checks"][0]["sourceRefs"][0].update(sha256="0" * 64),
    lambda r: r["checks"][0].update(candidateRefs=[]),
    lambda r: r["checks"][0].update(reason=" "),
    lambda r: r["checks"][0].update(status="FAIL"),
])
def test_sparse_or_forged_evidence_cannot_pass_the_wire_contract(mutation):
    value, result = fixture()
    mutation(result)
    with pytest.raises(ValueError):
        parse_review(wire(result), value)


def test_unknown_and_definite_failure_are_distinct_and_candidate_changes_invalidate_review():
    value, result = fixture()
    result["checks"][0].update(status="UNKNOWN", candidateRefs=[], sourceRefs=[])
    result["verdict"] = "UNKNOWN"
    assert parse_review(wire(result), value)["verdict"] == "UNKNOWN"
    result["checks"][1]["status"] = "FAIL"
    result["verdict"] = "BLOCK"
    assert parse_review(wire(result), value)["verdict"] == "BLOCK"
    changed = deepcopy(value)
    changed["candidate"] += "新增一个未审查断言。"
    with pytest.raises(ValueError, match="漂移"):
        parse_review(wire(result), changed)


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}',
                                 '{"x":"\\ud800"}', '[' * 100 + '0' + ']' * 100])
def test_raw_response_rejects_ambiguous_or_unencodable_json(raw):
    with pytest.raises(ValueError):
        decode(raw)


@pytest.mark.parametrize("value", [(1, 2), {1: "x"}, {"nested": float("inf")}, 2 ** 5000])
def test_public_wire_does_not_coerce_non_json_values(value):
    with pytest.raises(ValueError):
        wire(value)


def test_full_material_is_copied_not_summarized_or_replaced_by_selected_quotes():
    requirements = [{"id": "all", "text": "全文符合要求。"}]
    sources = [{"id": "s", "text": "完整来源😀\r\n末尾。"}]
    value = packet("advisor-delivery", "任务", requirements, "完整候选", sources)
    sources[0]["text"] = "外部修改"
    requirements.clear()
    assert value["sources"][0]["text"] == "完整来源😀\r\n末尾。"
    assert len(value["requirements"]) == 1
    with pytest.raises(ValueError, match="容量"):
        packet("advisor-delivery", "任务", value["requirements"], "a" * 262145, [])


@pytest.mark.parametrize("text", ["", " ", "\r\n\t"])
def test_blank_requirement_cannot_be_used_as_a_placeholder_to_approve_a_candidate(text):
    with pytest.raises(ValueError, match="全部验收要求"):
        packet("advisor-delivery", "任务", [{"id": "r", "text": text}], "正文", [])


@pytest.mark.parametrize("purpose", [[], {}, True, None])
def test_non_string_purpose_uses_normal_invalid_input_path(purpose):
    with pytest.raises(ValueError, match="用途"):
        packet(purpose, "任务", [{"id": "r", "text": "要求"}], "正文", [])


def test_wire_schema_binding_and_semantics_are_separate_records():
    value, result = fixture()
    good = inspect_review(wire(result), value)
    assert good["bindingStatus"] == "pass" and good["semanticStatus"] == "unknown"
    assert inspect_review("{", value)["rejectedLayer"] == "wire"
    incomplete = deepcopy(result)
    incomplete["checks"].pop()
    assert inspect_review(wire(incomplete), value)["rejectedLayer"] == "schema"
    unrelated = deepcopy(result)
    unrelated["checks"][0]["candidateRefs"][0]["quote"] = "伪造"
    observed = inspect_review(wire(unrelated), value)
    assert observed["rejectedLayer"] == "binding"
    assert observed["prediction"] == "FORMAT_REJECT" and observed["semanticStatus"] == "unknown"
    invalid_packet = deepcopy(value)
    invalid_packet["candidate"] += "另一个候选"
    with pytest.raises(ValueError, match="漂移"):
        inspect_review(wire(result), invalid_packet)
