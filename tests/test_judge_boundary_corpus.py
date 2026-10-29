from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.judge_boundary_corpus import prepare
from refractrouter.purpose_review import llm_messages


DATA = Path(__file__).resolve().parents[1] / "data/judge-regression-v1/semantic-boundaries.json"


def test_four_purpose_boundaries_preserve_user_rules_and_keep_expectations_out_of_model_inputs():
    corpus = json.loads(DATA.read_text())
    result = prepare(corpus)
    assert result["summary"]["total"] == 18
    assert set(result["summary"]["byPurpose"]) == {
        "task-fit", "stage-progress", "advisor-delivery", "escalation-takeover"}
    assert result["summary"]["newJudgeOutputs"] == 0
    assert result["summary"]["independentCalibrationCount"] == 0
    expected = {r["caseId"]: r["expected"] for r in result["adjudications"]}
    assert expected["premise-corrected"] == expected["ordinary-narrative"] == "PASS"
    assert expected["unrelated-extra-citation"] == "FAIL"
    assert expected["client-not-agent"] == expected["common-species"] == "UNKNOWN"
    assert expected["permission-is-not-defect"] == expected["normal-exploration"] == "PASS"
    for row, case in zip(result["inputs"], corpus["cases"]):
        public = json.loads(llm_messages(row["packet"])[1]["content"])
        assert "expected" not in public and "reason_zh" not in public
        assert public["candidate"] == case["candidate"]
        assert public["sources"] == case["sources"]


def test_boundary_material_cannot_be_relabelled_as_independent_or_omit_requirements():
    corpus = json.loads(DATA.read_text())
    bad = deepcopy(corpus)
    bad["sampleKind"] = "independent-calibration"
    with pytest.raises(ValueError, match="构造"):
        prepare(bad)
    bad = deepcopy(corpus)
    bad["cases"][0]["requirements"] = []
    with pytest.raises(ValueError, match="全部验收"):
        prepare(bad)
