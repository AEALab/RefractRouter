"""独立研究保留题的校准来源、隔离与累计额度。"""

import pytest

from experiments.run_task_research_holdout import _inputs, prepare, preflight
from refractrouter.ark_plan import catalog


def test_research_holdout_preflight_counts_unknown_usage_reservation():
    protocol, task, cards = _inputs()
    result = preflight(protocol, task, cards, catalog())
    assert result["maximumModelCalls"] == 18
    assert result["maximumProductionAfp"] == 344.3616
    assert result["priorAfpWorstCase"] == 95.25155
    assert result["maximumIncludingPriorAfp"] == 439.61315
    assert cards["deepseek-v4-flash"] != cards["deepseek-v4.1-flash"]


def test_research_holdout_prepares_three_independent_workspaces(tmp_path, monkeypatch):
    # CI 不下载本地 Judge 权重；这里只检查独立工作区和冻结补丁。
    monkeypatch.setattr("experiments.run_task_quality_pilot.preview",
                        lambda raw: {"strategies": [{"id": raw["defaultStrategy"],
                                                      "available": True, "issues": []}]})
    protocol, task, cards = _inputs()
    output = tmp_path / "holdout"
    result = prepare(protocol, task, cards, output)
    assert len(result["runs"]) == 3
    assert len(list((output / "workspaces").iterdir())) == 3
    assert all((path / "sources/S1.md").exists() for path in (output / "workspaces").iterdir())
    with pytest.raises(ValueError, match="已存在"):
        prepare(protocol, task, cards, output)
