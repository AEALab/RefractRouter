"""原始用量审计不重复计算思考、不掩盖错账，并绑定同一时刻的证据快照。"""
import hashlib
import json

import pytest

import experiments.audit_node_tool_pilot as audit


MODEL = {"api_model": "deepseek-v4-flash", "max_output_tokens": 384000,
         "input_cost_per_1k": .05, "output_cost_per_1k": .05, "cached_input_cost_per_1k": .05}


def fixture(tmp_path):
    directory = tmp_path / "r1"
    wire = directory / "wire"
    wire.mkdir(parents=True)
    usage = {"input_tokens": 100, "output_tokens": 200,
             "output_tokens_details": {"reasoning_tokens": 150}}
    response = {"type": "response.completed", "response": {"id": "resp", "status": "completed",
                "model": "deepseek-v4-flash-ga-260731", "usage": usage}}
    (wire / "001-response.txt").write_text("data: " + json.dumps(response) + "\n\n")
    (wire / "001-request.json").write_text(json.dumps({"model": MODEL["api_model"], "max_output_tokens": 384000}))
    row = {"runId": "r1", "phase": "prompt-audit", "arm": "one-shot", "status": "completed",
           "factStatus": "fail", "chargedOrReserved": .015,
           "checks": [{"check": "value", "status": "pass"}, {"check": "value:sources", "status": "fail"}],
           "calls": [{"call_id": "c1", "status": "billed", "charged": .015,
                      "input_tokens": 100, "output_tokens": 200, "reasoning_tokens": 0}]}
    frozen = {"model": MODEL, "protocolSha256": "protocol", "priorResults": [],
              "cumulativeModelCallLimit": 135, "productionAfpUpperBound": 286}
    return directory, row, frozen


def test_reasoning_is_in_total_output_and_zero_cache_rate_is_valid():
    usage = {"input_tokens": 100, "output_tokens": 200,
             "output_tokens_details": {"reasoning_tokens": 150}}
    assert audit.expected_afp(usage, MODEL) == .015
    usage["input_tokens_details"] = {"cached_tokens": 100}
    assert audit.expected_afp(usage, {**MODEL, "cached_input_cost_per_1k": 0}) == .01
    usage["input_tokens"] = True
    with pytest.raises(ValueError, match="用量字段"):
        audit.expected_afp(usage, MODEL)


def test_native_detail_loss_does_not_hide_wrong_charges(tmp_path):
    directory, row, frozen = fixture(tmp_path)
    result = audit.audit_case(row, directory, frozen)
    assert result["errors"] == []
    assert result["notes"] and result["receipts"][0]["providerReasoningTokens"] == 150
    assert result["failedValueChecks"] == [] and len(result["failedCitationChecks"]) == 1
    row["calls"][0]["charged"] = .02
    assert any("AFP 与账本" in e for e in audit.audit_case(row, directory, frozen)["errors"])
    path = directory / "wire/001-response.txt"
    path.write_text(path.read_text() * 2)
    with pytest.raises(ValueError, match="一个终态"):
        audit.terminal_receipt(path)


def test_snapshot_hash_stays_bound_when_live_summary_advances(tmp_path, monkeypatch):
    _, row, frozen = fixture(tmp_path)
    summary = {"simulated": False, "status": "running", "runs": [row], "protocolSha256": "protocol",
               "realModelCalls": 1, "actualOrReservedAfp": .015,
               "cumulativeRealModelCalls": 1, "cumulativeActualOrReservedAfp": .015}
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(summary))
    (tmp_path / "frozen.json").write_text(json.dumps(frozen))
    original = audit.audit_case
    def advance(*args):
        path.write_text(json.dumps({**summary, "status": "new-state"}))
        return original(*args)
    monkeypatch.setattr(audit, "audit_case", advance)
    snapshot = tmp_path / "snapshot.json"
    result = audit.audit(tmp_path, snapshot_path=snapshot)
    assert result["integrityStatus"] == "pass" and result["completeness"] == "pending"
    assert result["summarySha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert result["summarySha256"] != audit.sha(path)


def test_encoding_failure_is_not_reported_as_clean_field_checks(tmp_path):
    directory, row, frozen = fixture(tmp_path)
    row.update(checks=[], qualityError="Invalid control character")
    result = audit.audit_case(row, directory, frozen)
    assert result["errors"] == []  # 费用一致与交付可接受是不同结论。
    assert result["deliveryParseError"] == "Invalid control character"
    assert result["fieldChecksAvailable"] is False
    assert any("空字段检查列表" in note for note in result["notes"])


def test_archived_snapshot_can_be_rechecked_after_live_summary_changes(tmp_path):
    _, row, frozen = fixture(tmp_path)
    summary = {"simulated": False, "status": "running", "runs": [row], "protocolSha256": "protocol",
               "realModelCalls": 1, "actualOrReservedAfp": .015,
               "cumulativeRealModelCalls": 1, "cumulativeActualOrReservedAfp": .015}
    saved = tmp_path / "saved.snapshot.json"
    saved.write_text(json.dumps(summary))
    (tmp_path / "frozen.json").write_text(json.dumps(frozen))
    (tmp_path / "summary.json").write_text(json.dumps({"status": "later-state"}))
    result = audit.audit(tmp_path, summary_path=saved)
    assert result["integrityStatus"] == "pass" and result["cohortSamples"] == 1
    assert result["summarySha256"] == audit.sha(saved)
