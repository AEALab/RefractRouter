"""验证整任务冻结的真实风险：泄漏、变量混淆、失败分母与虚假付费准入。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.whole_task_protocol import digest, freeze_study, validate_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def contract():
    return json.loads((ROOT / "data/whole-task-routing/evaluation-contract-v1.json").read_text())


@pytest.fixture
def tasks():
    return [{"taskId": "dev-1", "sourceGroup": "source-dev", "kind": "cross-file-code",
             "split": "development", "materialSha256": "a" * 64, "criteriaSha256": "b" * 64},
            {"taskId": "hold-1", "sourceGroup": "source-hold", "kind": "cross-file-code",
             "split": "holdout", "materialSha256": "c" * 64, "criteriaSha256": "d" * 64}]


@pytest.fixture
def arms():
    return [{"armId": name, "routeSnapshotSha256": route * 64, "toolsSha256": tools * 64,
             "hostSnapshotSha256": "c" * 64, "deliveryContractSha256": "d" * 64}
            for name, route, tools in (("S0", "a", "b"), ("W0", "e", "b"), ("WF", "e", "f"))]


def test_freeze_is_zero_call_immutable_and_not_paid_admission(contract, tasks, arms):
    comparisons = [{"baseline": "S0", "candidate": "W0", "factor": "routing"},
                   {"baseline": "W0", "candidate": "WF", "factor": "tools"}]
    result = freeze_study(contract, tasks, arms, comparisons)
    assert result["modelCalls"] == 0 and not result["liveExecutionReady"]
    assert result["blockingRequirements"]
    assert result["splitCounts"] == {"development": 1, "holdout": 1}
    assert result["sha256"] == digest(result["snapshot"])
    tasks[0]["taskId"] = "mutated"
    assert result["snapshot"]["tasks"][0]["taskId"] == "dev-1"


@pytest.mark.parametrize("change", [
    {"failureDenominator": "successful-only"}, {"unknownQuality": "passed"},
    {"outputLimit": "cheap-cap"}, {"httpRetries": 1}, {"httpRetries": False},
    {"billing": "sum-cash-and-afp"}, {"unknownUsage": "release"},
    {"hiddenEvaluation": "available-to-tools"}, {"insufficientEvidence": "auto-expand"},
    {"costComponents": ["accepted-answer-only"]},
])
def test_cannot_weaken_frozen_rules(contract, change):
    contract["rules"].update(change)
    with pytest.raises(ValueError):
        validate_contract(contract)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "0", "1.0", 0.03, True, "-0.03"])
def test_reject_nonfinite_or_ambiguous_numeric_thresholds(contract, value):
    contract["acceptance"]["qualityMargin"] = value
    with pytest.raises(ValueError):
        validate_contract(contract)


@pytest.mark.parametrize("field,value", [("criticalErrorsAllowed", 1), ("criticalErrorsAllowed", False),
    ("positiveSavingsInBothHalves", False), ("intervalUnit", "repeats")])
def test_critical_quality_and_independence_are_required(contract, field, value):
    contract["acceptance"][field] = value
    with pytest.raises(ValueError):
        validate_contract(contract)


@pytest.mark.parametrize("field,value", [("qualityMargin", "0.04"), ("confidence", "0.90"),
                                         ("minimumSavings", "0.10")])
def test_cannot_relax_agreed_acceptance_thresholds(contract, field, value):
    contract["acceptance"][field] = value
    with pytest.raises(ValueError, match="不得放宽"):
        validate_contract(contract)


@pytest.mark.parametrize("field,value", [("taskId", "dev-1"), ("materialSha256", "a" * 64),
    ("sourceGroup", "source-dev"), ("criteriaSha256", "missing"), ("split", "test-later")])
def test_reject_duplicate_changed_or_leaking_tasks(contract, tasks, arms, field, value):
    tasks[1][field] = value
    with pytest.raises(ValueError):
        freeze_study(contract, tasks, arms, [{"baseline": "S0", "candidate": "W0", "factor": "routing"}])


def test_exposed_material_never_becomes_holdout(contract, tasks, arms):
    with pytest.raises(ValueError, match="已暴露"):
        freeze_study(contract, tasks, arms, [], exposed_materials={"c" * 64})


@pytest.mark.parametrize("key", ["hostSnapshotSha256", "deliveryContractSha256"])
def test_same_host_and_deliverable_required(contract, tasks, arms, key):
    arms[1][key] = "9" * 64
    with pytest.raises(ValueError, match="相同宿主"):
        freeze_study(contract, tasks, arms, [{"baseline": "S0", "candidate": "W0", "factor": "routing"}])


def test_cannot_attribute_tools_and_models_together_to_routing(contract, tasks, arms):
    with pytest.raises(ValueError, match="相同工具"):
        freeze_study(contract, tasks, arms, [{"baseline": "S0", "candidate": "WF", "factor": "routing"}])
    with pytest.raises(ValueError, match="相同模型"):
        freeze_study(contract, tasks, arms, [{"baseline": "S0", "candidate": "WF", "factor": "tools"}])


def test_missing_duplicate_or_self_comparisons_rejected(contract, tasks, arms):
    pair = {"baseline": "S0", "candidate": "W0", "factor": "routing"}
    for pairs in ([], [pair, deepcopy(pair)], [{**pair, "candidate": "missing"}],
                  [{**pair, "candidate": "S0"}], [{**pair, "factor": "both"}]):
        with pytest.raises(ValueError):
            freeze_study(contract, tasks, arms, pairs)


def test_freeze_cli_uses_new_file_and_explicit_exposure_registry(tmp_path, contract, tasks, arms):
    from experiments.freeze_whole_task_study import main
    study, registry, output = (tmp_path / name for name in ("study.json", "exposed.json", "frozen.json"))
    study.write_text(json.dumps({"contract": contract, "tasks": tasks, "arms": arms,
        "comparisons": [{"baseline": "S0", "candidate": "W0", "factor": "routing"}]}))
    registry.write_text("[]")
    args = ["--study", str(study), "--exposed-materials", str(registry), "--output", str(output)]
    assert main(args) == 0
    result = json.loads(output.read_text())
    assert result["sha256"] == digest(result["snapshot"])
    with pytest.raises(FileExistsError):
        main(args)
    registry.write_text(json.dumps(["c" * 64]))
    with pytest.raises(ValueError, match="已暴露"):
        main(args)
    with pytest.raises(SystemExit):
        main(args + ["--execute"])
