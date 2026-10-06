"""金额配置的显式迁移；只返回草稿，不保存宿主配置或推断模型等价。"""
from copy import deepcopy

from .planning_config import compile_config, number, SCHEMA_V6, SCHEMA_V7


def migrate_planning(raw, bindings, *, cny_budget=None, reference_budget=None):
    """bindings 按原角色模型 ID 给出完整目标配置，必须来自已核对的实际路线。"""
    if not isinstance(raw, dict) or raw.get('schemaVersion') not in (SCHEMA_V6, SCHEMA_V7):
        raise ValueError('请先完成旧策略设置升级，再迁移金额预算，避免改变审核行为')
    if not isinstance(bindings, dict):
        raise ValueError('需要明确的目标模型绑定')
    declared = {model['id'] for model in raw.get('models', [])}
    if set(bindings) - declared:
        raise ValueError('目标绑定包含不存在的角色模型 ID')
    if cny_budget is None:
        cny_budget = raw.get('maxProductionCostByUnit', {}).get('CNY')
        if cny_budget is None and raw.get('billingUnit') == 'CNY':
            cny_budget = raw.get('maxProductionCost')
    if cny_budget is None:
        raise ValueError('需要明确 CNY 预算；不会把 AFP 额度转换成现金')
    number(cny_budget, 'CNY 生产预算')
    draft = deepcopy(raw)
    changed = set()
    models = []
    for original in raw.get('models', []):
        identity = original['id']
        target = deepcopy(bindings.get(identity, original))
        if identity not in bindings and original.get('billingUnit', raw.get('billingUnit')) == 'AFP':
            if original.get('provider') not in ('ark', 'ark-plan'):
                raise ValueError(f'{identity} 需要明确订阅执行渠道')
            from .subscription_reference import planning_binding
            target = planning_binding(original)
        if not isinstance(target, dict) or target.get('id', identity) != identity:
            raise ValueError('迁移必须保留角色模型 ID')
        target['id'] = identity
        if target.get('billingUnit', raw.get('billingUnit')) not in ('CNY', 'USD'):
            raise ValueError(f'{identity} 尚未绑定现金路线')
        if (target.get('billingMode') != 'subscription'
                and original.get('billingUnit', raw.get('billingUnit')) == 'AFP'
                and (target.get('provider'), target.get('model')) ==
                    (original.get('provider'), original.get('model'))):
            raise ValueError(f'{identity} 不能只把 AFP 标签改成现金；需明确绑定新的实际路线')
        if (target.get('provider'), target.get('model')) != (original.get('provider'), original.get('model')):
            changed.add(identity)
            # 完整目标配置不继承原 provider 的信任和能力验收。
            if 'deployment' not in bindings[identity]:
                raise ValueError(f'{identity} 新路线需要明确数据域，不能继承旧提供方授权')
        target['billingUnit'] = target.get('billingUnit', raw.get('billingUnit'))
        models.append(target)
    for index, media in enumerate(raw.get('mediaRoutes', [])):
        if media.get('billingUnit', raw.get('billingUnit')) not in ('CNY', 'USD'):
            from .subscription_reference import media_binding
            draft['mediaRoutes'][index] = media_binding(media)
    draft.update(schemaVersion=SCHEMA_V7, billingUnit='CNY', maxProductionCost=cny_budget,
                 maxProductionCostByUnit={'CNY': cny_budget}, models=models)
    draft['compatiblePairs'] = [pair for pair in draft.get('compatiblePairs', [])
                                if not changed.intersection(pair)]
    if reference_budget is not None:
        draft['maxReferenceCost'] = number(reference_budget, '参考成本上限')
    compiled = compile_config(draft)
    if compiled['model_issues']:
        raise ValueError('目标现金路线配置未完成：' + str(compiled['model_issues']))
    return {'configuration': draft, 'modelCalls': 0, 'configurationWritten': False,
            'changedModelIds': sorted(changed),
            'historyCompatibilityRequiresValidation': sorted(changed),
            'requiresHostPreflight': True,
            'budgetSource': 'explicit-cny-only',
            'legacyHistoryPreserved': True}


def migrate_pool(raw, catalog, *, production_cash, evaluation_cash):
    """自动目录显式迁移，保留模型、权限和职责引用，原预算不换算。"""
    from .dsh_model_pool import compile_dsh_model_pool
    from .subscription_reference import reference_for, ARK_ENDPOINT
    if not isinstance(raw, dict) or raw.get('schemaVersion') not in (
            'refractagent-dsh-model-pool-v3', 'refractagent-dsh-model-pool-v4', 'refractagent-dsh-model-pool-v5'):
        raise ValueError('请先完成实际模型目录升级，再迁移金额计价')
    draft = deepcopy(raw)
    draft.update(schemaVersion='refractagent-dsh-model-pool-v5', billingUnit='CNY',
                 cashLimits={'production': number(production_cash, '生产现金上限'),
                             'evaluation': number(evaluation_cash, '评价现金上限')})
    # 显式迁移取消旧 AFP 系数筛选，不将其解释成金额或质量约束。
    removed_constraints = []
    if 'maxAfpCoefficient' in draft.get('objective', {}):
        draft['objective'].pop('maxAfpCoefficient')
        removed_constraints.append('objective.maxAfpCoefficient')
    hosts = {(row['provider'], row['model']): row for row in catalog.get('routes', [])}
    for route in draft.get('routes', []):
        host = hosts.get((route['provider'], route['model']))
        if host is None:
            if route.get('enabled', True):
                raise ValueError('宿主目录缺少当前启用模型')
            continue
        if (host.get('providerBaseURL') or '').rstrip('/') == ARK_ENDPOINT:
            try:
                route.update(billingMode='subscription', referencePricing=reference_for(route['model']))
            except ValueError:
                if route.get('enabled', True):
                    raise
                # 未启用的历史型号保持配置，启用前必须补齐公开价。
        else:
            route['billingMode'] = 'metered'
    compiled, evidence = compile_dsh_model_pool(draft, catalog)
    return {'configuration': draft, 'compiled': compiled, 'evidence': evidence,
            'modelCalls': 0, 'configurationWritten': False, 'legacyHistoryPreserved': True,
            'removedLegacyConstraints': removed_constraints}
