"""快速规划与动态执行验收：零调用冻结、显式执行、新目录保存全部尝试。"""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from refractrouter.agent import atomic_json, run_agent
from refractrouter.agent_cli import example_configuration

ROOT = Path(__file__).resolve().parents[1]


def freeze(protocol_path):
    protocol = json.loads(protocol_path.read_text())
    configuration = example_configuration('ark-agent-plan')
    configuration['qualityMin'] = 80
    sources = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT/'src/refractrouter').rglob('*.py'))}
    sources[str(Path(__file__).relative_to(ROOT))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    raw = {'protocol':protocol,'configuration':configuration,'source_hashes':sources,
        'limits': {'maximum_runs':len(protocol['runs']), 'maximum_calls':len(protocol['runs'])*12,
            'production_per_run':40,'evaluation_per_run':40,'http_retries':0},
        'scope':'开发回归与新留出分别记账；不估计总体成功率。动态触发的确定性测试另报，不伪造自然触发。'}
    return raw, hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=ROOT/'data/research/fast-dynamic-dag-v1.json')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--freeze-sha256')
    args=parser.parse_args()
    frozen, fingerprint=freeze(args.protocol)
    if args.execute and args.freeze_sha256!=fingerprint:
        parser.error('必须绑定当前协议、配置及源码摘要')
    args.output_dir.mkdir(parents=True,exist_ok=False)
    atomic_json(args.output_dir/'preflight.json',{**frozen,'sha256':fingerprint})
    if not args.execute:
        print(json.dumps({'sha256':fingerprint,**frozen['limits']}))
        return
    with tarfile.open(args.output_dir/'source.tar.gz','w:gz') as archive:
        for name in frozen['source_hashes']:
            archive.add(ROOT/name,arcname=name)
    rows=[]
    try:
        for item in frozen['protocol']['runs']:
            print('执行',item['id'],flush=True)
            result=run_agent({'task':item['task'],'acceptanceCriteria':item['criteria'],
                'strategy':'economy','template':item['template'],
                **({'maxDynamicSplits':1} if item['template']=='auto' or item.get('controlled_split') else {}),
                **({'plan':item['plan']} if 'plan' in item else {})},
                provider_config=frozen['configuration'],mode='live',execute_paid_run=True,
                runs_dir=args.output_dir/item['id'],production_budget=40,evaluation_budget=40,
                timeout_ms=180000,max_output_tokens=2048)
            rows.append({'case_id':item['id'],'split':item['split'],**result})
            atomic_json(args.output_dir/'results.json',rows)
            print(json.dumps({k:rows[-1][k] for k in ('case_id','status','planner','plan_ready_ms','wall_time_ms','costs','issues')},ensure_ascii=False),flush=True)
            if result['costs']['unconfirmed'] or result['status'] in {'failed','cancelled'}:
                raise RuntimeError('调用、预算或用量异常：保留当前证据并停止整批')
    finally:
        atomic_json(args.output_dir/'artifact-index.json',{str(p.relative_to(args.output_dir)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(args.output_dir.rglob('*')) if p.is_file()})


if __name__=='__main__':
    main()
