"""固定六种异构模型排列；默认只预检，不调用模型。"""
import argparse
import json
from pathlib import Path

from refractrouter.handoff_validation import load_handoff, run_handoff
from refractrouter.dag_study_execution import write_json
from refractrouter.openai_compatible import OpenAICompatibleClient


def main():
    parser = argparse.ArgumentParser(description='真实跨模型 DAG 交接验证')
    parser.add_argument('--protocol', type=Path, default=Path('data/benchmarks/dag-handoff-v3.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--demo', action='store_true')
    modes.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--approved-protocol-sha256')
    args = parser.parse_args()
    loaded = load_handoff(args.protocol)
    preflight = loaded[-1]
    if args.execute_paid_run:
        if args.approved_protocol_sha256 != preflight['protocol_sha256']:
            parser.error('真实执行需要获准的冻结协议指纹')
    elif args.approved_protocol_sha256 is not None:
        parser.error('仅真实执行接受授权指纹')
    if not args.demo and not args.execute_paid_run:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir/'preflight.json', preflight)
        print(json.dumps(preflight, ensure_ascii=False))
        return 0
    result = run_handoff(loaded, args.output_dir, simulated=args.demo,
        client=OpenAICompatibleClient(max_retries=0) if args.execute_paid_run else None,
        production_limit=preflight['production_limit'], evaluation_limit=preflight['evaluation_limit'])
    print(json.dumps({'status': result['status'], 'issues': result['issues'],
                      'calls': len(result['calls'])}, ensure_ascii=False))
    return int(result['status'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
