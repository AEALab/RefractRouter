"""MoA 升级评审运行器：只对已确认分歧的案例调用两位升级评审。

升级评审通过本机 codex / claude CLI 产生外部模型费用，不经过 Ark 账本；
必须先 --preflight 冻结调用包络，再以 --live 执行，且两者策略哈希必须一致。
"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.moa_review import MOA_POLICY, default_invoke, digest, judge, output_messages
from refractrouter.quality_study import file_digest, load_study


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_NAME = 'escalation-calls.jsonl'


def disputed_case_ids(summary):
    """从聚合摘要取出需要升级复评的案例；没有分歧时返回空列表。"""
    return [item['case_id'] for item in summary.get('disputed', [])]


def envelope(case_ids):
    """零调用冻结：案例、调用数上限、超时之和与策略哈希。"""
    calls = len(case_ids) * len(MOA_POLICY['escalation'])
    return {'kind': 'escalation', 'cases': list(case_ids), 'maximum_calls': calls,
            'timeout_sum_seconds': calls * MOA_POLICY['timeout_seconds'],
            'policy_sha256': digest(MOA_POLICY), 'real_model_calls': 0}


def read_evidence(path):
    """读取已有升级证据，用于断点续跑。"""
    if not Path(path).is_file():
        return []
    text = Path(path).read_text(encoding='utf-8')
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def run_escalation(cases, tasks_by_id, output_dir, *, invoke=default_invoke):
    """逐案例调用两位升级评审，边跑边落盘；已完成的案例不重复调用。"""
    evidence_path = Path(output_dir) / EVIDENCE_NAME
    completed = {record['case_id'] for record in read_evidence(evidence_path)
                 if record.get('status') == 'reviewed'}
    records = []
    with evidence_path.open('a', encoding='utf-8') as handle:
        for case in cases:
            if case['case_id'] in completed:
                continue
            task = tasks_by_id[case['task_id']]
            messages, criteria = output_messages(task, case['output'])
            prompt_sha256 = digest(messages)
            for reviewer in MOA_POLICY['escalation']:
                record = judge(reviewer, messages, criteria, invoke)
                record.update(case_id=case['case_id'], task_id=task['task_id'],
                              task_sha256=task['task_sha256'], prompt_sha256=prompt_sha256,
                              role='escalation',
                              author_semantic_label=case['author_semantic_label'])
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
                handle.flush()
                records.append(record)
    return records


def summarize(cases, records, *, policy_sha256):
    """统计升级调用的状态与判定，不替代 criterion 级聚合。"""
    by_case = {}
    for record in records:
        entry = by_case.setdefault(record['case_id'], {})
        entry[record['reviewer_id']] = {'status': record['status'], 'verdict': record['verdict'],
                                        'error': record.get('error'),
                                        'wall_time_ms': record.get('wall_time_ms')}
    return {'schema_version': 'moa-escalation-run-v1',
            'scope': '分歧案例的升级评审证据；仍需与两位初审一起聚合才形成共识。',
            'policy_sha256': policy_sha256, 'cases': len(cases),
            'calls': len(records),
            'reviewed': sum(record['status'] == 'reviewed' for record in records),
            'failed': sum(record['status'] != 'reviewed' for record in records),
            'verdict_counts': {verdict: sum(r['verdict'] == verdict for r in records)
                               for verdict in ('pass', 'fail', 'pending')},
            'by_case': by_case,
            'reviewers': MOA_POLICY['escalation'],
            'moa_review_cost': {'cost_ledger': 'external-cli-account', 'known_usage': 'unknown',
                                'ark_afp': None, 'calls': len(records)}}


def render_readme(preflight, summary=None):
    """生成中文说明：冻结包络 + 升级评审身份 + 执行结果。"""
    envelope = preflight['envelope']
    lines = ['# MoA 升级评审（Issue #79）', '',
             '本目录由 `experiments/run_moa_escalation.py` 生成；只覆盖已确认分歧的案例。',
             '', '## 冻结包络', '',
             '- 案例：' + '、'.join(f'`{case_id}`' for case_id in envelope['cases'])
             + f"（{len(envelope['cases'])} 例）",
             f"- 调用上限：{envelope['maximum_calls']} 次（两位升级评审 × 案例数），"
             f"超时之和 {envelope['timeout_sum_seconds']} 秒。",
             f"- 策略哈希：`{envelope['policy_sha256']}`。", '', '## 升级评审', '']
    for reviewer in preflight['reviewers']:
        lines.append(f"- {reviewer['reviewer_id']}：{reviewer['cli']} CLI，模型 "
                     f"`{reviewer['model']}`，thinking effort `{reviewer['thinking_effort']}`。")
    lines += ['', '## 结果', '']
    if summary is None:
        lines.append('- 尚未执行 `--live`，本目录目前只有零调用冻结。')
    else:
        lines.append(f"- 调用 {summary['calls']} 次：reviewed {summary['reviewed']}、"
                     f"failed {summary['failed']}。")
        lines.append(f"- 判定：pass {summary['verdict_counts']['pass']}、"
                     f"fail {summary['verdict_counts']['fail']}、"
                     f"pending {summary['verdict_counts']['pending']}。")
        for case_id, entry in sorted(summary['by_case'].items()):
            verdicts = '、'.join(f"{reviewer}={value['verdict']}（{value['status']}）"
                                 for reviewer, value in sorted(entry.items()))
            lines.append(f"  - `{case_id}`：{verdicts}")
    lines += ['', '## 口径', '',
              '- 升级证据必须与两位初审一起经 `experiments/aggregate_moa_consensus.py` '
              '聚合后才形成共识；单独看升级判定不构成结论。',
              '- 升级评审是模型共识，不是真人审查，也不能证明真实用户接受度。']
    for note in preflight.get('notes', []):
        lines.append(f'- {note}')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--consensus', type=Path,
                        help='聚合摘要目录或 summary.json；用于取出 disputed 案例')
    parser.add_argument('--case-id', action='append', default=[],
                        help='显式指定案例；与 --consensus 二选一')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--note', action='append', default=[],
                        help='附加在 README 的口径说明；冻结时记录，执行时沿用')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preflight', action='store_true')
    mode.add_argument('--live', action='store_true')
    args = parser.parse_args(argv)
    if args.preflight and args.output_dir.exists():
        parser.error('output directory already exists')
    if args.live and not args.output_dir.is_dir():
        parser.error('--live requires an existing preflight output directory')
    if bool(args.consensus) == bool(args.case_id):
        parser.error('--consensus 与 --case-id 必须二选一')
    if args.consensus:
        summary_path = args.consensus
        if summary_path.is_dir():
            summary_path = summary_path / 'summary.json'
        case_ids = disputed_case_ids(json.loads(summary_path.read_text(encoding='utf-8')))
    else:
        case_ids = list(args.case_id)
    _, tasks, _references, controls, *_ = load_study(args.study_dir)
    tasks_by_id = {task['task_id']: task for task in tasks}
    by_case = {case['case_id']: case for case in controls}
    unknown = [case_id for case_id in case_ids if case_id not in by_case]
    if unknown:
        parser.error(f'unknown case ids: {unknown}')
    cases = [by_case[case_id] for case_id in case_ids]
    frozen = envelope(case_ids)
    if args.preflight:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir / 'preflight.json',
                   {'envelope': frozen, 'reviewers': MOA_POLICY['escalation'],
                    'policy_sha256': digest(MOA_POLICY),
                    'notes': list(args.note),
                    'targets': [{'case_id': case['case_id'], 'task_id': case['task_id'],
                                 'author_semantic_label': case['author_semantic_label'],
                                 'output_sha256': digest(case['output'])} for case in cases]})
        preflight = json.loads((args.output_dir / 'preflight.json').read_text(encoding='utf-8'))
        (args.output_dir / 'README.md').write_text(render_readme(preflight), encoding='utf-8')
        write_json(args.output_dir / 'artifact-index.json',
                   {path.name: file_digest(path) for path in sorted(args.output_dir.iterdir())})
        print(json.dumps({'mode': 'preflight', 'real_model_calls': 0, 'cases': len(cases),
                          'maximum_calls': frozen['maximum_calls'],
                          'policy_sha256': frozen['policy_sha256'],
                          'case_ids': case_ids}, ensure_ascii=False))
        return
    preflight = json.loads((args.output_dir / 'preflight.json').read_text(encoding='utf-8'))
    if preflight['envelope']['policy_sha256'] != digest(MOA_POLICY):
        raise SystemExit('MOA 策略已改变，请重新运行 --preflight')
    if preflight['envelope']['cases'] != case_ids:
        raise SystemExit('冻结案例与当前输入不一致，请重新运行 --preflight')
    records = run_escalation(cases, tasks_by_id, args.output_dir)
    preview = read_evidence(Path(args.output_dir) / EVIDENCE_NAME)
    write_json(args.output_dir / 'summary.json',
               summarize(cases, preview, policy_sha256=digest(MOA_POLICY)))
    summary = json.loads((args.output_dir / 'summary.json').read_text(encoding='utf-8'))
    (args.output_dir / 'README.md').write_text(render_readme(preflight, summary), encoding='utf-8')
    write_json(args.output_dir / 'artifact-index.json',
               {path.name: file_digest(path) for path in sorted(args.output_dir.iterdir())})
    print(json.dumps({'mode': 'live', 'cases': len(cases), 'new_records': len(records),
                      'total_records': len(preview)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
