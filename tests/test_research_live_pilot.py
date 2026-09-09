"""付费入口的准入验证使用假客户端，不发起网络或消耗 AFP。"""
import json
from unittest.mock import patch

import pytest

from experiments import run_research_live_pilot as pilot
from experiments.rehearse_research_execution import DevelopmentClient


def prepared(tmp_path):
    raw = pilot.prepare()
    path = tmp_path / 'protocol.json'
    path.write_text(json.dumps(raw))
    manifest = pilot.load_model_manifest(pilot.ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    return raw, path, pilot.preflight(raw, manifest)


def test_default_preflight_never_creates_model_client(tmp_path):
    raw, path, preview = prepared(tmp_path)
    with patch.object(pilot, 'OpenAICompatibleClient') as client, patch('socket.socket', side_effect=AssertionError('禁止网络')):
        assert pilot.main(['--protocol', str(path), '--output-dir', str(tmp_path / 'preview')]) == 0
    client.assert_not_called()
    assert preview['maximum_calls'] == 84
    assert len({t['source_id'] for t in raw['tasks']}) == 3
    assert all(t['split'] == 'development' for t in raw['tasks'])


def test_live_requires_exact_protocol_and_budget(tmp_path):
    _, path, _ = prepared(tmp_path)
    with patch.object(pilot, 'OpenAICompatibleClient') as client:
        with pytest.raises(SystemExit):
            pilot.main(['--protocol', str(path), '--output-dir', str(tmp_path / 'blocked'), '--execute-paid-run'])
    client.assert_not_called()
    assert not (tmp_path / 'blocked').exists()


def test_live_path_with_fake_transport_records_all_planned_runs(tmp_path, monkeypatch):
    raw, path, preview = prepared(tmp_path)
    monkeypatch.setenv('CODEX_ARK_API_KEY', 'test-not-a-real-secret')
    with patch.object(pilot, 'OpenAICompatibleClient', return_value=DevelopmentClient(raw['tasks'])) as client:
        with patch('socket.socket', side_effect=AssertionError('禁止网络')):
            assert pilot.main(['--protocol', str(path), '--output-dir', str(tmp_path / 'run'), '--execute-paid-run',
                '--approved-protocol-sha256', preview['protocol_sha256'],
                '--max-production-cost', str(preview['production_limit']),
                '--max-evaluation-cost', str(preview['evaluation_limit'])]) == 0
    client.assert_called_once_with(max_retries=0)
    result = json.loads((tmp_path / 'run/session.json').read_text())
    assert len(result['planned_runs']) == len(result['runs']) == 12
    assert len(result['calls']) <= 84
    assert all(c['status'] == 'billed' for c in result['calls'])
    assert len(result['plan_setups']) == 3
