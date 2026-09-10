"""研究草案不得把模板变体、重复测量或零调用包络当成真实迁移证据。"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.prepare_research_studies import prepare
from experiments.preflight_research_studies import main
from refractrouter.manifest import load_model_manifest
from refractrouter.research_protocol import material_digest, preflight, validate_protocol

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest():
    return load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')


@pytest.mark.parametrize('issue,n,arms', [(39, 24, 9), (40, 21, 8)])
def test_zero_call_envelope_and_no_false_transfer_claim(manifest, issue, n, arms):
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        raw = prepare(issue)
        result = preflight(raw, manifest)
    assert result['real_model_calls'] == 0
    assert not result['live_execution_ready']
    assert not result['coverage']['independent_task_transfer_verified']
    assert result['coverage']['templates_shared_across_splits']
    assert result['coverage']['test_parameter_draws'] == n
    assert len(result['runs']) == n * 2 * arms
    assert result['maximum_calls'] == sum(result['planned_calls'].values())
    assert result['budget']['production'] > 0
    assert result['budget']['evaluation'] > 0
    if issue == 40:
        assert result['planned_calls']['cached_plan_setup'] == 2 * n
        assert result['planned_calls']['cached_plan_review'] == 2 * n


@pytest.mark.parametrize('mutation,message', [
    (lambda p: p.update(implementation_sha256={}), 'implementation'),
    (lambda p: p.update(manifest_sha256='changed'), 'manifest'),
    (lambda p: p.update(max_node_fallbacks=1), 'zero recovery'),
    (lambda p: p['coverage_cells'].append(p['coverage_cells'][0]), 'duplicate coverage'),
    (lambda p: p['tasks'][1].update(source_id=p['tasks'][0]['source_id']), 'source reused'),
    (lambda p: p['tasks'][0].update(task='替换材料'), 'changed material'),
    (lambda p: p['tasks'].pop(), 'split matrix'),
    (lambda p: p['acceptance'].update(target_mean_half_width=1), 'precision'),
    (lambda p: p.update(plan_review_criteria=['放宽验收']), 'semantic criteria'),
])
def test_reject_unfrozen_or_misleading_design(manifest, mutation, message):
    raw = prepare(40)
    mutation(raw)
    with pytest.raises(ValueError, match=message):
        validate_protocol(raw, manifest)


def test_historical_and_whitespace_duplicate_material_rejected(manifest):
    raw = prepare(39)
    with pytest.raises(ValueError, match='historical'):
        validate_protocol(raw, manifest, excluded_materials={raw['tasks'][0]['material_sha256']})
    raw['tasks'][1]['task'] = raw['tasks'][0]['task'] + '\n  '
    raw['tasks'][1]['material_sha256'] = material_digest(raw['tasks'][1]['task'])
    with pytest.raises(ValueError, match='duplicate'):
        validate_protocol(raw, manifest)


def test_actual_long_input_and_node_admission(manifest):
    raw = prepare(39)
    result = validate_protocol(raw, manifest)
    large = [r for r in result['tasks'] if '_large_' in r['cell']]
    assert large and min(r['material_bytes'] for r in large) >= 9000
    task = next(t for t in raw['tasks'] if t['input_scale'] == 'large')
    task['plan']['nodes'][0]['contract']['capability']['input_budget_tokens'] = 256
    with pytest.raises(ValueError, match='node-input-budget-exceeded'):
        validate_protocol(raw, manifest)


def test_manual_serial_dependency_has_real_user_requirement(manifest):
    raw = prepare(39)
    for task in raw['tasks']:
        if task['family'] == 'verification':
            assert '预算' in task['task']
            assert any('预算缺口' in c for c in task['criteria'])
            assert 'cost' in task['plan']['nodes'][1]['parents']
    validate_protocol(raw, manifest)


def test_cli_refuses_output_reuse_and_has_no_live_option(tmp_path):
    import json
    raw = prepare(40)
    raw['manifest_path'] = str(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    protocol = tmp_path / 'protocol.json'
    protocol.write_text(json.dumps(raw))
    args = ['--protocol', str(protocol), '--output-dir', str(tmp_path / 'output')]
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        assert main(args) == 0
        with pytest.raises(FileExistsError):
            main(args)
        with pytest.raises(SystemExit):
            main(args + ['--live'])
