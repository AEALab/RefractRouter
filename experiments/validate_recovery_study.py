"""保存三组确定性恢复证据；禁止网络，所有费用和评分均为模拟。"""
import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
from unittest.mock import patch

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.dag_study_execution import StudyDemoClient
from refractrouter.manifest import load_model_manifest
from refractrouter.recovery_study import ARMS, digest, run_study

ROOT = Path(__file__).resolve().parents[1]


def validate(output_dir):
    manifest = load_model_manifest(ROOT / 'data/model-manifests/openai-gpt-5.4.json')
    profile = json.loads((ROOT / 'data/routing/demo-usd-v1.json').read_text())
    plan = json.loads((ROOT / 'data/task-plans/serial-analysis-v2.json').read_text())
    protocol = {'schema_version': 'recovery-study-v1', 'implementation_sha256': implementation_fingerprint(),
        'manifest_sha256': digest(asdict(manifest)), 'profile_sha256': digest(profile),
        'failure_policy': 'settled-output-only-stop-on-infrastructure',
        'model_order': ['cheap', 'mid', 'strong'], 'max_switches': 2, 'repeats': 1, 'order_seed': 38,
        'judge_input_cap': 65536, 'execution_policy': {'maxConcurrency': 1},
        'constraints': {'qualityMin': 80, 'costMax': 10, 'latencyMaxMs': 300000},
        'tasks': [{'task_id': 'deterministic', 'task': '比较两个方案，核对成本约束。', 'plan': plan}]}
    class Fault(StudyDemoClient):
        def complete(self, model, messages, *, json_mode=False):
            response = super().complete(model, messages, json_mode=json_mode)
            if model.model_id == 'cheap' and json.loads(messages[-1]['content']).get('node_id') == 'risk':
                return replace(response, content='{"result":"未闭合')
            return response
    with patch('socket.socket', side_effect=AssertionError('验收禁止网络')):
        result = run_study(protocol, manifest, profile, output_dir, client=Fault())
    groups = {r['arm']: r for r in result['runs']}
    assert groups[ARMS[0]]['status'] == 'failed'
    assert all(groups[a]['status'] == 'completed' for a in ARMS[1:])
    for arm, row in groups.items():
        assert all(c['status'] == 'billed' for c in row['calls'])
        counts = [json.loads(c['request_messages'][-1]['content']).get('node_id') for c in row['calls']]
        assert counts.count('cost') == (2 if arm == ARMS[2] else 1)
    risk = [c for c in groups[ARMS[1]]['calls'] if json.loads(c['request_messages'][-1]['content']).get('node_id') == 'risk']
    assert len(risk) == 2 and risk[0]['input_sha256'] == risk[1]['input_sha256']
    return {'real_model_calls': 0, 'checks_passed': True,
            'simulated_calls': len(result['calls']), 'statuses': {a: r['status'] for a, r in groups.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    print(json.dumps(validate(parser.parse_args().output_dir), ensure_ascii=False))
