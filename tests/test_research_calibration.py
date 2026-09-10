"""留出隔离与校准失败不得因只取成功样本而被隐藏。"""
from copy import deepcopy
from pathlib import Path

import pytest

from experiments.prepare_research_studies import prepare
from refractrouter.manifest import load_model_manifest
from refractrouter.research_calibration import freeze_direct_models


def fixture():
    config = prepare(40)
    tasks = [t for t in config['tasks'] if t['cell'] == 'parallel' and t['split'] == 'calibration']
    manifest = load_model_manifest(Path(__file__).resolve().parents[1] / 'data/model-manifests/volcengine-agent-plan.json')
    rows = [{'task_id': t['task_id'], 'mode': 'direct', 'assignments': {'answer': m.model_id},
        'delivered': True, 'score': 90, 'deployment_cost': i + 1, 'wall_time_ms': 10, 'cost_known': True}
        for t in tasks for i, m in enumerate(manifest.candidates)]
    return tasks, rows, manifest, config['constraints']


def test_freeze_direct_a_and_b_before_test():
    tasks, rows, manifest, cap = fixture()
    frozen = freeze_direct_models(tasks, rows, manifest, cap, held_out_ids=['heldout'])
    assert frozen['selections']['parallel']['A']['selected_model'] == 'cheap'
    assert frozen['selections']['parallel']['B']['selected_model'] == 'cheap'
    assert frozen['held_out_ids'] == ['heldout']


def test_failed_candidate_excluded_not_averaged_away():
    tasks, rows, manifest, cap = fixture()
    rows[0]['delivered'] = False
    frozen = freeze_direct_models(tasks, rows, manifest, cap, held_out_ids=[])
    assert frozen['selections']['parallel']['A']['selected_model'] == 'mid'


@pytest.mark.parametrize('kind', ['overlap', 'missing', 'duplicate', 'test'])
def test_invalid_calibration_evidence(kind):
    tasks, rows, manifest, cap = fixture()
    heldout = [tasks[0]['task_id']] if kind == 'overlap' else []
    if kind == 'missing':
        rows.pop()
    if kind == 'duplicate':
        rows.append(deepcopy(rows[0]))
    if kind == 'test':
        tasks[0]['split'] = 'test'
    with pytest.raises(ValueError):
        freeze_direct_models(tasks, rows, manifest, cap, held_out_ids=heldout)
