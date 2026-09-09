"""Issue #38 三组恢复对照；默认零调用，真实运行需确认协议指纹与双预算。"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.recovery_study import preflight, run_study


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=Path('data/benchmarks/recovery-study-v1.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--demo', action='store_true')
    modes.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--approved-protocol-sha256')
    parser.add_argument('--max-production-cost', type=float)
    parser.add_argument('--max-evaluation-cost', type=float)
    args = parser.parse_args(argv)
    protocol = json.loads(args.protocol.read_text())
    manifest = load_model_manifest(args.protocol.parent / protocol['manifest_path'])
    profile = json.loads((args.protocol.parent / protocol['profile_path']).read_text())
    preview = preflight(protocol, manifest, profile)
    if args.execute_paid_run:
        if args.approved_protocol_sha256 != preview['protocol_sha256']:
            parser.error('真实执行必须提供已获准的冻结协议 SHA-256')
        for name in ('production', 'evaluation'):
            value = getattr(args, 'max_' + name + '_cost')
            if value is None or not value >= preview['budget'][name]:
                parser.error('授权的双预算必须覆盖完整调用包络；运行器仍以冻结包络为硬上限')
    elif any(v is not None for v in (args.approved_protocol_sha256, args.max_production_cost, args.max_evaluation_cost)):
        parser.error('预检与模拟模式不接受付费授权参数')
    if not args.demo and not args.execute_paid_run:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir / 'protocol.json', protocol)
        write_json(args.output_dir / 'preflight.json', preview)
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0
    result = run_study(protocol, manifest, profile, args.output_dir, simulated=args.demo,
        client=OpenAICompatibleClient(max_retries=0) if args.execute_paid_run else None)
    print(json.dumps({'status': result['status'], 'simulated': result['simulated'],
                      'charged': result['charged'], 'calls': len(result['calls'])}, ensure_ascii=False))
    return int(result['status'] == 'stopped')


if __name__ == '__main__':
    raise SystemExit(main())
