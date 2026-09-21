"""#112 真实绑定后的零调用预算冻结；只计算证据，不执行模型。"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from .security_benchmark import ARMS, digest, validate_protocol
from .security_benchmark_bindings import audit_bindings


def _calls(protocol):
    calls = []
    judge = next(row['id'] for row in protocol['models'] if row['role'] == 'judge')
    for task in protocol['tasks']:
        for repeat in range(1, protocol['constraints']['repetitions'] + 1):
            for arm in ARMS:
                if arm == 'external-reference':
                    rows = [(task['externalReferenceModel'], task['directInputTokens'],
                             task['directOutputTokens'], None)]
                elif arm in {'trusted-direct', 'constrained-direct'}:
                    field = 'trustedDirectModel' if arm == 'trusted-direct' else 'constrainedDirectModel'
                    rows = [(task[field], task['directInputTokens'], task['directOutputTokens'], None)]
                else:
                    rows = [(node['modelId'], node['inputTokens'], node['outputTokens'], node['id'])
                            for node in task['fixedDag']]
                for model_id, input_tokens, output_tokens, node_id in rows:
                    calls.append({'purpose': 'production', 'task_id': task['id'],
                                  'repeat': repeat, 'arm': arm, 'node_id': node_id,
                                  'role_id': model_id, 'input_tokens': input_tokens,
                                  'output_tokens': output_tokens})
                calls.append({'purpose': 'evaluation', 'task_id': task['id'],
                              'repeat': repeat, 'arm': arm, 'node_id': None,
                              'role_id': judge,
                              'input_tokens': task['directOutputTokens'] + 512,
                              'output_tokens': 512})
    return calls


def _binding_map(inventory):
    return {row['roleId']: row for row in inventory['bindings']}


def freeze_budget(protocol, inventory):
    """冻结 48 次计划调用与价格可见部分；缺失绑定时总价必须保持未知。"""
    validate_protocol(protocol)
    binding_audit = audit_bindings(protocol, inventory)
    calls = _calls(protocol)
    hard_cap = protocol['constraints']['maxCalls']
    if len(calls) > hard_cap:
        raise ValueError('CALL_ENVELOPE_EXCEEDED: planned calls exceed protocol hard cap')
    bindings = _binding_map(inventory)
    totals = defaultdict(lambda: {'calls': 0, 'input_tokens': 0, 'output_tokens': 0,
                                  'purposes': defaultdict(int)})
    for call in calls:
        row = totals[call['role_id']]
        row['calls'] += 1
        row['input_tokens'] += call['input_tokens']
        row['output_tokens'] += call['output_tokens']
        row['purposes'][call['purpose']] += 1
    role_rows, unresolved, known_cost = [], [], 0.0
    for role_id in sorted(totals):
        total = totals[role_id]
        binding_row = bindings[role_id]
        cost = None
        if binding_row['status'] == 'bound':
            pricing = binding_row['binding']['pricing']
            cost = round(total['input_tokens'] / 1000 * pricing['inputPer1k']
                         + total['output_tokens'] / 1000 * pricing['outputPer1k'], 12)
            known_cost += cost
        else:
            unresolved.append({'role_id': role_id,
                               'requirements': list(binding_row['blockers'])})
        role_rows.append({'role_id': role_id, 'calls': total['calls'],
                          'purposes': dict(sorted(total['purposes'].items())),
                          'input_tokens': total['input_tokens'],
                          'output_tokens': total['output_tokens'],
                          'projected_cost': cost})
    production_calls = sum(call['purpose'] == 'production' for call in calls)
    evaluation_calls = sum(call['purpose'] == 'evaluation' for call in calls)
    return {
        'schema_version': 'security-benchmark-budget-freeze-v1',
        'real_model_calls': 0,
        'protocol_sha256': digest(protocol),
        'binding_sha256': binding_audit['binding_sha256'],
        'billing_unit': inventory['billing_unit'],
        'calls': calls,
        'role_totals': role_rows,
        'planned_calls': {'production': production_calls, 'evaluation': evaluation_calls,
                          'total': len(calls)},
        'authorization_call_cap': len(calls),
        'protocol_hard_call_cap': hard_cap,
        'automatic_http_retries': 0,
        'node_fallbacks': 0,
        'recovery_calls_authorized': 0,
        'cache_discount_assumed': False,
        'known_bound_cost': round(known_cost, 12),
        'maximum_total_cost': None if unresolved else round(known_cost, 12),
        'unresolved_cost_roles': unresolved,
        'binding_audit': binding_audit,
        'authorization_request_ready': not unresolved,
        'paid_execution_authorized': False,
        'live_execution_ready': False,
        'blocking_requirements': [
            requirement
            for row in unresolved
            for requirement in row['requirements']
        ] + ['PAID_EXECUTION_UNAUTHORIZED：开发批次尚未取得明确调用与预算授权。'],
        'stop_policy': {
            'task_route_failure': '停止该任务该路线的下游，结算在途调用，保留失败分母。',
            'batch_failure': '隐私违规、凭证异常、用量未知、账本异常或证据写入失败时停止整批。',
            'no_expansion': '不补样、不临时换模型、不自动消耗协议硬上限与计划调用之间的余量。',
        },
    }


def pricing_snapshot(inventory):
    """提取可公开提交的价格与来源；不包含凭证值。"""
    rows = []
    for row in inventory['bindings']:
        if row['binding'] is None:
            continue
        binding = row['binding']
        rows.append({'role_id': row['roleId'], 'provider': binding['provider'],
                     'model': binding['model'], 'deployment': binding['deployment'],
                     'version': deepcopy(binding['version']),
                     'pricing': deepcopy(binding['pricing']),
                     'profile_provenance': binding['profileProvenance'],
                     'evidence_sources': list(binding['evidenceSources'])})
    return {'schema_version': 'security-benchmark-pricing-snapshot-v1',
            'pricing_snapshot_date': inventory['pricing_snapshot_date'],
            'billing_unit': inventory['billing_unit'], 'routes': rows,
            'sources': deepcopy(inventory['sources'])}
