"""节点工具的真实核心选模、共享账本、证据与停止边界；不调用网络模型。"""
from copy import deepcopy
import json

import pytest

from refractrouter.node_tools import NAME, catalog
from refractrouter.planning_runtime import PlanningRuntime
from tests.test_planning_routing import configuration, receipt

PROFILE = {"enabled": True}
ARGS = {"intent": "check", "task": "核对价格", "context": "价格为 100 元。"}


def setup(tmp_path, *, cfg=None, profile=None, calls=1):
    runtime = PlanningRuntime(tmp_path)
    cfg = cfg or configuration("static")
    profile = profile or PROFILE
    run = runtime.handle({"op": "begin", "identity": {"session": "s", "agent": "a", "turn": 1},
        "config": cfg, "nodeTools": profile})["runId"]
    tools = catalog(profile)["tools"]
    action = runtime.handle({"op": "step", "runId": run, "messages": [{"role": "user", "content": "核对材料"}],
                             "tools": tools})
    issued = [{"type": "tool-call", "id": f"node-{i}", "name": NAME,
               "arguments": json.dumps(ARGS, ensure_ascii=False)} for i in range(calls)]
    receipt(runtime, run, action, tools=issued)
    return runtime, run


def node(runtime, run, id="node-0", args=None):
    return runtime.handle({"op": "node-tool-start", "runId": run,
                          "toolCallId": id, "name": NAME, "arguments": args or ARGS})


def artifact(runtime, run, action, **overrides):
    return receipt(runtime, run, action, content=json.dumps({"artifact": "已核对价格", "quotes": ["100 元"],
                                                            "limitations": []}, ensure_ascii=False), **overrides)


def test_three_nodes_share_parent_budget_and_receipts(tmp_path):
    cfg = configuration("static")
    cfg["maxCalls"] = 4
    r, run = setup(tmp_path, cfg=cfg, calls=3)
    tokens = []
    for i in range(3):
        action = node(r, run, f"node-{i}")
        assert action["tools"] == []  # 专家无工具入口，不构造 DAG 或递归。
        assert action["model"]["id"] == "small"
        result = artifact(r, run, action)
        tokens.append(action["callId"])
        assert result["action"] == "node-result"
        assert result["result"]["toolCallId"] == f"node-{i}"
        assert result["result"]["modelCallId"] == action["callId"]
        assert result["result"]["usage"]["input_tokens"] == 100
    r.handle({"op": "end", "runId": run})
    record = r.handle({"op": "query", "runId": run})
    assert record["status"] == "completed"
    assert len(record["calls"]) == 4
    assert len(list((tmp_path / "planning").glob("*.json"))) == 1
    assert [c["call_id"] for c in record["calls"][1:]] == tokens
    assert all(c["status"] == "billed" for c in record["calls"])
    assert all(i["status"] == "completed" for i in record["nodeTools"]["invocations"])
    assert record["costs"]["production"] == pytest.approx(sum(c["charged"] for c in record["calls"]))
    assert "offered" not in record["nodeTools"]


def test_default_off_and_unsupported_modes(tmp_path):
    assert catalog(None)["tools"] == []
    r = PlanningRuntime(tmp_path)
    run = r.handle({"op": "begin", "identity": {"session": "s", "agent": "a", "turn": 1},
                    "config": configuration("static")})["runId"]
    with pytest.raises(ValueError, match="未启用"):
        node(r, run)
    with pytest.raises(ValueError, match="仅支持"):
        setup(tmp_path / "advisor", cfg=configuration("advisor"))


@pytest.mark.parametrize("tools", [[], catalog(PROFILE)["tools"] * 2,
    [{**catalog(PROFILE)["tools"][0], "description": "篡改定义"}]])
def test_host_schema_registration_is_required(tmp_path, tools):
    r = PlanningRuntime(tmp_path)
    run = r.handle({"op": "begin", "identity": {"session": "s", "agent": "a", "turn": 1},
                    "config": configuration("static"), "nodeTools": PROFILE})["runId"]
    with pytest.raises(ValueError):
        r.handle({"op": "step", "runId": run, "messages": [{"role": "user", "content": "任务"}], "tools": tools})
    assert not r.runs[run]["budget"].records


def test_definition_limit_includes_host_tools(tmp_path):
    r, run = setup(tmp_path, profile={"enabled": True, "maxTools": 1})
    with pytest.raises(ValueError, match="合计"):
        r.handle({"op": "step", "runId": run, "messages": [{"role": "user", "content": "任务"}],
                  "tools": catalog(PROFILE)["tools"] + [{"name": "read"}]})


def test_calls_cannot_be_forged_changed_or_repeated(tmp_path):
    r, run = setup(tmp_path)
    with pytest.raises(ValueError, match="未由"):
        node(r, run, "forged")
    with pytest.raises(ValueError, match="不符"):
        node(r, run, args={**ARGS, "context": "篡改材料"})
    with pytest.raises(ValueError, match="已执行"):
        node(r, run)
    assert len(r.runs[run]["budget"].records) == 1
    assert r.handle({"op": "query", "runId": run})["nodeTools"]["invocations"][0]["status"] == "refused"


def test_parent_call_limit_also_bounds_expert(tmp_path):
    cfg = configuration("static")
    cfg["maxCalls"] = 1
    r, run = setup(tmp_path, cfg=cfg)
    with pytest.raises(ValueError, match="最大调用数"):
        node(r, run)
    assert len(r.runs[run]["budget"].records) == 1
    assert r.runs[run]["flow"] is None


def test_node_call_limit_is_separate_from_model_limit(tmp_path):
    r, run = setup(tmp_path, profile={"enabled": True, "maxNodeCalls": 1}, calls=2)
    artifact(r, run, node(r, run))
    with pytest.raises(ValueError, match="次数耗尽"):
        node(r, run, "node-1")
    assert len(r.runs[run]["budget"].records) == 2


def test_actual_expert_context_is_admitted_before_dispatch(tmp_path):
    cfg = configuration("static")
    cfg["security"] = {"sensitiveTerms": ["100 元"]}
    for m in cfg["models"]:
        m["deployment"] = "external-cloud"
    r, run = setup(tmp_path, cfg=cfg)
    with pytest.raises(ValueError, match="数据域"):
        node(r, run)
    assert len(r.runs[run]["budget"].records) == 1
    assert r.runs[run]["status"] == "running"


def test_unknown_usage_stops_with_reservation_and_no_retry(tmp_path):
    r, run = setup(tmp_path)
    action = node(r, run)
    reserved = r.runs[run]["budget"].records[-1]["charged"]
    with pytest.raises(ValueError):
        artifact(r, run, action, usageAvailable=False)
    record = r.handle({"op": "query", "runId": run})
    assert record["calls"][-1]["status"] == "unknown-usage"
    assert record["calls"][-1]["charged"] == reserved
    assert record["nodeTools"]["invocations"][0]["status"] == "usage-unknown"
    with pytest.raises(ValueError, match="停止"):
        node(r, run)


def test_cancelled_late_receipt_only_settles_once(tmp_path):
    r, run = setup(tmp_path)
    action = node(r, run)
    r.handle({"op": "cancel", "runId": run})
    assert artifact(r, run, action)["action"] == "stop"
    assert r.runs[run]["budget"].records[-1]["status"] == "billed"
    assert r.runs[run]["flow"] is None
    with pytest.raises(ValueError, match="已结算"):
        artifact(r, run, action)


def test_invalid_quote_bills_actual_call_then_stops(tmp_path):
    r, run = setup(tmp_path)
    action = node(r, run)
    with pytest.raises(ValueError, match="逐字子串"):
        receipt(r, run, action, content=json.dumps({"artifact": "错误", "quotes": ["不是原文"], "limitations": []}))
    assert r.runs[run]["budget"].records[-1]["status"] == "billed"
    assert r.runs[run]["status"] == "node-output-invalid"


def test_parallel_node_request_does_not_cancel_inflight(tmp_path):
    r, run = setup(tmp_path, calls=2)
    action = node(r, run)
    with pytest.raises(ValueError, match="未结算"):
        node(r, run, "node-1")
    assert r.runs[run]["status"] == "running"
    assert artifact(r, run, action)["action"] == "node-result"


def test_stage_reuses_existing_hold_policy_for_node(tmp_path):
    cfg = configuration("stage")
    r, run = setup(tmp_path, cfg=cfg)
    # 用既有 Stage 状态验证专家和主模型共用选模原语，而非 TS 或节点重新实现策略。
    r.runs[run]["state"]["hold"] = 1
    action = node(r, run)
    assert action["model"]["id"] == "large"
    artifact(r, run, action)
    record = r.handle({"op": "query", "runId": run})
    assert record["decisions"][-1]["reason"] == "capable-hold"
    assert record["decisions"][-1]["ruleVersion"] == "stage-v4"


def test_parent_money_limit_also_bounds_expert(tmp_path):
    r, run = setup(tmp_path)
    ledger = next(iter(r.runs[run]["budget"].ledgers.values()))
    ledger.limits["production"] = ledger.charged["production"] + .000001
    with pytest.raises(ValueError, match="预算"):
        node(r, run)
    assert len(r.runs[run]["budget"].records) == 1
    assert r.runs[run]["nodeTools"]["invocations"][0]["status"] == "refused"


@pytest.mark.parametrize("field", ["maxCalls", "timeoutMs"])
def test_experiment_requires_bounded_parent(tmp_path, field):
    cfg = configuration("static")
    cfg[field] = 0
    with pytest.raises(ValueError, match="有限"):
        setup(tmp_path, cfg=cfg)


def test_expert_cannot_delegate_again(tmp_path):
    r, run = setup(tmp_path)
    action = node(r, run)
    recursive = {"type": "tool-call", "id": "recursive", "name": NAME, "arguments": "{}"}
    with pytest.raises(ValueError, match="invalid or truncated"):
        receipt(r, run, action, tools=[recursive])
    record = r.handle({"op": "query", "runId": run})
    assert len(record["calls"]) == 2
    assert record["calls"][-1]["status"] == "billed"
    assert record["status"] == "node-output-invalid"
    assert record["nodeTools"]["invocations"][0]["status"] == "failed"


def test_core_directory_does_not_depend_on_dsh_types():
    directory = catalog(PROFILE)
    assert directory["owner"] == "python-core"
    assert set(directory["nodeMapping"]) == {"analyze", "check", "synthesize"}
    assert "session" not in json.dumps(directory)
