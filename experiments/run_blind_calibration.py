"""GLM-5.3 两样本独立校准；默认生成零调用预检，需要单独授权才执行。"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from refractrouter.blind_review import digest
from refractrouter.calibration_runner import calibration_plan, run_calibration
from refractrouter.openai_compatible import OpenAICompatibleClient

if __package__:
    from .run_k3_baseline import read_bundle, write
else:
    from run_k3_baseline import read_bundle, write

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--approved-preflight', type=Path)
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--max-review-cost', type=float)
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('必须使用全新输出目录')
    state = read_bundle(args.input_dir)
    if state.get('simulation') or state['stage'] != 'preflight':
        parser.error('必须使用真实对照的零调用预检材料')
    frozen = json.loads((args.input_dir/'preflight.json').read_text())
    forbidden = [m['api_model'] for m in frozen['config']['models']]
    plan = calibration_plan(state['calibration'], forbidden)
    code = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in (ROOT/'src/refractrouter', ROOT/'experiments') for p in sorted(base.glob('*.py'))}
    preflight = {'plan': plan, 'code_sha256': digest(code),
                 'input_index_sha256': hashlib.sha256((args.input_dir/'evidence-index.json').read_bytes()).hexdigest()}
    if args.execute_paid_run:
        if not args.approved_preflight or digest(json.loads(args.approved_preflight.read_text())) != digest(preflight):
            parser.error('必须提供与本次材料和代码完全一致的获批预检文件')
        if args.max_review_cost is None or not args.max_review_cost >= plan['reserved_cost'] or args.max_review_cost == float('inf'):
            parser.error('必须提供覆盖两次调用的有限评审额度')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write(args.output_dir/'preflight.json', preflight)
    summary = {'status': 'preflight', 'actual_model_calls': 0, 'actual_cost': 0,
               'reserved_cost': plan['reserved_cost'], 'billing_unit': 'AFP'}
    if args.execute_paid_run:
        client = OpenAICompatibleClient(max_retries=0, environment={**os.environ,
            'REFRACTROUTER_MODEL_PROGRESS': str(args.output_dir/'model-progress.ndjson')})
        summary = run_calibration(state['calibration'], plan, client, args.output_dir,
                                  limit=args.max_review_cost, forbidden_models=forbidden)
        summary['review_cost_limit'] = args.max_review_cost
        if summary['submitted_reviews']:
            write(args.output_dir/'reviews.json', summary['submitted_reviews'])
    write(args.output_dir/'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in {'submitted_reviews', 'calibration'}}, ensure_ascii=False))
    return 1 if summary['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
