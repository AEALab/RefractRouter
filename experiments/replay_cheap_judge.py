"""用 cheap 模型（ark/deepseek-v4-flash）重播已封存 judge 判例；候选 B 的小样本对照。

每个判例沿用与 Ark judge 完全相同的 request_messages，只更换模型乐器；单一评审者，
零重试，输出严格解析（pending 留在分母）。成本按冻结清单 0.05 AFP/1k 以封存 token
估算，同时记录实际调用次数与墙钟；本工具不经 Ark 账本读取余额，真实扣费以 Ark 侧为准。
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re

from refractrouter.agent import atomic_json
from refractrouter.moa_review import MOA_POLICY, _parse, default_invoke
from refractrouter.quality_study import digest

SCHEMA_VERSION = 'cheap-judge-replay-v1'
MODEL = 'ark/deepseek-v4-flash'
EFFORT = 'high'
TIMEOUT_SECONDS = 480
MAX_RETRIES = 0
WORKERS = 6
PRICE_IN_PER_1K = 0.05
PRICE_OUT_PER_1K = 0.05
REFERENCES = ('delivery-judge', 'research-judge')
DEFAULT_CASES = 'reports/judge-cost-v1/replay-01/cases.json'
DEFAULT_THRESHOLDS = 'reports/judge-cost-v1/replay-01/thresholds.json'
DEFAULT_OUT = 'reports/judge-cost-v1/cheap-judge-01'
FROZEN_NAME = 'cheap-judge-protocol.json'

REVIEWER = {
    'reviewer_id': 'cheap-judge',
    'cli': 'codex',
    'model': MODEL,
    'thinking_effort': EFFORT,
    'output_schema': False,
}

def load_cases(path=DEFAULT_CASES):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('schema_version') != 'judge-replay-v1':
        raise ValueError('未預期的判例 schema：' + str(payload.get('schema_version')))
    return payload['cases']

def load_thresholds(path=DEFAULT_THRESHOLDS):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    return payload['thresholds']

def _case_messages(case):
    return case['request']['messages']

def _case_criteria(case):
    payload = json.loads(case['request']['messages'][-1]['content'])
    return payload['criteria']

def _estimate_afp(case):
    recorded = case['recorded']['delivery-judge']
    tokens = (recorded.get('input_tokens') or 0) + (recorded.get('output_tokens') or 0)
    return tokens * (PRICE_IN_PER_1K / 1000)

def _arm_of(case_id):
    match = re.match(r'^.+?-r[12]-(.+)$', case_id)
    return match.group(1) if match else 'unknown'

def invoke_case(case):
    messages = _case_messages(case)
    criteria = _case_criteria(case)
    started = None
    exit_code, stdout, stderr, elapsed_ms, cli_version = default_invoke(REVIEWER, messages)
    parsed, parse_error = _parse(stdout, criteria)
    verdict = parsed['verdict'] if parsed else 'pending'
    criteria_map = {item['criterion']: item.get('verdict') for item in parsed['criteria']} if parsed else {}
    return {
        'case_id': case['case_id'],
        'task_id': case['task_id'],
        'arm': _arm_of(case['case_id']),
        'repeat': case['repeat'],
        'ark': {
            'verdicts': {ref: case['recorded'][ref]['verdict'] for ref in REFERENCES},
            'criteria': {ref: case['recorded'][ref]['criteria'] for ref in REFERENCES},
        },
        'reviewer_id': REVIEWER['reviewer_id'],
        'model': MODEL,
        'thinking_effort': EFFORT,
        'exit_code': exit_code,
        'wall_time_ms': round(elapsed_ms, 3),
        'verdict': verdict,
        'criteria': {criterion: criteria_map.get(criterion, 'pending') for criterion in criteria},
        'raw_response': stdout if stdout else None,
        'stderr': stderr or None,
        'parse_error': parse_error or None,
        'prompt_sha256': digest(messages),
        'response_sha256': digest(stdout) if stdout else None,
        'estimated_afp': _estimate_afp(case),
        'ark_afp_in_ledger': 0,
    }

def _agreement(counter):
    total = sum(counter.values())
    agree = sum(count for (left, right), count in counter.items() if left == right)
    return agree, total

def summarize(records, thresholds):
    ark = {r['case_id']: r['ark'] for r in records}
    disagree = [r['case_id'] for r in records
                if ark[r['case_id']]['verdicts']['delivery-judge']
                != ark[r['case_id']]['verdicts']['research-judge']]
    agreed = [r for r in records if r['case_id'] not in disagree]
    by_reference = {}
    for ref in REFERENCES:
        verdicts = Counter()
        criteria = Counter()
        risks = 0
        for r in agreed:
            left = ark[r['case_id']]['verdicts'][ref]
            right = r['verdict']
            verdicts[(left, right)] += 1
            if left == 'fail' and right == 'pass':
                risks += 1
            for criterion in r['criteria']:
                ark_c = ark[r['case_id']]['criteria'][ref].get(criterion)
                criteria[(ark_c, r['criteria'][criterion])] += 1
        agree, total = _agreement(verdicts)
        c_agree, c_total = _agreement(criteria)
        by_reference[ref] = {
            'verdict_agreement': round(agree / total, 6) if total else None,
            'criterion_agreement': round(c_agree / c_total, 6) if c_total else None,
            'verdict_pairs': _pairs(verdicts),
            'criterion_pairs': _pairs(criteria),
            'risk_direction': round(risks / len(records), 6) if records else None,
            'verdict_agreement_ok': (agree / total if total else 0) >= thresholds['verdict_agreement_min'],
            'criterion_agreement_ok': (c_agree / c_total if c_total else 0) >= thresholds['criterion_agreement_min'],
            'risk_direction_ok': (risks / len(records) if records else 1) <= thresholds['risk_direction_max'],
        }
        by_reference[ref]['all_ok'] = all(
            by_reference[ref][key] for key in ('verdict_agreement_ok', 'criterion_agreement_ok', 'risk_direction_ok'))
    decision = 'replace' if all(info['all_ok'] for info in by_reference.values()) else 'keep'
    cost = {
        'calls': len(records),
        'estimated_afp': round(sum(r['estimated_afp'] for r in records), 6),
        'wall_time_ms': sum(r['wall_time_ms'] for r in records),
        'ark_afp_in_ledger': 0,
        'note': '成本為按封存 token 與 0.05 AFP/1k 的估算；實際扣費以 Ark 側為準，本工具不讀取餘額。'
    }
    latency_ms = sorted(r['wall_time_ms'] for r in records)
    latency = {
        'median_ms': latency_ms[len(latency_ms) // 2] if latency_ms else None,
        'p90_ms': latency_ms[int(len(latency_ms) * 0.9)] if latency_ms else None,
        'max_ms': max(latency_ms) if latency_ms else None,
    }
    return {
        'schema_version': SCHEMA_VERSION,
        'case_count': len(records),
        'excluding_reference_disagreements': len(disagree),
        'reference_disagreement_cases': sorted(disagree),
        'by_reference': by_reference,
        'decision': decision,
        'decision_rule': '未達門檻則不替換 judge；達到門檻才進入階段四評審設計。',
        'thresholds': thresholds,
        'cost': cost,
        'latency_ms': latency,
        'scope': '候選 B 的 cheap judge 重播；只比較判定一致性，不構成真人審查。',
    }

def _pairs(counter):
    return {' -> '.join(str(part) for part in pair): count for pair, count in sorted(counter.items())}

def run(cases_path=DEFAULT_CASES, out=DEFAULT_OUT, *, force=False, case_ids=None, limit=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    records_path = out / 'records.json'
    records = []
    done = set()
    if records_path.is_file() and not force:
        records = json.loads(records_path.read_text(encoding='utf-8'))['records']
        done = {r['case_id'] for r in records}
    cases = load_cases(cases_path)
    if case_ids:
        wanted = set(case_ids)
        cases = [c for c in cases if c['case_id'] in wanted]
    pending = [c for c in cases if c['case_id'] not in done]
    if limit is not None:
        pending = pending[:limit]
    print(f'待重判 {len(pending)} 例（已完成 {len(done)} 例，個案並行 {WORKERS}）', flush=True)
    finished = 0

    def collect(record):
        nonlocal finished
        records.append(record)
        finished += 1
        atomic_json(records_path, {'schema_version': SCHEMA_VERSION,
                                   'cases_path': str(cases_path),
                                   'records': records})
        print(f'[{finished}/{len(pending)}] {record["case_id"]} → {record["verdict"]} '
              f'（{round(record["wall_time_ms"] / 1000, 1)}s，est {round(record["estimated_afp"], 4)} AFP）', flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(invoke_case, case) for case in pending]
        for future in as_completed(futures):
            collect(future.result())
    atomic_json(records_path, {'schema_version': SCHEMA_VERSION,
                               'cases_path': str(cases_path),
                               'records': records})
    return records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', default=DEFAULT_CASES)
    parser.add_argument('--thresholds', default=DEFAULT_THRESHOLDS)
    parser.add_argument('--out', default=DEFAULT_OUT)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--case-ids', default=None, help='逗號分隔的 case_id 白名單')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--summarize-only', action='store_true')
    parser.add_argument('--freeze', action='store_true', help='寫出凍結協議並退出（零調用）')
    args = parser.parse_args()
    if args.freeze:
        protocol = {
            'schema_version': 'cheap-judge-protocol-v1',
            'purpose': '候选 B：cheap 模型重判已封存 judge 判例，验证 92.5% 一致率可否达成。',
            'model': MODEL,
            'thinking_effort': EFFORT,
            'timeout_seconds': TIMEOUT_SECONDS,
            'request_max_retries': MAX_RETRIES,
            'reviewer_policy': '单一评审者，无升级，输出严格解析；unparsed 记 pending 留在分母。',
            'prompt': '固定沿用封存请求的 request_messages，与 Ark judge 相同。',
            'cases_path': args.cases,
            'cases_sha256': digest(json.loads(Path(args.cases).read_text(encoding='utf-8'))),
            'thresholds_path': args.thresholds,
            'max_calls': 107,
            'estimated_afp_ceiling': None,
            'price': {'input_per_1k': PRICE_IN_PER_1K, 'output_per_1k': PRICE_OUT_PER_1K},
            'decision_rule': '未达门槛则不替换 judge。',
        }
        cases = load_cases(args.cases)
        ceiling = round(sum(_estimate_afp(case) for case in cases) * 1.5, 6)
        protocol['estimated_afp_ceiling'] = ceiling
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        atomic_json(out / FROZEN_NAME, protocol)
        print(json.dumps(protocol, ensure_ascii=False, indent=2))
        return
    cases = load_cases(args.cases)
    records = run(args.cases, args.out, force=args.force,
                  case_ids=[item for item in (args.case_ids.split(',') if args.case_ids else []) if item],
                  limit=args.limit)
    thresholds = load_thresholds(args.thresholds)
    summary = summarize(records, thresholds)
    out = Path(args.out)
    atomic_json(out / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()

