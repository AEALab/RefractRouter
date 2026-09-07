"""冻结 DAG 对照实验；默认只预检，真实运行要求协议指纹和双预算。"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study import load_study, study_preflight
from refractrouter.dag_study_execution import run_study, write_json
from refractrouter.openai_compatible import OpenAICompatibleClient


def main():
    parser = argparse.ArgumentParser(description='执行冻结的 DAG 多任务对照')
    parser.add_argument('--protocol', type=Path, default=Path('data/benchmarks/dag-routing-v1.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--demo', action='store_true')
    modes.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--approved-protocol-sha256')
    parser.add_argument('--max-production-cost', type=float)
    parser.add_argument('--max-evaluation-cost', type=float)
    args = parser.parse_args()
    raw, manifest = load_study(args.protocol)
    preflight = study_preflight(raw, manifest)
    if args.execute_paid_run:
        if args.approved_protocol_sha256 != preflight['protocol_sha256']:
            parser.error('真实执行必须提供获准的协议 SHA-256')
        if args.max_production_cost is None or args.max_evaluation_cost is None:
            parser.error('真实执行必须提供生产与评审双预算')
    elif args.approved_protocol_sha256 or args.max_production_cost is not None or args.max_evaluation_cost is not None:
        parser.error('预检和模拟模式不接受付费授权参数')
    if not args.execute_paid_run and not args.demo:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir/'protocol.json', raw)
        write_json(args.output_dir/'preflight.json', preflight)
        print(json.dumps(preflight, ensure_ascii=False))
        return 0
    result = run_study(raw, manifest, args.output_dir, simulated=args.demo,
        client=OpenAICompatibleClient(max_retries=0) if args.execute_paid_run else None,
        production_limit=args.max_production_cost, evaluation_limit=args.max_evaluation_cost)
    print(json.dumps({'status': result['status'], 'charged': result['charged'],
                      'calls': len(result['calls']), 'issues': result['issues']}, ensure_ascii=False))
    return 1 if result['status']=='failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
