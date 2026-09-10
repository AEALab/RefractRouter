"""K3 冻结材料的 GLM-5.3 独立评审，默认零调用，复用已完成校准。"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

from refractrouter.blind_review import digest
from refractrouter.k3_review_runner import validate_review_input, review_plan, run_reviews
from refractrouter.openai_compatible import OpenAICompatibleClient

if __package__:
    from .run_k3_baseline import read_bundle, write
else:
    from run_k3_baseline import read_bundle, write

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--calibration-reviews', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--approved-preflight', type=Path)
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--max-review-cost', type=float)
    parser.add_argument('--timeout-seconds', type=float, default=600.0,
                        help='非流式评审的 socket 等待时间，默认 600 秒，必须随预检冻结')
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error('必须使用不存在的新输出目录')
    state = read_bundle(args.input_dir)
    calibration = json.loads(args.calibration_reviews.read_text())['calibration']
    public, key, forbidden = validate_review_input(state, calibration)
    try:
        plan = review_plan(public, forbidden, timeout_seconds=args.timeout_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    code = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in (ROOT / 'src/refractrouter', ROOT / 'experiments') for p in sorted(base.glob('*.py'))}
    preflight = {'plan': plan, 'code_sha256': digest(code),
                 'source_config_sha256': state['config_sha256'],
                 'input_index_sha256': hashlib.sha256((args.input_dir / 'evidence-index.json').read_bytes()).hexdigest(),
                 'calibration_reviews_sha256': digest(calibration)}
    if args.execute_paid_run:
        if (not args.approved_preflight
                or digest(json.loads(args.approved_preflight.read_text())) != digest(preflight)):
            parser.error('必须提供与材料、校准和代码完全一致的获批预检')
        if (args.max_review_cost is None or not math.isfinite(args.max_review_cost)
                or args.max_review_cost < plan['reserved_cost']):
            parser.error('评审额度必须有限且覆盖冻结预留')
    args.output_dir.mkdir(parents=True)
    write(args.output_dir / 'preflight.json', preflight)
    summary = {'status': 'preflight', 'actual_model_calls': 0, 'production_calls': 0,
               'actual_cost': 0, 'reserved_cost': plan['reserved_cost'], 'billing_unit': 'AFP'}
    if args.execute_paid_run:
        client = OpenAICompatibleClient(max_retries=0, timeout_seconds=plan['timeout_seconds'],
            environment={**os.environ, 'REFRACTROUTER_MODEL_PROGRESS': str(args.output_dir / 'model-progress.ndjson')})
        summary = run_reviews(public, plan, client, args.output_dir,
                              limit=args.max_review_cost, forbidden_models=forbidden)
        write(args.output_dir / 'partial-reviews.json', summary.pop('partial_reviews'))
        if summary['status'] == 'review-ready':
            response = json.loads((args.output_dir / 'partial-reviews.json').read_text())
            write(args.output_dir / 'reviews.json', {'calibration': calibration, key: response})
    write(args.output_dir / 'summary.json', summary)
    write(args.output_dir / 'evidence-index.json', {'artifacts': {
        str(p.relative_to(args.output_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(args.output_dir.rglob('*')) if p.is_file()}})
    print(json.dumps({k: v for k, v in summary.items() if k != 'scores'}, ensure_ascii=False))
    return 1 if summary['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
