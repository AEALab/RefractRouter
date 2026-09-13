"""模型参数兼容结论只应用于核验端点和型号，不推广到通用 provider。"""
import pytest
from refractrouter.ark_plan import application_configuration
from refractrouter.application_config import compile_configuration


def config_for(model):
    config = application_configuration()
    row = next(m for m in config['models'] if m['model'] == model and m['role'] == 'candidate')
    row['requestOptions'] = {'thinking': {'type': 'auto'}}
    return config


@pytest.mark.parametrize('model', ['doubao-seed-2.0-mini', 'doubao-seed-2.0-lite',
    'doubao-seed-2.1-turbo', 'doubao-seed-evolving', 'glm-5.3', 'glm-5.3-flash'])
def test_rejected_auto_fails_before_invocation(model):
    with pytest.raises(ValueError, match=f'{model} 不接受 thinking.type=auto'):
        compile_configuration(config_for(model))


@pytest.mark.parametrize('model', ['deepseek-v4-flash', 'deepseek-v4-pro'])
def test_accepted_auto_is_preserved(model):
    compiled = compile_configuration(config_for(model))
    row = next(m for m in compiled.manifest.models if m.api_model == model and m.role == 'candidate')
    assert row.request_options['thinking']['type'] == 'auto'


def test_other_provider_with_same_model_name_is_not_restricted():
    config = config_for('doubao-seed-2.0-mini')
    config['providers'][0].update(type='openai-compatible', baseUrl='https://example.com/v1')
    assert compile_configuration(config).manifest.models[0].request_options['thinking']['type'] == 'auto'
