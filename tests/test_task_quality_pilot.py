"""冻结 Task 小样本的任务分割和 AFP 上界。"""

from copy import deepcopy
import json

import pytest

from experiments.preflight_task_quality_pilot import PROTOCOL, ROOT, preflight
from experiments.run_task_quality_pilot import _cards, _config, _patch, prepare
from refractrouter.ark_plan import catalog
from refractrouter.task_budget import request_input_bound


def inputs():
    protocol = json.loads(PROTOCOL.read_text())
    tasks = json.loads((ROOT / protocol["taskSource"]).read_text())
    return protocol, tasks


def test_task_quality_pilot_preflight_freezes_disjoint_tasks_and_cost():
    protocol, tasks = inputs()
    result = preflight(protocol, tasks, catalog())
    assert result["realModelCalls"] == 0
    assert result["maximumRuns"] == 10
    assert result["maximumModelCalls"] == 60
    assert result["maximumProductionAfp"] == 839.5008
    assert result["maximumIncludingPriorAfp"] == 869.4838
    assert result["modelCostUpperPerCallAfp"] == {
        "deepseek-v4-flash": 4.1152, "deepseek-v4.1-flash": 20.576}
    assert request_input_bound([{"role": "user", "content": "x" * 60000}]) <= \
        protocol["limits"]["maxRequestBytesPerCall"] + 256
    assert len({(row["split"], row["taskId"], row["arm"]) for row in result["runs"]}) == 10
    assert result["judgeApiAfp"] == 0


def test_task_quality_pilot_preflight_rejects_holdout_leakage():
    protocol, tasks = inputs()
    protocol = deepcopy(protocol)
    protocol["holdout"][0] = protocol["calibration"][0]
    with pytest.raises(ValueError, match="互不重叠"):
        preflight(protocol, tasks, catalog())


def test_task_quality_pilot_preflight_uses_dearest_candidate_for_task_bound():
    protocol, tasks = inputs()
    result = preflight(protocol, tasks, catalog())
    task_runs = [row for row in result["runs"] if row["arm"] == "task-choice-v2"]
    strong_runs = [row for row in result["runs"] if row["arm"] == "static-v4.1-flash"
                   and row["split"] == "holdout"]
    assert [row["costUpperAfp"] for row in task_runs] == \
        [row["costUpperAfp"] for row in strong_runs]


def test_task_quality_pilot_prepares_isolated_workspaces_and_routes(tmp_path, monkeypatch):
    # 本测试只验证冻结文件与路线编译；本地权重就绪由运行期零调用诊断覆盖。
    monkeypatch.setattr("experiments.run_task_quality_pilot.preview",
                        lambda raw: {"strategies": [{"id": raw["defaultStrategy"],
                                                      "available": True, "issues": []}]})
    protocol, tasks = inputs()
    output = tmp_path / "pilot"
    evidence = prepare(protocol, tasks, output)
    assert len(list((output / "workspaces").iterdir())) == evidence["maximumRuns"]
    with pytest.raises(ValueError, match="已存在"):
        prepare(protocol, tasks, output)
    for arm in ("static-flash", "static-v4.1-flash", "task-choice-v2"):
        config = _config(protocol, arm, {}, 123.456)
        assert config["defaultStrategy"] == ("task" if arm == "task-choice-v2" else "static")
        assert config["security"]["maxPromptBytes"] == 80000
        patch = _patch(protocol, arm, {}, 123.456)
        assert "rr:task" in patch if arm == "task-choice-v2" else "rr:static" in patch
        assert "maxRetries" in patch and "\"maxRetries\":0" in patch


def test_task_quality_pilot_calibration_cards_only_use_real_results():
    rows = [{"split": "calibration", "family": family, "arm": arm,
             "exitCode": 0, "metrics": {"modelCalls": 1},
             "evaluation": {"success": family == "code" and arm == "static-flash"}}
            for family in ("code", "research") for arm in ("static-flash", "static-v4.1-flash")]
    cards = _cards(rows)
    assert "代码" not in cards["deepseek-v4-flash"]  # 能力卡只使用协议中的 family 标识
    assert "code校准：通过" in cards["deepseek-v4-flash"]
    assert "code校准：未通过" in cards["deepseek-v4.1-flash"]
    with pytest.raises(ValueError, match="不完整"):
        _cards(rows[:-1])
    rows[0]["exitCode"] = 124
    with pytest.raises(ValueError, match="未完整运行"):
        _cards(rows)
