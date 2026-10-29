"""图表保留缺失、格式和事实差别；无需 Matplotlib 或网络。"""
from copy import deepcopy
import pytest

from experiments.plot_node_tool_pilot import TASKS, category, collect, metric


def sample():
    return {"phase": "comparison", "taskId": "procurement-versions", "repeat": 1, "arm": "one-shot",
            "status": "completed", "factStatus": "fail", "chargedOrReserved": .5, "taskElapsedMs": 1200,
            "checks": [{"check": "cost", "status": "pass"}, {"check": "cost:sources", "status": "fail"}]}


def test_plot_preserves_format_missing_and_source_distinctions():
    row = sample()
    assert category(None) == "missing" and category(row) == "sources"
    assert category({**row, "checks": [], "qualityError": "Invalid control character"}) == "format"
    assert category({**row, "checks": []}) == "unassessed"
    assert category({**row, "checks": [{"check": "cost", "status": "pending"}]}) == "unassessed"
    assert category({**row, "status": "failed"}) == "execution"
    assert category({**row, "checks": [{"check": "cost", "status": "fail"}]}) == "values"
    assert metric(None, "chargedOrReserved") is None
    assert metric(row, "taskElapsedMs") == 1.2
    assert metric({**row, "chargedOrReserved": 0}, "chargedOrReserved") == 0
    for value in (float("nan"), float("inf"), -1, True):
        with pytest.raises(ValueError, match="未知值"):
            metric({"chargedOrReserved": value}, "chargedOrReserved")


def test_plot_rejects_incomplete_rehearsal_and_duplicate_matrix():
    frozen = {"protocolSha256": "sha", "tasks": dict.fromkeys(TASKS)}
    summary = {"protocolSha256": "sha", "simulated": False, "status": "running", "runs": [sample()]}
    with pytest.raises(ValueError, match="尚未完成"):
        collect(summary, frozen)
    rows, complete = collect(summary, frozen, allow_partial=True)
    assert len(rows) == 1 and complete is False
    with pytest.raises(ValueError, match="演练"):
        collect({**summary, "simulated": True}, frozen, allow_partial=True)
    with pytest.raises(ValueError, match="重复"):
        collect({**summary, "runs": [sample(), deepcopy(sample())]}, frozen, allow_partial=True)
    with pytest.raises(ValueError, match="身份"):
        collect({**summary, "runs": [{**sample(), "repeat": 4}]}, frozen, allow_partial=True)


def test_complete_plot_requires_all_27_comparisons_baseline_and_pairs():
    frozen = {"protocolSha256": "sha", "tasks": dict.fromkeys(TASKS)}
    comparisons = [{**sample(), "taskId": tid, "repeat": repeat, "arm": arm}
                   for tid in TASKS for repeat in range(1, 4) for arm in ("one-shot", "node-as-tool", "dag")]
    baseline = [{"phase": "prompt-audit"} for _ in range(18)]
    summary = {"protocolSha256": "sha", "simulated": False, "status": "completed-development-pilot",
               "runs": comparisons + baseline, "pairs": [{} for _ in range(18)]}
    assert collect(summary, frozen)[1] is True
    for incomplete in ({**summary, "pairs": []}, {**summary, "runs": summary["runs"][:-1]},
                       {**summary, "runs": comparisons + [{"phase": "other"}] + baseline[1:]}):
        with pytest.raises(ValueError, match="尚未完成"):
            collect(incomplete, frozen)
