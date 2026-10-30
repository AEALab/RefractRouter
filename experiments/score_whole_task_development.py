"""隔离评分入口：不导入生成器、不保留认证环境、不联网，不执行候选代码。"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

from refractrouter.development_evaluation import evaluate, paired_screen, repair_decorator_ranges
from refractrouter.task_cost_observation import amount


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def score(suite_root, run_root, expected_manifest, expected_oracles, *, diagnostic_decorators=False):
    root, run = Path(suite_root).resolve(), Path(run_root).resolve()
    manifest_raw = (root/'manifest.json').read_bytes()
    oracle_raw = (root/'isolated-evaluation/oracles.json').read_bytes()
    if sha(manifest_raw) != expected_manifest or sha(oracle_raw) != expected_oracles:
        raise ValueError('评分清单身份不符')
    suite, oracles = json.loads(manifest_raw), json.loads(oracle_raw)
    ledger_raw = (run/'ledger.json').read_bytes(); ledger = json.loads(ledger_raw)
    if ledger['manifestSha256'] != expected_manifest:
        raise ValueError('答卷不属于本次冻结')
    expected_pairs = {(t['taskId'], arm) for t in suite['tasks'] for arm in ('S0', 'W0', 'WF')}
    if any((c.get('task_id'), c.get('arm')) not in expected_pairs for c in ledger['calls']):
        raise ValueError('逐调用账本有无法归属的费用，不能跳过')
    if len({c['label'] for c in ledger['calls']}) != len(ledger['calls']):
        raise ValueError('调用身份重复')
    if abs(sum(amount(c['charged']) for c in ledger['calls'])
            - amount(ledger['chargedStandardAFPIncludingUnknownReserves'])) > Decimal('0.00000001'):
        raise ValueError('逐调用费用与保护总账不平，停止评分')
    indexed = {}; items = []; repairs = []
    for result in ledger['results']:
        key = result['taskId'], result['arm']
        if key in indexed:
            raise ValueError('同一配对路线答卷重复')
        expected_calls = [c['label'] for c in ledger['calls']
            if c.get('task_id') == result['taskId'] and c.get('arm') == result['arm']]
        if result['calls'] != expected_calls:
            raise ValueError('答卷调用引用与账本不完整对应')
        indexed[key] = result
    if any((c['task_id'], c['arm']) not in indexed for c in ledger['calls']):
        raise ValueError('账本调用缺少所属答卷')
    for task in suite['tasks']:
        if oracles[task['taskId']]['oracle']['criteriaSha256'] != task['criteriaSha256']:
            raise ValueError('公开要求与隔离评分合同身份不符')
        files = {r['path']: (root/task['root']/r['path']).read_bytes().decode('utf-8') for r in task['files']}
        oracle = oracles[task['taskId']]['oracle']
        if diagnostic_decorators:
            oracle, changes = repair_decorator_ranges(files, oracle)
            repairs.extend(dict(taskId=task['taskId'], **c) for c in changes)
        for arm in ('S0', 'W0', 'WF'):
            raw = indexed.get((task['taskId'], arm))
            calls = [r for r in ledger['calls'] if r.get('task_id') == task['taskId'] and r.get('arm') == arm]
            known = sum(Decimal(str(c['charged'])) for c in calls if c['status'] == 'billed')
            reserve = sum(Decimal(str(c['charged'])) for c in calls if c['status'] != 'billed')
            cost_known = bool(calls) and all(c['status'] == 'billed' for c in calls)
            if raw and raw['status'] == 'completed':
                if (not cost_known or calls[-1].get('response_output') != raw['candidate']
                        or calls[-1].get('response', {}).get('content') != raw['candidate']
                        or calls[-1].get('output_sha256') != sha(raw['candidate'].encode())
                        or calls[-1].get('finish_reason') != 'stop'
                        or calls[-1].get('response', {}).get('finish_reason') != 'stop'
                        or calls[-1].get('response', {}).get('usage_available') is not True
                        or calls[-1].get('response', {}).get('tool_calls')):
                    raise ValueError('最终答卷不能绑定到已结算的正常终止回执')
            assessment = evaluate(raw['candidate'], files, oracle) if (
                raw and raw['status'] == 'completed' and isinstance(raw.get('candidate'), str)) else None
            items.append({'taskId': task['taskId'], 'arm': arm, 'half': task['half'],
                'kind': task['kind'], 'assessment': assessment,
                'passed': assessment['passed'] if assessment else (False if raw and cost_known else None),
                'completed': raw is not None and (raw['status'] == 'completed' or cost_known),
                'knownCost': cost_known,
                'knownStandardAFP': float(known), 'unknownReservedStandardAFP': float(reserve),
                'modelCalls': len(calls), 'toolQueries': len(raw.get('toolQueries', [])) if raw else 0,
                'wallSeconds': raw['wallSeconds'] if raw else None})
    comparisons = {}
    for candidate in ('W0', 'WF'):
        rows = []
        for task in suite['tasks']:
            a = next(i for i in items if i['taskId'] == task['taskId'] and i['arm'] == 'S0')
            b = next(i for i in items if i['taskId'] == task['taskId'] and i['arm'] == candidate)
            rows.append({'taskId': task['taskId'], 'half': task['half'], 'baselinePassed': a['passed'],
                'candidatePassed': b['passed'], 'baselineCost': a['knownStandardAFP'],
                'candidateCost': b['knownStandardAFP'], 'completedPair': a['completed'] and b['completed'],
                'knownCost': a['knownCost'] and b['knownCost']})
        comparisons[candidate] = paired_screen(rows)
    totals = {arm: {'passed': sum(i['passed'] is True for i in items if i['arm'] == arm),
        'planned': len(suite['tasks']), 'knownStandardAFP': sum(i['knownStandardAFP'] for i in items if i['arm'] == arm),
        'unknownReservedStandardAFP': sum(i['unknownReservedStandardAFP'] for i in items if i['arm'] == arm),
        'wallSecondsObserved': sum(i['wallSeconds'] or 0 for i in items if i['arm'] == arm),
        'modelCalls': sum(i['modelCalls'] for i in items if i['arm'] == arm),
        'toolQueries': sum(i['toolQueries'] for i in items if i['arm'] == arm)} for arm in ('S0', 'W0', 'WF')}
    return {'schemaVersion': 'whole-task-development-assessment-v1', 'manifestSha256': expected_manifest,
        'diagnosticOnly': diagnostic_decorators, 'decoratorRangeRepairs': repairs,
        'formalFrozenResultReplaced': False,
        'oracleSha256': expected_oracles, 'ledgerSha256': sha(ledger_raw), 'items': items,
        'comparisons': comparisons, 'totals': totals, 'modelCallsForResearchScoring': 0,
        'actualProviderDebitVerified': False, 'heldoutExecuted': 0, 'releaseAllowed': False,
        'scope': '人工受控六题的完整合同筛选；不是开放修复能力、随机总体或生产收益证明。'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True); parser.add_argument('--run', required=True)
    parser.add_argument('--manifest-sha256', required=True); parser.add_argument('--oracle-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--diagnostic-decorators', action='store_true',
        help='仅作另存的装饰器范围误拒诊断，不替换原冻结评分')
    args = parser.parse_args()
    os.environ.clear()
    def audit(event, _):
        if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'}:
            raise RuntimeError('隔离评分禁止联网和启动执行进程')
    sys.addaudithook(audit)
    result = score(args.suite, args.run, args.manifest_sha256, args.oracle_sha256,
        diagnostic_decorators=args.diagnostic_decorators)
    with Path(args.output).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'totals': result['totals'], 'releaseAllowed': False}, ensure_ascii=False))
