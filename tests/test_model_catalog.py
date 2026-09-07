import json
from pathlib import Path

import pytest

from refractrouter.model_catalog import load_catalog, list_models, main


def test_catalog_expands_all_documented_modalities_without_changing_benchmark():
    data=load_catalog()
    assert len(data['models'])==19
    assert len(list_models(capability='text-generation'))==11
    ids={row['model_id'] for row in data['models']}
    assert {'glm-5.3','glm-5.3-flash','kimi-k2.7-code','doubao-seed-2.1-turbo',
            'doubao-seedream-5.0-lite','doubao-seedance-2.0-mini'} <= ids
    assert len({row['capability'] for row in data['models']})==6
    assert data['account_plan_tier'] is None
    manifest=json.loads((Path(__file__).resolve().parents[1]/data['benchmark_manifest']).read_text())
    assert {model['api_model'] for model in manifest['models']}=={'kimi-k3','deepseek-v4-pro','deepseek-v4-flash','minimax-m3'}


def test_plan_thinking_pricing_and_retirement_are_explicit():
    data={row['model_id']:row for row in list_models()}
    assert 'kimi-k3' not in {row['model_id'] for row in list_models(plan_tier='small')}
    assert not list_models(capability='video-generation',plan_tier='small')
    assert len(list_models(capability='video-generation',plan_tier='large'))==4
    assert data['glm-5.3']['thinking_policy']=='required-cannot-disable'
    assert data['glm-5.3-flash']['promotional_pricing']['ends_at']=='2026-09-11T23:59:59+08:00'
    assert data['doubao-seedream-5.0-lite']['pricing']['unit']=='afp-per-successful-image'
    assert data['doubao-seedance-1.5-pro']['lifecycle']=='retiring'
    assert data['doubao-seedance-1.5-pro']['availability_notes']
    with pytest.raises(ValueError):
        list_models(capability='video')


def test_inventory_command_is_offline_and_filters(capsys, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket,'connect',lambda *args:pytest.fail('unexpected network'))
    assert main(['--capability','image-generation','--json'])==0
    output=json.loads(capsys.readouterr().out)
    assert output['model_calls']==0 and len(output['models'])==1
