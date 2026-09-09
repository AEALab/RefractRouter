"""#39/#40 开发材料上的无网络执行演练；不提供付费或正式留出执行选项。"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

from experiments.prepare_research_studies import prepare
from refractrouter.dag_study_execution import StudyDemoClient
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import ChatResponse
from refractrouter.profile_calibration import build_stratified_profile
from refractrouter.node_routing import load_profile
from refractrouter.research_calibration import freeze_direct_models
from refractrouter.research_execution import ResearchSession

ROOT = Path(__file__).resolve().parents[1]


class DevelopmentClient(StudyDemoClient):
    def __init__(self, tasks):
        self.plans = {t['task']: t['plan'] for t in tasks}

    def complete(self, model, messages, *, json_mode=False):
        payload = json.loads(messages[-1]['content'])
        if 'acceptance_criteria' in payload:
            return ChatResponse(json.dumps(self.plans[payload['task']], ensure_ascii=False),
                                100, 80, 0, 0, 10, 1, 'stop', None)
        return super().complete(model, messages, json_mode=json_mode)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    with patch('socket.socket', side_effect=AssertionError('开发演练禁止网络')):
        config = prepare(40)
        # 草案校准材料降为开发夹具；不使用草案 test 材料，不宣称新留出结果。
        tasks = [deepcopy(t) for t in config['tasks'] if t['cell'] == 'parallel' and t['split'] == 'calibration']
        for task in tasks:
            task['split'] = 'development'
        target = next(t for t in config['tasks'] if t['cell'] == 'parallel' and t['split'] == 'development')
        config['execution_policy']['providerMinIntervalMs']['ark-plan'] = 0
        manifest = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
        session = ResearchSession(manifest, config, args.output_dir, DevelopmentClient([*tasks, target]),
            production_limit=1000, evaluation_limit=10000, max_calls=100, simulated=True)
        try:
            rows = [session.run_trial(t, f'cal-{i}-{m.model_id}', mode='direct', fixed_model=m.model_id)
                    for i, t in enumerate(tasks) for m in manifest.candidates]
            frozen = freeze_direct_models(tasks, rows, manifest, config['constraints'], held_out_ids=[target['task_id']])
            session.result['direct_calibration'] = frozen
            for task in tasks:
                for node in task['plan']['nodes']:
                    for model in manifest.candidates:
                        session.probe_node(task, node['node_id'], model.model_id)
            profile = build_stratified_profile(session.result['observations'], manifest,
                calibration_task_ids=[t['task_id'] for t in tasks], test_task_ids=[target['task_id']], allow_unavailable_evaluation=True)
            session.result['node_profile'] = profile
            profiles = load_profile(profile, manifest)
            task = target
            for assignment in ('per-node', 'single-model'):
                session.run_trial(task, assignment, mode='manual', profiles=profiles, assignment_mode=assignment)
            for mode in ('manual', 'auto-cold'):
                session.run_trial(task, mode, mode=mode, fixed_model='strong')
            session.cache_plan(task, 'warm')
            for n in (1, 2):
                session.run_trial(task, f'reuse-{n}', mode='auto-reuse', cache_id='warm', fixed_model='strong')
            session.result['scope'] = '只验证开发流程；固定强模型 DAG 不冒充节点 A/B，合成校准不代表实测能力。'
            session.result['real_model_calls'] = 0
        finally:
            result = session.close()
    print(json.dumps({'status': result['status'], 'real_model_calls': 0,
        'simulated_calls': len(result['calls']), 'delivered_runs': sum(r['delivered'] for r in result['runs']),
        'runs': len(result['runs']), 'cached_plan_setups': len(result['plan_setups'])}, ensure_ascii=False))
    return 0 if all(r['delivered'] for r in result['runs']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
