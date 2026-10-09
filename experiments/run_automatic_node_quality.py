"""有限节点校准：冻结原宿主路线，以独立答案校验生成能力档案，不调用额外 Judge。"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from refractrouter.agent import atomic_json
from refractrouter.application_config import compile_configuration, execution_capacity_model
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.node_quality import import_node_quality
from refractrouter.openai_compatible import DshStdioBridge, OpenAICompatibleClient
from refractrouter.routing_actions import action_binding, action_identity
from refractrouter.schemas import NodeSpec
from refractrouter.task_budget import TaskCallBudget, InvalidModelOutput, request_input_bound
from refractrouter.task_execution import node_messages
from refractrouter.task_inputs import prepare_inputs
from experiments.run_automatic_applicability import historical_protection, historical_roots, source_hashes

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'data/automatic-node-quality-cases-v2.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   allow_nan=False).encode()).hexdigest()


def oracle(case, output, *, json_text_policy='raw-json-v1'):
    """固定字段与数值；不让待评模型或其他生成式模型更改正确答案。"""
    if json_text_policy not in {'raw-json-v1', 'text-json-semantic-v1'}:
        raise ValueError('未知节点 JSON 文本评估规则')
    normalized = False
    candidate = output
    if json_text_policy == 'text-json-semantic-v1' and isinstance(output, str):
        fence = re.fullmatch(r'\s*```(?:json)?\s*\n(.*)\n```\s*', output, re.DOTALL)
        if fence:
            candidate, normalized = fence[1], True
    try:
        actual = json.loads(candidate)
    except (ValueError, TypeError):
        actual = None
    checks = [{'id': 'exact-fields', 'passed': isinstance(actual, dict)
               and set(actual) == set(case['expected'])}]
    for name, wanted in case['expected'].items():
        value = actual.get(name) if isinstance(actual, dict) else None
        passed = isinstance(value, str)
        if passed:
            try:
                passed = Decimal(value.strip()) == Decimal(wanted)
            except InvalidOperation:
                passed = value.strip().casefold() == wanted.casefold()
        checks.append({'id': name, 'passed': passed})
    criteria = case if json_text_policy == 'raw-json-v1' else {'case': case, 'policy': json_text_policy}
    return {'method': 'independent-node-oracle-v1', 'status': 'completed',
        'score': 100 * sum(c['passed'] for c in checks) / len(checks),
        'passed': all(c['passed'] for c in checks),
        'oracle': {'criteria_sha256': digest(criteria), 'checks': checks},
        'text_policy': json_text_policy, 'whole_json_fence_removed': normalized,
        'raw_json_format_compliant': isinstance(actual, dict) and not normalized}


def observation_corpus(cases, rows, split):
    return {'schema_version': 'node-observations-v1', 'kind': 'empirical',
        'expected_contexts': [{'task_id': case['id'], 'repeat': 1, 'node_id': 'probe'}
                              for case in cases if case['split'] == split],
        'observations': [{k: v for k, v in row.items() if k != 'split'}
                         for row in rows if row['split'] == split]}


def archive_bundle(frozen, rows):
    cases = frozen['cases']['cases']
    compiled = compile_configuration(frozen['config'])
    return {'schema_version': 'node-quality-bundle-v1', 'kind': 'empirical',
        'scope': frozen['cases']['scope'], 'action_bindings': frozen['action_bindings'],
        'execution_action_bindings': {m.model_id: action_binding(execution_capacity_model(m))
            for m in compiled.manifest.candidates if m.model_id in frozen['action_bindings']},
        'execution_output_mode': 'provider-default-capacity',
        'calibration_task_ids': [case['id'] for case in cases if case['split'] == 'calibration'],
        'held_out_task_ids': [case['id'] for case in cases if case['split'] == 'held-out'],
        'observations': observation_corpus(cases, rows, 'calibration'),
        'held_out_observations': observation_corpus(cases, rows, 'held-out')}


def reassess(source, output):
    """另存派生评估，保留原始响应、原评分和账本，不发起任何模型调用。"""
    frozen = json.loads((source / 'preflight.json').read_text())
    original = json.loads((source / 'observations.json').read_text())
    cases = {case['id']: case for case in frozen['cases']['cases']}
    rows = []
    for row in original:
        revised = dict(row)
        if row['status'] == 'completed' and row['finish_reason'] == 'stop':
            revised['evaluation'] = {**oracle(cases[row['task_id']], row['output'],
                json_text_policy='text-json-semantic-v1'),
                'input_sha256': row['input_sha256'], 'output_sha256': row['output_sha256']}
        rows.append(revised)
    archive = archive_bundle(frozen, rows)
    archive['derivation'] = {'policy': 'text-json-semantic-v1', 'new_model_calls': 0,
        'source_preflight_sha256': hashlib.sha256((source / 'preflight.json').read_bytes()).hexdigest(),
        'source_observations_sha256': hashlib.sha256((source / 'observations.json').read_bytes()).hexdigest(),
        'raw_responses_unchanged': True, 'format_compliance_reported_separately': True}
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_json(output / 'observations.json', rows)
    atomic_json(output / 'node-quality-bundle.json', archive)
    _, imported = import_node_quality(output / 'node-quality-bundle.json', compile_configuration(frozen['config']))
    summary = {'complete': True, 'new_model_calls': 0, 'derivation': archive['derivation'],
        'imported': imported, 'passed': sum(r['evaluation']['passed'] for r in rows),
        'observations': len(rows),
        'raw_json_format_failures': sum(r['evaluation'].get('raw_json_format_compliant') is False for r in rows),
        'held_out_passed': all(r['evaluation']['passed'] for r in rows if r['split'] == 'held-out'),
        'results': [{k: v for k, v in r.items() if k not in {'input', 'output', 'evaluation'}}
            | {'passed': r['evaluation']['passed'],
               'whole_json_fence_removed': r['evaluation'].get('whole_json_fence_removed', False)} for r in rows]}
    atomic_json(output / 'summary.json', summary)
    return {k: summary[k] for k in ('new_model_calls', 'passed', 'observations', 'raw_json_format_failures', 'imported')}


def messages(case, context):
    _, task, _ = prepare_inputs({'task': case['task']}, context, for_node=True)
    contract = {'objective': '只核对给定公开材料并返回规定 JSON 文本', 'inputs': {},
        'output': {'format': 'text', 'fields': {'text': '任务规定的 JSON 文本'}},
        'capability': {'difficulty': case['difficulty'], 'risk': case['risk'],
                       'input_budget_tokens': 131072, 'expected_output_tokens': 512},
        'checks': ['字段、数值和材料事实正确'], 'covers': [0],
        'execution': 'text-model', 'failure_policy': 'stop'}
    node = NodeSpec(case['id'].replace('-', '_'), case['type'], '完整执行当前节点任务，不沿用历史任务的答案。')
    return node_messages(task, node, contract, {}), contract


def freeze(catalog, context, extra_history_cny):
    cases = json.loads(CASES.read_text())
    config, _ = compile_dsh_model_pool(catalog['pool'],
        {'schemaVersion': 'refractagent-dsh-catalog-v1', 'routes': catalog['routes']})
    c = compile_configuration(config)
    wanted = set(cases['models'])
    selected = [m for m in c.manifest.candidates if f'{m.provider}/{m.api_model}' in wanted]
    if len(selected) != len(wanted) or any(m.billing_mode != 'subscription' for m in selected):
        raise ValueError('有限校准只允许冻结的两条既有订阅路线')
    envelopes = []
    for case in cases['cases']:
        prompt, _ = messages(case, context)
        size = request_input_bound(prompt)
        if not 256 <= size <= 131072:
            raise ValueError('校准输入超出冻结能力分层，不截断上下文')
        for model in selected:
            b = TaskCallBudget(None, 1e6, 1, cash_limits={'production': 1, 'evaluation': 1})
            reservation = b.reserve(execution_capacity_model(model), prompt, label=case['id'])
            envelopes.append({'case': case['id'], 'model_id': model.model_id,
                              'input_bound': size, 'maximumReferenceCny': reservation.row['reserved']})
    history = historical_protection(historical_roots(ROOT, Path.home()/'Documents/Codes/RefractRouter'))
    worst = sum(e['maximumReferenceCny'] for e in envelopes)
    protected = history['cashProtectedCny'] + extra_history_cny
    if protected > 100 or worst + protected > 100:
        raise ValueError('保守地同时核对参考上界与累计 100 CNY，超限停止')
    frozen = {'schema_version': 'automatic-node-quality-batch-v1', 'cases': cases,
        'cases_sha256': hashlib.sha256(CASES.read_bytes()).hexdigest(), 'catalog_sha256': digest(catalog),
        'context_sha256': hashlib.sha256(context.encode()).hexdigest(), 'context_chars': len(context),
        'sourceHashes': source_hashes(), 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'models': {m.model_id: action_identity(m) for m in selected},
        'action_bindings': {m.model_id: action_binding(m) for m in selected}, 'config': config,
        'maximumModelCalls': len(envelopes), 'maximumReferenceCny': worst, 'maximumCashCny': 0,
        'timeoutSecondsPerCall': 180, 'httpRetries': 0, 'extraJudgeCalls': 0,
        'history': history, 'extraHistoryProtectionCny': extra_history_cny,
        'protectedCny': protected, 'envelopes': envelopes}
    frozen['sha256'] = digest(frozen)
    return frozen


def execute(frozen, context, output):
    catalog_probe = subprocess.run(['node', '--experimental-strip-types',
        str(ROOT / 'validation/dsh/applicability_host.ts')], cwd=ROOT, text=True,
        input=json.dumps({'op': 'catalog', 'outputMode': 'model-capacity'}) + '\n',
        capture_output=True, timeout=30, env={k: v for k, v in os.environ.items()
                                           if k != 'REFRACT_AUTOMATIC_MULTIPLEX'})
    if (catalog_probe.returncode != 0
            or digest(json.loads(catalog_probe.stdout.strip().splitlines()[-1])) != frozen['catalog_sha256']):
        raise ValueError('原宿主目录、路线或参数已变化，禁止派发')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_json(output / 'preflight.json', frozen)
    log = (output / 'host-stderr.txt').open('w')
    process = subprocess.Popen(['node', '--experimental-strip-types',
        str(ROOT / 'validation/dsh/applicability_host.ts')], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
        env={**os.environ, 'REFRACT_AUTOMATIC_MULTIPLEX': '1'})
    bridge = DshStdioBridge(reader=process.stdout, writer=process.stdin)
    budget = TaskCallBudget(OpenAICompatibleClient(dsh_bridge=bridge, max_retries=0, timeout_seconds=None),
        frozen['maximumReferenceCny'], 1, max_calls=frozen['maximumModelCalls'], capture_payload=True,
        cash_limits={'production': 1e-9, 'evaluation': 1e-9})
    c = compile_configuration(frozen['config'])
    rows = []
    complete = False
    def persist(*_):
        amounts, records = budget.snapshot()
        atomic_json(output / 'batch-ledger.json', {'referenceCostsCny': amounts,
            'cashCostsCny': budget.cash_snapshot(), 'records': records})
    budget.on_reserve = persist
    budget.on_dispatch = persist
    try:
        bridge.capabilities()
        for case in frozen['cases']['cases']:
            prompt, contract = messages(case, context)
            input_text = json.dumps(prompt, ensure_ascii=False)
            ih = hashlib.sha256(input_text.encode()).hexdigest()
            for mid in frozen['models']:
                model = next(m for m in c.manifest.candidates if m.model_id == mid)
                reservation = budget.reserve(execution_capacity_model(model), prompt, label=case['id'])
                status = 'completed'
                try:
                    reply = budget.invoke(reservation, timeout_seconds=frozen['timeoutSecondsPerCall'])
                    result = asdict(reply)
                except InvalidModelOutput:
                    status = 'billed-output-invalid'
                    result = reservation.row['response']
                finally:
                    persist()
                oh = hashlib.sha256(result['content'].encode()).hexdigest()
                evaluation = oracle(case, result['content'])
                if status != 'completed':
                    evaluation = {'method': 'deterministic-rejection', 'status': 'completed',
                                  'score': 0, 'passed': False}
                row = {'task_id': case['id'], 'repeat': 1, 'node_id': 'probe', 'model_id': mid,
                    'input': input_text, 'output': result['content'], 'input_sha256': ih, 'output_sha256': oh,
                    'status': status, 'finish_reason': result['finish_reason'],
                    'features': {'node_type': case['type'], 'difficulty': case['difficulty'],
                                 'risk': case['risk'], 'input_budget_tokens': request_input_bound(prompt)},
                    'output_contract': contract['output'],
                    'evaluation': {**evaluation, 'input_sha256': ih, 'output_sha256': oh},
                    'usage': {k: result[k] for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens')},
                    'latency_ms': result['latency_ms'], 'split': case['split']}
                rows.append(row)
                atomic_json(output / 'observations.json', rows)
                print(json.dumps({'case': case['id'], 'model': model.api_model,
                    'passed': evaluation['passed'], 'latency_ms': result['latency_ms'],
                    'referenceCny': reservation.row['charged']}, ensure_ascii=False), flush=True)
        archive = archive_bundle(frozen, rows)
        atomic_json(output / 'node-quality-bundle.json', archive)
        _, imported = import_node_quality(output / 'node-quality-bundle.json', c)
        complete = True
        atomic_json(output / 'summary.json', {'complete': True, 'imported': imported,
            'held_out_passed': all(r['evaluation']['passed'] for r in rows if r['split'] == 'held-out'),
            'results': [{k: v for k, v in r.items() if k not in {'input', 'output', 'evaluation'}}
                | {'passed': r['evaluation']['passed']} for r in rows]})
    finally:
        persist()
        bridge.close()
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        log.close()
        atomic_json(output / 'completion.json', {'complete': complete, 'completedCases': len(rows),
                                                 'modelCalls': len(budget.records)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--context-request', type=Path)
    parser.add_argument('--extra-history-protection-cny', type=float)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--freeze-sha256')
    parser.add_argument('--reassess-from', type=Path)
    args = parser.parse_args()
    if args.reassess_from:
        if args.execute:
            parser.error('派生评估禁止付费执行')
        print(json.dumps(reassess(args.reassess_from, args.output_dir), ensure_ascii=False))
        return
    if args.catalog is None or args.context_request is None or args.extra_history_protection_cny is None:
        parser.error('预检和付费执行必须明确目录、上下文及额外历史保护额度')
    if args.extra_history_protection_cny < 0:
        parser.error('历史额外保护须非负')
    context = json.loads(args.context_request.read_text())['payload']['context']
    frozen = freeze(json.loads(args.catalog.read_text()), context, args.extra_history_protection_cny)
    if not args.execute:
        args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        atomic_json(args.output_dir / 'preflight.json', frozen)
        print(json.dumps({k: frozen[k] for k in ('sha256', 'maximumModelCalls', 'maximumReferenceCny',
                                               'maximumCashCny', 'protectedCny')}, ensure_ascii=False))
    else:
        if args.freeze_sha256 != frozen['sha256']:
            parser.error('源码、范围或历史费用改变，禁止执行')
        execute(frozen, context, args.output_dir)


if __name__ == '__main__':
    main()
