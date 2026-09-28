"""Composite 有限验收协议。"""
from experiments.preflight_composite_acceptance import preflight


def test_composite_acceptance_preflight_is_zero_paid_call_and_bounded():
    report = preflight()
    assert report["billingUpperBounds"] == {"AFP": 0, "CNY": 0}
    assert report["flows"]["clientNormal"]["clients"] == ["dsh", "codex", "hermes"]
    assert report["flows"]["trustedFailure"]["maximumUpstreamCalls"] == 6
    assert report["flows"]["localLaya"]["maximumForwards"] == 2
