"""失败文本节点的格式验证；默认零调用预检。"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.task_contract_replay import load_replay, run_replay


def main():
    parser = argparse.ArgumentParser(description='冻结节点的严格 JSON 格式验证')
    parser.add_argument('--protocol', type=Path, default=Path('data/benchmarks/dag-handoff-replay-v3.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--approved-protocol-sha256')
    parser.add_argument('--max-production-cost', type=float)
    args = parser.parse_args()
    loaded = load_replay(args.protocol)
    preflight = loaded[-1]
    if args.execute_paid_run:
        if args.approved_protocol_sha256 != preflight['protocol_sha256']:
            parser.error('付费格式验证需要获准的协议指纹')
        if args.max_production_cost is None or args.max_production_cost < preflight['max_production_cost']:
            parser.error('付费格式验证需要完整生产预算')
        result = run_replay(loaded, args.output_dir, client=OpenAICompatibleClient(max_retries=0),
                            production_limit=args.max_production_cost)
        print(json.dumps({'status':result['status'],'charged':result['charged'],'issues':result['issues']},ensure_ascii=False))
        return 0 if result['status']=='contract-valid' else 1
    if args.approved_protocol_sha256 is not None or args.max_production_cost is not None:
        parser.error('预检不接受付费授权参数')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir/'preflight.json', preflight)
    write_json(args.output_dir/'protocol.json', loaded[0])
    print(json.dumps(preflight,ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
