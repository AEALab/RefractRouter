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


def _project(tokens, pricing):
    return round(tokens['input_tokens'] / 1000 * pricing['inputPer1k']
                 + tokens['output_tokens'] / 1000 * pricing['outputPer1k'], 12)


def freeze_budget(protocol, inventory):
    """冻结调用与双账本；执行资源和公开参考价格绝不互相替代或跨单位求和。"""
    validate_protocol(protocol)
    binding_audit = audit_bindings(protocol, inventory)
    version = 3 if inventory['schema_version'].endswith('v3') else 2
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
    role_rows, unresolved, known_usage = [], [], 0.0
    execution_totals = defaultdict(float)
    local_resource_totals = defaultdict(float)
    unresolved_local_resources = []
    reference_totals = defaultdict(float)
    unresolved_reference = []
    for role_id in sorted(totals):
        total = totals[role_id]
        binding_row = bindings[role_id]
        execution_usage = None
        reference_cost = None
        reference_unit = None
        execution_unit = inventory.get('execution_billing_unit')
        local_resource_cost = None
        local_resource_unit = None
        if binding_row['status'] == 'bound':
            binding = binding_row['binding']
            if binding['executionPricing'] is not None:
                execution_usage = _project(total, binding['executionPricing'])
                execution_unit = binding['executionPricing']['unit']
                execution_totals[execution_unit] += execution_usage
                if version == 2:
                    known_usage += execution_usage
            else:
                execution_unit = None
                resource = binding['localResource']
                local_resource_unit = resource['resourceCostUnit']
                if resource['resourceCostPerCall'] is None:
                    unresolved_local_resources.append({
                        'role_id': role_id,
                        'requirements': list(resource['resourceCostBlockers']),
                    })
                else:
                    local_resource_cost = round(total['calls'] * resource['resourceCostPerCall'], 12)
                    local_resource_totals[local_resource_unit] += local_resource_cost
            if binding['referencePricing'] is None:
                unresolved_reference.append({
                    'role_id': role_id,
                    'requirements': list(binding['referencePricingBlockers']),
                })
            else:
                reference = binding['referencePricing']['pricing']
                reference_unit = reference['unit']
                reference_cost = _project(total, reference)
                reference_totals[reference_unit] += reference_cost
        else:
            unresolved.append({'role_id': role_id,
                               'requirements': list(binding_row['blockers'])})
        role_row = {'role_id': role_id, 'calls': total['calls'],
                          'purposes': dict(sorted(total['purposes'].items())),
                          'input_tokens': total['input_tokens'],
                          'output_tokens': total['output_tokens'],
                          'projected_execution_usage': execution_usage,
                          'execution_billing_unit': execution_unit,
                          'projected_reference_cost': reference_cost,
                          'reference_billing_unit': reference_unit}
        if version == 3:
            role_row['projected_local_resource_cost'] = local_resource_cost
            role_row['local_resource_billing_unit'] = local_resource_unit
        role_rows.append(role_row)
    production_calls = sum(call['purpose'] == 'production' for call in calls)
    evaluation_calls = sum(call['purpose'] == 'evaluation' for call in calls)
    result = {
        'schema_version': f'security-benchmark-budget-freeze-v{version}',
        'real_model_calls': 0,
        'protocol_sha256': digest(protocol),
        'binding_sha256': binding_audit['binding_sha256'],
        'execution_billing_unit': inventory.get('execution_billing_unit'),
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
        'known_bound_execution_usage': round(known_usage, 12) if version == 2 else None,
        'maximum_total_execution_usage': (
            None if unresolved or version == 3 else round(known_usage, 12)),
        'unresolved_execution_usage_roles': unresolved,
        'reference_cost_totals_by_unit': {
            unit: round(value, 12) for unit, value in sorted(reference_totals.items())
        },
        'maximum_total_reference_cost': (
            round(next(iter(reference_totals.values())), 12)
            if not unresolved and not unresolved_reference and len(reference_totals) == 1
            else None
        ),
        'maximum_total_reference_cost_unit': (
            next(iter(reference_totals))
            if not unresolved and not unresolved_reference and len(reference_totals) == 1
            else None
        ),
        'unresolved_reference_cost_roles': unresolved_reference,
        'execution_cash_cost': None,
        'execution_cash_cost_method': None,
        'execution_cash_cost_blockers': [
            'SUBSCRIPTION_ALLOCATION_UNFROZEN：尚未冻结订阅费用、包含 AFP、有效期与利用率，'
            '不得把 AFP 用量解释为现金成本。'
        ] if any(row['binding'] is not None
                 and row['binding']['executionPricing'] is not None
                 and row['binding']['executionPricing']['unit'] == 'AFP'
                 for row in inventory['bindings']) else [],
        'binding_audit': binding_audit,
        'authorization_request_ready': not unresolved,
        'paid_execution_authorized': False,
        'live_execution_ready': False,
        'blocking_requirements': [
            requirement
            for row in unresolved
            for requirement in row['requirements']
        ] + [
            requirement
            for row in unresolved_local_resources
            for requirement in row['requirements']
        ] + ['PAID_EXECUTION_UNAUTHORIZED：开发批次尚未取得明确调用与预算授权。'],
        'stop_policy': {
            'task_route_failure': '停止该任务该路线的下游，结算在途调用，保留失败分母。',
            'batch_failure': '隐私违规、凭证异常、用量未知、账本异常或证据写入失败时停止整批。',
            'no_expansion': '不补样、不临时换模型、不自动消耗协议硬上限与计划调用之间的余量。',
        },
    }
    if version == 3:
        result.update({
            'known_execution_usage_by_unit': {
                unit: round(amount, 12) for unit, amount in sorted(execution_totals.items())},
            'maximum_execution_usage_by_unit': (
                None if unresolved else {unit: round(amount, 12)
                                         for unit, amount in sorted(execution_totals.items())}),
            'known_local_resource_cost_by_unit': {
                unit: round(amount, 12) for unit, amount in sorted(local_resource_totals.items())},
            'maximum_local_resource_cost_by_unit': (
                None if unresolved or unresolved_local_resources else {
                    unit: round(amount, 12)
                    for unit, amount in sorted(local_resource_totals.items())}),
            'unresolved_local_resource_cost_roles': unresolved_local_resources,
            'authorization_request_ready': not unresolved and not unresolved_local_resources,
        })
    return result


def pricing_snapshot(inventory):
    """提取执行与参考计价来源；不包含凭证值，也不推断模型等价关系。"""
    rows = []
    for row in inventory['bindings']:
        if row['binding'] is None:
            continue
        binding = row['binding']
        route = {'role_id': row['roleId'], 'provider': binding['provider'],
                     'model': binding['model'], 'deployment': binding['deployment'],
                     'version': deepcopy(binding['version']),
                     'execution_pricing': deepcopy(binding['executionPricing']),
                     'reference_pricing': deepcopy(binding['referencePricing']),
                     'reference_pricing_blockers':
                         list(binding['referencePricingBlockers']),
                     'profile_provenance': binding['profileProvenance'],
                     'evidence_sources': list(binding['evidenceSources'])}
        if inventory['schema_version'].endswith('v3'):
            route['local_resource'] = deepcopy(binding['localResource'])
        rows.append(route)
    return {'schema_version': 'security-benchmark-pricing-snapshot-v3'
            if inventory['schema_version'].endswith('v3') else 'security-benchmark-pricing-snapshot-v2',
            'pricing_snapshot_date': inventory['pricing_snapshot_date'],
            'execution_billing_unit': inventory.get('execution_billing_unit'), 'routes': rows,
            'sources': deepcopy(inventory['sources'])}
