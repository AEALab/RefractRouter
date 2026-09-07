"""在完整、可追溯的节点质量证据上，选择质量达标后的最低费用候选。"""
from math import isfinite

from .node_availability import select_available_candidates, evaluation_state

POLICY = 'quality-floor-min-cost-v1'


def select_cost_effective(rows, *, task, model_ids, quality_floor=85.0, max_quality_gap=5.0):
    for value in (quality_floor, max_quality_gap):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= 100:
            raise ValueError('质量阈值与允许差距必须是 0—100 的有限数值')
    decision = select_available_candidates(rows, task=task, model_ids=model_ids)
    decision.update(selection_policy=POLICY, quality_floor=quality_floor,
                    max_quality_gap=max_quality_gap, qualified_by_node={}, thresholds={})
    decision['assignments'] = {}
    if not decision['route_executable']:
        return decision
    for node in task.nodes:
        eligible = [r for r in rows if r['node_id'] == node.node_id and evaluation_state(r) == 'judged']
        best = max(r['evaluation']['final_score'] for r in eligible)
        threshold = max(quality_floor, best - max_quality_gap)
        qualified = [r for r in eligible if r['evaluation']['final_score'] >= threshold]
        decision['thresholds'][node.node_id] = threshold
        decision['qualified_by_node'][node.node_id] = [r['model_id'] for r in qualified]
        if not qualified:
            decision['blocking_reasons'].append(f'quality-floor-unmet:{node.node_id}')
            continue
        selected = min(qualified, key=lambda r: (r['node_result']['cost'],
                        -r['evaluation']['final_score'], r['model_id']))
        decision['assignments'][node.node_id] = selected['model_id']
    if decision['blocking_reasons']:
        decision['route_executable'] = False
        decision['assignments'] = {}
    return decision
