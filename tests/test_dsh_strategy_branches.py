from refractrouter.dsh_strategy_branches import (
    AUTHORIZED_AFP, STRATEGY_COUNTS, configuration, preflight,
)


def test_branch_matrix_and_preflight_fit_authorization():
    frozen = preflight()
    assert STRATEGY_COUNTS == {"stage": 6, "composite": 6, "advisor": 6, "escalation": 6}
    assert frozen["limits"]["authorizedCumulativeAfp"] == AUTHORIZED_AFP == 5000
    assert frozen["limits"]["maximumIncludingPriorAfp"] < AUTHORIZED_AFP
    assert frozen["limits"]["maximumRealModelCalls"] == 90
    assert frozen["realModelCalls"] == 0
    assert len(frozen["implementationDigest"]) == 64


def test_branch_configurations_use_real_routes_and_explicit_fixtures():
    for strategy in STRATEGY_COUNTS:
        config = configuration(strategy)
        assert config["defaultStrategy"] == strategy
        assert config["maxCalls"] == 10
    advisor = configuration("advisor")
    assert advisor["advisor"]["executor"] == "advisor-executor-fixture"
    assert advisor["advisor"]["judge"]["modelId"] == "efficient"
    composite = configuration("composite")
    assert composite["composite"]["judge"]["modelId"] == "composite-task-judge-fixture"
    escalation = configuration("escalation")
    assert escalation["escalation"]["initial"] == "escalation-initial-fixture"
    assert escalation["escalation"]["takeover"] == "capable"
    assert escalation["escalation"]["judge"]["modelId"] == "efficient"
