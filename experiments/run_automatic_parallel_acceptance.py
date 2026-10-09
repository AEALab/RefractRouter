"""固定四节点 DAG 的真实 DSH 并行接线验收；默认零调用，不用于收益比较。"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess

from refractrouter.agent import atomic_json, automatic_cost_trace
from refractrouter.application_config import compile_configuration, execution_capacity_model
from refractrouter.configured_routing import configured_profile
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.openai_compatible import DshStdioBridge, OpenAICompatibleClient
from refractrouter.task_runtime import run_task
from refractrouter.task_plan import validate_plan
from experiments.run_automatic_node_quality import oracle
from experiments.run_automatic_applicability import digest, historical_protection, historical_roots, source_hashes

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'settled_reference': '0.15', 'cash_occupied': '0.10', 'serial_seconds': '28',
            'parallel_seconds': '15', 'released': '0.06', 'remaining_occupied': '0.11'}
TASK = ('独立核对三组材料后汇总。A：已结算订阅参考0.12 CNY、已结算现金0.03 CNY、未知现金预留0.07 CNY；'
        '总参考＝订阅参考＋现金，现金占用＝已结算现金＋未知现金预留。'
        'B：三个无依赖分支耗时8、12、5秒，汇总耗时3秒；并发容量3，没有其他延时。'
        'C：尚未派发现金预留0.06 CNY、已派发未知预留0.09 CNY、已结算现金0.02 CNY；'
        '取消只释放尚未派发预留。最终只输出一个原始 JSON 对象，所有值为不带单位的数字字符串，'
        '字段恰好为 settled_reference、cash_occupied、serial_seconds、parallel_seconds、released、remaining_occupied。')


def fixture_plan():
    criteria = ['A 总参考和现金占用分别为0.15和0.10。', 'B 串行为28秒、并行为15秒。',
                'C 释放0.06，取消后的总现金占用为0.11。', '最终交付恰好六个字段，数值是字符串。']
    groups = [
        ('ledger', '仅核对材料 A，计算总参考和现金占用。', ['settled_reference', 'cash_occupied']),
        ('timing', '仅核对材料 B，计算串行和并行耗时。', ['serial_seconds', 'parallel_seconds']),
        ('cancel', '仅核对材料 C，计算释放金额和取消后的总现金占用。', ['released', 'remaining_occupied'])]
    nodes = []
    for index, (nid, job, fields) in enumerate(groups):
        nodes.append({'node_id': nid, 'node_type': 'synthesis', 'parents': [], 'prompt_template': job,
            'contract': {'objective': job, 'inputs': {},
                'output': {'format': 'json', 'fields': {field: '数字字符串，不带单位' for field in fields}},
                'capability': {'difficulty': 'low', 'risk': 'low', 'input_budget_tokens': 131072,
                               'expected_output_tokens': 512},
                'checks': [criteria[index]], 'covers': [index], 'execution': 'text-model', 'failure_policy': 'stop'}})
    nodes.append({'node_id': 'answer', 'node_type': 'generation',
        'parents': [nid for nid, _, _ in groups], 'prompt_template': '核对三组原材料与上游结果，交付六字段 JSON。',
        'contract': {'objective': '完整交付三项独立检查的汇总，不漏项、不重复计费。',
            'inputs': {nid: {'fields': fields, 'reason': '需要该分支的独立核对结果。'} for nid, _, fields in groups},
            'output': {'format': 'text', 'fields': {'text': '原始六字段 JSON 对象，不添加围栏或说明。'}},
            'capability': {'difficulty': 'medium', 'risk': 'high', 'input_budget_tokens': 131072,
                           'expected_output_tokens': 1024},
            'checks': criteria, 'covers': list(range(len(criteria))),
            'execution': 'text-model', 'failure_policy': 'stop'}})
    return validate_plan({'schema_version': 'text-task-plan-v2', 'decomposition_reason':
        '受控接线夹具：三项无依赖核对并行，最后统一交付；不作为自然任务收益样本。',
        'nodes': nodes, 'final_node_id': 'answer', 'acceptance_criteria': criteria})


def freeze(catalog, context, node_profile, extra_history):
    pool = dict(catalog['pool'], nodeProfilePath=str(node_profile.resolve()))
    raw, provenance = compile_dsh_model_pool(pool,
        {'schemaVersion': 'refractagent-dsh-catalog-v1', 'routes': catalog['routes']})
    compiled = compile_configuration(raw)
    history = historical_protection(historical_roots(ROOT, Path.home() / 'Documents/Codes/RefractRouter'))
    flash = next(m for m in compiled.manifest.candidates
                 if m.provider == 'ark' and m.api_model == 'deepseek-v4-flash')
    models = [execution_capacity_model(flash)] * 4 + [compiled.manifest.judge]
    worst = sum((m.context_window * m.input_cost_per_1k
                 + m.max_output_tokens * m.output_cost_per_1k) / 1000 for m in models)
    if any(m.billing_mode != 'subscription' for m in models) or worst + history['cashProtectedCny'] + extra_history > 100:
        raise ValueError('冻结范围超过既有累计额度或包含未冻结的现金路线')
    frozen = {'schema_version': 'automatic-parallel-acceptance-v1', 'scope': 'controlled-functional-only',
        'configuration': raw, 'provenance': provenance, 'catalog_sha256': digest(catalog),
        'context_sha256': hashlib.sha256(context.encode()).hexdigest(), 'sourceHashes': source_hashes(),
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'task': TASK, 'expected': EXPECTED, 'plan': fixture_plan().to_dict(),
        'maximum_model_calls': 5, 'maximum_cash_cny': 0, 'maximum_reference_cny': worst,
        'history_cash_protected_cny': history['cashProtectedCny'] + extra_history,
        'allowed_model_ids': list({m.model_id for m in models}), 'max_concurrency': 3,
        'timeout_ms': 300000, 'review_timeout_ms': 180000, 'review_reserve_ms': 60000,
        'http_retries': 0, 'jev_calls': 0,
        'tools': False, 'model_capacity_output': True, 'user_profile_modified': False}
    frozen['sha256'] = digest(frozen)
    return frozen


def execute(frozen, context, output):
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    atomic_json(output / 'preflight.json', frozen)
    compiled = compile_configuration(frozen['configuration'])
    manifest = replace(compiled.manifest, models=tuple(execution_capacity_model(m)
        if 'worker' in m.roles else m for m in compiled.manifest.models))
    plan = validate_plan(frozen['plan'])
    profile = configured_profile(compiled, manifest, plan.to_dict())
    request = {'task': TASK, 'plan': plan.to_dict(), 'mode': 'run', 'method': 'A',
        'qualityMin': compiled.quality_min, 'costMax': frozen['maximum_reference_cny'],
        'latencyMaxMs': frozen['timeout_ms'], 'maxConcurrency': 3, 'maxNodeFallbacks': 0,
        'reviewReserveMs': frozen['review_reserve_ms'], 'reviewTimeoutMs': 180000, 'reviewMaxOutputTokens': 8192,
        'maxFinalRevisions': 0, 'adaptiveOutputBudget': True}
    # 宿主目录先以零调用核对；派发只经生产插件的同一个并行桥接。
    probe = subprocess.run(['node', '--experimental-strip-types', str(ROOT / 'validation/dsh/applicability_host.ts')],
        input=json.dumps({'op': 'catalog', 'outputMode': 'model-capacity'}) + '\n',
        capture_output=True, text=True, cwd=ROOT, timeout=30,
        env={k: v for k, v in os.environ.items() if k != 'REFRACT_AUTOMATIC_MULTIPLEX'})
    if probe.returncode or digest(json.loads(probe.stdout.strip().splitlines()[-1])) != frozen['catalog_sha256']:
        raise ValueError('原 DSH 目录或参数变化，禁止派发')
    with (output / 'host-stderr.txt').open('w') as log:
        host = subprocess.Popen(['node', '--experimental-strip-types', str(ROOT / 'validation/dsh/applicability_host.ts')],
            cwd=ROOT, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
            env={**os.environ, 'REFRACT_AUTOMATIC_MULTIPLEX': '1'})
        bridge = DshStdioBridge(reader=host.stdout, writer=host.stdin)
        actual = OpenAICompatibleClient(dsh_bridge=bridge, max_retries=0, timeout_seconds=None)
        capacities = {m.model_id: execution_capacity_model(m).max_output_tokens for m in manifest.models}
        class FrozenClient:
            max_retries = 0
            dsh_bridge = bridge
            def __init__(self, delegate):
                self.delegate = delegate
            def for_task_call(self, seconds):
                return FrozenClient(self.delegate.for_task_call(seconds))
            def complete(self, model, messages, *, json_mode=False, tools=None):
                if (model.model_id not in frozen['allowed_model_ids'] or tools
                        or model.max_output_tokens > capacities[model.model_id]):
                    raise ValueError('调用超出冻结模型、工具或输出容量；停止本次接线验收')
                return self.delegate.complete(model, messages, json_mode=json_mode)
        client = FrozenClient(actual)
        def checkpoint(result):
            atomic_json(output / 'result.json', result)
        try:
            result = run_task(request, manifest, profile, client=client,
                production_limit=frozen['maximum_reference_cny'], evaluation_limit=frozen['maximum_reference_cny'],
                configured_application=True, configuration=compiled, checkpoint=checkpoint,
                conversation_context=context, context_limit_bytes=1000000, input_cap=1000000,
                max_model_calls=5, final_validator=lambda answer: oracle(
                    {'expected': EXPECTED}, answer, json_text_policy='text-json-semantic-v1'))
            checkpoint(result)
        finally:
            bridge.close()
            host.stdin.close()
            try:
                host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                host.terminate()
                host.wait(timeout=5)
    attempts = result.get('nodes', [])
    roots = [row for row in attempts if row['node_id'] in {'ledger', 'timing', 'cancel'}]
    answer = next((row for row in attempts if row['node_id'] == 'answer'), None)
    overlapping = (len(roots) == 3 and max(r['start_ms'] for r in roots) < min(r['end_ms'] for r in roots))
    join_ordered = bool(answer and len(roots) == 3 and answer['start_ms'] >= max(r['end_ms'] for r in roots))
    passed = (result['status'] == 'completed' and overlapping and join_ordered
        and result['execution']['peak_active_nodes'] == 3
        and all(row['status'] == 'billed' for row in result['calls'])
        and {row['model_id'] for row in result['calls']} <= set(frozen['allowed_model_ids']))
    summary = {'scope': 'controlled-functional-only', 'passed': passed, 'status': result['status'],
        'root_requests_overlap': overlapping, 'join_after_all_roots': join_ordered,
        'execution': result.get('execution'), 'host_capabilities': result.get('host_capabilities'),
        'evaluation': result.get('evaluation'), 'issues': result['issues'],
        'wall_time_ms': result['wall_time_ms'], 'model_calls': len(result['calls']),
        'cash_costs_cny': result.get('cash_costs_cny'), 'reference_costs_cny': result.get('reference_costs_cny'),
        'cost_trace': automatic_cost_trace(result, manifest),
        'nodes': [{k: row.get(k) for k in ('node_id', 'model_id', 'start_ms', 'end_ms', 'status')} for row in attempts]}
    atomic_json(output / 'summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('passed','status','root_requests_overlap','join_after_all_roots',
        'wall_time_ms','model_calls','reference_costs_cny','cash_costs_cny','issues')}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--context-request', type=Path, required=True)
    parser.add_argument('--node-profile', type=Path, required=True)
    parser.add_argument('--extra-history-protection-cny', type=float, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    if args.extra_history_protection_cny < 0:
        parser.error('额外历史保护不能为负数')
    context = json.loads(args.context_request.read_text())['payload']['context']
    frozen = freeze(json.loads(args.catalog.read_text()), context, args.node_profile, args.extra_history_protection_cny)
    if args.execute:
        if frozen['sha256'] != args.freeze_sha256:
            parser.error('预检范围或源码发生变化，停止派发')
        execute(frozen, context, args.output_dir)
    else:
        args.output_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        atomic_json(args.output_dir / 'preflight.json', frozen)
        print(json.dumps({k: frozen[k] for k in ('sha256','maximum_model_calls','maximum_cash_cny',
            'maximum_reference_cny','history_cash_protected_cny')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
