"""对冻结样本与结果作配对统计，可导入真实的人工意见；不自动生成审查签署。"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.quality_statistics import analyze
from refractrouter.quality_study import load_study, make_blind_packet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, required=True)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--human-reviews', type=Path)
    parser.add_argument('--purpose-review', type=Path)
    parser.add_argument('--blind-output-dir', type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output already exists')
    if args.blind_output_dir and args.blind_output_dir.exists():
        parser.error('blind output directory already exists')
    _, tasks, refs, *_ = load_study(args.study_dir)
    result = json.loads(args.results.read_text())
    report = analyze(json.loads(args.frozen.read_text()), result, tasks,
                     references=refs,
                     human_reviews=json.loads(args.human_reviews.read_text()) if args.human_reviews else (),
                     purpose_review=json.loads(args.purpose_review.read_text()) if args.purpose_review else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    if args.blind_output_dir:
        records = [{**r, 'arm_id': r['arm'], 'model_id': None} for r in result['runs'] if 'output' in r]
        packet, mapping = make_blind_packet(records, tasks, refs)
        args.blind_output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.blind_output_dir / 'blind-output-packet.json', packet)
        write_json(args.blind_output_dir / 'private-blind-mapping.json', mapping)
    print(json.dumps({'observed_runs': report['observed_runs'], 'human_review_pending': report['human_review_pending'],
                      'confirmed_pareto_frontier': report['confirmed_pareto_frontier']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
