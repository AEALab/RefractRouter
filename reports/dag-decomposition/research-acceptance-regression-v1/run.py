"""冻结 SQLite 两路线修复回归；默认预检，显式 --execute 才真实调用。"""
import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.dag_study_execution import write_json
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.research_execution import ResearchSession, delivery_task
from refractrouter.research_protocol import digest
from refractrouter.task_execution import node_messages
from refractrouter.task_plan import validate_plan

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def prepare():
    original = ROOT.parent / 'research-live-pilot-v1-actual/output/session.json'
    old = json.loads(original.read_text())
    assert old['status'] == 'finished' and all(c['status'] == 'billed' for c in old['calls'])
    assert len(old['calls']) + 6 <= 84
    assert sum(old['charged'].values()) + 55 + 148 <= 2219.2129
    task = deepcopy(next(t for t in old['config']['tasks'] if t['task_id'] == 'sqlite-fk'))
    plan = validate_plan(task['plan'], required_criteria=task['criteria'], require_v2=True)
    context = {n.node_id: {'result': '检查用占位', 'evidence': 'S1', 'assumptions': '未执行'} for n in plan.nodes}
    for node in plan.nodes:
        node_messages(delivery_task(task), node, plan.contracts[node.node_id], context)
    manifest = load_model_manifest(REPO / 'data/model-manifests/volcengine-agent-plan.json')
    return {'purpose': '验收条目传递修复的针对性回归，不作为新的独立留出或收益证据',
        'source_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
        'implementation_sha256': implementation_fingerprint(),
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'manifest_sha256': digest(asdict(manifest)), 'config': old['config'], 'task': task,
        'modes': ['direct', 'manual'], 'max_calls': 6, 'production_limit': 55, 'evaluation_limit': 148}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    protocol = prepare()
    frozen = ROOT / 'protocol.json'
    if not args.execute:
        assert not frozen.exists(), '不覆盖已有冻结协议'
        write_json(frozen, protocol)
        print({'model_calls': 0, 'protocol_sha256': digest(protocol), 'max_calls': 6,
               'production_limit': 55, 'evaluation_limit': 148})
        return
    assert digest(json.loads(frozen.read_text())) == digest(protocol), '冻结协议变化，禁止调用'
    manifest = load_model_manifest(REPO / 'data/model-manifests/volcengine-agent-plan.json')
    session = ResearchSession(manifest, protocol['config'], ROOT / 'output', OpenAICompatibleClient(max_retries=0),
        production_limit=55, evaluation_limit=148, max_calls=6, simulated=False)
    session.result['regression_protocol'] = protocol
    try:
        for mode in protocol['modes']:
            session.run_trial(protocol['task'], 'sqlite-fixed-' + mode, mode=mode, fixed_model='strong')
    finally:
        result = session.close()
    print({'actual_calls': len(result['calls']), 'charged': result['charged'],
           'runs': [(r['run_id'], r['status'], r['score']) for r in result['runs']]})


if __name__ == '__main__':
    main()
