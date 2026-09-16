"""MoA 评审 CLI：--preflight 零调用冻结策略；--live 显式执行外部模型评审。

live 会通过本机 codex / claude CLI 产生外部模型费用，必须使用新的输出目录，
且先有对应 preflight 冻结文件。评审不经过 Ark 账本，成本单独报告。
"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.moa_review import (MOA_POLICY, REVIEW_SCHEMA, digest,
    material_review, output_review, preflight_envelope, purpose_review)
from refractrouter.quality_study import file_digest, load_study

ROOT = Path(__file__).resolve().parents[1]


def _targets(args):
    if args.kind == 'material':
        _, tasks, refs, *_ = load_study(args.study_dir)
        return [{'task_id': t['task_id'], 'task_sha256': t['task_sha256'],
                 'reference_sha256': digest(refs[t['task_id']])} for t in tasks]
    if args.kind == 'output':
        if args.results is None:
            raise SystemExit('--kind output 需要 --results 指向已评估结果文件')
        result = json.loads(args.results.read_text())
        return [{'run_id': r['run_id'], 'task_id': r['task_id'], 'output_sha256': digest(r['output'])}
                for r in result['runs'] if 'output' in r]
    if args.frozen is None:
        raise SystemExit('--kind purpose 需要 --frozen 指向冻结协议文件')
    frozen = json.loads(args.frozen.read_text())
    return [{'policy_sha256': digest(frozen['statistics_policy']),
             'task_bindings': frozen['task_bindings']}]
    raise SystemExit('unknown kind')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--kind', choices=('material', 'output', 'purpose'), required=True)
    parser.add_argument('--results', type=Path)
    parser.add_argument('--frozen', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--live', action='store_true')
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error('output directory already exists')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    targets = _targets(args)
    if args.preflight:
        write_json(args.output_dir / 'preflight.json',
                   {'envelope': preflight_envelope(args.kind, targets), 'targets': targets,
                    'policy': MOA_POLICY, 'review_schema': REVIEW_SCHEMA})
        print(json.dumps({'mode': 'preflight', 'real_model_calls': 0,
                          'targets': len(targets),
                          'policy_sha256': digest(MOA_POLICY)}, ensure_ascii=False))
        return
    preflight = json.loads((args.output_dir / 'preflight.json').read_text())
    if preflight['envelope']['policy_sha256'] != digest(MOA_POLICY):
        raise SystemExit('MOA 策略已改变，请重新运行 --preflight')
    if args.kind == 'material':
        _, tasks, refs, *_ = load_study(args.study_dir)
        records = material_review(tasks, refs)
    elif args.kind == 'output':
        _, tasks, refs, *_ = load_study(args.study_dir)
        result = json.loads(args.results.read_text())
        rows = [r for r in result['runs'] if 'output' in r]
        records = output_review(tasks, refs, rows)
    else:
        frozen = json.loads(args.frozen.read_text())
        records = [purpose_review(digest(frozen['statistics_policy']), frozen['task_bindings'])]
    write_json(args.output_dir / 'moa-results.json',
               {'kind': args.kind, 'policy_sha256': digest(MOA_POLICY), 'records': records})
    write_json(args.output_dir / 'artifact-index.json',
               {p.name: file_digest(p) for p in sorted(args.output_dir.iterdir())})
    print(json.dumps({'mode': 'live', 'targets': len(targets),
                      'records': len(records),
                      'policy_sha256': digest(MOA_POLICY)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

