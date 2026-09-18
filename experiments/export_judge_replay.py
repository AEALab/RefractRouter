"""匯出已封存的 judge 判例重播集；零模型調用。

來源是已完成的付費批次 @@reports/pareto-development-v1/live-01/session.json@@：
每一列 @@runs@@ 都帶有線上 @@delivery-judge@@ 與離線 @@research-judge@@ 兩次呼叫，
而 @@calls@@ 保留了當時送出的完整 @@request_messages@@。本工具把它們整理成
可重播的判例集，供後續用本地 CLI MoA 或便宜模型重判並比較一致性（#98）；
不發起任何模型調用，也不改寫既有證據。
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from refractrouter.agent import atomic_json

SCHEMA_VERSION = 'judge-replay-v1'
SOURCE_SCHEMAS = ('bound-quality-results-v1', 'pareto-development-report-v1')
JUDGE_STAGES = ('delivery-judge', 'research-judge')


def _sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _load_source(source):
    session_path = source / 'session.json'
    if not session_path.is_file():
        raise ValueError('缺少 session.json：' + str(session_path))
    raw = session_path.read_bytes()
    session = json.loads(raw)
    if session.get('schema_version') not in SOURCE_SCHEMAS:
        raise ValueError('未預期的 session schema：' + str(session.get('schema_version')))
    if not isinstance(session.get('runs'), list) or not isinstance(session.get('calls'), list):
        raise ValueError('session 缺少 runs 或 calls 清單')
    return session, hashlib.sha256(raw).hexdigest()


def _verdict(review):
    return review.get('verdict') if isinstance(review, dict) else None


def _criterion_map(review):
    if not isinstance(review, dict):
        return {}
    return {c.get('criterion'): c.get('verdict') for c in review.get('criteria', [])
            if isinstance(c, dict) and c.get('criterion')}


def _case_record(row, index, stats):
    run_id = row.get('run_id')
    if not run_id:
        return None, 'missing-run-id'
    calls = {}
    for stage in JUDGE_STAGES:
        call = index.get(run_id + ':' + stage)
        if call is None:
            return None, 'missing-' + stage
        if not call.get('request_messages'):
            return None, 'missing-request-messages'
        calls[stage] = call
    messages = {stage: call['request_messages'] for stage, call in calls.items()}
    same_request = messages['delivery-judge'] == messages['research-judge']
    recorded = {}
    for stage, call in calls.items():
        review = row.get('delivery_review') if stage == 'delivery-judge' else row.get('research_review')
        recorded[stage] = {
            'label': call['label'],
            'model_id': call.get('model_id'),
            'category': call.get('category'),
            'status': call.get('status'),
            'charged_afp': call.get('charged'),
            'input_tokens': call.get('input_tokens'),
            'output_tokens': call.get('output_tokens'),
            'reasoning_tokens': call.get('reasoning_tokens'),
            'request_sha256': call.get('input_sha256'),
            'response_sha256': call.get('output_sha256'),
            'request_id': call.get('request_id'),
            'response_output': call.get('response_output'),
            'verdict': _verdict(review),
            'criteria': _criterion_map(review),
        }
    stats['verdict_pairs'][(recorded['delivery-judge']['verdict'],
                            recorded['research-judge']['verdict'])] += 1
    delivery = recorded['delivery-judge']['criteria']
    research = recorded['research-judge']['criteria']
    for criterion in sorted(set(delivery) | set(research)):
        stats['criterion_pairs'][(delivery.get(criterion), research.get(criterion))] += 1
    return {
        'case_id': run_id,
        'run_id': run_id,
        'task_id': row.get('task_id'),
        'arm': row.get('arm'),
        'repeat': row.get('repeat'),
        'task_sha256': row.get('task_sha256'),
        'request': {
            'messages': messages['delivery-judge'],
            'payload_sha256': _sha256(messages['delivery-judge'][-1]['content']),
            'identical_between_judges': same_request,
        },
        'recorded': recorded,
    }, None


def _agreement(counter):
    total = sum(counter.values())
    agree = sum(count for (left, right), count in counter.items() if left == right)
    return agree, total


def _pair_summary(counter):
    return {' -> '.join(str(part) for part in pair): count
            for pair, count in sorted(counter.items(), key=lambda item: str(item[0]))}


def export(source, out):
    """把封存批次整理成重播集，回傳摘要；只讀寫檔案，不呼叫模型。"""
    source = Path(source)
    out = Path(out)
    session, source_sha256 = _load_source(source)
    index = {call['label']: call for call in session.get('calls', [])}
    stats = {'verdict_pairs': Counter(), 'criterion_pairs': Counter()}
    cases = []
    skipped = Counter()
    for row in session.get('runs', []):
        case, reason = _case_record(row, index, stats)
        if case is None:
            skipped[reason] += 1
        else:
            cases.append(case)
    cases.sort(key=lambda item: item['case_id'])

    verdict_agree, verdict_total = _agreement(stats['verdict_pairs'])
    criterion_agree, criterion_total = _agreement(stats['criterion_pairs'])
    charged = Counter()
    for case in cases:
        for record in case['recorded'].values():
            charged[record['model_id']] += record.get('charged_afp') or 0
    by_stage = Counter()
    for case in cases:
        for stage, record in case['recorded'].items():
            by_stage[stage] += record.get('charged_afp') or 0
    summary = {
        'schema_version': SCHEMA_VERSION,
        'source': str(source),
        'source_sha256': source_sha256,
        'case_count': len(cases),
        'skipped': dict(skipped),
        'identical_request_between_judges': sum(
            1 for case in cases if case['request']['identical_between_judges']),
        'replayed_afp_by_stage': {stage: round(value, 6) for stage, value in sorted(by_stage.items())},
        'replayed_afp_by_model': {model: round(value, 6) for model, value in sorted(charged.items())},
        'verdict_pairs': _pair_summary(stats['verdict_pairs']),
        'verdict_agreement': round(verdict_agree / verdict_total, 6) if verdict_total else None,
        'criterion_pairs': _pair_summary(stats['criterion_pairs']),
        'criterion_agreement': round(criterion_agree / criterion_total, 6) if criterion_total else None,
        'noise_floor_note': '同一 judge 模型、同一 payload 的兩次取樣；一致率是重複取樣基準，不是獨立第二意見。',
    }
    out.mkdir(parents=True, exist_ok=True)
    atomic_json(out / 'cases.json', {'schema_version': SCHEMA_VERSION, 'source': str(source),
                                     'source_sha256': source_sha256, 'cases': cases})
    atomic_json(out / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description='匯出 judge 判例重播集（零模型調用）')
    parser.add_argument('--source', default='reports/pareto-development-v1/live-01',
                        help='含 session.json 的封存批次目錄')
    parser.add_argument('--out', default='reports/judge-cost-v1/replay-01', help='輸出目錄')
    args = parser.parse_args()
    summary = export(args.source, args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
