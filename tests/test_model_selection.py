from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from experiments.analyze_model_selection import analyze
from experiments.review_node_quality_evidence import observation
from refractrouter.model_selection import (
    Candidate, Constraints, Weights, build_candidates, pareto_model_ids, select_model,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "reports/v0.3-contract-recovery/repeated-agent-plan"
LIMITS = Constraints(88, 6, 80000)
WEIGHTS = Weights(.5, .25, .25)


def pool():
    # Quality/cost favors cheap; tail latency favors fast; third is dominated.
    return (Candidate("cheap", 90, 1, 80, 3), Candidate("fast", 88, 5, 50, 3),
            Candidate("dominated", 84, 9, 90, 3))


def test_a_constraints_switch_winner_keep_baseline_and_report_no_solution():
    for limit, expected in ((80, "cheap"), (50, "fast"), (49, None)):
        decision = select_model(pool(), method="A", constraints=Constraints(88, 6, limit))
        assert decision["selected_model"] == expected
        assert decision["quality_baseline"] == "cheap"
        assert decision["status"] == ("selected" if expected else "no-feasible-model")
    assert select_model(pool(), method="A", constraints=Constraints(90, 6, 50))["selected_model"] is None
    assert select_model(pool(), method="A", constraints=Constraints(88, 4, 50))["selected_model"] is None
    exact = select_model(pool(), method="A", constraints=Constraints(90, 1, 80))
    assert exact["selected_model"] == "cheap"


def test_b_sensitivity_and_fixed_normalization_before_constraints():
    quality = select_model(pool(), method="B", weights=Weights(1, 0, 0))
    latency = select_model(pool(), method="B", weights=Weights(0, 0, 10))
    assert quality["selected_model"] == "cheap"
    assert latency["selected_model"] == "fast"
    assert latency["normalized_weights"] == {"quality": 0, "cost": 0, "latency": 1}
    gated = select_model(pool(), method="B", weights=Weights(1, 0, 0), constraints=Constraints(88, 6, 50))
    assert gated["selected_model"] == "fast"
    assert gated["quality_baseline"] == "cheap"
    assert gated["normalization_bounds"] == quality["normalization_bounds"]
    assert gated["candidates"]["fast"]["score"] == quality["candidates"]["fast"]["score"]
    assert gated["candidates"]["cheap"]["reasons"] == ["latency-above-maximum"]


def test_degenerate_normalization_ties_empty_pool_and_pareto():
    candidates = (Candidate("z", 90, 1, 50, 1), Candidate("a", 90, 1, 50, 1))
    decision = select_model(candidates, method="B", weights=WEIGHTS)
    assert decision["selected_model"] == "a"
    assert decision["candidates"]["z"]["score"] == 1
    assert pareto_model_ids(candidates) == ["a", "z"]
    assert pareto_model_ids(pool()) == ["cheap", "fast"]
    assert select_model((), method="B", weights=WEIGHTS)["status"] == "no-feasible-model"
    with pytest.raises(ValueError, match="Duplicate"):
        select_model((candidates[0], candidates[0]), method="B", weights=WEIGHTS)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_numbers_rejected(value):
    with pytest.raises(ValueError):
        Constraints(88, value, 80000)
    with pytest.raises(ValueError):
        select_model(pool(), method="B", weights=Weights(value, 1, 1))
    with pytest.raises(ValueError):
        Candidate("bad", value, 1, 1, 3)


def test_explicit_policy_parameters_required():
    with pytest.raises(ValueError):
        select_model(pool(), method="A")
    with pytest.raises(ValueError):
        select_model(pool(), method="B")
    with pytest.raises(ValueError):
        select_model(pool(), method="B", weights=Weights(0, 0, 0))
    with pytest.raises(ValueError):
        select_model(pool(), method="B", weights=Weights(1e308, 1e308, 0))
    with pytest.raises(ValueError):
        select_model(pool(), method="unknown")


def saved_observation(repeat=1):
    record = json.loads((EVIDENCE / f"single-models/report_001/repeat-{repeat}/cheap.json").read_text())
    return observation(record, repeat=repeat, strategy="cheap")


@pytest.mark.parametrize("problem", ["missing", "judge", "failure", "nan", "billing", "mixed", "nodes"])
def test_incomplete_candidate_is_excluded_without_dropping_bad_repeat(problem):
    first, second = saved_observation(), saved_observation(2)
    if problem == "judge":
        second = replace(second, judge=None)
    elif problem == "failure":
        second = replace(second, result=replace(second.result, failure_types=("timeout",)))
    elif problem == "nan":
        second = replace(second, judge=replace(second.judge, final_score=float("nan")))
    elif problem == "billing":
        second = replace(second, result=replace(second.result, billing_unit="USD"))
    elif problem == "mixed":
        assignments = dict(second.result.model_assignments, write_report="mid")
        second = replace(second, result=replace(second.result, model_assignments=assignments))
    elif problem == "nodes":
        second = replace(second, result=replace(second.result, node_results=()))
    observations = [first] if problem == "missing" else [first, second]
    candidates = build_candidates(observations, expected_model_ids=["cheap", "absent"],
                                  expected_blocks=[("report_001", 1), ("report_001", 2)])
    assert all(c.exclusions and c.quality_mean is None and c.cost_afp_mean is None for c in candidates)
    result = select_model(candidates, method="A", constraints=LIMITS)
    assert result["selected_model"] is None
    assert result["quality_baseline"] is None


def test_aligned_aggregation_uses_final_judge_unrounded_p95_and_rejects_duplicates():
    observations = [saved_observation(repeat) for repeat in (1, 2, 3)]
    kwargs = {"expected_model_ids": ["cheap"], "expected_blocks": [("report_001", r) for r in (1, 2, 3)]}
    c, = build_candidates(observations, **kwargs)
    assert c.quality_mean == pytest.approx(271 / 3)  # Ignore deterministic task_score=100.
    assert c.cost_afp_mean == pytest.approx(.6652666666666667)
    assert c.latency_p95_ms == pytest.approx(76654.9)
    assert select_model([c], method="A", constraints=Constraints(88, 6, 76654.89))["selected_model"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        build_candidates(observations + [observations[0]], **kwargs)
    with pytest.raises(ValueError, match="Unexpected"):
        build_candidates([replace(observations[0], repeat=4)], **kwargs)


def test_archived_analysis_is_zero_call_and_preserves_evidence():
    paths = list(EVIDENCE.rglob("*"))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
        report = analyze(EVIDENCE, LIMITS, WEIGHTS)
    assert report["model_calls"] == 0
    assert report["quality_baseline"] == report["A"]["selected_model"] == "cheap"
    assert report["B_sensitivity"]["latency-priority"]["selected_model"] == "mid"
    assert report["pareto_model_ids"] == ["cheap", "mid"]
    assert len(report["runs"]) == 9 and len(report["A_sensitivity"]) == 60
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())


def test_tampered_evidence_rejected(tmp_path):
    archive = tmp_path / "archive"
    shutil.copytree(EVIDENCE, archive)
    path = archive / "single-models/report_001/repeat-1/cheap.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        analyze(archive, LIMITS, WEIGHTS)


def test_cli_writes_fresh_report_and_rejects_overwriting_or_archival_output(tmp_path):
    output = tmp_path / "analysis"
    command = [sys.executable, "-m", "experiments.analyze_model_selection", str(EVIDENCE),
               "--quality-min", "88", "--cost-afp-max", "6", "--latency-p95-ms-max", "60000",
               "--weights", ".5", ".25", ".25", "--output-dir"]
    completed = subprocess.run(command + [str(output)], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "selection-analysis.json").read_text())
    assert report["A"]["selected_model"] == report["B_with_constraints"]["selected_model"] == "mid"
    assert report["quality_baseline"] == "cheap"
    assert (output / "selection-analysis.md").exists()
    for forbidden in (output, EVIDENCE / "new-analysis"):
        rejected = subprocess.run(command + [str(forbidden)], cwd=ROOT, capture_output=True, text=True)
        assert rejected.returncode != 0
