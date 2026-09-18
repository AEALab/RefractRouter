"""評審成本投影的確定性回歸；只用合成的呼叫帳本與單價表。"""
import json

import pytest

from experiments.project_judge_cost import JUDGE_STAGES, load_prices, project, stage_totals

PRICES = {
    'cheap': {'provider': 'ark-plan', 'input_cost_per_1k': 0.05,
              'output_cost_per_1k': 0.05, 'cached_input_cost_per_1k': 0.05},
    'judge': {'provider': 'ark-plan', 'input_cost_per_1k': 1.0,
              'output_cost_per_1k': 1.0, 'cached_input_cost_per_1k': 1.0},
}


def _call(stage, input_tokens, output_tokens, afp):
    return {'stage': stage, 'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'actual_afp': afp}


def test_stage_totals_group_calls_tokens_and_afp():
    totals = stage_totals([_call('final', 100, 10, 0.5), _call('final', 50, 5, 0.25),
                           _call('delivery-judge', 800, 200, 1.0)])

    assert totals['final'] == {'calls': 2, 'input_tokens': 150, 'output_tokens': 15, 'afp': 0.75}
    assert totals['delivery-judge']['calls'] == 1


def test_projection_rescales_only_target_stages():
    call_table = [_call('worker', 1000, 1000, 1.1),
                  _call('delivery-judge', 1000, 1000, 2.0),
                  _call('research-judge', 1000, 1000, 2.0)]
    report = project(call_table, PRICES)
    scenarios = {row['name']: row for row in report['scenarios']}

    assert report['baseline']['afp'] == 5.1
    assert report['baseline']['judge_share'] == round(4.0 / 5.1, 6)
    both = scenarios['both → cheap']
    assert both['replaced_afp'] == 4.0
    assert both['substituted_afp'] == 0.2        # 2000 token/1000 × 0.05 × 2 階段
    assert both['projected_total_afp'] == 1.3    # worker 帳原樣保留
    assert both['saving_share'] == round(3.8 / 5.1, 6)
    assert scenarios['delivery-judge → judge']['projected_total_afp'] == 5.1


def test_projection_includes_zero_cost_local_reviewer():
    call_table = [_call('research-judge', 1000, 1000, 2.0)]
    scenarios = {row['name']: row
                 for row in project(call_table, PRICES, targets=('research-judge',))['scenarios']}
    local = scenarios['research-judge → local-cli-moa']

    assert local['provider'] == 'local-cli'
    assert local['substituted_afp'] == 0.0
    assert local['projected_total_afp'] == 0.0
    assert local['saving_share'] == 1.0


def test_projection_notes_state_whether_caching_can_save():
    call_table = [_call('research-judge', 1000, 1000, 2.0)]
    targets = ('research-judge',)
    assert '不減少 AFP' in project(call_table, PRICES, targets=targets)['notes']['cache_discount']

    discounted = {'cheap': {**PRICES['cheap'], 'cached_input_cost_per_1k': 0.01}}
    assert '未計入本投影' in project(call_table, discounted, targets=targets)['notes']['cache_discount']


def test_projection_rejects_missing_judge_stage():
    with pytest.raises(ValueError, match='帳本缺少階段'):
        project([_call('worker', 10, 10, 0.1)], PRICES)


def test_frozen_batch_matches_archived_projection():
    """回歸：封存批次的評審佔比與替換情境必須可重算。"""
    analysis = json.loads(open('reports/pareto-development-v1/live-01-analysis/analysis.json',
                               encoding='utf-8').read())
    prices = load_prices('reports/pareto-development-v1/live-01/frozen.json')
    report = project(analysis['call_table'], prices, targets=JUDGE_STAGES)
    scenarios = {row['name']: row for row in report['scenarios']}

    assert report['baseline'] == {**report['baseline'], 'calls': 474, 'afp': 394.5012,
                                  'judge_share': round(287.7 / 394.5012, 6)}
    assert scenarios['both → cheap']['projected_total_afp'] == 121.1862
    assert scenarios['both → local-cli-moa']['projected_total_afp'] == 106.8012
