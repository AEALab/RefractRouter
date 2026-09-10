"""自动 DAG 应用验收；默认零调用预检，实跑须绑定协议和源码摘要。"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from refractrouter.agent import atomic_json, run_agent
from refractrouter.agent_cli import example_configuration
from refractrouter.application_config import compile_configuration

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'data/research/automatic-dag-acceptance-v1.json'


def digest(raw):
    return hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def preflight(protocol, split):
    tasks = [t for t in protocol['tasks'] if t['split'] == split]
    if not tasks or protocol['http_retries'] or protocol['node_fallbacks'] or protocol['planner_repairs'] not in (0,1):
        raise ValueError('invalid acceptance protocol')
    config = example_configuration(protocol['provider_preset'])
    config['qualityMin'] = protocol['quality_min']
    for model in config['models']:
        model['maxOutputTokens'] = protocol['max_output_tokens']
    compile_configuration(config)
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/refractrouter').rglob('*.py'))}
    sources[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    maximum_runs = len(tasks) * len(protocol['order'])
    return {'protocol': protocol, 'split': split, 'provider_configuration': config, 'source_hashes': sources,
        'maximum_calls': len(tasks) * (12 + protocol['planner_repairs']), 'maximum_runs': maximum_runs,
        'budget': {'production': maximum_runs * protocol['production_budget'],
                   'evaluation': maximum_runs * protocol['evaluation_budget']},
        'scope': '不修改冻结历史；自动路线不提供手写计划；直接路线使用同一候选池和策略。配置预测不是实测画像。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['development', 'holdout'], required=True)
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    frozen = preflight(protocol, args.split)
    fingerprint = digest(frozen)
    if args.execute and args.freeze_sha256 != fingerprint:
        parser.error('执行前必须绑定当前协议、模型配置及源码摘要')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output_dir/'preflight.json', {**frozen, 'sha256': fingerprint})
    if not args.execute:
        print(json.dumps({'sha256': fingerprint, 'maximum_calls': frozen['maximum_calls'], 'budget': frozen['budget']}))
        return
    with tarfile.open(args.output_dir/'source.tar.gz', 'w:gz') as archive:
        for name in frozen['source_hashes']:
            archive.add(ROOT/name, arcname=name)
    rows = []
    try:
        for task in protocol['tasks']:
            if task['split'] != args.split:
                continue
            for template in protocol['order']:
                print('执行', task['id'], template, flush=True)
                result = run_agent({'task': task['task'], 'acceptanceCriteria': task['criteria'],
                    'strategy': protocol['strategy'], 'template': template,
                    **({'maxPlanRepairs':protocol['planner_repairs']} if template=='auto' else {})},
                    provider_config=frozen['provider_configuration'], mode='live', execute_paid_run=True,
                    runs_dir=args.output_dir/task['id']/template, production_budget=protocol['production_budget'],
                    evaluation_budget=protocol['evaluation_budget'], timeout_ms=protocol['timeout_ms'],
                    max_output_tokens=protocol['max_output_tokens'])
                row = {'task_id': task['id'], 'template': template, **result}
                rows.append(row)
                atomic_json(args.output_dir/'results.json', rows)
                print(json.dumps({k: row[k] for k in ('task_id','template','status','models','cost_breakdown','wall_time_ms','issues')},ensure_ascii=False),flush=True)
                # 未知用量、认证、证据或预算问题不能作为普通质量失败继续调用。
                if result['costs']['unconfirmed'] or result['status'] in {'failed','cancelled'}:
                    raise RuntimeError('验收遇到执行／基础设施异常，已保存证据并停止；不得直接重跑留出。')
    finally:
        index = {str(p.relative_to(args.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(args.output_dir.rglob('*')) if p.is_file()}
        atomic_json(args.output_dir/'artifact-index.json', index)


if __name__ == '__main__':
    main()
