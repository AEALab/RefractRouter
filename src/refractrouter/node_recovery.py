"""节点局部切换：保持原始 profile 标尺，按剩余资源选择未尝试的可行模型。"""
from __future__ import annotations

from .task_scheduling import estimate_schedule


def validate_fallback_limit(value):
    if type(value) is not int or not 0 <= value <= 2:
        raise ValueError('maxNodeFallbacks must be an integer in 0..2')
    return value


class NodeRecovery:
    def __init__(self, plan, profiles, candidates, routing, policy, *, max_fallbacks):
        self.max_fallbacks = validate_fallback_limit(max_fallbacks)
        self.plan, self.candidates, self.routing, self.policy = plan, candidates, routing, policy
        self.profiles = {(n.node_id, p.model_id): p for n in plan.nodes for p in profiles
                         if p.matches(n, plan) and p.model_id in routing['eligible_models'][n.node_id]}

    def choose(self, nid, assignments, attempted, completed, active, *, spent, cost_limit, remaining_ms, input_bound):
        """在途调用的费用已预留，时延按完整预测保守计入；不更换其他节点。"""
        options = []
        for (node_id, mid), candidate in self.profiles.items():
            if node_id != nid or mid in attempted or candidate.quality < self.routing['quality_min_per_node']:
                continue
            model = self.candidates[mid]
            output_bound = min(model.max_output_tokens, 8192)
            reserve = input_bound/1000*model.input_cost_per_1k + output_bound/1000*model.output_cost_per_1k
            if input_bound + output_bound > model.context_window or spent + reserve > cost_limit:
                continue
            chosen = {**assignments, nid: mid}
            rows = {n.node_id: self.profiles[(n.node_id, chosen[n.node_id])] for n in self.plan.nodes}
            future_cost = sum(p.cost for key, p in rows.items() if key not in completed and key not in active)
            if spent + future_cost > cost_limit:
                continue
            duration = {key: 0 if key in completed else p.latency_ms for key, p in rows.items()}
            latency = estimate_schedule(self.plan, duration,
                {key: self.candidates[chosen[key]].provider for key in rows}, self.policy)['makespan_ms']
            if latency > remaining_ms:
                continue
            quality = sum(p.quality for p in rows.values()) / len(rows)
            score = 0
            weights = self.routing['normalized_weights']
            if weights:
                for key, p in rows.items():
                    for metric in ('quality', 'cost'):
                        lo, hi = self.routing['normalization_bounds'][key][metric]
                        utility = 1 if lo == hi else ((p.quality-lo)/(hi-lo) if metric == 'quality'
                                                      else (hi-p.cost)/(hi-lo))
                        score += weights[metric] * utility / len(rows)
                lo, hi = self.routing['scheduled_latency_bounds_ms']
                score += weights['latency'] * (1 if lo == hi else (hi-latency)/(hi-lo))
            tie = (future_cost, -quality, latency, mid)
            options.append(((-score, *tie) if weights else tie, mid))
        return min(options)[1] if options else None
