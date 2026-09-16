"""MoA 双初审证据聚合：把两侧单侧初审合并为逐 criterion 共识产物。

只读取既有证据文件，不发起任何模型调用。两位初审一致的 criterion 直接采用；
不一致时若没有升级证据，保留 pending，不推测升级结论。
"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.moa_review import (MOA_POLICY, aggregate, digest,
    final_quality_status, output_messages)
from refractrouter.quality_study import check_output, file_digest, load_study


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 'moa-consensus-v1'
SCOPE = ('两位初审模型的逐 criterion 共识；分歧在缺少升级证据时保留 pending。'
         '不是真人审查，也不能证明真实用户接受度或独立留出任务质量。')
ESCALATION_NOTE = {
    'executed': '已执行升级评审，分歧 criterion 由两位升级评审复评。',
    'not-executed': '未执行升级评审：当前没有升级证据，分歧 criterion 与缺少有效初审的 '
                    'criterion 一律保留 pending，不推测升级结论。',
}
ARTIFACT_NAMES = ('consensus.json', 'summary.json', 'README.md', 'artifact-index.json')


def read_records(path):
    """读取 JSONL 首轮证据，忽略空行。"""
    text = Path(path).read_text(encoding='utf-8')
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def index_by_case(records, source):
    """按 case_id 建立索引；重复证据直接报错，避免静默覆盖。"""
    by_case = {}
    for record in records:
        case_id = record.get('case_id')
        if case_id is None:
            raise ValueError(f'{source}: evidence without case_id')
        if case_id in by_case:
            raise ValueError(f'{source}: duplicate case evidence: {case_id}')
        by_case[case_id] = record
    return by_case


def record_view(record):
    """保留可核对的调用摘要，不复制正文，避免聚合文件膨胀。"""
    return {'reviewer_id': record['reviewer_id'], 'model': record['model'],
            'thinking_effort': record['thinking_effort'], 'status': record['status'],
            'verdict': record['verdict'], 'error': record.get('error'),
            'response_sha256': record.get('response_sha256'),
            'wall_time_ms': record.get('wall_time_ms')}


def case_consensus(case, task, reference, primary_records, escalation_records=()):
    """聚合单个案例：校验提示哈希、逐 criterion 共识与最终门槛。"""
    messages, criteria = output_messages(task, case['output'])
    prompt_sha256 = digest(messages)
    for record in list(primary_records) + list(escalation_records):
        if record.get('prompt_sha256') != prompt_sha256:
            raise ValueError(f"{record.get('case_id')}: prompt hash mismatch")
    deterministic = check_output(task, reference, case['output'])
    consensus = aggregate(list(primary_records), list(escalation_records), criteria)
    disputed = [row['criterion'] for row in consensus['criteria']
                if len(set(row['primary'].values())) > 1]
    return {
        'case_id': case['case_id'], 'task_id': task['task_id'],
        'author_semantic_label': case['author_semantic_label'],
        'prompt_sha256': prompt_sha256,
        'deterministic_status': deterministic['status'],
        'expected_check_status': case['expected_check_status'],
        'deterministic_status_matches_expectation': (
            deterministic['status'] == case['expected_check_status']),
        'primary': {record['reviewer_id']: record_view(record) for record in primary_records},
        'escalation': {record['reviewer_id']: record_view(record) for record in escalation_records},
        'consensus': consensus,
        'disputed_criteria': disputed,
        'final_status': final_quality_status(deterministic['status'], consensus['overall']),
        'expected_final_status': case['expected_final_status'],
    }


def summarize(cases, *, escalation_state, sources):
    """汇总共识判定、误判、待判定与升级状态。"""
    def count(predicate):
        return sum(predicate(case) for case in cases)

    acceptable = [c for c in cases if c['author_semantic_label'] == 'acceptable']
    unacceptable = [c for c in cases if c['author_semantic_label'] == 'unacceptable']
    def rate(numerator, denominator):
        return numerator / denominator if denominator else None
    false_accepts = count(lambda c: c['author_semantic_label'] == 'unacceptable'
                          and c['consensus']['overall'] == 'pass')
    false_rejects = count(lambda c: c['author_semantic_label'] == 'acceptable'
                          and c['consensus']['overall'] == 'fail')
    return {
        'schema_version': SCHEMA_VERSION,
        'scope': SCOPE,
        'sources': sources,
        'policy_sha256': digest(MOA_POLICY),
        'escalation_state': escalation_state,
        'cases': len(cases),
        'author_label_counts': {'acceptable': len(acceptable), 'unacceptable': len(unacceptable)},
        'consensus_counts': {
            status: count(lambda c, status=status: c['consensus']['overall'] == status)
            for status in ('pass', 'fail', 'pending')},
        'final_status_counts': {
            status: count(lambda c, status=status: c['final_status'] == status)
            for status in ('pass', 'fail', 'pending')},
        'deterministic_expectation_mismatches': [
            c['case_id'] for c in cases if not c['deterministic_status_matches_expectation']],
        'false_accepts': false_accepts,
        'false_rejects': false_rejects,
        'final_false_accepts': count(lambda c: c['author_semantic_label'] == 'unacceptable'
                                     and c['final_status'] == 'pass'),
        'final_false_rejects': count(lambda c: c['author_semantic_label'] == 'acceptable'
                                     and c['final_status'] == 'fail'),
        'false_accept_rate': rate(false_accepts, len(unacceptable)),
        'false_reject_rate': rate(false_rejects, len(acceptable)),
        'pending_on_unacceptable': count(lambda c: c['author_semantic_label'] == 'unacceptable'
                                         and c['consensus']['overall'] == 'pending'),
        'pending_on_acceptable': count(lambda c: c['author_semantic_label'] == 'acceptable'
                                       and c['consensus']['overall'] == 'pending'),
        'escalated_criteria': sum(c['consensus']['escalated_criteria'] for c in cases),
        'failed_records': sum(c['consensus']['failed_records'] for c in cases),
        'calls': sum(len(c['primary']) + len(c['escalation']) for c in cases),
        'disputed': [{'case_id': c['case_id'], 'author_semantic_label': c['author_semantic_label'],
                      'primary': {name: r['verdict'] for name, r in c['primary'].items()},
                      'criteria': c['disputed_criteria'], 'consensus': c['consensus']['overall'],
                      'escalation': {name: r['verdict'] for name, r in c['escalation'].items()}}
                     for c in cases if c['disputed_criteria']],
        'moa_review_cost': {'cost_ledger': 'external-cli-account', 'known_usage': 'unknown',
                            'ark_afp': None,
                            'calls': sum(len(c['primary']) + len(c['escalation']) for c in cases)},
    }


def render_readme(summary, notes):
    """生成中文说明，数字全部来自 summary，避免手写口径漂移。"""
    counts = summary['consensus_counts']
    labels = summary['author_label_counts']
    lines = [
        '# MoA 双初审逐 criterion 共识（Issue #79）',
        '',
        '本目录由 `experiments/aggregate_moa_consensus.py` 从既有单侧初审证据聚合生成，'
        '聚合过程不发起任何模型调用。',
        '',
        '## 来源',
        '',
    ]
    for source in summary['sources']:
        lines.append(f"- {source['role']}：`{source['path']}`（{source['cases']} 例，"
                     f"sha256 `{source['file_sha256']}`）")
    lines += [
        '',
        '## 结果',
        '',
        f"- 案例：{summary['cases']} 例（可接受 {labels['acceptable']}、"
        f"不可接受 {labels['unacceptable']}）。",
        f"- 共识判定：pass {counts['pass']}、fail {counts['fail']}、pending {counts['pending']}；"
        f"最终门槛同为 pass {summary['final_status_counts']['pass']}、"
        f"fail {summary['final_status_counts']['fail']}、"
        f"pending {summary['final_status_counts']['pending']}。",
        f"- 误放行 {summary['false_accepts']}、误杀 {summary['false_rejects']}；"
        f"待判定落在不可接受例 {summary['pending_on_unacceptable']} 例、"
        f"可接受例 {summary['pending_on_acceptable']} 例。",
        f"- 确定性检查与作者预期不一致：{len(summary['deterministic_expectation_mismatches'])} 例。",
        f"- 升级状态：{summary['escalation_state']}。{ESCALATION_NOTE[summary['escalation_state']]}",
        f"- 分歧 criterion {summary['escalated_criteria']} 项，无效初审记录 "
        f"{summary['failed_records']} 条，聚合使用调用记录 {summary['calls']} 条。",
        '',
        '## 分歧明细',
        '',
    ]
    if summary['disputed']:
        for item in summary['disputed']:
            primary = '、'.join(f'{name}={verdict}' for name, verdict in sorted(item['primary'].items()))
            lines.append(f"- `{item['case_id']}`（作者标签 {item['author_semantic_label']}，"
                         f"初审 {primary}，共识 {item['consensus']}）：")
            for criterion in item['criteria']:
                lines.append(f"  - {criterion}")
    else:
        lines.append('- 无。')
    lines += ['', '## 口径', '', f'- {SCOPE}']
    if notes:
        lines.append('')
        for note in notes:
            lines.append(f'- {note}')
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--primary-evidence', type=Path, action='append', required=True)
    parser.add_argument('--escalation-evidence', type=Path, action='append', default=[])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--note', action='append', default=[],
                        help='附加在 README 的口径说明；用于记录基础设施或授权限制')
    parser.add_argument('--refresh', action='store_true',
                        help='允许覆盖本脚本自己生成的四个产物，用于同一批证据重算')
    args = parser.parse_args(argv)
    if args.output_dir.exists() and not args.refresh:
        parser.error('output directory already exists')
    if args.refresh and not args.output_dir.is_dir():
        parser.error('--refresh 需要既有的输出目录')
    if args.refresh:
        unexpected = {path.name for path in args.output_dir.iterdir()} - set(ARTIFACT_NAMES)
        if unexpected:
            parser.error(f'输出目录存在非本脚本产物，拒绝覆盖：{sorted(unexpected)}')
    _, tasks, references, controls, *_ = load_study(args.study_dir)
    by_id = {task['task_id']: task for task in tasks}
    case_ids = [case['case_id'] for case in controls]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit('study contains duplicate case ids')
    primary_sets = []
    sources = []
    for path in args.primary_evidence:
        records = read_records(path)
        primary_sets.append(index_by_case(records, path))
        sources.append({'role': 'primary', 'path': str(path), 'cases': len(records),
                        'file_sha256': file_digest(path)})
    escalation_by_case = {}
    for path in args.escalation_evidence:
        records = read_records(path)
        escalation_by_case.update(index_by_case(records, path))
        sources.append({'role': 'escalation', 'path': str(path), 'cases': len(records),
                        'file_sha256': file_digest(path)})
    expected_ids = set(case_ids)
    for index, by_case in enumerate(primary_sets):
        if set(by_case) != expected_ids:
            raise SystemExit(f'primary evidence {index} case set differs from study controls')
    if escalation_by_case and not set(escalation_by_case) <= expected_ids:
        raise SystemExit('escalation evidence contains unknown cases')
    cases = []
    for case in controls:
        task = by_id[case['task_id']]
        cases.append(case_consensus(
            case, task, references[task['task_id']],
            [by_case[case['case_id']] for by_case in primary_sets],
            [escalation_by_case[case['case_id']]] if case['case_id'] in escalation_by_case else []))
    escalation_state = 'executed' if escalation_by_case else 'not-executed'
    summary = summarize(cases, escalation_state=escalation_state, sources=sources)
    if args.note:
        summary['notes'] = list(args.note)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / 'consensus.json',
               {'schema_version': SCHEMA_VERSION, 'scope': SCOPE, 'sources': sources,
                'policy_sha256': digest(MOA_POLICY), 'escalation_state': escalation_state,
                'cases': cases})
    write_json(args.output_dir / 'summary.json', summary)
    (args.output_dir / 'README.md').write_text(render_readme(summary, args.note),
                                               encoding='utf-8')
    write_json(args.output_dir / 'artifact-index.json',
               {path.name: file_digest(path) for path in sorted(args.output_dir.iterdir())})
    print(json.dumps({'mode': 'aggregate', 'cases': len(cases),
                      'escalation_state': escalation_state,
                      'consensus_counts': summary['consensus_counts'],
                      'disputed_cases': [item['case_id'] for item in summary['disputed']],
                      'false_accepts': summary['false_accepts'],
                      'false_rejects': summary['false_rejects']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
