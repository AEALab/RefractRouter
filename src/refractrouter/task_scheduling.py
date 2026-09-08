"""共享的有界列表调度规则：用于离线预测与真实节点调度。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
import math


@dataclass(frozen=True)
class ExecutionPolicy:
    max_concurrency: int = 1
    provider_concurrency: dict[str, int] = field(default_factory=dict)
    provider_min_interval_ms: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if type(self.max_concurrency) is not int or not 1 <= self.max_concurrency <= 8:
            raise ValueError('maxConcurrency must be an integer in 1..8')
        for values, name, low, high in (
            (self.provider_concurrency, 'providerConcurrency', 1, 8),
            (self.provider_min_interval_ms, 'providerMinIntervalMs', 0, 60000),
        ):
            if not isinstance(values, dict) or len(values) > 16:
                raise ValueError(f'invalid {name}')
            for key, value in values.items():
                if not isinstance(key, str) or not key.strip() or len(key) > 100 or type(value) is not int or not low <= value <= high:
                    raise ValueError(f'invalid {name}')

    @classmethod
    def from_request(cls, request):
        return cls(request.get('maxConcurrency', 1), request.get('providerConcurrency', {}),
                   request.get('providerMinIntervalMs', {}))

    def limit(self, provider):
        return min(self.max_concurrency, self.provider_concurrency.get(provider, self.max_concurrency))

    def interval(self, provider):
        return self.provider_min_interval_ms.get(provider, 0)

    def to_dict(self):
        return {'policy_version': 'topological-list-v1', **asdict(self)}


def available(node_id, provider, active, last_start, now, policy):
    """active 映射节点到 provider；并发上限与启动间隔同时满足才允许派发。"""
    return (len(active) < policy.max_concurrency
            and sum(p == provider for p in active.values()) < policy.limit(provider)
            and now >= last_start.get(provider, -math.inf) + policy.interval(provider))


def estimate_schedule(plan, durations, providers, policy):
    """无调度/网络开销的列表调度预测，不是任务 p95 或 SLA。"""
    order = plan.order()
    parents = {n.node_id: n.parents for n in plan.nodes}
    if set(durations) != set(order) or set(providers) != set(order):
        raise ValueError('schedule requires every node duration and provider')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in durations.values()):
        raise ValueError('invalid schedule duration')
    pending, completed, running, starts, ends = set(order), set(), {}, {}, {}
    last_start, now = {}, 0.0
    while pending or running:
        for nid in list(running):
            if ends[nid] <= now:
                completed.add(nid)
                del running[nid]
        ready = [nid for nid in order if nid in pending and set(parents[nid]) <= completed]
        for nid in ready:
            provider = providers[nid]
            if available(nid, provider, running, last_start, now, policy):
                starts[nid], ends[nid] = now, now + durations[nid]
                running[nid] = provider
                last_start[provider] = now
                pending.remove(nid)
        times = [ends[nid] for nid in running]
        if len(running) < policy.max_concurrency:
            for nid in ready:
                provider = providers[nid]
                if nid in pending and sum(p == provider for p in running.values()) < policy.limit(provider):
                    times.append(max(now, last_start.get(provider, -math.inf) + policy.interval(provider)))
        if pending or running:
            if not times:
                raise ValueError('schedule cannot make progress')
            now = min(times)
    return {'makespan_ms': max(ends.values()), 'nodes': {
        nid: {'start_ms': starts[nid], 'end_ms': ends[nid],
              'queue_ms': starts[nid] - max((ends[p] for p in parents[nid]), default=0)} for nid in order}}
