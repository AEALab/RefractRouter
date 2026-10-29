"""校准门槛的确定性算术测试；人工构造观察不是模型或独立样本证据。"""
from copy import deepcopy

import pytest

from refractrouter.judge_qualification import interval, qualify
from refractrouter.purpose_review import digest


BACKEND = {"provider": "fixture", "model": "fixture-judge", "modelRevision": "fixture-r1",
           "templateSha256": "a" * 64, "contractVersion": "purpose-review-v1", "scoreThreshold": None}
POLICY = {"minNegative": 50, "minPositive": 50, "maxFalseAllowUpper": .05,
          "maxFalseBlockUpper": .15, "maxUnknownRate": .1, "maxFormatRejectRate": .05}


def row(case_id, *, label="FAIL", prediction="BLOCK", kind="historical-regression", backend=None,
        purpose="advisor-delivery", cluster=None):
    return {"caseId": case_id, "clusterId": cluster or case_id, "sampleKind": kind,
            "purpose": purpose, "backend": deepcopy(backend or BACKEND), "prediction": prediction,
            "adjudication": {"label": label, "method": "pending" if label == "UNKNOWN" else
                             "source-counterexample" if label == "FAIL" else "explicit-acceptance",
                             "recordSha256": digest({"testOnly": case_id})}}


def key(value):
    return digest({"purpose": value["purpose"], "backend": value["backend"]})


def independent():
    return [row(f"n-{i}", kind="independent-calibration") for i in range(60)] + [
        row(f"p-{i}", label="PASS", prediction="ALLOW", kind="independent-calibration") for i in range(60)]


def test_zero_denominator_is_unknown_and_small_zero_error_sample_is_not_safe():
    assert interval(0, 0)["upper"] is None
    assert interval(0, 2)["upper"] > .5
    assert interval(0, 50)["upper"] > .05
    assert interval(0, 60)["upper"] < .05


def test_empty_or_missing_exact_policy_cannot_admit_a_backend():
    assert qualify([], {})["allObservedGroupsQualified"] is False
    v = row("known-bad", prediction="ALLOW")
    report = qualify([v], {})["groups"][0]
    assert report["falseAllow"]["numerator"] == 1
    assert report["falseAllow"]["denominator"] == 1
    assert report["qualified"] is False
    assert "confirmed-counterexample-approved" in report["reasons"]


def test_known_regression_overrides_large_zero_error_independent_batch_without_changing_raw_prediction():
    rows = independent()
    report = qualify(rows, {key(rows[0]): POLICY})
    assert report["allObservedGroupsQualified"] is True  # 只验证算术，不是实际模型准入。
    rows.append(row("old-confirmed-miss", prediction="ALLOW"))
    before = deepcopy(rows)
    report = qualify(rows, {key(rows[0]): POLICY})
    assert report["allObservedGroupsQualified"] is False
    assert report["groups"][0]["independentFalseAllow"]["numerator"] == 0
    assert report["groups"][0]["falseAllow"]["numerator"] == 1
    assert rows == before
    assert report["productionConfigurationChanged"] is False
    assert report["modelCalls"] == 0


def test_format_unknown_and_misclassification_have_distinct_denominators():
    rows = [row("miss", prediction="ALLOW"), row("format", prediction="FORMAT_REJECT"),
            row("unknown", prediction="UNKNOWN"), row("false-block", label="PASS", prediction="BLOCK"),
            row("undecided", label="UNKNOWN", prediction="ALLOW")]
    result = qualify(rows, {})["groups"][0]
    assert result["falseAllow"]["denominator"] == 3
    assert result["falseAllow"]["numerator"] == 1
    assert result["falseBlock"]["denominator"] == 1
    assert result["falseBlock"]["numerator"] == 1
    assert result["predictions"]["FORMAT_REJECT"] == 1
    assert result["predictions"]["UNKNOWN"] == 1
    assert result["unsupportedAllow"] == 1


@pytest.mark.parametrize("field,value", [
    ("model", "another-judge"), ("provider", "another-provider"), ("modelRevision", "r2"),
    ("templateSha256", "b" * 64), ("contractVersion", "another-contract"), ("scoreThreshold", .9),
])
def test_backend_model_template_revision_and_threshold_do_not_share_admission(field, value):
    rows = independent()
    changed = row("changed", kind="independent-calibration")
    changed["backend"][field] = value
    rows.append(changed)
    groups = qualify(rows, {key(rows[0]): POLICY})["groups"]
    assert len(groups) == 2
    assert next(g for g in groups if g["total"] == 1)["qualified"] is False


def test_purposes_are_separate_and_repeated_case_cannot_inflate_sample_count():
    v = row("x")
    with pytest.raises(ValueError, match="重复样本"):
        qualify([v, deepcopy(v)], {})
    other = row("x", purpose="stage-progress")
    assert len(qualify([v, other], {})["groups"]) == 2


def test_correlated_or_unpinned_samples_and_synthetic_cases_cannot_establish_admission():
    rows = independent()
    rows[1]["clusterId"] = rows[0]["clusterId"]
    assert "independent-calibration-has-reused-source-cluster" in qualify(rows, {key(rows[0]): POLICY})["groups"][0]["reasons"]
    for r in rows:
        r["sampleKind"] = "constructed-contract"
    assert qualify(rows, {key(rows[0]): POLICY})["allObservedGroupsQualified"] is False
    rows = independent()
    for r in rows:
        r["backend"]["modelRevision"] = "unknown"
    assert "model-revision-unpinned" in qualify(rows, {key(rows[0]): POLICY})["groups"][0]["reasons"]


def test_unknown_rate_is_measured_on_independent_batch_not_diluted_by_old_regression():
    rows = independent()
    for r in rows[:20]:
        r["prediction"] = "UNKNOWN"
    rows.extend(row(f"old-{i}") for i in range(400))
    assert "unknown-rate-exceeded" in qualify(rows, {key(rows[0]): POLICY})["groups"][0]["reasons"]
