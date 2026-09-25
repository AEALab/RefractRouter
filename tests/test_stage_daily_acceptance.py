import json
from pathlib import Path

import pytest

from refractrouter.stage_daily_acceptance import (CAPABLE_MODEL, EFFICIENT_MODEL,
                                                  EFFICIENT_REASONING_EFFORT,
                                                  planning_config, preflight,
                                                  prepare, render_patch,
                                                  task_prompt)
from refractrouter.stage_study import load_protocol


ROOT = Path(__file__).parents[1]


def protocol():
    return load_protocol(ROOT / "data/benchmarks/stage-routing-v1.json")


def test_daily_preflight_is_zero_call_and_bounded():
    preview = preflight(protocol())
    assert preview["tasks"] == [
        {"id": "code-tdd-slug", "family": "code",
         "sha256": preview["tasks"][0]["sha256"]},
        {"id": "research-compare-search", "family": "research",
         "sha256": preview["tasks"][1]["sha256"]},
    ]
    assert preview["models"] == {
        "efficient": {"id": EFFICIENT_MODEL,
                      "reasoningEffort": EFFICIENT_REASONING_EFFORT},
        "capable": {"id": CAPABLE_MODEL,
                    "reasoningEffort": "provider-default"},
    }
    assert preview["limits"]["maxCallsPerTask"] == 8
    assert preview["limits"]["maxInputTokensPerCall"] == 32768
    assert preview["limits"]["maxOutputTokensPerCall"] == 4096
    assert preview["limits"]["maxProductionAfpPerTask"] == 66.3552
    assert preview["limits"]["maxProductionAfpTotal"] == 132.7104
    assert preview["evaluationAfp"] == 0
    assert preview["httpRetries"] == 0


def test_daily_config_uses_stage_trusted_ark_and_separate_task_budget():
    config = planning_config()
    assert config["defaultStrategy"] == "stage"
    assert config["maxCalls"] == 8
    assert config["maxProductionCostByUnit"] == {"AFP": 66.3552}
    assert [row["model"] for row in config["models"]] == [EFFICIENT_MODEL, CAPABLE_MODEL]
    assert config["models"][0]["reasoningEffort"] == "low"
    assert "reasoningEffort" not in config["models"][1]
    assert all(row["deployment"] == "trusted-cloud" for row in config["models"])
    assert config["security"]["maxPromptBytes"] == 131072
    patch = render_patch()
    assert "https://ark.cn-beijing.volces.com/api/plan/v3" in patch
    assert '"maxRetries":0' in patch
    assert '"reasoningEfforts":{"low":"low","high":"high","max":"max"}' in patch
    assert "tool-subagent" in patch
    assert "disabled: true" in patch


def test_code_only_preflight_has_independent_fingerprint_and_budget():
    both = preflight(protocol())
    code = preflight(protocol(), ("code-tdd-slug",))
    assert [row["id"] for row in code["tasks"]] == ["code-tdd-slug"]
    assert code["limits"]["maxProductionAfpTotal"] == 66.3552
    assert code["acceptanceSha256"] != both["acceptanceSha256"]


def test_prepare_creates_two_isolated_workspaces_and_refuses_overwrite(tmp_path):
    output = prepare(protocol(), tmp_path / "daily")
    preview = json.loads((output / "preflight.json").read_text())
    assert preview == preflight(protocol())
    assert (output / "workspaces/code-tdd-slug/SPEC.md").is_file()
    assert (output / "workspaces/research-compare-search/sources/S1.md").is_file()
    assert (output / "workspaces/code-tdd-slug/.refractagent/settings.yaml").read_text() == "{}\n"
    code_task = next(task for task in protocol()["tasks"] if task["id"] == "code-tdd-slug")
    research_task = next(task for task in protocol()["tasks"]
                         if task["id"] == "research-compare-search")
    assert "不要读取或修改 .refractagent" in task_prompt(code_task)
    assert "Cafe\\u0301 应输出 café" in task_prompt(code_task)
    assert "分别使用 [S1]、[S2] 或 [S3]" in task_prompt(research_task)
    assert (output / "workspaces/research-compare-search/TASK.md").read_text().endswith(
        "不得把其他来源标成 [S1]。\n")
    with pytest.raises(ValueError, match="拒绝覆盖"):
        prepare(protocol(), output)
