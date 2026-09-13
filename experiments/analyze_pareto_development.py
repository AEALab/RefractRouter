"""复算开发批次账本、阶段时序与配对结果，导出表格；不会产生模型调用。"""
import argparse
import csv
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.pareto_analysis import audit_and_analyze
from refractrouter.quality_statistics import analyze
from refractrouter.quality_study import file_digest, load_study, make_blind_packet


def table(path, rows):
    if not rows: return
    fields = sorted({k for row in rows for k in row})
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fields); writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                         for k, v in row.items()} for row in rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists(): parser.error('output already exists')
    for name in ('artifact-index.json', 'evaluation-index.json'):
        path = args.run_dir / name
        if not path.exists():
            if name == 'evaluation-index.json': continue
            raise ValueError('raw session has no finalized artifact index')
        for filename, expected in json.loads(path.read_text()).items():
            source = (args.run_dir / filename).resolve()
            if not source.is_relative_to(args.run_dir.resolve()) or file_digest(source) != expected:
                raise ValueError('raw artifact integrity failure')
    frozen = json.loads((args.run_dir / 'frozen.json').read_text())
    source = args.run_dir / 'evaluated-results.json'
    if not source.exists(): source = args.run_dir / 'session.json'
    result = json.loads(source.read_text())
    _, tasks, refs, _, _, manifest = load_study(args.study_dir)
    report = audit_and_analyze(frozen, result, tasks, refs, manifest)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / 'analysis.json', report)
    write_json(args.output_dir / 'quality-statistics.json', analyze(frozen, result, tasks, references=refs))
    table(args.output_dir / 'paired-runs.csv', report['rows'])
    table(args.output_dir / 'calls.csv', report['call_table'])
    table(args.output_dir / 'arm-summary.csv', [{'arm': arm, **row} for arm, row in report['summaries'].items()])
    packet, mapping = make_blind_packet([{**r, 'arm_id': r['arm']} for r in result['runs'] if 'output' in r], tasks, refs)
    write_json(args.output_dir / 'blind-output-packet.json', packet)
    write_json(args.output_dir / 'private-blind-mapping.json', mapping)
    write_json(args.output_dir / 'provenance.json', {'result_sha256': file_digest(source),
        'frozen_sha256': file_digest(args.run_dir / 'frozen.json'),
        'analysis_implementation': {str(p): file_digest(p) for p in
            (Path(__file__), Path(__file__).parents[1] / 'src/refractrouter/pareto_analysis.py')},
        'scope': '运行后分析版本独立绑定；冻结分析政策必须相同。'})
    write_json(args.output_dir / 'artifact-index.json', {p.name: file_digest(p) for p in sorted(args.output_dir.iterdir())})
    print(json.dumps({k: report[k] for k in ('actual_model_calls', 'actual_afp', 'ledger_audit', 'missing_runs', 'confirmed_pareto_frontier')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
