"""五条自动路由有限验收：真实核心、固定模拟模型，不发起远程调用。"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
from threading import Event

from refractrouter.agent import run_agent
from tests.test_live_execution import CompactClient, authorization, config


def verified_fixture_config():
    # 仅为控制选路分支的固定测试画像，绝非模型质量的实测证明。
    raw = config()
    for model in raw['models']:
        if model['id'] == 'local-router':
            model['routing'] = {'quality': 50, 'latencyMs': 10000,
                'profiles': [{'nodeType': kind, 'difficulty': 'medium', 'risk': 'medium',
                    'inputMinTokens': 256, 'inputMaxTokens': 131073, 'quality': 90,
                    'latencyMs': 1000, 'outputTokens': 1000}
                    for kind in ('extraction', 'verification', 'generation')]}
    return raw


def verify_paths(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    for scenario in ('direct', 'dag', 'node-failure', 'budget-insufficient', 'cancelled'):
        cancelled = Event()
        class Client(CompactClient):
            def complete(self, model, messages, **kwargs):
                response = super().complete(model, messages, **kwargs)
                payload = json.loads(messages[-1]['content'])
                if payload.get('node_id') == 'facts':
                    if scenario == 'node-failure':
                        return replace(response, finish_reason='length')
                    if scenario == 'cancelled':
                        cancelled.set()
                return response
        raw = config() if scenario == 'direct' else verified_fixture_config()
        task = '请用一句话解释缓存命中率。' if scenario in {'direct', 'budget-insufficient'} else \
               '分别核对第一项事实和第二项风险，然后汇总建议。'
        payload = {'task': task, 'strategy': 'auto'}
        cap = .000001 if scenario == 'budget-insufficient' else 10
        folder = directory/scenario
        preview = run_agent(payload, provider_config=raw, runs_dir=folder/'preview',
                            production_budget=cap, evaluation_budget=10)
        client = Client()
        if scenario == 'budget-insufficient':
            result = preview
        else:
            result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
                provider_config=raw, runs_dir=folder/'execute', mode='live', execute_paid_run=True,
                client=client, production_budget=cap, evaluation_budget=10, cancel_event=cancelled)
        saved = json.loads(Path(result['result_path']).read_text())
        labels = [json.loads(messages[-1]['content']).get('node_id', model)
                  for model, messages in client.calls]
        passed = {
            'direct': result['status'] == 'completed' and result['plan_origin'] == 'direct-gate'
                      and len(client.calls) == 1,
            'dag': result['status'] == 'completed' and len(result['plan']['nodes']) == 3
                   and result['route_comparison']['route'] == 'dag' and len(client.calls) == 5,
            'node-failure': result['status'] != 'completed' and 'answer' not in labels
                            and any(row['status'] == 'failed' for row in saved.get('nodes', []))
                            and any(row.get('finish_reason') == 'length' and row['status'] == 'billed'
                                    for row in saved.get('calls', [])),
            'budget-insufficient': result['status'] == 'no-feasible-route' and not client.calls,
            'cancelled': result['status'] == 'cancelled' and 'answer' not in labels
                         and result['costs']['unconfirmed'] == 0,
        }[scenario]
        rows.append({'scenario': scenario, 'passed': passed, 'status': result['status'],
            'route': (result.get('route_comparison') or {}).get('route'),
            'planOrigin': result.get('plan_origin'), 'nodeCount': len(result.get('plan', {}).get('nodes', [])),
            'modelCalls': len(client.calls), 'paidCalls': 0, 'callLabels': labels,
            'costs': result['costs'], 'result': str(Path(result['result_path']).relative_to(directory)),
            'forcedDag': result['complexity_gate']['forced']})
    summary = {'contract': 'automatic-reliability-acceptance-v1', 'paidCalls': 0,
        'evidenceKind': 'deterministic-core-with-model-fixtures',
        'qualityProfiles': 'fixed-test-fixtures-not-model-quality-evidence',
        'cases': rows, 'passed': all(row['passed'] for row in rows)}
    (directory/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = verify_paths(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary['passed'] else 1)
