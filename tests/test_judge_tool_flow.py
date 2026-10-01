"""真实 Judge 验收驱动的零调用边界和离线账本恢复。"""

import json

from experiments import replay_tool_judges_jev
from experiments.validate_real_judge_tool_flow import (SCENARIOS, preflight,
                                                       summarize_existing)
from refractrouter.advisor_decision import decision_request, llm_messages


def test_four_tool_flows_have_bounded_zero_call_preflight():
    for scenario in SCENARIOS:
        _, frozen = preflight(scenario)
        assert frozen["scenario"] == scenario
        assert frozen["maxRemoteJudgeCalls"] == 2
        assert frozen["maximumAfp"] == 6.656
        assert frozen["httpRetries"] == 0


def test_advisor_contract_distinguishes_required_tool_omission_from_external_unknown():
    request = decision_request([{"role": "user", "content": "调用工具后再回答"}], [],
                               {"content": "工具已经执行", "toolCalls": []}, .8)
    rule = llm_messages(request)[0]["content"]
    assert "已接受历史和可信事件都没有相应调用或结果" in rule
    assert "应选 REDO" in rule
    assert "一般外部事实不明" in rule


def test_existing_receipts_can_be_summarized_without_dispatch(tmp_path):
    output = tmp_path / "batch"
    archive = output / "runs/planning"
    archive.mkdir(parents=True)
    (output / "client-stdout.txt").write_text(json.dumps({"status": "pass",
                                                           "hostTools": 1}) + "\n")
    (output / "client-stderr.txt").write_text("")
    (archive / "run.json").write_text(json.dumps({"calls": [
        {"purpose": "execute", "disposition": "accepted", "charged": 0},
        {"purpose": "advisor", "disposition": "consult", "charged": .03}],
        "decisions": [{"reason": "advisor-approved"}]}))
    result = summarize_existing("advisor-normal", output)
    assert result["clientCompleted"] is True
    assert result["remoteJudgeCalls"] == 1
    assert result["chargedJudgeAfp"] == .03
    assert result["hostToolResultReceived"] is True
    assert result["decisionReasons"] == ["advisor-approved"]


def test_jev_replay_is_frozen_to_completed_synthetic_tool_traces(tmp_path, monkeypatch):
    monkeypatch.setattr(replay_tool_judges_jev, "SOURCE", tmp_path)
    for flow, labels in replay_tool_judges_jev.FLOWS.items():
        archive = tmp_path / flow / "runs/planning"
        archive.mkdir(parents=True)
        purpose = "advisor" if flow.startswith("advisor") else "escalation"
        calls = [{"purpose": purpose, "status": "billed",
                  "request_messages": [{"role": "system", "content": "审核规则"},
                                       {"role": "user", "content": json.dumps({"task": "合成任务"})}],
                  "response_output": json.dumps({"verdict": label})}
                 for label in labels]
        (archive / "run.json").write_text(json.dumps({"status": "completed", "calls": calls}))
    rows, fingerprints = replay_tool_judges_jev.load()
    frozen = replay_tool_judges_jev.preflight(rows, fingerprints)
    assert len(rows) == 6
    assert frozen["maximumRequests"] == 6
    assert frozen["maximumUsd"] == .016128
    assert frozen["httpRetries"] == 0
