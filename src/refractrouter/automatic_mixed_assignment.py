"""自动路由的双计费单位节点分配；仅使用已冻结的质量与费用预测。"""
from __future__ import annotations

from itertools import product
import math

from .node_routing import NodeProfile, number, validate_profiles
from .task_scheduling import ExecutionPolicy, estimate_schedule


def route_nodes_mixed(plan, profiles: tuple[NodeProfile, ...], *, model_units,
                      quality_min, budgets, eligible_models=None, execution_policy=None,
                      model_providers=None, latency_max_ms=None, assignment_mode='per-node',
                      quality_reference=None):
    """在质量、额度准入后，依 CNY、AFP、时延选择完整节点分配。

    ``quality_reference`` 是同口径的已接受质量先验下界；若不存在，结果只证明
    ``quality_min`` 准入，不声称与其他路线等质。调用方不得把此结果标为实证收益。
    """
    if assignment_mode not in {'per-node', 'single-model'}:
        raise ValueError('unsupported assignment mode')
    number(quality_min, 'quality_min', maximum=100)
    if quality_reference is not None:
        number(quality_reference, 'quality_reference', maximum=100)
    if latency_max_ms is not None:
        number(latency_max_ms, 'latency_max_ms')
    if not isinstance(budgets, dict) or set(budgets) != {'AFP', 'CNY'}:
        raise ValueError('mixed routing requires AFP and CNY budgets')
    for unit, value in budgets.items():
        number(value, f'{unit} budget')
    if not isinstance(model_units, dict) or any(unit not in {'AFP', 'CNY'} for unit in model_units.values()):
        raise ValueError('mixed routing requires model billing units')
    validate_profiles(profiles)
    policy = execution_policy or ExecutionPolicy()
    providers = model_providers or {profile.model_id: 'default' for profile in profiles}
    if (policy.provider_concurrency or policy.provider_min_interval_ms) and model_providers is None:
        raise ValueError('provider policy requires model_providers')
    options = []
    for node in plan.nodes:
        pool = sorted((profile for profile in profiles
            if profile.matches(node, plan) and profile.quality >= quality_min
            and (eligible_models is None or profile.model_id in eligible_models.get(node.node_id, []))),
            key=lambda profile: profile.model_id)
        if any(profile.model_id not in model_units for profile in pool):
            raise ValueError('candidate lacks an actual billing unit')
        options.append(pool)
    combinations = math.prod(map(len, options))
    if combinations > 100000:
        raise ValueError('assignment search exceeds 100000 combinations; narrow the profile or DAG')
    rejected = {'assignment-mode': 0, 'quality-reference': 0, 'unit-budget': 0,
                'latency': 0, 'afp-below-feasible-cash-quality': 0}
    best = None
    best_key = None
    feasible_rows = []
    for combination in product(*options):
        if assignment_mode == 'single-model' and len({profile.model_id for profile in combination}) != 1:
            rejected['assignment-mode'] += 1
            continue
        quality = min(profile.quality for profile in combination)
        if quality_reference is not None and quality < quality_reference:
            rejected['quality-reference'] += 1
            continue
        costs = {'AFP': 0.0, 'CNY': 0.0}
        for profile in combination:
            costs[model_units[profile.model_id]] += profile.cost
        if any(budgets[unit] != 0 and costs[unit] > budgets[unit] + 1e-12 for unit in costs):
            rejected['unit-budget'] += 1
            continue
        schedule = estimate_schedule(plan,
            {node.node_id: profile.latency_ms for node, profile in zip(plan.nodes, combination)},
            {node.node_id: providers[profile.model_id] for node, profile in zip(plan.nodes, combination)}, policy)
        latency = schedule['makespan_ms']
        if latency_max_ms is not None and latency > latency_max_ms:
            rejected['latency'] += 1
            continue
        feasible_rows.append((combination, costs, latency, quality, schedule))
    # 现金模型必须存在于一条预算和时延都可行的完整分配中，才可作为 AFP
    # 的质量参照。不可派发的现金模型不能排除唯一可行的订阅路线。
    cash_reference = {node.node_id: max((combination[index].quality
        for combination, *_ in feasible_rows
        if model_units[combination[index].model_id] == 'CNY'), default=None)
        for index, node in enumerate(plan.nodes)}
    excluded_afp_quality = {node.node_id: sorted({profile.model_id
        for profile in options[index]
        if model_units[profile.model_id] == 'AFP' and cash_reference[node.node_id] is not None
        and profile.quality < cash_reference[node.node_id]})
        for index, node in enumerate(plan.nodes)}
    feasible = 0
    for combination, costs, latency, quality, schedule in feasible_rows:
        if any(profile.model_id in excluded_afp_quality[node.node_id]
               for node, profile in zip(plan.nodes, combination)):
            rejected['afp-below-feasible-cash-quality'] += 1
            continue
        feasible += 1
        key = (costs['CNY'], costs['AFP'], latency, -quality,
               tuple(profile.model_id for profile in combination))
        if best_key is None or key < best_key:
            best_key = key
            best = (combination, costs, latency, quality, schedule)
    result = {'policy_version': 'automatic-mixed-assignment-v1',
              'status': 'selected' if best else 'no-feasible-route',
              'quality_basis': 'configured-profile-prior',
              'quality_noninferiority_verified': False,
              'quality_reference': quality_reference,
              'excluded_afp_below_cash_quality_prior': excluded_afp_quality,
              'budgets_by_unit': dict(budgets),
              'combinations': combinations, 'feasible_combinations': feasible,
              'rejected_combinations': rejected, 'assignments': {}, 'prediction': None}
    if best is not None:
        combination, costs, latency, quality, schedule = best
        result['assignments'] = {node.node_id: profile.model_id
            for node, profile in zip(plan.nodes, combination)}
        result['prediction'] = {'costs_by_unit': costs, 'scheduled_latency_ms': latency,
                                'minimum_node_quality_proxy': quality, 'schedule': schedule}
    return result
