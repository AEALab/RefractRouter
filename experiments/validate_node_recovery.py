"""零模型调用的故障注入验收；输出不作为真实质量、可靠性或收益证据。"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.manifest import load_model_manifest
from refractrouter.task_runtime import DemoTaskClient, run_task

ROOT = Path(__file__).resolve().parents[1]


def validate(output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    manifest_path = ROOT/'data/model-manifests/openai-gpt-5.4.json'
    profile = json.loads((ROOT/'data/routing/demo-usd-v1.json').read_text())
    plan = json.loads((ROOT/'data/task-plans/parallel-analysis-v2.json').read_text())
    manifest = load_model_manifest(manifest_path)
    request = {'task': '比较两个方案，分别分析成本和风险，再汇总建议。', 'mode': 'demo',
               'qualityMin': 80, 'costMax': 10, 'latencyMaxMs': 300000, 'plan': plan}
    cases = [('disabled', 'A', 0, 1, 'structure'), ('switch-a', 'A', 1, 1, 'structure'),
             ('switch-b', 'B', 1, 1, 'structure'), ('exhausted', 'A', 2, 3, 'structure'),
             ('unknown-usage', 'A', 2, 1, 'unknown'), ('truncated', 'A', 1, 1, 'truncated')]
    summary = {'kind': 'deterministic-fault-injection', 'real_model_calls': 0, 'cases': [],
               'limitation': '只验证恢复机制和模拟账本；不评估模型真实质量、可靠性或回退收益。'}
    for name, method, limit, failures, kind in cases:
        class FaultClient(DemoTaskClient):
            def __init__(self):
                self.seen = 0

            def complete(self, model, messages, *, json_mode=False):
                answer = super().complete(model, messages, json_mode=json_mode)
                if json.loads(messages[-1]['content']).get('node_id') == 'cost':
                    self.seen += 1
                    if self.seen <= failures:
                        return replace(answer, content='{"result":"模拟未闭合',
                            finish_reason='length' if kind == 'truncated' else 'stop',
                            usage_available=kind != 'unknown')
                return answer
        args = {**request, 'method': method, 'maxNodeFallbacks': limit}
        if method == 'B':
            args['weights'] = {'quality': .5, 'cost': .25, 'latency': .25}
        with patch('socket.socket', side_effect=AssertionError('本验收禁止网络')), patch(
                'refractrouter.task_runtime.DemoTaskClient', FaultClient):
            result = run_task(args, manifest, profile)
        switched = name in ('switch-a', 'switch-b', 'truncated')
        assert result['status'] == ('simulated' if switched else 'failed'), name
        calls = [c for c in result['calls'] if c['label'].startswith('cost')]
        assert len(calls) == (2 if switched else 3 if name == 'exhausted' else 1), name
        assert len({c['model_id'] for c in calls}) == len(calls)
        assert len({c['input_sha256'] for c in calls}) == 1
        if switched:
            assert len(result['calls']) == 4 and len(result['node_attempts']) == 4
            parents = {r['node_id']: json.loads(r['output']) for r in result['nodes'] if r['node_id'] != 'answer'}
            payload = json.loads(next(c for c in result['calls'] if c['label']=='answer')['request_messages'][-1]['content'])
            assert payload['upstream'] == parents
        if kind == 'unknown':
            assert calls[0]['status'] == 'unknown-usage' and calls[0]['charged'] == calls[0]['reserved']
        (out/f'{name}.json').write_text(json.dumps({'request': args, 'result': result}, ensure_ascii=False, indent=2)+'\n')
        summary['cases'].append({'case': name, 'status': result['status'], 'simulated_calls': len(result['calls']),
                                 'models_tried_at_cost': [c['model_id'] for c in calls], 'checks_passed': True})
    for name, data in [('summary', summary), ('implementation', implementation_fingerprint()),
                       ('profile', profile), ('manifest', json.loads(manifest_path.read_text()))]:
        (out/f'{name}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    index = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    (out/'artifact-index.json').write_text(json.dumps(index, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    print(json.dumps(validate(parser.parse_args().output_dir), ensure_ascii=False, indent=2))
