"""规划路由 Jev／Laya 固定题比较的无网络测试。"""

import json

from experiments.evaluate_planning_jev import LAYER, _comparison, _render_markdown, load_suites, preflight


def test_preflight_freezes_only_planning_judge_suites():
    frozen = preflight(load_suites())
    assert frozen["caseCount"] == 78
    assert frozen["httpRequestsMaximum"] == 78
    assert frozen["httpRetries"] == 0
    assert set(frozen["suites"]) == {"task-audit", "task-holdout", "stage", "advisor", "escalation"}
    assert frozen["conservativeUsdUpperBound"] == 0.209664


def test_comparison_uses_case_id_and_preserves_both_outcomes(tmp_path):
    journal = []
    for name, filename in LAYER.items():
        (tmp_path / filename).write_text(json.dumps({"cases": [
            {"id": name, "expected": "accept", "outcome": "reject", "matched": False,
             "latencyMs": 10}]}))
        journal.append({"suite": name, "case": {"id": name, "expected": "accept",
            "outcome": "accept", "matched": True, "latencyMs": 20}})
    compared = _comparison(journal[::-1], tmp_path)
    assert all(result["jevMatched"] == 1 and result["layaMatched"] == 0
               for result in compared.values())
    assert compared["stage"]["cases"][0]["laya"] == "reject"
    rendered = _render_markdown({"actualRequests": 5, "actualUsd": .0001, "comparison": compared})
    assert "Task 开发题" in rendered and "Escalation 候选审核" in rendered
    assert "DAG 是否拆分属于自动路由" in rendered
