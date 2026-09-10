"""小样本、重复相关、缺失分母和来源族配对的统计边界。"""
from copy import deepcopy
from pathlib import Path

import pytest

from refractrouter.quality_material_audit import audit, recalculate
from refractrouter.quality_statistics import binomial_lower, paired_quality_lower, paired_performance
from refractrouter.quality_study import load_study

STUDY = Path(__file__).resolve().parents[1] / 'data/quality-study-v1'


def test_exact_small_sample_bound_does_not_certify_ninety_percent():
    assert binomial_lower(12, 12) == pytest.approx(.7790778080544442)
    assert binomial_lower(0, 12) == 0
    assert 0 < binomial_lower(10, 12) < 10 / 12
    assert paired_quality_lower([True] * 12, [True] * 12, .003125) < -.05


def test_pairing_cannot_drop_failures_or_missing_metrics():
    with pytest.raises(ValueError, match='identical complete'):
        paired_performance({'a': 5}, {'a': 10, 'b': 20}, {'a': 'x'})
    r = paired_performance({'a': 5, 'b': 5}, {'a': 10, 'b': 10}, {'a': 'x', 'b': 'y'}, draws=1000)
    assert r['mean_difference'] == -5 and r['degenerate']
    assert r['relative_gain'] == .5 and r['inference'] == 'exploratory-only'
    with pytest.raises(ValueError):
        paired_performance({'a': float('nan')}, {'a': 10}, {'a': 'x'})


def test_reference_arithmetic_recomputed_from_material_instead_of_gold():
    report = audit(STUDY)
    assert report['reference_mismatches'] == 0 and len(report['rows']) == 18
    assert all(count == 2 for count in report['coverage'].values())
    task = deepcopy(load_study(STUDY)[1][0])
    assert recalculate(task)['expected_stock'] == 60
    task['materials'][0]['text'] = task['materials'][0]['text'].replace('入库30件', '入库31件')
    assert recalculate(task)['expected_stock'] == 61
    assert recalculate(task)['observed_gap'] == -2


def test_human_binding_and_missing_repeat_prevent_false_quality_frontier():
    from refractrouter.quality_runtime import prepare
    from refractrouter.quality_statistics import analyze, POLICY
    from refractrouter.quality_study import digest
    _, tasks, refs, *_ = load_study(STUDY)
    selected = [t for t in tasks if t['split'] == 'holdout-candidate']
    frozen = prepare(STUDY, task_ids=[t['task_id'] for t in selected],
                     arms=['direct-or-dag', 'direct-strong', 'task-selector'], repeats=3)
    rows = []
    for spec in frozen['schedule']:
        cheaper = spec['arm'] == 'direct-or-dag'
        rows.append({**spec, 'status': 'delivered-unconfirmed', 'quality_status': 'pass',
                     'output': refs[spec['task_id']]['author_reference'], 'cost_known': True,
                     'online_afp': .5 if cheaper else 1, 'online_finished_ms': 500 if cheaper else 1000})
    result = {'frozen_sha256': digest(frozen), 'simulated': False, 'runs': rows}
    report = analyze(frozen, result, tasks, references=refs)
    assert not report['confirmed_pareto_frontier']
    assert report['arms']['direct-or-dag']['run_counts']['pending'] == 36
    reviews = [{'origin': 'human', 'reviewer': reviewer, 'evidence': 'fixture://review',
                'task_sha256': t['task_sha256'], 'output_sha256': digest(refs[t['task_id']]['author_reference']),
                'criteria': t['semantic_criteria'], 'verdict': 'pass', 'stage': 'initial'}
               for t in selected for reviewer in ('fixture-A', 'fixture-B')]
    purpose = {'origin': 'human', 'reviewer': 'fixture-C', 'evidence': 'fixture://purpose',
               'policy_sha256': digest(POLICY), 'task_bindings': frozen['task_bindings'], 'verdict': 'pass'}
    report = analyze(frozen, result, tasks, references=refs, human_reviews=reviews, purpose_review=purpose)
    assert report['confirmed_pareto_frontier'] == ['direct-or-dag']
    assert not report['comparisons'][0]['conditional_noninferiority_supported']
    missing = deepcopy(result)
    missing['runs'] = [r for r in missing['runs'] if r['run_id'] != next(r['run_id'] for r in rows if r['arm'] == 'direct-or-dag')]
    report = analyze(frozen, missing, tasks, references=refs, human_reviews=reviews, purpose_review=purpose)
    assert report['arms']['direct-or-dag']['planned_runs'] == 36
    assert report['arms']['direct-or-dag']['run_counts']['pending'] == 1
    assert not report['arms']['direct-or-dag']['performance_complete']
    assert report['comparisons'][0]['performance'] is None


def test_failed_delivery_and_missing_setup_cannot_improve_stratified_accounting():
    from refractrouter.quality_runtime import prepare
    from refractrouter.quality_statistics import analyze
    from refractrouter.quality_study import digest
    _, tasks, refs, *_ = load_study(STUDY)
    frozen = prepare(STUDY, task_ids=['rules-02'], arms=['shared-single-1'], repeats=1)
    spec = frozen['schedule'][0]
    result = {'frozen_sha256': digest(frozen), 'simulated': True, 'runs': [
        {**spec, 'status': 'withheld', 'quality_status': 'pass', 'cost_known': True,
         'online_afp': 2, 'online_finished_ms': 100}],
        'setups': [{'task_id': 'rules-02', 'status': 'ready', 'offline_afp': 3, 'wall_time_ms': 900}]}
    report = analyze(frozen, result, tasks, references=refs)
    task = next(t for t in tasks if t['task_id'] == 'rules-02')
    stratum = report['descriptive_strata']['category'][task['category']]['shared-single-1']
    assert stratum['run_counts'] == {'pass': 0, 'fail': 1, 'pending': 0}
    assert stratum['mean_online_afp'] == 2
    allocations = report['setup_amortization']['shared-single-1']
    assert allocations['1']['mean_afp_with_setup_allocation'] == 5
    assert allocations['3']['mean_ms_with_setup_allocation'] == 400
    result['setups'] = []
    report = analyze(frozen, result, tasks, references=refs)
    assert report['setup_amortization']['shared-single-1']['1']['mean_afp_with_setup_allocation'] is None
    changed = deepcopy(frozen)
    changed['statistics_policy']['pass_rate_floor'] = .5
    result['frozen_sha256'] = digest(changed)
    with pytest.raises(ValueError, match='analysis policy differs'):
        analyze(changed, result, tasks, references=refs)
