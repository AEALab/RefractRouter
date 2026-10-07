"""公开源码任务的有限 direct／DAG 实跑；默认零模型调用预检。"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import threading
import time

from refractrouter.agent import atomic_json, run_agent
from refractrouter.application_config import compile_configuration
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.openai_compatible import DshStdioBridge, OpenAICompatibleClient
from refractrouter.task_budget import TaskCallBudget, request_input_bound, InvalidModelOutput

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'data/research/automatic-applicability-v3.json'
HOST = ROOT/'validation/dsh/applicability_host.ts'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def bounded_complete(client, model, messages, *, json_mode, timeout_seconds):
    """期限经客户端快照传递；complete 不接收 timeout_seconds 参数。"""
    bound = client.for_task_call(timeout_seconds) if timeout_seconds is not None else client
    return bound.complete(model, messages, json_mode=json_mode)


def historical_protection(roots):
    """按真实派发身份去重；旧订阅单位不冒充现金，未知现金预留继续占额度。"""
    calls = {}
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob('result.json'):
            raw = json.loads(path.read_text())
            if raw.get('mode') in {'preflight', 'demo'}:
                continue
            manifest_path = path.with_name('manifest.json')
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text())
            models = {m['model_id']: m for m in manifest.get('models', [])}
            for row in raw.get('calls', []):
                model = models.get(row.get('model_id'), {})
                unit = row.get('billing_unit', raw.get('billing_unit', manifest.get('billing_unit')))
                if (unit != 'CNY' or not row.get('dispatch_at')
                        or model.get('deployment') in {'local', 'simulated-local'}
                        or model.get('billing_mode', row.get('billing_mode')) == 'subscription'):
                    continue
                identity = digest([row['dispatch_at'], row['model_id'], row.get('input_sha256')])
                amount = row.get('charged', row.get('reserved', 0))
                entry = {'source': str(path), 'model': row['model_id'], 'status': row['status'],
                         'amountCny': amount}
                previous = calls.get(identity)
                if previous and previous['amountCny'] != amount:
                    # 同一派发的后续结算优先；两个不同结算金额必须人工核对。
                    if previous['status'] == 'billed' and entry['status'] == 'billed':
                        raise ValueError('同一历史调用的费用记录冲突')
                    if previous['status'] == 'billed':
                        continue
                calls[identity] = entry
    return {'calls': calls, 'cashProtectedCny': sum(r['amountCny'] for r in calls.values()),
            'unknownCount': sum(r['status'] == 'unknown-usage' for r in calls.values()),
            'scope': '可核对的自动路由 result／manifest 按派发身份去重；独立 Jev 账本另行预留。'}


def task_check(answer, task):
    """检查固定事实及完整交付；不把字段存在当作自由文字理由正确。"""
    text = answer.strip()
    if text.startswith('```json') and text.endswith('```'):
        text = text[7:-3].strip()
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {'passed': False, 'reason': '最终回复不是完整 JSON'}
    if not isinstance(parsed, dict) or not isinstance(parsed.get('answers'), dict):
        return {'passed': False, 'reason': '缺少 answers 对象'}
    observed = parsed['answers']
    mismatches = []
    for key, expected in task['expectedAnswers'].items():
        actual = observed.get(key, '__missing__')
        correct = (type(actual) in (int, float) and abs(actual-expected) < 1e-8
                   if type(expected) in (int, float) else type(actual) is type(expected) and actual == expected)
        if not correct:
            mismatches.append({'key': key, 'expected': expected, 'actual': actual})
    explanation = parsed.get('explanation')
    explained = isinstance(explanation, str) and bool(explanation.strip())
    return {'passed': not mismatches and explained, 'mismatches': mismatches,
            'explanationPresent': explained, 'explanationQualityVerified': False}


def freeze(catalog, history, extra_history_cny, authorization_cny):
    protocol = json.loads(PROTOCOL.read_text())
    compiled, provenance = compile_dsh_model_pool(catalog['pool'], {
        'schemaVersion': 'refractagent-dsh-catalog-v1', 'routes': catalog['routes']})
    models = compile_configuration(compiled).manifest.models
    maximum_calls = len(protocol['tasks']) * (protocol['maxCallsPerDirect'] + protocol['maxCallsPerDag'])
    # 互斥目标用单次最贵合法价格作保守包络，不把五个模型价格相加。
    amounts = [(protocol['inputBoundPerCall']*m.input_cost_per_1k
                + protocol['outputLimitPerCall']*m.output_cost_per_1k)/1000 for m in models]
    maximum_reference = maximum_calls * max(amounts)
    maximum_cash = maximum_calls * max(amount for amount, model in zip(amounts, models)
        if model.billing_mode != 'subscription')
    protected = history['cashProtectedCny'] + extra_history_cny
    if not math.isfinite(authorization_cny) or authorization_cny <= 0:
        raise ValueError('必须给出实际获授权的正数现金上限')
    if protected + maximum_cash > authorization_cny:
        raise ValueError('冻结最坏现金包络超出历史授权余额；禁止实跑')
    order = [{'task': t['id'], 'route': route} for t in protocol['tasks'] for route in protocol['routes']]
    random.Random(protocol['orderSeed']).shuffle(order)
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [*sorted((ROOT/'src/refractrouter').rglob('*.py')), Path(__file__), HOST, PROTOCOL]}
    for task in protocol['tasks']:
        for material in task['materials']:
            if hashlib.sha256((ROOT/material['path']).read_bytes()).hexdigest() != material['sha256']:
                raise ValueError('冻结材料源文件已变化；不能无记录更换任务')
    frozen = {'protocol': protocol, 'catalog': catalog, 'configuration': compiled,
        'provenance': provenance, 'order': order, 'sourceHashes': sources,
        'maximumModelCalls': maximum_calls, 'maximumReferenceCny': maximum_reference,
        'maximumCashCny': maximum_cash, 'history': history, 'extraHistoryProtectionCny': extra_history_cny,
        'cashAuthorizationCny': authorization_cny,
        'remainingCashAuthorizationCny': authorization_cny-protected,
        'newJevCalls': 0, 'note': '只比较显式 Direct／DAG 对照；不宣称自动入口已选择 DAG。'}
    return {**frozen, 'sha256': digest(frozen)}


def run(frozen, output, host_command, catalog):
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'preflight.json', frozen)
    protocol = frozen['protocol']
    log = (output/'host-stderr.txt').open('w')
    process = subprocess.Popen(host_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=log, text=True, cwd=ROOT)
    results = []
    budget = None
    try:
        process.stdin.write('{"op":"catalog"}\n'); process.stdin.flush()
        current = json.loads(process.stdout.readline())
        if digest(current) != digest(catalog):
            raise ValueError('原 DSH 目录在预检后变化')
        bridge = DshStdioBridge(process.stdout, process.stdin)
        actual_client = OpenAICompatibleClient(dsh_bridge=bridge, max_retries=0, timeout_seconds=None)
        budget = TaskCallBudget(actual_client, frozen['maximumReferenceCny'], 1,
            max_calls=frozen['maximumModelCalls'], capture_payload=True,
            cash_limits={'production': frozen['maximumCashCny'], 'evaluation': 1})
        lock = threading.RLock()
        state = {'task': None, 'route': None, 'calls': 0}
        identities = {(m['provider'], m['model']): m for m in catalog['routes']}
        def persist():
            costs, records = budget.snapshot()
            atomic_json(output/'batch-ledger.json', {'referenceCostsCny': costs,
                'cashCostsCny': budget.cash_snapshot(), 'records': records})
        class Guard:
            max_retries = 0
            def __init__(self, timeout_seconds=None):
                self.timeout_seconds = timeout_seconds
            def for_task_call(self, timeout_seconds):
                return Guard(timeout_seconds)
            def complete(self, model, messages, *, json_mode=False, tools=None):
                with lock:
                    cap = protocol['maxCallsPerDirect'] if state['route']=='direct' else protocol['maxCallsPerDag']
                    if ((model.provider, model.api_model) not in identities or tools
                            or state['calls'] >= cap or model.max_output_tokens > protocol['outputLimitPerCall']
                            or request_input_bound(messages, tools) > protocol['inputBoundPerCall']):
                        budget.stop(); persist()
                        raise ValueError('实际调用超出冻结模型、容量、工具或次数合同')
                    state['calls'] += 1
                    try:
                        reservation = budget.reserve(model, messages,
                            label=f"{state['task']}/{state['route']}/{state['calls']}", json_mode=json_mode)
                    except BaseException:
                        budget.stop(); persist(); raise
                    budget.dispatch(reservation, timeout_seconds=self.timeout_seconds)
                    persist()  # 在通信前记录未知用量；恢复时绝不重新提交。
                    try:
                        response = bounded_complete(actual_client, reservation.model, messages,
                            json_mode=json_mode, timeout_seconds=self.timeout_seconds)
                        budget.settle(reservation, response)
                    except InvalidModelOutput:
                        persist(); raise  # 截断等普通已结算任务失败不丢弃计费记录。
                    except BaseException:
                        budget.stop(); persist(); raise
                    persist()
                    return response
        tasks = {t['id']: t for t in protocol['tasks']}
        for item in frozen['order']:
            task, route = tasks[item['task']], item['route']
            if budget.stopped or any(r['status']=='unknown-usage' for r in budget.records):
                raise ValueError('整批存在未确认调用，停止后续调用')
            state.update(task=task['id'], route=route, calls=0)
            config = deepcopy(frozen['configuration'])
            config['objective']['dagMode'] = 'never' if route=='direct' else 'force'
            payload = {'task': task['task'], 'acceptanceCriteria': task['criteria'], 'strategy': 'auto',
                'reviewPolicy': 'always', 'maxConcurrency': 1, 'boundedCallOutput': True,
                'plannerMaxOutputTokens': protocol['outputLimitPerCall'],
                'plannerTimeoutMs': protocol['plannerTimeoutMs'], 'maxPlanRepairs': 0}
            folder = output/task['id']/route
            common = dict(provider_config=config, production_budget='unlimited', evaluation_budget='unlimited',
                timeout_ms=protocol['timeoutMs'], max_output_tokens=protocol['outputLimitPerCall'],
                model_profile_provenance=frozen['provenance'])
            preview = run_agent(payload, mode='preflight', runs_dir=folder/'preview', **common)
            permit = preview['live_authorization_preview']
            if not permit['ready']:
                row = {**item, 'status': preview['status'], 'preflightRejected': True, 'modelCalls': 0}
            else:
                auth = {k: permit[k] for k in ('schema_version', 'authorization_id', 'issued_at', 'expires_at', 'preview_sha256')}
                start = time.monotonic()
                result = run_agent({**payload, 'authorization': auth}, mode='live', execute_paid_run=True,
                    client=Guard(), runs_dir=folder/'live', **common)
                raw = json.loads(Path(result['result_path']).read_text())
                row = {**item, 'status': result['status'], 'modelCalls': state['calls'],
                    'nodeCount': len((raw.get('plan') or {}).get('nodes', [])),
                    'wallMs': round((time.monotonic()-start)*1000),
                    'factCheck': task_check(raw.get('final_output', ''), task),
                    'evaluation': raw.get('evaluation'), 'issues': raw.get('issues'),
                    'referenceCostsCny': raw.get('charged'), 'cashCostsCny': raw.get('cash_costs_cny'),
                    'resultPath': str(Path(result['result_path']).relative_to(output.resolve())),
                    'forcedDag': route=='dag'}
                if any(c['status']=='unknown-usage' for c in raw.get('calls', [])):
                    budget.stop(); persist()
            results.append(row)
            atomic_json(output/'results.json', results)
            print(json.dumps({k:v for k,v in row.items() if k in {'task','route','status','modelCalls','nodeCount','wallMs','factCheck'}}, ensure_ascii=False), flush=True)
    finally:
        if budget is not None:
            persist()
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate(); process.wait(timeout=15)
        log.close()
        atomic_json(output/'completion.json', {'planned':len(frozen['order']), 'finished':len(results),
            'complete':len(results)==len(frozen['order']), 'modelCalls':len(budget.records) if budget else 0})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--extra-history-protection-cny', type=float, required=True)
    parser.add_argument('--authorized-cash-cny', type=float, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    if not 0 <= args.extra_history_protection_cny < args.authorized_cash_cny:
        parser.error('必须给出独立历史现金的非负保护额度')
    history_roots = [*ROOT.joinpath('reports').glob('automatic*'), ROOT/'.refractagent/runs',
        Path.home()/'Documents/Codes/RefractRouter/.refractagent/runs']
    history = historical_protection(history_roots)
    catalog = json.loads(args.catalog.read_text())
    frozen = freeze(catalog, history, args.extra_history_protection_cny, args.authorized_cash_cny)
    if not args.execute:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        atomic_json(args.output_dir/'preflight.json', frozen)
        print(json.dumps({k:frozen[k] for k in ('sha256','maximumModelCalls','maximumReferenceCny',
            'maximumCashCny','remainingCashAuthorizationCny','newJevCalls')}, ensure_ascii=False))
        return
    if args.freeze_sha256 != frozen['sha256']:
        parser.error('实跑必须绑定未变化的源码、模型、材料和历史保护摘要')
    run(frozen, args.output_dir, ['node','--experimental-strip-types',str(HOST)], catalog)


if __name__ == '__main__':
    main()
