"""公开源码任务的有限 direct／DAG 实跑；默认零模型调用预检。"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import subprocess
import threading
import time

from refractrouter.agent import atomic_json, run_agent
from refractrouter.application_config import compile_configuration
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.openai_compatible import DshStdioBridge, OpenAICompatibleClient, ModelInvocationError
from refractrouter.task_budget import TaskCallBudget, request_input_bound, InvalidModelOutput

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'data/research/automatic-applicability-v3.json'
CLARIFIED_PROTOCOL = ROOT/'data/research/automatic-applicability-v4.json'
HOST = ROOT/'validation/dsh/applicability_host.ts'
HOST_AUDIT = ROOT/'validation/dsh/applicability_audit.ts'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def bounded_complete(client, model, messages, *, json_mode, timeout_seconds):
    """期限经客户端快照传递；complete 不接收 timeout_seconds 参数。"""
    bound = client.for_task_call(timeout_seconds) if timeout_seconds is not None else client
    return bound.complete(model, messages, json_mode=json_mode)


def record_invocation_failure(budget, reservation, error):
    """普通已计费失败只结束当前样本；基础设施和未知用量仍停止整批。"""
    try:
        budget.settle_failure(reservation, error)
    except BaseException:
        budget.stop()
        raise
    if reservation.row['status'] != 'billed' or error.failure_type != 'provider-error':
        budget.stop()


def source_hashes():
    """同时冻结实际加载的桥接构建与源码，防止预检后更换调用边界。"""
    plugin = ROOT/'validation/dsh/plugin'
    files = [*sorted((ROOT/'src/refractrouter').rglob('*.py')), Path(__file__), HOST, HOST_AUDIT,
        PROTOCOL, CLARIFIED_PROTOCOL, ROOT/'data/research/automatic-applicability-v5.json',
        ROOT/'data/research/automatic-applicability-v6.json',
        *sorted((plugin/'src').rglob('*.ts')), *sorted((plugin/'src').rglob('*.tsx')),
        plugin/'package-lock.json', *sorted((plugin/'dist').rglob('*.js'))]
    if not (plugin/'dist/index.js').exists():
        raise ValueError('请先构建实际宿主桥接，再冻结预检')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def validate_materials(protocol):
    """审查材料固定在来源提交；运行实现的修复不能替换历史题目。"""
    commit = protocol.get('sourceCommit', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('材料必须绑定完整来源提交')
    hashes = {}
    for task in protocol['tasks']:
        for material in task['materials']:
            path = material['path']
            if Path(path).is_absolute() or '..' in Path(path).parts:
                raise ValueError('材料路径必须在仓库内')
            if path not in hashes:
                source = subprocess.run(['git', 'show', f'{commit}:{path}'], cwd=ROOT,
                    check=True, capture_output=True).stdout
                hashes[path] = hashlib.sha256(source).hexdigest()
            if hashes[path] != material['sha256']:
                raise ValueError('冻结材料源提交摘要不匹配；不能无记录更换任务')


def historical_roots(root, deployed_root):
    """私有证据与旧公开产物共同核对，复制的派发记录由账本身份去重。"""
    return [*root.joinpath('reports').glob('automatic*'), root/'.refractagent/runs',
            root/'.refractagent/private-audit', root/'.refractagent/acceptance',
            deployed_root/'.refractagent/runs', deployed_root/'.refractagent/private-audit',
            deployed_root/'.refractagent/acceptance']


def historical_protection(roots):
    """按真实派发身份去重；旧订阅单位不冒充现金，未知现金预留继续占额度。"""
    calls = {}
    def collect(row, model, path, unit):
        if (unit != 'CNY' or not row.get('dispatch_at')
                or model.get('deployment') in {'local', 'simulated-local'}
                or model.get('billing_mode', row.get('billing_mode')) == 'subscription'):
            return
        identity = digest([row['dispatch_at'], row['model_id'], row.get('input_sha256')])
        amount = row.get('charged', row.get('reserved', 0))
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0:
            raise ValueError('历史现金费用无效，不能继续派发')
        entry = {'source': str(path), 'model': row['model_id'], 'status': row['status'],
                 'amountCny': amount}
        previous = calls.get(identity)
        if previous and previous['amountCny'] != amount:
            if previous['status'] == 'billed' and entry['status'] == 'billed':
                raise ValueError('同一历史调用的费用记录冲突')
            if previous['status'] == 'billed':
                return
        calls[identity] = entry
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
                collect(row, model, path, unit)
        for path in base.rglob('batch-ledger.json'):
            raw = json.loads(path.read_text())
            if not {'referenceCostsCny', 'cashCostsCny', 'records'} <= set(raw):
                continue
            for row in raw['records']:
                collect(row, {}, path, row.get('billing_unit', 'CNY'))
    return {'calls': calls, 'cashProtectedCny': sum(r['amountCny'] for r in calls.values()),
            'unknownCount': sum(r['status'] == 'unknown-usage' for r in calls.values()),
            'scope': '自动路由 result／manifest 与有限验收批账本按派发身份去重；独立 Jev 账本另行预留。'}


def task_check(answer, task, *, review_receipt=False):
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
    result = {'passed': not mismatches and explained, 'mismatches': mismatches,
              'explanationPresent': explained, 'explanationQualityVerified': False}
    if review_receipt and result['passed']:
        result['review_receipt'] = {'version': 'deterministic-answer-fields-v1',
            'candidate_sha256': hashlib.sha256(answer.encode()).hexdigest(),
            'checked_fields': list(task['expectedAnswers']), 'scope': 'answers-only'}
    return result


def ledger_answers(contract):
    """由题目输入推导费用标准答案；仅供实验校验，不修改模型回复。"""
    if contract.get('version') != 'reference-cash-ledger-v1':
        raise ValueError('未知答案合同')
    reference = cash = unknown = Decimal(0)
    for row in contract['rows']:
        if row['mode'] not in ('subscription', 'metered') or row['status'] not in ('billed', 'unknown-usage'):
            raise ValueError('非法账本案例')
        amount = (Decimal(row['amount']) if 'amount' in row else
            (Decimal(row['inputTokens'])*Decimal(row['inputPer1k'])
             + Decimal(row['outputTokens'])*Decimal(row['outputPer1k']))/1000)
        if not amount.is_finite() or amount < 0:
            raise ValueError('非法案例金额')
        if row['status'] == 'billed':
            reference += amount
            if row['mode'] == 'metered':
                cash += amount
        elif row['mode'] == 'metered':
            unknown += amount
    return dict(knownReferenceCny=float(reference), knownCashCny=float(cash),
                unknownReserveCny=float(unknown), cashProtectedCny=float(cash+unknown), subscriptionCashCny=None)


def validate_answer_contracts(protocol):
    for task in protocol['tasks']:
        if 'answerContract' not in task:
            continue
        answers = ledger_answers(task['answerContract'])
        for key, expected in task['expectedAnswers'].items():
            if key in answers and answers[key] != expected:
                raise ValueError(f'标准答案与账本案例不一致：{task["id"]}/{key}')
        if json.dumps(task['answerContract']['rows'], ensure_ascii=False) not in task['task']:
            raise ValueError('执行器未收到完整账本案例，禁止验收')


def freeze(catalog, history, extra_history_cny, authorization_cny, *,
           model_capacity_output=False, batch_ceiling_cny=None, task_ids=None, sample_ids=None, protocol_version='v3'):
    if protocol_version not in ('v3', 'v4', 'v5', 'v6'):
        raise ValueError('未知实验协议')
    path = ROOT/f'data/research/automatic-applicability-{protocol_version}.json' if protocol_version in ('v5', 'v6') else (
        CLARIFIED_PROTOCOL if protocol_version == 'v4' else PROTOCOL)
    protocol = json.loads(path.read_text())
    validate_answer_contracts(protocol)
    source_protocol_version = protocol['schemaVersion']
    if model_capacity_output:
        selection = catalog.get('catalogRequest', {})
        if (set(selection) != {'op', 'outputMode', 'flashReasoning'} or selection['op'] != 'catalog'
                or selection['outputMode'] != 'model-capacity' or selection['flashReasoning'] not in {'high', 'low'}):
            raise ValueError('新实验必须冻结真实目录容量及推理档位，不得混用旧 8192 目录')
        if (type(batch_ceiling_cny) not in (int, float) or not math.isfinite(batch_ceiling_cny)
                or batch_ceiling_cny <= 0):
            raise ValueError('取消单次输出限制仍须明确整批费用上限')
        protocol.update(schemaVersion='automatic-applicability-model-capacity-v1',
            taskProtocolVersion=source_protocol_version,
            executionOutputMode='model-capacity', reasoningEffort='ark-flash-'+selection['flashReasoning'],
            outputRevisionReason='题目版本单独记录；执行使用目录容量，整批保留硬预算，耗尽即停止。')
    if task_ids is not None:
        known = {t['id'] for t in protocol['tasks']}
        if not task_ids or len(task_ids) != len(set(task_ids)) or set(task_ids) - known:
            raise ValueError('定向复验必须使用不重复的已冻结任务 ID')
        protocol['tasks'] = [t for t in protocol['tasks'] if t['id'] in task_ids]
        protocol['targetedRepairRecheck'] = list(task_ids)
    order = [{'task': t['id'], 'route': route} for t in protocol['tasks'] for route in protocol['routes']]
    if sample_ids is not None:
        known = {f"{row['task']}:{row['route']}": row for row in order}
        if (task_ids is not None or not sample_ids or len(sample_ids) != len(set(sample_ids))
                or set(sample_ids) - known.keys()):
            raise ValueError('定向路线复验必须使用不重复的已冻结 task:route，不能同时指定任务组')
        order = [known[key] for key in sample_ids]
        selected = {row['task'] for row in order}
        protocol['tasks'] = [t for t in protocol['tasks'] if t['id'] in selected]
        protocol['targetedRepairSamples'] = deepcopy(order)
    compiled, provenance = compile_dsh_model_pool(catalog['pool'], {
        'schemaVersion': 'refractagent-dsh-catalog-v1', 'routes': catalog['routes']})
    models = compile_configuration(compiled).manifest.models
    maximum_calls = sum(protocol['maxCallsPerDirect'] if row['route'] == 'direct'
                        else protocol['maxCallsPerDag'] for row in order)
    # 互斥目标用单次最贵合法价格作保守包络，不把五个模型价格相加。
    capacities = {m.model_id: m.max_output_tokens if model_capacity_output
                  else min(m.max_output_tokens, protocol['outputLimitPerCall']) for m in models}
    amounts = [(protocol['inputBoundPerCall']*m.input_cost_per_1k
                + capacities[m.model_id]*m.output_cost_per_1k)/1000 for m in models]
    worst_reference = maximum_calls * max(amounts)
    worst_cash = maximum_calls * max((amount for amount, model in zip(amounts, models)
        if model.billing_mode != 'subscription'), default=0)
    maximum_reference = min(worst_reference, batch_ceiling_cny) if model_capacity_output else worst_reference
    maximum_cash = min(worst_cash, batch_ceiling_cny) if model_capacity_output else worst_cash
    protected = history['cashProtectedCny'] + extra_history_cny
    if not math.isfinite(authorization_cny) or authorization_cny <= 0:
        raise ValueError('必须给出实际获授权的正数现金上限')
    if protected + maximum_cash > authorization_cny:
        raise ValueError('冻结最坏现金包络超出历史授权余额；禁止实跑')
    random.Random(protocol['orderSeed']).shuffle(order)
    sources = source_hashes()
    validate_materials(protocol)
    frozen = {'protocol': protocol, 'catalog': catalog, 'configuration': compiled,
        'provenance': provenance, 'order': order, 'sourceHashes': sources,
        'maximumModelCalls': maximum_calls, 'maximumReferenceCny': maximum_reference,
        'maximumCashCny': maximum_cash, 'history': history, 'extraHistoryProtectionCny': extra_history_cny,
        'cashAuthorizationCny': authorization_cny,
        'remainingCashAuthorizationCny': authorization_cny-protected,
        'newJevCalls': 0, 'note': '只比较显式 Direct／DAG 对照；不宣称自动入口已选择 DAG。'}
    if model_capacity_output:
        frozen.update(outputCapsByModel=capacities, worstCaseReferenceCny=worst_reference,
            worstCaseCashCny=worst_cash, budgetMayStopBeforeAllRoutes=True,
            catalogRequest=catalog['catalogRequest'])
    return {**frozen, 'sha256': digest(frozen)}


def run(frozen, output, host_command, catalog):
    if 'sourceHashes' in frozen and source_hashes() != frozen['sourceHashes']:
        raise ValueError('桥接或源码在预检后变化；禁止执行')
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'preflight.json', frozen)
    protocol = frozen['protocol']
    log = (output/'host-stderr.txt').open('w')
    process = subprocess.Popen(host_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=log, text=True, cwd=ROOT,
                               env={**os.environ, 'REFRACT_APPLICABILITY_AUDIT':
                                    str((output/'host-diagnostics.ndjson').resolve())})
    results = []
    budget = None
    try:
        process.stdin.write(json.dumps(frozen.get('catalogRequest', {'op': 'catalog'}))+'\n'); process.stdin.flush()
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
                            or state['calls'] >= cap or model.max_output_tokens > frozen.get(
                                'outputCapsByModel', {}).get(model.model_id, protocol['outputLimitPerCall'])
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
                    except ModelInvocationError as exc:
                        try:
                            record_invocation_failure(budget, reservation, exc)
                        finally:
                            persist()
                        raise
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
            for field in ('maxFinalRevisions', 'reviewTimeoutMs', 'reviewReserveMs', 'reviewMaxOutputTokens'):
                if field in protocol:
                    payload[field] = protocol[field]
            if protocol.get('executionOutputMode') == 'model-capacity':
                payload['unlimitedNodeOutput'] = True
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
                    client=Guard(), runs_dir=folder/'live',
                    final_validator=lambda answer: task_check(answer, task,
                        review_receipt=protocol.get('deterministicReviewReceipt') is True), **common)
                raw = json.loads(Path(result['result_path']).read_text())
                row = {**item, 'status': result['status'], 'modelCalls': state['calls'],
                    'nodeCount': len((raw.get('plan') or {}).get('nodes', [])),
                    'wallMs': round((time.monotonic()-start)*1000),
                    'factCheck': task_check(raw.get('final_output', ''), task),
                    'evaluation': raw.get('evaluation'), 'issues': raw.get('issues'),
                    'finalCorrection': raw.get('final_correction'),
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
    parser.add_argument('--model-capacity-output', action='store_true')
    parser.add_argument('--batch-ceiling-cny', type=float)
    parser.add_argument('--task', action='append', dest='task_ids')
    parser.add_argument('--sample', action='append', dest='sample_ids', help='仅复验冻结的 task:direct 或 task:dag')
    parser.add_argument('--protocol-version', choices=('v3', 'v4', 'v5', 'v6'), default='v3')
    args = parser.parse_args()
    if not 0 <= args.extra_history_protection_cny < args.authorized_cash_cny:
        parser.error('必须给出独立历史现金的非负保护额度')
    history = historical_protection(historical_roots(
        ROOT, Path.home()/'Documents/Codes/RefractRouter'))
    catalog = json.loads(args.catalog.read_text())
    frozen = freeze(catalog, history, args.extra_history_protection_cny, args.authorized_cash_cny,
        model_capacity_output=args.model_capacity_output, batch_ceiling_cny=args.batch_ceiling_cny,
        task_ids=args.task_ids, sample_ids=args.sample_ids, protocol_version=args.protocol_version)
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
