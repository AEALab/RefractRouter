"""冻结反例重放必须保留未知与共同费用，不冒充真实质量或反事实收益。"""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path

import pytest

from experiments.replay_stage_progress import run
from refractrouter.stage_progress_replay import compare

SOURCE = Path(__file__).resolve().parents[1] / "data/stage-progress-v1/cases.json"


def corpus():
    return json.loads(SOURCE.read_text())


def test_frozen_adversarial_traces_keep_denominators_and_cost_scope():
    result = compare(corpus())
    old, new = (result["metrics"][key] for key in ("fixed-hold", "new-evidence"))
    assert len(result["cases"]) == 9 and old["boundaries"] == new["boundaries"] == 40
    assert old["falseUpgrades"] == 2 and old["prematureRestores"] == 3
    assert new["falseUpgrades"] == new["prematureRestores"] == 0
    assert old["unscoredBoundaries"] == new["unscoredBoundaries"] == 2
    assert result["actualCompleteCostComparison"] == "unknown"
    assert result["wholeTaskQualityProven"] is result["actualModelBenefitProven"] is False
    assert result["hybrid"]["existingDowngradeConfirmations"] is True
    assert result["hybrid"]["newQualificationGranted"] is False


def test_simulated_full_cost_counts_common_review_in_both_arms():
    value = corpus()
    with_review = compare(value)
    value["simulatedPrices"]["commonCalls"] = []
    without_review = compare(value)
    for arm in ("fixed-hold", "new-evidence"):
        full = Decimal(with_review["metrics"][arm]["simulatedCompleteCostCny"])
        no_review = Decimal(without_review["metrics"][arm]["simulatedCompleteCostCny"])
        assert full - no_review == Decimal(".02") * len(value["cases"])


@pytest.mark.parametrize("change", ["unit", "negative", "infinite", "actual", "duplicate-case"])
def test_bad_inputs_do_not_turn_into_actual_cost_or_extra_independent_cases(change):
    value = corpus()
    if change == "unit":
        value["simulatedPrices"]["unit"] = "AFP"
    elif change == "negative":
        value["simulatedPrices"]["capable"] = "-1"
    elif change == "infinite":
        value["simulatedPrices"]["capable"] = "Infinity"
    elif change == "actual":
        value["kind"] = "real-model"
    else:
        value["cases"].append(deepcopy(value["cases"][0]))
    with pytest.raises(ValueError):
        compare(value)


def test_frozen_cli_hashes_actual_implementation_and_preserves_source(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "cases.json"
    source.write_bytes(SOURCE.read_bytes())
    before = source.read_bytes()
    output = tmp_path / "replay"
    result = run(source, output)
    assert source.read_bytes() == before and result["modelCalls"] == 0
    assert (output / "inputs-before.json").read_bytes() == (output / "inputs-after.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(source, output)
    with pytest.raises(ValueError, match="分离"):
        run(source, source_dir / "output")


def test_frozen_cli_records_failures_without_overwriting_any_old_evidence(tmp_path):
    source = tmp_path / "source/cases.json"
    source.parent.mkdir()
    source.write_text('{"kind":"constructed","kind":"real-model"}')
    output = tmp_path / "replay"
    with pytest.raises(ValueError, match="重复键"):
        run(source, output)
    failure = json.loads((output / "failure.json").read_text())
    assert failure["status"] == "failed" and not (output / "result.json").exists()
