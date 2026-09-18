"""用本地 CLI 多模型共识（MoA）重判已封存的 judge 判例；零 Ark AFP。

输入是 reports/judge-cost-v1/replay-01/cases.json（由 export_judge_replay.py 產生）：
每一例都帶著當時送給 Ark judge 的完整 request_messages。本工具固定沿用同一份
prompt，只把評審儀器換成本地 CLI，逐 criterion 比較與 Ark 兩次封存裁決的一致性，
並按已凍結門檻（同目錄 thresholds.json）給出是否可替換的判定。

遠端調用只發生在本地 codex / claude CLI；本工具不經 Ark 账本，Ark AFP 記為 0。
逐例寫入，可中斷後續跑。
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from difflib import SequenceMatcher
import json
from pathlib import Path
import time

from refractrouter.agent import atomic_json
from refractrouter.moa_review import (MOA_POLICY, _parse, _strip_code_fences, aggregate,
                                      criterion_consensus, default_invoke, judge)
from refractrouter.quality_study import digest

SCHEMA_VERSION = 'judge-moa-replay-v1'
REFERENCES = ('delivery-judge', 'research-judge')
DEFAULT_CASES = 'reports/judge-cost-v1/replay-01/cases.json'
DEFAULT_OUT = 'reports/judge-cost-v1/moa-local-01'
LABEL_SIMILARITY_MIN = 0.80
LABEL_SIMILARITY_MARGIN = 0.05


def load_cases(path):
    payload = json.loads(Path(path).read_text())
    if payload.get('schema_version') != 'judge-replay-v1':
        raise ValueError('未預期的判例 schema：' + str(payload.get('schema_version')))
    cases = payload.get('cases')
    if not isinstance(cases, list) or not cases:
        raise ValueError('判例集為空或格式錯誤')
    return cases


def case_criteria(case):
    """從封存請求的 payload 取回 criteria 的原順序與原文。"""
    messages = case['request']['messages']
    payload = json.loads(messages[-1]['content'])
    criteria = payload.get('criteria')
    if not isinstance(criteria, list) or not criteria:
        raise ValueError('判例缺少 criteria：' + str(case.get('case_id')))
    return list(criteria)


def ark_verdicts(case):
    return {stage: case['recorded'][stage]['verdict'] for stage in REFERENCES}


def ark_criteria(case):
    return {stage: dict(case['recorded'][stage]['criteria']) for stage in REFERENCES}


def load_response_object(stdout):
    """解析評審回應的 JSON 物件；沿用核心的圍欄剝離，失敗回傳 None。"""
    try:
        payload = json.loads(_strip_code_fences(stdout or ''))
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _similarity(left, right):
    return SequenceMatcher(None, left.strip(), right.strip()).ratio()


def repair_criterion_labels(stdout, criteria, min_ratio=LABEL_SIMILARITY_MIN,
                            margin=LABEL_SIMILARITY_MARGIN):
    """把被近義改寫的 criterion 標籤對回原文；回傳 (回應文字, 修補紀錄)。

    只為觀測候選評審者能否替換：核心 parse_review 要求標籤集合完全相等，
    近義改寫（例如把「扩大」寫成「夸大」）會讓整例判 pending，失去可比訊號。
    配對規則保守：數量必須一致、逐一取相似度最高者、且與次高者必須拉開差距；
    任何一項無法確定就整份原樣返回，交由凍結語意判 pending。每次修補都寫進
    紀錄，報告須同時列出有修補與無修補的結果。
    """
    payload = load_response_object(stdout)
    if payload is None:
        return stdout, {'status': 'unparsed', 'repairs': []}
    rows = payload.get('criteria')
    if not isinstance(rows, list) or len(rows) != len(criteria):
        returned = len(rows) if isinstance(rows, list) else None
        return stdout, {'status': 'count-mismatch', 'repairs': [],
                        'expected_count': len(criteria), 'returned_count': returned}
    mapping = {}
    repairs = []
    unmatched = []
    used = set()
    for index, row in enumerate(rows):
        label = row.get('criterion') if isinstance(row, dict) else None
        if isinstance(label, str) and label in criteria and label not in used:
            used.add(label)
            mapping[index] = label
    for index, row in enumerate(rows):
        if index in mapping:
            continue
        label = row.get('criterion') if isinstance(row, dict) else None
        if not isinstance(label, str):
            unmatched.append({'index': index, 'returned': None})
            continue
        scored = sorted(((_similarity(label, item), item)
                         for item in criteria if item not in used),
                        key=lambda pair: (pair[0], pair[1]), reverse=True)
        if not scored:
            unmatched.append({'index': index, 'returned': label})
            continue
        ratio, best = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if ratio >= min_ratio and ratio - runner_up >= margin:
            used.add(best)
            mapping[index] = best
            repairs.append({'index': index, 'returned': label, 'matched': best,
                            'ratio': round(ratio, 4), 'runner_up_ratio': round(runner_up, 4)})
        else:
            unmatched.append({'index': index, 'returned': label, 'best': best,
                              'ratio': round(ratio, 4), 'runner_up_ratio': round(runner_up, 4)})
    if unmatched:
        return stdout, {'status': 'unmatched', 'repairs': repairs, 'unmatched': unmatched}
    if not repairs:
        return stdout, {'status': 'exact', 'repairs': []}
    for index, label in mapping.items():
        rows[index]['criterion'] = label
    return json.dumps(payload, ensure_ascii=False), {'status': 'repaired', 'repairs': repairs}


def repairing_invoke(invoke, criteria, sink):
    """包一層 invoke：在 judge 解析前修補標籤，並保留未修補的原始回應。"""
    def wrapped(reviewer, messages, schema=None):
        exit_code, stdout, stderr, elapsed_ms, cli_version = invoke(reviewer, messages, schema)
        repaired, repair = repair_criterion_labels(stdout, criteria)
        sink[reviewer['reviewer_id']] = {'original': stdout, 'repair': repair}
        return exit_code, repaired, stderr, elapsed_ms, cli_version
    return wrapped


def override_codex_reviewer(policy, group, spec):
    """以「模型[:effort]」覆寫某組的 codex 側評審者；回傳新策略與覆寫說明。

    覆寫只發生在實驗層：凍結策略的摘要不變，但每筆紀錄都會記下實際生效的
    評審者與策略摘要，讀者可以分辨哪些結果來自哪一組評審陣容。
    """
    model, _, effort = spec.partition(':')
    if not model:
        raise ValueError('覆寫規格缺少模型：' + repr(spec))
    updated = copy.deepcopy(policy)
    changed = []
    for reviewer in updated[group]:
        if reviewer['cli'] != 'codex':
            continue
        before = {'reviewer_id': reviewer['reviewer_id'], 'model': reviewer['model'],
                  'thinking_effort': reviewer['thinking_effort']}
        reviewer['model'] = model
        if effort:
            reviewer['thinking_effort'] = effort
        reviewer['reviewer_id'] = 'codex-' + model.replace('/', '-')
        if effort:
            reviewer['reviewer_id'] += '-' + effort
        changed.append({'group': group, 'before': before,
                        'after': {'reviewer_id': reviewer['reviewer_id'], 'model': model,
                                  'thinking_effort': reviewer['thinking_effort']}})
    if not changed:
        raise ValueError(f'{group} 沒有 codex 側評審者可供覆寫')
    return updated, changed


def effective_policy(primary_spec=None, escalation_spec=None, policy=MOA_POLICY):
    """套用兩側 codex 覆寫，回傳 (生效策略, 覆寫紀錄)。"""
    current = policy
    overrides = []
    for group, spec in (('primary', primary_spec), ('escalation', escalation_spec)):
        if spec:
            current, changed = override_codex_reviewer(current, group, spec)
            overrides.extend(changed)
    return current, overrides


def _judge_group(reviewers, messages, criteria, invoke, workers):
    """並行執行同一組評審者；單線程時保留原始順序語意。"""
    if workers <= 1 or len(reviewers) <= 1:
        return [judge(reviewer, messages, criteria, invoke) for reviewer in reviewers]
    with ThreadPoolExecutor(max_workers=min(workers, len(reviewers))) as pool:
        return list(pool.map(lambda reviewer: judge(reviewer, messages, criteria, invoke),
                             reviewers))


def review_target(messages, criteria, invoke=default_invoke, reviewer_workers=2, policy=MOA_POLICY):
    """沿用 src 的 judge / criterion_consensus / aggregate，只把組內調用並行化。

    不修改 src/refractrouter/moa_review.py：付費留出批次的凍結件會因 src 變更失效，
    因此並行編排放在實驗層，共識與升級規則仍由核心模組決定。
    """
    primary = _judge_group(policy['primary'], messages, criteria, invoke, reviewer_workers)
    escalation = []
    if any(row['escalated'] for row in criterion_consensus(primary, [], criteria)):
        escalation = _judge_group(policy['escalation'], messages, criteria, invoke,
                                  reviewer_workers)
    consensus = aggregate(primary, escalation, criteria)
    return {'primary': primary, 'escalation': escalation, 'consensus': consensus,
            'policy_sha256': digest(policy)}


def replay_case(case, invoke=default_invoke, reviewer_workers=2, repair_labels=False,
                policy=MOA_POLICY):
    """對單一判例跑本地 MoA，回傳可併入 records 的紀錄。"""
    criteria = case_criteria(case)
    sink = {}
    if repair_labels:
        invoke = repairing_invoke(invoke, criteria, sink)
    started = time.monotonic()
    result = review_target(list(case['request']['messages']), criteria, invoke, reviewer_workers,
                           policy)
    elapsed_ms = (time.monotonic() - started) * 1000
    repairs = {}
    for group in ('primary', 'escalation'):
        for row in result[group]:
            captured = sink.get(row['reviewer_id'])
            if not captured or captured['repair']['status'] == 'exact':
                continue
            original = captured['original']
            if row.get('raw_response') != original:
                row['repaired_response'] = row.get('raw_response')
            row['raw_response'] = original
            row['response_sha256'] = digest(original) if original else None
            _, strict_error = _parse(original or '', criteria)
            row['strict_status'] = 'reviewed' if strict_error is None else 'failed'
            if strict_error:
                row['strict_error'] = strict_error
            repairs[row['reviewer_id']] = captured['repair']
    return {
        'case_id': case['case_id'],
        'run_id': case['run_id'],
        'task_id': case['task_id'],
        'arm': case['arm'],
        'repeat': case['repeat'],
        'criteria': criteria,
        'payload_sha256': case['request']['payload_sha256'],
        'ark': {'verdicts': ark_verdicts(case), 'criteria': ark_criteria(case),
                'afp': sum(case['recorded'][stage].get('charged_afp') or 0 for stage in REFERENCES)},
        'moa': result,
        'label_repairs': repairs,
        'elapsed_ms': round(elapsed_ms, 3),
        'ark_afp': 0,
    }


def run(cases_path=DEFAULT_CASES, out=DEFAULT_OUT, *, case_ids=None, limit=None,
        invoke=default_invoke, force=False, sleep_seconds=0.0, case_workers=1,
        reviewer_workers=2, repair_labels=False, policy=MOA_POLICY, policy_overrides=None):
    """逐例重判並寫入紀錄；既有紀錄預設跳過，可中斷後續跑。"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    records_path = out / 'records.json'
    records = []
    if records_path.is_file() and not force:
        records = json.loads(records_path.read_text())['records']
    done = {record['case_id'] for record in records}
    cases = load_cases(cases_path)
    if case_ids is not None:
        wanted = set(case_ids)
        cases = [case for case in cases if case['case_id'] in wanted]
        missing = wanted - {case['case_id'] for case in cases}
        if missing:
            raise ValueError('找不到判例：' + ', '.join(sorted(missing)))
    pending = [case for case in cases if case['case_id'] not in done]
    if limit is not None:
        pending = pending[:limit]
    header = {'schema_version': SCHEMA_VERSION, 'cases_path': str(cases_path),
              'cases_sha256': digest(json.loads(Path(cases_path).read_text())),
              'policy_sha256': digest(policy),
              'frozen_policy_sha256': digest(MOA_POLICY),
              'policy_overrides': list(policy_overrides or []),
              'parse_mode': 'labels-repaired' if repair_labels else 'strict'}
    print(f'待重判 {len(pending)} 例（已完成 {len(done)} 例，個案並行 {case_workers}，'
          f'評審並行 {reviewer_workers}，評審陣容 '
          f'{[r["reviewer_id"] for r in policy["primary"] + policy["escalation"]]}）', flush=True)
    order = {case['case_id']: index for index, case in enumerate(cases)}
    finished = 0

    def collect(record):
        nonlocal finished
        records.append(record)
        records.sort(key=lambda item: order.get(item['case_id'], len(records)))
        finished += 1
        atomic_json(records_path, {**header, 'records': records})
        print(f'[{finished}/{len(pending)}] {record["case_id"]} → '
              f'{record["moa"]["consensus"]["overall"]} '
              f'（Ark {record["ark"]["verdicts"]["delivery-judge"]}/'
              f'{record["ark"]["verdicts"]["research-judge"]}，'
              f'{round(record["elapsed_ms"] / 1000, 1)}s）', flush=True)

    if case_workers <= 1:
        for case in pending:
            collect(replay_case(case, invoke, reviewer_workers, repair_labels, policy))
            if sleep_seconds:
                time.sleep(sleep_seconds)
    else:
        with ThreadPoolExecutor(max_workers=case_workers) as pool:
            futures = [pool.submit(replay_case, case, invoke, reviewer_workers, repair_labels, policy)
                       for case in pending]
            for future in as_completed(futures):
                collect(future.result())
    atomic_json(out / 'records.json', {**header, 'records': records})
    return records


def _agreement(counter):
    total = sum(counter.values())
    agree = sum(count for (left, right), count in counter.items() if left == right)
    return agree, total


def _pairs(counter):
    return {' -> '.join(str(part) for part in pair): count
            for pair, count in sorted(counter.items(), key=lambda item: str(item[0]))}


def _reference_summary(records, reference):
    verdicts = Counter()
    criteria = Counter()
    risk = 0
    for record in records:
        ark = record['ark']['verdicts'][reference]
        candidate = record['moa']['consensus']['overall']
        verdicts[(ark, candidate)] += 1
        if ark == 'fail' and candidate == 'pass':
            risk += 1
        ark_rows = record['ark']['criteria'][reference]
        candidate_rows = {row['criterion']: row['verdict']
                          for row in record['moa']['consensus']['criteria']}
        for criterion in record['criteria']:
            criteria[(ark_rows.get(criterion), candidate_rows.get(criterion))] += 1
    agree, total = _agreement(verdicts)
    criterion_agree, criterion_total = _agreement(criteria)
    return {
        'verdict_pairs': _pairs(verdicts),
        'verdict_agreement': round(agree / total, 6) if total else None,
        'criterion_pairs': _pairs(criteria),
        'criterion_agreement': round(criterion_agree / criterion_total, 6) if criterion_total else None,
        'ark_fail_candidate_pass': risk,
        'risk_direction': round(risk / total, 6) if total else None,
    }


def _reviewer_latency(records, reviewer_id):
    """單一評審者的延遲分布；線上交付閘門的時限是 45 秒，超時即不可用於該位置。

    分布只取實際可用的呼叫（exit_code 為 0）：額度或認證失敗會在數秒內結束，
    混進分布會把中位數拉低，低估替換候選真實的等待時間。失敗次數另計。
    """
    rows = [row for record in records
            for row in record['moa']['primary'] + record['moa']['escalation']
            if row['reviewer_id'] == reviewer_id]
    if not rows:
        return None
    values = sorted(row['wall_time_ms'] for row in rows if row.get('exit_code', 0) == 0)
    payload = {'calls': len(rows),
               'timed_calls': len(values),
               'unavailable_calls': len(rows) - len(values)}
    if not values:
        return payload

    def percentile(fraction):
        return values[min(len(values) - 1, int(round(fraction * (len(values) - 1))))]

    payload.update({
        'median_ms': round(percentile(0.5), 3),
        'p90_ms': round(percentile(0.9), 3),
        'max_ms': round(values[-1], 3),
        'at_or_over_45s': sum(1 for value in values if value >= 45_000),
    })
    return payload


def _reviewer_reference_summary(records, reviewer_id, reference):
    """單一評審者獨自作為候選時的對照；只計該評審者實際跑完的案例。

    用來分辨共識不一致是兩位都偏，還是單一評審者主導：只保留一位評審者可以
    再省一次調用與等待，但那一位單獨的一致性必須先看得到。
    """
    verdicts = Counter()
    criteria = Counter()
    for record in records:
        rows = [row for row in record['moa']['primary'] + record['moa']['escalation']
                if row['reviewer_id'] == reviewer_id and row.get('exit_code', 0) == 0
                and row.get('status') == 'reviewed']
        if not rows:
            continue
        row = rows[0]
        reviewed = {item.get('criterion'): item.get('verdict')
                    for item in (row.get('review') or {}).get('criteria', [])}
        verdicts[(record['ark']['verdicts'][reference], row.get('verdict'))] += 1
        ark_rows = record['ark']['criteria'][reference]
        for criterion in record['criteria']:
            criteria[(ark_rows.get(criterion), reviewed.get(criterion))] += 1
    agree, total = _agreement(verdicts)
    criterion_agree, criterion_total = _agreement(criteria)
    return {
        'reviewed_cases': total,
        'verdict_pairs': _pairs(verdicts),
        'verdict_agreement': round(agree / total, 6) if total else None,
        'criterion_pairs': _pairs(criteria),
        'criterion_agreement': round(criterion_agree / criterion_total, 6) if criterion_total else None,
    }


def summarize(records, thresholds, parse_mode='strict', policy=MOA_POLICY):
    """對照凍結門檻彙總；reference 互相矛盾的判例單列，不計入主判定。

    「評審者不可用」與「判定不一致」分開統計：本機 CLI 的額度、認證或網路失敗
    會讓該例根本沒有候選判定，這不是候選評審的反對證據，也不該稀釋一致率。
    主判定只看實際跑完的案例，不可用案例另列清單與覆蓋率；全案例口徑保留為
    對照欄位。缺席案例未補齊前，達標也只能算部分覆蓋。
    """
    def references_disagree(record):
        verdicts = record['ark']['verdicts']
        return verdicts['delivery-judge'] != verdicts['research-judge']

    def reviewer_unavailable(record):
        return any(row.get('exit_code', 0) != 0
                   for row in record['moa']['primary'] + record['moa']['escalation'])

    disagree = [record for record in records if references_disagree(record)]
    agreed = [record for record in records if not references_disagree(record)]
    unavailable = [record for record in records if reviewer_unavailable(record)]
    runnable_agreed = [record for record in records
                       if not reviewer_unavailable(record) and not references_disagree(record)]
    by_reference = {reference: _reference_summary(records, reference) for reference in REFERENCES}
    primary = {reference: _reference_summary(agreed, reference) for reference in REFERENCES}
    primary_runnable = {reference: _reference_summary(runnable_agreed, reference)
                        for reference in REFERENCES}
    clean = [record for record in records
             if not record.get('label_repairs')
             and all(row['status'] == 'reviewed'
                     for row in record['moa']['primary'] + record['moa']['escalation'])]
    primary_clean = {reference: _reference_summary(clean, reference) for reference in REFERENCES}

    def checks_for(stats_by_reference):
        checks = {}
        for reference, stats in stats_by_reference.items():
            checks[reference] = {
                'verdict_agreement_ok': (stats['verdict_agreement'] or 0) >= thresholds['verdict_agreement_min'],
                'criterion_agreement_ok': (stats['criterion_agreement'] or 0) >= thresholds['criterion_agreement_min'],
                'risk_direction_ok': (stats['risk_direction'] if stats['risk_direction'] is not None else 1) <= thresholds['risk_direction_max'],
            }
            checks[reference]['all_ok'] = all(checks[reference].values())
        return checks

    def decision_for(checks, case_count):
        if not case_count:
            return 'insufficient'
        return 'replace' if all(check['all_ok'] for check in checks.values()) else 'keep'

    checks = checks_for(primary)
    checks_runnable = checks_for(primary_runnable)
    decision = decision_for(checks_runnable, len(runnable_agreed))
    if decision == 'replace' and unavailable:
        decision = 'replace-pending-coverage'
    failed = sum(record['moa']['consensus']['failed_records'] for record in records)
    escalated = sum(record['moa']['consensus']['escalated_criteria'] for record in records)
    calls = sum(len(record['moa']['primary']) + len(record['moa']['escalation']) for record in records)
    recovery = Counter()
    label_cases = 0
    for record in records:
        issues = record.get('label_repairs') or {}
        if issues:
            label_cases += 1
        for reviewer_id, repair in issues.items():
            recovery[(reviewer_id, repair['status'])] += 1
    recoverable = Counter()
    unrecoverable = []
    for record in records:
        for row in record['moa']['primary'] + record['moa']['escalation']:
            if row.get('exit_code', 0) != 0 or row.get('status') == 'reviewed':
                continue
            _, repair = repair_criterion_labels(row.get('raw_response') or '', record['criteria'])
            recoverable[(row['reviewer_id'], repair['status'])] += 1
            if repair['status'] != 'repaired':
                unrecoverable.append({'case_id': record['case_id'],
                                      'reviewer_id': row['reviewer_id'],
                                      'status': repair['status'],
                                      'error': str(row.get('error'))[:160]})
    reviewer_ids = [reviewer['reviewer_id']
                    for reviewer in policy['primary'] + policy['escalation']]
    latency = {reviewer_id: _reviewer_latency(records, reviewer_id) for reviewer_id in reviewer_ids}
    by_reviewer = {reviewer_id: {reference: _reviewer_reference_summary(records, reviewer_id, reference)
                                 for reference in REFERENCES}
                   for reviewer_id in reviewer_ids}
    return {
        'schema_version': SCHEMA_VERSION,
        'policy_sha256': digest(policy),
        'frozen_policy_sha256': digest(MOA_POLICY),
        'parse_mode': parse_mode,
        'case_count': len(records),
        'excluding_reference_disagreements': len(disagree),
        'reference_disagreement_cases': sorted(record['case_id'] for record in disagree),
        'by_reference_all_cases': by_reference,
        'primary': primary,
        'primary_reviewers_available_only': primary_runnable,
        'reviewer_unavailable_case_ids': sorted(record['case_id'] for record in unavailable),
        'clean_case_count': len(clean),
        'primary_clean_only': primary_clean,
        'checks': checks,
        'checks_reviewers_available_only': checks_runnable,
        'thresholds': thresholds,
        'decision': decision,
        'decision_all_cases': decision_for(checks, len(agreed)),
        'decision_basis': {
            'case_count_used': len(runnable_agreed),
            'excluded_reviewer_unavailable': len(unavailable),
            'excluded_reference_disagreements': len(disagree),
            'coverage_complete': not unavailable,
        },
        'parse_recovery': {
            'cases_with_label_issues': label_cases,
            'by_reviewer_status': {' / '.join(key): count for key, count in sorted(recovery.items())},
            'pending_overall': sum(1 for record in records
                                   if record['moa']['consensus']['overall'] == 'pending'),
            'reviewer_unavailable_cases': len(unavailable),
            'strict_failures_by_repair_status': {' / '.join(key): count
                                                 for key, count in sorted(recoverable.items())},
            'strict_failures_unrecoverable_count': len(unrecoverable),
            'strict_failures_unrecoverable': unrecoverable[:20],
        },
        'moa_review_cost': {
            'cli_calls': calls,
            'escalated_criteria': escalated,
            'failed_records': failed,
            'wall_time_ms': round(sum(record['elapsed_ms'] for record in records), 3),
            'ark_afp': 0,
            'ark_model_calls': sum(1 for record in records
                                   for row in record['moa']['escalation']
                                   if str(row['model']).startswith('ark/')),
            'ark_afp_note': ('本工具不經 Ark 帳本；升級層含一個 Ark 評審，'
                             '其用量由 Ark 方案外部計費，不在此統計。'),
        },
        'reviewer_latency': {key: value for key, value in latency.items() if value},
        'by_reviewer_agreement': {key: value for key, value in by_reviewer.items()
                                  if any(stats['reviewed_cases'] for stats in value.values())},
        'online_gate_cap_seconds': 45,
        'scope': ('候選 A 的本地 CLI MoA 重判；只比較判定一致性，'
                  '不構成真人審查，也不證明用戶可接受性。'),
    }


def main():
    parser = argparse.ArgumentParser(description='用本地 CLI MoA 重判 judge 判例（零 Ark AFP）')
    parser.add_argument('--cases', default=DEFAULT_CASES)
    parser.add_argument('--out', default=DEFAULT_OUT)
    parser.add_argument('--thresholds', default='reports/judge-cost-v1/replay-01/thresholds.json')
    parser.add_argument('--case-ids', default=None, help='逗號分隔的 case_id 白名單')
    parser.add_argument('--limit', type=int, default=None, help='只跑前 N 例')
    parser.add_argument('--force', action='store_true', help='重跑並覆蓋既有紀錄')
    parser.add_argument('--sleep-seconds', type=float, default=0.0)
    parser.add_argument('--case-workers', type=int, default=1, help='同時處理的判例數')
    parser.add_argument('--reviewer-workers', type=int, default=2, help='組內評審並行數')
    parser.add_argument('--repair-labels', action='store_true',
                        help='把近義改寫的 criterion 標籤對回原文後再解析（預設關閉）')
    parser.add_argument('--codex-primary', default=None,
                        help='覆寫 codex 側初審模型，格式 模型[:effort]')
    parser.add_argument('--codex-escalation', default=None,
                        help='覆寫 codex 側升級模型，格式 模型[:effort]')
    parser.add_argument('--summarize-only', action='store_true', help='只用既有紀錄重算摘要')
    args = parser.parse_args()
    thresholds = json.loads(Path(args.thresholds).read_text())['thresholds']
    case_ids = args.case_ids.split(',') if args.case_ids else None
    parse_mode = 'labels-repaired' if args.repair_labels else 'strict'
    policy, overrides = effective_policy(args.codex_primary, args.codex_escalation)
    if args.summarize_only:
        payload = json.loads((Path(args.out) / 'records.json').read_text())
        records = payload['records']
        parse_mode = payload.get('parse_mode', parse_mode)
        stored = payload.get('policy_overrides') or []
        policy, overrides = effective_policy(
            next((row['after']['model'] + ':' + row['after']['thinking_effort']
                  for row in stored if row['group'] == 'primary'), None),
            next((row['after']['model'] + ':' + row['after']['thinking_effort']
                  for row in stored if row['group'] == 'escalation'), None))
    else:
        records = run(args.cases, args.out, case_ids=case_ids, limit=args.limit,
                      force=args.force, sleep_seconds=args.sleep_seconds,
                      case_workers=args.case_workers,
                      reviewer_workers=args.reviewer_workers,
                      repair_labels=args.repair_labels,
                      policy=policy, policy_overrides=overrides)
    summary = summarize(records, thresholds, parse_mode=parse_mode, policy=policy)
    atomic_json(Path(args.out) / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
