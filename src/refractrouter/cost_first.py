"""成本优先拆分门：只核验可结构核对的部分，未校准时不给任何收益估计。"""
from .selective_context import HANDOFF_FIELDS

COST_GATE_POLICY = 'cost-first-v1'
STRUCTURED_FIELDS = frozenset(HANDOFF_FIELDS)


def _price(model):
    return model.input_cost_per_1k + model.output_cost_per_1k


def _admissible(contract, model, limit_fn):
    capability = (contract or {}).get('capability')
    if not capability:
        return True
    budget = capability['input_budget_tokens']
    limit = limit_fn(model, budget)
    return budget + limit <= model.context_window and capability['expected_output_tokens'] <= limit


def _cheaper_part(plan, candidates, limit_fn):
    """至少一个非最终节点有比最终节点候选更便宜的可用候选；不代表实际选模结果。"""
    if len(plan.nodes) < 2:
        return False
    prices = {mid: _price(model) for mid, model in candidates.items()}
    usable = {node.node_id: [mid for mid in candidates
                             if _admissible(plan.contracts.get(node.node_id), candidates[mid], limit_fn)]
              for node in plan.nodes}
    final = plan.final_node_id
    if not usable.get(final):
        return False
    ceiling = max(prices[mid] for mid in usable[final])
    return any(min(prices[mid] for mid in usable[nid]) < ceiling
               for nid in usable if nid != final and usable[nid])


def _structured_handoffs(plan):
    """非最终节点用字段交接而不是整篇正文，才算是可复用同图选模的输出压缩。"""
    if len(plan.nodes) < 2:
        return False
    for node in plan.nodes:
        if node.node_id == plan.final_node_id:
            continue
        fields = set(((plan.contracts.get(node.node_id) or {}).get('output') or {}).get('fields', {}))
        if not fields or fields == {'text'} or not fields <= STRUCTURED_FIELDS:
            return False
    return True


def verify_cost_drivers(plan, decision, *, candidates, limit_fn):
    """核验规划器声明的成本驱动；没有可核实驱动时建议先合并为直接回答。"""
    declared = (decision.get('cost_basis') or {}).get('declared_drivers', [])
    checks = {'parallel': bool(plan.diagnostics()['parallel_opportunities']),
              'cheap-model': _cheaper_part(plan, candidates, limit_fn),
              'compact-output': _structured_handoffs(plan)}
    verified = [driver for driver in declared if checks.get(driver)]
    verdict = {'policy': COST_GATE_POLICY, 'structural_checks': checks,
               'declared_drivers': list(declared), 'verified_drivers': verified,
               'unverified_drivers': [driver for driver in declared if driver not in verified],
               'estimate': None, 'calibration': 'unregistered', 'benefit_verified': False,
               'structure_only': True, 'fallback': None, 'fallback_reason': None}
    if declared and not verified:
        verdict['fallback'] = 'merged-to-direct'
        verdict['fallback_reason'] = 'no-verified-cost-driver'
    return verdict
