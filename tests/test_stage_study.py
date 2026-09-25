"""Stage 三路线冻结实验的零调用合同。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import refractrouter.stage_study as stage_study
from refractrouter.stage_study import (_judge_payload, _metrics, load_protocol, planning_config,
                                       pilot_preflight, preflight, prepare, prepare_live_pilot,
                                       render_dsh_patch, run_paid_batch, schedule, summarize)


PROTOCOL = Path("data/benchmarks/stage-routing-v1.json")


def test_frozen_protocol_builds_72_interleaved_runs_and_afp_envelope():
    protocol = load_protocol(PROTOCOL)
    assert protocol["design"]["reasoningEffort"] == "provider-default"
    rows = schedule(protocol)
    assert len(rows) == 72
    assert {row["arm"] for row in rows} == {"static-flash", "static-pro", "stage"}
    assert all(sum(r["taskId"] == task["id"] for r in rows) == 6 for task in protocol["tasks"])
    result = preflight(protocol)
    assert result["stageRuleVersion"] == "stage-v3"
    assert result["runs"] == 72
    assert result["maxExecutionCalls"] == 1440
    assert result["evaluationCalls"] == 36
    assert result["maxCallsIncludingEvaluation"] == 1476
    assert result["callUpperBoundByModel"] == {
        "deepseek-v4.1-flash": 504, "deepseek-v4-pro": 972}
    assert set(result["dshPatchSha256"]) == {"static-flash", "static-pro", "stage"}
    assert result["afpUpperBound"]["production"] > result["afpUpperBound"]["evaluation"] > 0
    assert result["afpUpperBound"]["total"] == pytest.approx(
        result["afpUpperBound"]["production"] + result["afpUpperBound"]["evaluation"])


def test_paid_batch_rejects_unfrozen_reasoning_effort(tmp_path):
    protocol = load_protocol(PROTOCOL)
    protocol["design"]["reasoningEffort"] = "provider-default-pending-live-capability-check"
    with pytest.raises(ValueError, match="推理档位能力尚未冻结"):
        run_paid_batch(protocol, tmp_path)


def test_live_pilot_freezes_authorized_envelope(tmp_path):
    protocol = load_protocol(PROTOCOL)
    preview = pilot_preflight(protocol)
    assert preview["stageRuleVersion"] == "stage-v3"
    assert preview["profile"] == "headless"
    assert preview["maxCalls"] == 6
    assert preview["maxProductionAfp"] == pytest.approx(221.184)
    assert preview["evaluationAfp"] == 0
    assert preview["httpRetries"] == 0
    output = prepare_live_pilot(protocol, tmp_path / "pilot")
    patch = (output / "stage-pilot.patch.yml").read_text()
    assert '"runsDir":".refractagent/runs"' in patch
    assert '"path":".refractagent/settings.yaml","watch":false' in patch
    assert (output / "workspace" / ".refractagent" / "settings.yaml").read_text() == "{}\n"
    assert '"maxCalls":6' in patch
    assert '"AFP":221.184' in patch
    assert "maxRetries\":0" in patch
    assert "tool-subagent\n  disabled: true" in patch
    with pytest.raises(ValueError, match="拒绝覆盖"):
        prepare_live_pilot(protocol, output)


def test_dsh_invocation_resolves_patch_before_changing_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    patch = tmp_path / "pilot.yml"
    patch.write_text("[]\n")
    captured = {}

    def fake_run(command, **kwargs):
        captured.update(command=command, kwargs=kwargs)
        return stage_study.subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(stage_study.subprocess, "run", fake_run)
    outcome, _ = stage_study._invoke_dsh("web", patch, workspace, "prompt", 1000)
    assert outcome.returncode == 0
    assert captured["command"][4] == str(patch.resolve())
    assert captured["kwargs"]["cwd"] == workspace.resolve()


def test_prepare_materializes_isolated_workspaces_without_hidden_checks(tmp_path):
    protocol = load_protocol(PROTOCOL)
    output = tmp_path / "batch"
    rows = prepare(protocol, output)
    assert len(rows) == 72
    first = output / "workspaces" / rows[0]["runId"]
    assert (first / "TASK.md").is_file()
    assert (first / ".refractagent" / "settings.yaml").read_text() == "{}\n"
    assert {path.name for path in (output / "patches").iterdir()} == {
        "static-flash.yml", "static-pro.yml", "stage.yml", "research-judge.yml"}
    assert not any("hidden" in path.name.lower() for path in first.rglob("*"))
    with pytest.raises(ValueError, match="已存在"):
        prepare(protocol, output)


def test_summary_keeps_failures_in_denominator_and_units_per_success():
    protocol = load_protocol(PROTOCOL)
    records = []
    for index, row in enumerate(schedule(protocol)[:6]):
        records.append({**row, "success": index % 2 == 0, "productionAfp": 10,
                        "evaluationAfp": 1 if row["family"] == "research" else 0,
                        "firstByteMs": 100 + index, "elapsedMs": 1000 + index,
                        "modelSwitches": 1 if row["arm"] == "stage" else 0,
                        "capableCalls": 1, "modelCalls": 2,
                        **({"failureReason": "task-failed"} if index % 2 else {})})
    result = summarize(protocol, records)
    assert not result["complete"]
    assert result["observedRuns"] == 6
    assert sum(arm["runs"] for arm in result["arms"].values()) == 6
    assert all(arm["successRate"] is None or 0 <= arm["successRate"] <= 1
               for arm in result["arms"].values())


def test_protocol_rejects_category_drift(tmp_path):
    raw = json.loads(PROTOCOL.read_text())
    raw["tasks"][0]["category"] = "tdd"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="类别"):
        load_protocol(path)


def test_dsh_patches_use_planning_static_baselines_and_disable_delegation():
    protocol = load_protocol(PROTOCOL)
    flash = planning_config(protocol, "static-flash")
    pro = planning_config(protocol, "static-pro")
    stage = planning_config(protocol, "stage")
    assert flash["defaultStrategy"] == pro["defaultStrategy"] == "static"
    assert flash["roles"]["efficient"] == "flash"
    assert pro["roles"]["efficient"] == "pro"
    assert stage["defaultStrategy"] == "stage"
    assert stage["roles"] == {"efficient": "flash", "capable": "pro"}
    assert stage["maxCalls"] == 20 and stage["timeoutMs"] == 900000
    assert all(model["contextWindow"] == 1024000 for model in stage["models"])
    patch = render_dsh_patch(protocol, "stage")
    assert '"provider":"refractagent","model":"planning"' in patch
    assert "https://ark.cn-beijing.volces.com/api/plan/v3" in patch
    assert "maxRetries\":0" in patch
    assert "tool-subagent\n  disabled: true" in patch
    assert "ARK_API_KEY" in patch and "apiKey" not in patch.replace("apiKeyEnv", "")


def test_record_metrics_require_settled_usage_and_detect_recovery():
    record = {"costsByUnit": {"AFP": {"production": 3}}, "calls": [
        {"purpose": "execute", "status": "billed", "actual_model": "deepseek-v4.1-flash", "ttft_ms": 20},
        {"purpose": "execute", "status": "billed", "actual_model": "deepseek-v4-pro", "ttft_ms": 30},
        {"purpose": "execute", "status": "billed", "actual_model": "deepseek-v4.1-flash", "ttft_ms": 10},
    ]}
    result = _metrics(record)
    assert result["modelCalls"] == 3 and result["capableCalls"] == 1
    assert result["modelSwitches"] == 2 and result["recovered"]
    assert result["firstByteMs"] == 20 and result["productionAfp"] == 3
    record["calls"][1]["status"] = "unknown-usage"
    with pytest.raises(RuntimeError, match="用量未知"):
        _metrics(record)


def test_research_judge_requires_strict_json_contract():
    valid = _judge_payload('说明\n{"score":82,"criticalFactError":false,"fabricatedCitation":false}')
    assert valid["valid"] and valid["score"] == 82
    assert not _judge_payload('{"score":"82","criticalFactError":false,"fabricatedCitation":false}')["valid"]
    assert not _judge_payload("APPROVE")["valid"]
