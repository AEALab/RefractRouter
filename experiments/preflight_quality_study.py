"""归档 #52 材料校准、盲审模板与逐路线包络；只支持零模型调用。"""
import argparse
import json
from pathlib import Path

from refractrouter.quality_study import (file_digest, load_study, make_blind_packet,
                                        execution_payload, material_review_packet, preflight)

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    report = preflight(args.study_dir)
    protocol, tasks, refs, controls, _, _ = load_study(args.study_dir)
    records = [{'task_id': c['task_id'], 'arm_id': c['case_id'], 'model_id': 'author-control',
                'output': c['output']} for c in controls]
    packet, mapping = make_blind_packet(records, tasks, refs)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    def write(name, data):
        (args.output_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    write('protocol.json', protocol)
    write('preflight.json', report)
    write('execution-inputs.json', {t['task_id']: execution_payload(t) for t in tasks})
    write('blind-calibration-packet.json', packet)
    write('private-blind-mapping.json', mapping)
    write('material-review-packet.json', material_review_packet(tasks, refs))
    write('artifact-index.json', {p.name: file_digest(p) for p in sorted(args.output_dir.iterdir())})
    print(json.dumps({k: report[k] for k in ('real_model_calls', 'formal_run_ready', 'task_counts', 'totals')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
