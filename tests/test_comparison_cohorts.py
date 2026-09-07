"""Regression evidence for issue #29's comparison and availability semantics."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experiments.review_node_quality_evidence import review
from refractrouter.benchmark import (
    BenchmarkObservation, aggregate_observations, baseline_markdown, oracle_gate,
    pareto_front_markdown,
)
from refractrouter.comparisons import paired_comparisons
from refractrouter.node_availability import matrix_availability
from tests.test_node_quality import fixture

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'reports/v0.3-contract-recovery/repeated-agent-plan'


def observations():
    _, _, result, _ = fixture()
    return [BenchmarkObservation(result.task_id, repeat, strategy,
                replace(result, total_cost=cost, critical_path_latency_ms=latency),
                SimpleNamespace(final_score=score, cost=2, billing_unit='USD'))
            for strategy in ('task-oracle', 'node-oracle')
            for repeat, cost, latency, score in ((1, 9, 90, 90), (2, 6, 60, 92), (3, 4, 40, 91))]


def test_skipped_and_failed_costs_do_not_dilute_quality_cohort():
    rows = observations()
    rows[3] = replace(rows[3], result=replace(rows[3].result, total_cost=0,
        critical_path_latency_ms=0, failure_types=('node-quality-incomplete',), final_output=''), judge=None)
    summary = aggregate_observations(rows)
    node = summary['node-oracle']
    assert node['quality_mean'] == 91.5
    assert node['production_cost_mean'] == 5
    assert node['critical_path_p50_ms'] == 50
    assert node['comparison_runs'] == 2 and node['expected_runs'] == 3
    assert node['success_rate'] == node['judge_coverage'] == .6667
    assert node['production_cost_total'] == 10
    assert node['evaluation_cost_total'] == 4
    assert node['cohort']['included'] == [dict(task_id=rows[0].task_id, repeat=i) for i in (2, 3)]
    assert oracle_gate(summary)['decision'] == 'Insufficient-evidence'
    assert '2/3 blocks' in baseline_markdown(summary)
    assert 'Excluded' in pareto_front_markdown(summary)
    # A failed, even judged, run still costs money; all three comparison metrics exclude it.
    rows[3] = replace(rows[3], result=replace(rows[3].result, total_cost=7), judge=rows[0].judge)
    node = aggregate_observations(rows)['node-oracle']
    assert node['production_cost_mean'] == 5 and node['production_cost_total'] == 17
    assert node['evaluation_cost_total'] == 6 and node['judge_coverage'] == 1
    assert node['comparison_runs'] == 2


def test_missing_runs_empty_cohorts_and_duplicates():
    rows = observations()
    summary = aggregate_observations(rows[:-1])
    assert summary['node-oracle']['cohort']['excluded'][0]['reasons'] == ['missing-run']
    assert oracle_gate(summary)['decision'] == 'Insufficient-evidence'
    unjudged = [replace(row, judge=None) for row in rows]
    summary = aggregate_observations(unjudged)
    for values in summary.values():
        assert values['quality_mean'] is values['production_cost_mean'] is values['critical_path_p95_ms'] is None
        assert values['production_cost_total'] == 19
    assert 'N/A' in baseline_markdown(summary) and 'N/A' in pareto_front_markdown(summary)
    with pytest.raises(ValueError, match='Duplicate'):
        aggregate_observations(rows + rows[:1])
    with pytest.raises(ValueError, match='outside expected'):
        aggregate_observations(rows, expected_blocks=[(rows[0].task_id, 1)])


@pytest.mark.parametrize('metric', ['cost', 'latency', 'quality'])
def test_invalid_metrics_excluded_from_all_deltas(metric):
    rows = observations()
    if metric == 'quality':
        rows[3] = replace(rows[3], judge=SimpleNamespace(final_score=float('nan'), cost=2, billing_unit='USD'))
    else:
        field = 'total_cost' if metric == 'cost' else 'critical_path_latency_ms'
        rows[3] = replace(rows[3], result=replace(rows[3].result, **{field: float('inf')}))
    summary = aggregate_observations(rows)
    assert summary['node-oracle']['comparison_runs'] == 2
    assert oracle_gate(summary)['decision'] == 'Insufficient-evidence'
    report = paired_comparisons(rows)
    pair = next(row for row in report['pairs'] if row['candidate'] == 'node-oracle'
                and row['baseline'] == 'task-oracle' and row['repeat'] == 1)
    assert pair['included'] is False
    assert pair['quality_delta'] is pair['cost_delta'] is pair['latency_delta_ms'] is None
    assert report['summaries']['node-oracle vs task-oracle']['pairs'] == 2


def test_complete_judges_on_different_blocks_cannot_pass_gate():
    rows = observations()
    task = aggregate_observations(rows[:3])['task-oracle']
    node = aggregate_observations([replace(row, repeat=row.repeat + 3) for row in rows[3:]])['node-oracle']
    gate = oracle_gate({'task-oracle': task, 'node-oracle': node})
    assert not gate['cohorts_aligned'] and gate['decision'] == 'Insufficient-evidence'
    expected = [(rows[0].task_id, i) for i in range(1, 5)]
    report = paired_comparisons(rows, expected_blocks=expected)
    assert report['summaries']['node-oracle vs task-oracle']['excluded_blocks'][0]['repeat'] == 4


def cells():
    matrix = json.loads((ARCHIVE / 'node-quality-matrix.json').read_text())['rows']
    return [row for row in matrix if row['repeat'] == 1]


def assess(rows):
    return matrix_availability(rows, node_ids=[n.node_id for n in fixture()[0].nodes],
                               model_ids=['cheap', 'mid', 'strong'])


def test_known_rejection_keeps_records_and_evaluation_available_but_legacy_route_blocked():
    result = assess(cells())
    assert result['records_complete'] and result['evaluations_available']
    assert result['evaluation_states'] == {'contract-rejected': 1, 'judged': 20}
    assert not result['nodes_without_eligible_candidates']
    assert not result['legacy_route_executable']


@pytest.mark.parametrize('case', ['all-rejected', 'missing-judge', 'transport', 'invalid-context', 'missing-cell', 'duplicate'])
def test_availability_failures_remain_explicit(case):
    rows = cells()
    target = next(row for row in rows if row['evaluation'].get('method') == 'deterministic-rejection')
    if case == 'all-rejected':
        rows = [dict(target, model_id=row['model_id']) if row['node_id'] == target['node_id'] else row for row in rows]
    elif case == 'missing-cell':
        rows.pop()
    elif case == 'duplicate':
        rows.append(rows[0])
    else:
        row = rows[0]
        if case == 'missing-judge':
            rows[0] = dict(row, evaluation=dict(row['evaluation'], final_score=None, error='missing-judge'))
        else:
            failure = 'timeout' if case == 'transport' else 'invalid-reference-context'
            rows[0] = dict(row, node_result=dict(row['node_result'], status='failed', failure_type=failure))
    result = assess(rows)
    assert not result['legacy_route_executable']
    if case == 'all-rejected':
        assert result['evaluations_available']
        assert result['nodes_without_eligible_candidates'] == [target['node_id']]
    else:
        assert not result['evaluations_available']


def test_offline_archive_review_preserves_every_historical_file(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, 'connect', lambda *args: pytest.fail('offline review used network'))
    before = {str(path.relative_to(ARCHIVE)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in ARCHIVE.rglob('*') if path.is_file()}
    output = tmp_path / 'review'
    review(ARCHIVE, output)
    summary = json.loads((output / 'reviewed-summary.json').read_text())
    node = summary['strategies']['node-oracle']
    assert node['quality_mean'] == 91.5 and node['production_cost_mean'] == 5.365025
    assert summary['oracle_gate']['decision'] == 'Insufficient-evidence'
    pairs = json.loads((output / 'reviewed-strategy-comparisons.json').read_text())
    pair = pairs['summaries']['node-oracle vs task-oracle']
    assert pair['quality_delta_mean'] == -4.5 and pair['cost_delta_mean'] == 2.598275
    states = json.loads((output / 'reviewed-node-availability.json').read_text())['blocks']
    assert states[0]['evaluations_available'] and not states[0]['route_executed']
    assert states[1]['route_executed'] and states[2]['route_judged']
    assert before == {str(path.relative_to(ARCHIVE)): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in ARCHIVE.rglob('*') if path.is_file()}
    with pytest.raises(ValueError, match='fresh'):
        review(ARCHIVE, output)
    with pytest.raises(ValueError, match='separate'):
        review(ARCHIVE, ARCHIVE / 'new')
