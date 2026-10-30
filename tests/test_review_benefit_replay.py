"""构造回执重放是合同证据，不增加真实研究的独立题数。"""
import json
from pathlib import Path

import pytest

from refractrouter.review_benefit_replay import run

SOURCE = Path(__file__).resolve().parents[1] / 'data/review-benefit-v1/cases.json'


@pytest.fixture(scope='module')
def replay(tmp_path_factory):
    folder = tmp_path_factory.mktemp('review-benefit') / 'evidence'
    before = SOURCE.read_bytes()
    summary = run(SOURCE, folder)
    assert SOURCE.read_bytes() == before
    return folder, summary


def report(replay, name):
    return json.loads((replay[0] / name / 'audit.json').read_text())


def test_replay_keeps_sources_and_raw_ledgers_and_never_claims_empirical_qualification(replay):
    folder, summary = replay
    assert summary['fixtureTaskPairs'] == 12 and summary['empiricalIndependentTasks'] == 0
    assert summary['actualModelBenefitProven'] is False and summary['paidModelCalls'] == 0
    assert summary['fixturePricesAreActualSpend'] is False and summary['hostToolsExecuted'] == 0
    assert (folder / 'source-before.json').read_bytes() == (folder / 'source-after.json').read_bytes()
    with pytest.raises(FileExistsError):
        run(SOURCE, folder)


def test_earlier_allowed_failure_cannot_be_spliced_into_later_unnecessary_intervention(replay):
    row = report(replay, 'earlier-fail-later-good')['reviewed']
    assert row['falseAllowed'] == 1 and row['unnecessaryInterventions'] == 1
    assert row['repairedKnownFailure'] is False and row['attemptedRepairOfKnownFailure'] is False
    assert row['repairEpisodes'][0]['sourceQuality'] == 'PASS'


def test_later_failure_is_repaired_even_when_first_tool_candidate_was_correct(replay):
    row = report(replay, 'earlier-good-later-fail')['reviewed']
    assert row['initialCandidateQuality'] == 'PASS'
    assert row['repairedKnownFailure'] is True and row['attemptedRepairOfKnownFailure'] is True
    assert row['repairEpisodes'][0]['sourceQuality'] == 'FAIL'


def test_stall_below_takeover_threshold_still_counts_actual_bad_tool_release(replay):
    row = report(replay, 'stall-releases-bad-tool')['reviewed']
    assert row['knownDefectiveReviewed'] == 1 and row['falseAllowed'] == 1
    assert row['intervenedCandidates'] == 0 and row['quality'] == 'UNKNOWN'


def test_discarded_tools_are_retained_as_evidence_without_host_execution(replay):
    row = report(replay, 'escalation-discard-tool')['reviewed']
    assert row['intervenedCandidates'] == 1 and row['repairedKnownFailure'] is True
    assert row['quality'] == 'PASS' and row['discardedExecutionSubset']


def test_invalid_review_retains_fee_and_no_approval_without_hiding_review_attempt(replay):
    row = report(replay, 'advisor-invalid-review')['reviewed']
    assert row['reviewAttempts'] == 1 and len(row['reviewWithoutDecisionCallIds']) == 1
    assert row['reviewedCandidates'] == 1 and row['falseAllowed'] == 0
    assert row['quality'] == 'UNKNOWN' and row['costObservation']['pricedCallAmountsComplete'] is True
