"""就绪队列排空在途调用后，以有界子图替换困难节点，保留已完成状态。"""
from copy import deepcopy
from dataclasses import replace
from concurrent.futures import CancelledError
import hashlib
import json
import time

from .compact_planning import generate_compact
from .configured_routing import configured_profile
from .model_selection import Weights
from .node_routing import load_profile, route_nodes
from .planning_support import compile_generated_capacity, admission_diagnostics
from .task_plan import MAX_NODES, validate_plan
from .responses_api import output_token_limit


def graft(plan, nid, subplan):
    """原节点保留 ID 和输出契约，作为子图的汇总出口；原下游无需改接口。"""
    original = next(n for n in plan.to_dict()['nodes'] if n['node_id'] == nid)
    prefix = nid if len(nid) <= 48 else 'node_' + hashlib.sha256(nid.encode()).hexdigest()[:16]
    mapping = {n.node_id: nid if n.node_id == subplan.final_node_id else f'{prefix}_split_{i}'
               for i, n in enumerate(subplan.nodes)}
    if len(plan.nodes) + len(subplan.nodes) - 1 > MAX_NODES:
        raise ValueError('dynamic-node-limit-exhausted')
    existing = {n.node_id for n in plan.nodes}
    if any(key != nid and key in existing for key in mapping.values()):
        raise ValueError('dynamic-node-id-collision')
    rows = []
    for row in subplan.to_dict()['nodes']:
        is_join = row['node_id'] == subplan.final_node_id
        parents = [mapping[p] for p in row['parents']]
        inputs = {mapping[p]: value for p, value in row['contract']['inputs'].items()}
        row['node_id'] = mapping[row['node_id']]
        row['parents'] = [*original['parents'], *parents]
        row['contract']['inputs'] = {**deepcopy(original['contract']['inputs']), **inputs}
        if is_join:
            # 汇总必须履行困难节点的全部原职责，不能由再拆规划器缩减原接口与验收条件。
            row['node_type'] = original['node_type']
            row['prompt_template'] = original['prompt_template'] + '\n使用新增分支的结果完成原职责，逐项核对原始事实和矛盾。'
            row['contract'] = {**deepcopy(original['contract']), 'inputs': row['contract']['inputs']}
        else:
            row['contract']['covers'] = []
        rows.append(row)
    raw = plan.to_dict()
    raw['nodes'] = [n for n in raw['nodes'] if n['node_id'] != nid] + rows
    return validate_plan(raw, required_criteria=plan.acceptance_criteria), set(mapping.values())


class DynamicDecomposition:
    def __init__(self, *, request, manifest, configuration, profiles, planner, budget, policy,
                 task, result, persist, deadline, cancel_event=None):
        self.request, self.manifest, self.configuration = request, manifest, configuration
        self.profiles, self.planner, self.budget, self.policy = profiles, planner, budget, policy
        self.task, self.result, self.persist, self.deadline = task, result, persist, deadline
        self.cancel_event, self.protected = cancel_event, set()
        self.candidates = {m.model_id: m for m in manifest.candidates}
        self.limit = request['maxDynamicSplits']
        result['dynamic_decomposition'] = {'policy_version': 'drain-and-graft-v1',
            'max_splits': self.limit, 'max_total_nodes': MAX_NODES, 'max_subplan_nodes': 3,
            'max_depth': 1, 'events': []}

    def eligible(self, nid, plan):
        return (nid not in self.protected and len(plan.nodes) < MAX_NODES
            and len(self.result['dynamic_decomposition']['events']) < self.limit
            and not self.budget.stopped)

    def expand(self, plan, nid, context, completed, reason, dispatch_history):
        if not self.eligible(nid, plan):
            raise ValueError('dynamic-split-limit-exhausted')
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise CancelledError('task-cancelled-before-split')
        if time.monotonic() >= self.deadline:
            raise ValueError('task-deadline-exhausted')
        _, calls = self.budget.snapshot()
        if any(c['status'] not in {'billed', 'cancelled-before-dispatch'} for c in calls):
            raise ValueError('dynamic-requires-settled-calls')
        node = next(n for n in plan.nodes if n.node_id == nid)
        contract = plan.contracts[nid]
        upstream = {p: {key: context[p][key] for key in info['fields']} for p, info in contract['inputs'].items()}
        event = {'node_id': nid, 'reason': reason[:1000], 'status': 'planning',
            'completed_nodes': sorted(completed), 'upstream': deepcopy(upstream),
            'upstream_sha256': hashlib.sha256(json.dumps(upstream, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'previous_plan': plan.to_dict(), 'planner': {}}
        events = self.result['dynamic_decomposition']['events']
        events.append(event)
        self.protected.add(nid)
        self.persist()
        try:
            # 调度器已排空所有在途请求；规划仍遵循同一个 provider 的启动间隔。
            provider = self.planner.provider
            while time.monotonic() < dispatch_history.get(provider, -float('inf')) + self.policy.interval(provider)/1000:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    raise CancelledError('task-cancelled-before-split')
                if time.monotonic() >= self.deadline:
                    raise ValueError('task-deadline-exhausted')
                time.sleep(.01)
            dispatch_history[provider] = time.monotonic()
            subplan = generate_compact(self.budget, self.planner, {
                'task': self.task, 'failed_node': {'instruction': node.prompt_template,
                    'objective': contract['objective'], 'checks': contract['checks']},
                'failure': reason[:1000],
                'instruction': '仅拆当前困难节点为 2..3 个更小职责，最后一项汇总原职责。独立检查尽量并行。不得重复已完成的上游，也不得修改原始要求。'},
                event['planner'], criteria=plan.acceptance_criteria,
                cost_limit=self.request['costMax'], deadline=min(self.deadline,
                    time.monotonic() + self.request.get('plannerTimeoutMs', 12000)/1000),
                persist=self.persist, label=f'dynamic-planner-{len(events)}',
                max_nodes=min(3, MAX_NODES-len(plan.nodes)+1),
                output_cap=max(output_token_limit(m) for m in self.candidates.values()))
            if len(subplan.nodes) < 2:
                raise ValueError('dynamic-plan-did-not-split')
            expanded, affected = graft(plan, nid, subplan)
            profiles = self.profiles
            if self.configuration:
                expanded, estimates = compile_generated_capacity(expanded, self.task, self.candidates,
                    output_constraints=self.request.get('outputConstraints'))
                profile = configured_profile(self.configuration, self.manifest, expanded.to_dict(),
                    input_forecasts={n: row['forecast_input_tokens'] for n,row in estimates.items()})
                profiles = load_profile(profile, self.manifest)
                event['routing_profile'] = profile
            # 路由只估算尚未执行部分；执行计划仍保留所有真实父依赖及冻结上游。
            residual = replace(expanded, nodes=tuple(replace(n, parents=tuple(p for p in n.parents if p not in completed))
                for n in expanded.nodes if n.node_id not in completed))
            admission = admission_diagnostics(expanded, self.task, self.candidates, profiles,
                self.request['qualityMin'], output_constraints=self.request.get('outputConstraints'))
            now = time.monotonic()
            wait_ms = max((dispatch_history.get(m.provider, -float('inf')) + self.policy.interval(m.provider)/1000 - now
                           for m in self.candidates.values()), default=0) * 1000
            routing = route_nodes(residual, profiles, method=self.request['method'],
                quality_min=self.request['qualityMin'], cost_max=min(self.budget.remaining(),
                    max(0, self.request['costMax']-self.budget.snapshot()[0]['production'])),
                latency_max_ms=max(0, (self.deadline-now)*1000-max(0, wait_ms)),
                weights=Weights(**self.request['weights']) if self.request['method']=='B' else None,
                eligible_models={n.node_id:admission[n.node_id]['eligible_models'] for n in residual.nodes},
                execution_policy=self.policy, model_providers={mid:m.provider for mid,m in self.candidates.items()})
            event.update(plan=expanded.to_dict(), admission=admission, routing=routing)
            if routing['status'] != 'selected':
                raise ValueError('dynamic-no-feasible-route')
            # 已完成节点契约/记录保持原样；容量重算只应作用于尚未执行的工作。
            original_contracts = plan.to_dict()
            frozen = {n['node_id']: n for n in original_contracts['nodes'] if n['node_id'] in completed}
            raw = expanded.to_dict()
            raw['nodes'] = [frozen.get(n['node_id'], n) for n in raw['nodes']]
            expanded = validate_plan(raw, required_criteria=plan.acceptance_criteria)
            self.protected.update(affected)
            event.update(status='admitted', plan=expanded.to_dict(), added_nodes=sorted(affected-{nid}))
            return expanded, routing['assignments']
        except Exception as exc:
            event.update(status='failed', error=str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__)
            raise
        finally:
            self.persist()
