"""统计入口不隐藏失败、缺测和设置费用。"""
from copy import deepcopy

import pytest

from refractrouter.research_analysis import compare_research


def inputs():
    protocol = {'coverage_cells': ['small'], 'arms': ['left', 'right'],
        'constraints': {'qualityMin': 80}, 'acceptance': {'primary_pairs': [['left', 'right']],
        'bootstrap_repeats': 100, 'bootstrap_seed': 39}}
    runs = [{'task_id': task, 'repeat': repeat, 'arm': arm, 'cell': 'small'}
        for task in ('one', 'two') for repeat in (1, 2) for arm in ('left', 'right')]
    rows = [{**r, 'score': 90, 'judge_passed': True, 'delivered': True,
        'deployment_cost': 2 if r['arm'] == 'left' else 3, 'wall_time_ms': 10} for r in runs]
    return {'runs': runs}, protocol, rows


def test_task_clusters_and_setup_cost():
    preview, protocol, rows = inputs()
    result = compare_research(preview, protocol, rows, simulated=True, setup_cost=7)
    pair = result['groups']['overall']['primary_comparisons'][0]
    assert pair['task_clusters'] == 2
    assert pair['paired_repeats'] == 4
    assert pair['metrics']['deployment_cost'] == {'mean_delta': -1, 'interval_97_5': [-1, -1]}
    assert result['runtime_cost'] == 20
    assert result['first_use_cost'] == 27
    assert not result['benefit_verified']


def test_missing_run_retains_denominator_and_unknown_full_cost():
    preview, protocol, rows = inputs()
    rows.pop(0)
    result = compare_research(preview, protocol, rows, simulated=False)
    left = result['groups']['overall']['arms']['left']
    assert left['planned'] == 4 and left['delivered'] == 3
    assert left['delivery_rate'] == .75
    assert left['full_deployment_cost'] is None
    assert result['first_use_cost'] is None
    assert result['runtime_cost'] is None


def test_failed_but_graded_pair_is_not_dropped():
    preview, protocol, rows = inputs()
    rows[0].update(score=10, delivered=False, judge_passed=False)
    result = compare_research(preview, protocol, rows, simulated=True)
    pair = result['groups']['overall']['primary_comparisons'][0]
    assert pair['paired_repeats'] == 4
    assert pair['metrics']['score']['mean_delta'] == -20


def test_all_metrics_use_common_cohort():
    preview, protocol, rows = inputs()
    rows[0]['deployment_cost'] = None
    rows[2].update(score=1, delivered=False, judge_passed=False)
    result = compare_research(preview, protocol, rows, simulated=True)
    pair = result['groups']['overall']['primary_comparisons'][0]
    assert pair['paired_repeats'] == 3
    # one 任务剩一对 -89，two 两对均为 0；按任务均值，不能按三对均值。
    assert pair['metrics']['score']['mean_delta'] == -44.5


@pytest.mark.parametrize('field,value', [('score', float('nan')), ('wall_time_ms', -1),
    ('deployment_cost', float('inf')), ('delivered', 1), ('judge_passed', False)])
def test_invalid_evidence_rejected(field, value):
    preview, protocol, rows = inputs()
    rows[0][field] = value
    with pytest.raises(ValueError):
        compare_research(preview, protocol, rows, simulated=True)


def test_duplicate_evidence_rejected():
    preview, protocol, rows = inputs()
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match='duplicate'):
        compare_research(preview, protocol, rows, simulated=True)


@pytest.mark.parametrize('change,expected', [('none',True),('missing',False),('failed',False),('slow',False),('simulated',False)])
def test_benefit_requires_complete_delivery_and_all_frozen_thresholds(change,expected):
    preview,protocol,rows=inputs()
    protocol['acceptance'].update(maximum_quality_loss=3,minimum_cost_saving=.2,maximum_latency_ratio=1.1)
    if change=='missing':rows.pop()
    elif change=='failed':rows[0].update(delivered=False,judge_passed=False,score=90)
    elif change=='slow':
        for r in rows:
            if r['arm']=='left':r['wall_time_ms']=20
    result=compare_research(preview,protocol,rows,simulated=change=='simulated')
    assert result['benefit_verified'] is expected
