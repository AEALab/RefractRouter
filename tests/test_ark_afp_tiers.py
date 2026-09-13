import pytest

from refractrouter.ark_plan import afp_metadata, application_configuration
from refractrouter.application_config import compile_configuration


def test_catalog_has_all_text_models_and_six_regular_cost_tiers():
    data = afp_metadata()
    assert data['tiers'] == [0.25, 0.5, 2.5, 4.5, 5.5, 10]
    assert len(data['models']) == 11
    assert next(m for m in data['models'] if m['model'] == 'glm-5.3-flash')['coefficient'] == 0.5
    config = application_configuration()
    candidates = [m for m in config['models'] if m['role'] == 'candidate']
    assert {m['id'] for m in candidates} == {m['model'] for m in data['models']}
    assert len({m['routing']['quality'] for m in candidates}) == 1  # 成本不能推导质量。
    assert all(m['pricing']['inputPer1k'] == next(row for row in data['models']
               if row['model'] == m['model'])['inputCoefficient'] / 10 for m in candidates)


@pytest.mark.parametrize('ceiling,count', [(0.25, 1), (0.5, 4), (2.5, 7), (4.5, 9), (5.5, 10), (10, 11)])
def test_each_tier_restricts_actual_candidate_manifest(ceiling, count):
    config = application_configuration()
    config['strategies'] = {'economy': {'maxAfpCoefficient': ceiling, 'reasoningEffort': 'high'}}
    compiled = compile_configuration(config, strategy='economy')
    candidates = [m for m in compiled.manifest.models if m.role == 'candidate']
    assert len(candidates) == count
    assert all(max(m.input_cost_per_1k, m.output_cost_per_1k) * 10 <= ceiling for m in candidates)
    assert all(m.request_options['reasoning_effort'] == 'high' for m in candidates)
    assert len([m for m in compiled.manifest.models if m.role == 'judge']) == 1
    assert len(compile_configuration(config, strategy='quality').predictions) == 11


def test_manual_selection_intersects_cost_ceiling_and_empty_pool_fails():
    config = application_configuration()
    config['strategies'] = {'balanced': {'maxAfpCoefficient': 0.5,
        'models': ['deepseek-v4-flash', 'minimax-m3']}}
    compiled = compile_configuration(config, strategy='balanced')
    assert list(compiled.predictions) == ['deepseek-v4-flash']
    config['strategies']['balanced']['models'] = ['minimax-m3']
    with pytest.raises(ValueError, match='no candidate'):
        compile_configuration(config, strategy='balanced')


def test_cost_ceiling_checks_input_and_output_and_requires_afp():
    config = application_configuration()
    config['strategies'] = {'economy': {'maxAfpCoefficient': 0.25}}
    config['models'][0]['pricing']['outputPer1k'] = 0.1
    with pytest.raises(ValueError, match='no candidate'):
        compile_configuration(config, strategy='economy')
    config['billingUnit'] = 'USD'
    with pytest.raises(ValueError, match='AFP billingUnit'):
        compile_configuration(config)


@pytest.mark.parametrize('value', [0, -1, float('inf'), True, '0.5'])
def test_invalid_cost_ceiling_is_rejected(value):
    config = application_configuration()
    config['strategies'] = {'economy': {'maxAfpCoefficient': value}}
    with pytest.raises(ValueError):
        compile_configuration(config, strategy='economy')


def test_ark_preset_does_not_assume_shared_thinking_modes():
    config = application_configuration()
    for model in config['models']:
        assert model['requestOptions'] == ({'thinking': {'type': 'enabled'}}
            if model['model'] == 'glm-5.3' else {})
