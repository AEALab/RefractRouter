"""冻结研究的计数、校准隔离、真实调用准入与模拟全流程。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from refractrouter.dag_study import load_study, study_preflight
from refractrouter.dag_study_execution import compare_runs, run_study

PROTOCOL_PATH = Path(__file__).resolve().parents[1]/'data/benchmarks/dag-routing-v1.json'


def test_frozen_preflight_counts_all_production_probe_and_judge_calls():
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        protocol, manifest = load_study(PROTOCOL_PATH)
        result = study_preflight(protocol, manifest)
    assert result['real_model_calls'] == 0 and result['maximum_calls'] == 456
    assert result['planned_calls'] == {'calibration_nodes': 84, 'calibration_probes': 84,
                                      'node_judges': 84, 'final_judges': 90, 'test_nodes': 114}
    assert result['budget']['total'] == pytest.approx(19085.7216)
    assert len([t for t in protocol['tasks'] if t['split']=='test']) == 3
    assert len({t['task_id'] for t in protocol['tasks']}) == 9


def test_full_demo_never_calls_models_or_claims_real_improvement(tmp_path):
    protocol, manifest = load_study(PROTOCOL_PATH)
    protocol['execution_policy']['providerMinIntervalMs']['ark-plan'] = 0  # 测试缩短等待，指纹随之变化。
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        result = run_study(protocol, manifest, tmp_path/'demo')
    assert result['status'] == 'simulated', result['issues']
    assert len(result['calls']) == result['preflight']['maximum_calls'] == 456
    assert len(result['runs']) == 90
    from refractrouter.manifest import load_model_manifest
    assert load_model_manifest(tmp_path/'demo/manifest.json') == manifest
    assert 'task_execution.py' in json.loads((tmp_path/'demo/implementation.json').read_text())
    for run in result['runs']:
        artifact = json.loads((tmp_path/'demo'/run['result_path']).read_text())
        policy = artifact['execution']['policy']
        assert policy['provider_concurrency'] == protocol['execution_policy']['providerConcurrency']
        assert policy['provider_min_interval_ms'] == protocol['execution_policy']['providerMinIntervalMs']
        assert policy['max_concurrency'] == (1 if run['method'] in (
            'calibration', 'direct-strong', 'dag-strong-serial') else 2)
    assert result['comparison']['status'] == 'simulated'
    assert all(c['exploratory_signal'] is None and len(c['pairs']) == 9 for c in result['comparison']['comparisons'])
    profile = json.loads((tmp_path/'demo/profile.json').read_text())
    assert profile['kind'] == 'synthetic'
    observations = json.loads((tmp_path/'demo/observations.json').read_text())
    assert {r['task_id'] for r in observations['observations']} == set(profile['calibration_task_ids'])
    assert not set(profile['calibration_task_ids']) & set(profile['held_out_task_ids'])
    assert len(list((tmp_path/'demo/calls').glob('*-request.json'))) == 456
    assert len(list((tmp_path/'demo/calls').glob('*-response.json'))) == 456
    for relative, digest in json.loads((tmp_path/'demo/artifact-index.json').read_text()).items():
        assert hashlib.sha256((tmp_path/'demo'/relative).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        run_study(protocol, manifest, tmp_path/'demo')


def test_paid_study_requires_admission_and_stops_on_first_unknown_usage(tmp_path):
    protocol, manifest = load_study(PROTOCOL_PATH)
    class FailingClient:
        max_retries = 0
        calls = 0
        def complete(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError('不得在报告中泄露的服务诊断')
    client = FailingClient()
    with pytest.raises(ValueError, match='admission'):
        run_study(protocol, manifest, tmp_path/'underfunded', simulated=False, client=client,
                  production_limit=1, evaluation_limit=1)
    assert client.calls == 0
    preflight = study_preflight(protocol, manifest)
    result = run_study(protocol, manifest, tmp_path/'failure', simulated=False, client=client,
        production_limit=preflight['budget']['production'], evaluation_limit=preflight['budget']['evaluation'])
    assert result['status'] == 'failed' and client.calls == 1
    assert result['calls'][0]['status'] == 'unknown-usage'
    assert result['charged']['production'] > 0
    assert result['issues'] == ['RuntimeError']
    assert 'comparison' not in result


def test_incomplete_comparisons_cannot_be_reported_as_success():
    protocol, _ = load_study(PROTOCOL_PATH)
    assert compare_runs([], protocol, simulated=False)['status'] == 'insufficient-evidence'


@pytest.mark.parametrize('extra', [
    ['--execute-paid-run', '--approved-protocol-sha256', '错误指纹',
     '--max-production-cost', '100000', '--max-evaluation-cost', '100000'],
    ['--execute-paid-run'],
    ['--demo', '--max-production-cost', '100000'],
])
def test_cli_rejects_unapproved_or_mixed_mode_before_client_creation(tmp_path, monkeypatch, extra):
    from experiments import run_dag_study
    monkeypatch.setattr('sys.argv', ['run_dag_study', '--protocol', str(PROTOCOL_PATH),
                                    '--output-dir', str(tmp_path/'study'), *extra])
    with patch.object(run_dag_study, 'OpenAICompatibleClient', side_effect=AssertionError('不应创建真实客户端')):
        with pytest.raises(SystemExit) as error:
            run_dag_study.main()
    assert error.value.code == 2
    assert not (tmp_path/'study').exists()


def test_bound_implementation_changes_fail_before_study_calls():
    from refractrouter.dag_study import implementation_fingerprint
    protocol, manifest=load_study(PROTOCOL_PATH)
    protocol['implementation_sha256']=implementation_fingerprint()
    assert study_preflight(protocol,manifest)['maximum_calls']==456
    protocol['implementation_sha256']['task_execution.py']='变更后的提示不能沿用旧指纹'
    with patch('socket.socket',side_effect=AssertionError('禁止网络')):
        with pytest.raises(ValueError,match='implementation changed'):
            study_preflight(protocol,manifest)
