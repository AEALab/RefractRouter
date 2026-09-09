"""三组恢复对照：相同初始模型、共享累计账本和截止，保留失败及未执行样本。"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import time

from .dag_study import implementation_fingerprint
from .dag_study_execution import StudyDemoClient, write_json
from .dag_batch_study import recoverable as settled_sample_failure
from .node_recovery import NodeRecovery, validate_fallback_limit
from .node_routing import load_profile, number, route_nodes
from .responses_api import output_token_limit
from .task_budget import TaskCallBudget
from .task_evaluation import evaluate_text
from .task_execution import RecoveryEligibleFailure, execute_nodes
from .task_plan import validate_plan
from .task_scheduling import ExecutionPolicy, estimate_schedule

ARMS = ('no-recovery', 'local-node-switch', 'whole-dag-switch')


class EvidenceFailure(RuntimeError):
    """证据异常必须停止整批，不得与可隔离的结果异常混淆。"""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class OrderedRecovery(NodeRecovery):
    """候选次序冻结；仍由已有核心检查质量、容量、剩余预算与调度。"""

    def __init__(self, *args, model_order, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_order = model_order

    def choose(self, nid, assignments, attempted, *args, **kwargs):
        for mid in self.model_order:
            if mid not in attempted:
                choice = super().choose(nid, assignments,
                    set(self.candidates) - {mid}, *args, **kwargs)
                if choice is not None:
                    return choice
        return None


def resume_settled(budget, error, *, next_sample=False):
    """仅实验驱动器可在调度器完成结算后恢复派发；不重置费用、次数或期限。"""
    isolated = next_sample and (settled_sample_failure(error, budget) or (
        isinstance(error, ValueError) and str(error).startswith('production-budget-exhausted before ')))
    if not isinstance(error, RecoveryEligibleFailure) and not isolated:
        raise ValueError('cannot resume an unclassified failure')
    with budget.lock:
        if any(r['status'] not in ('billed', 'cancelled-before-dispatch')
               or r['charged'] > r['reserved'] + 1e-8 for r in budget.records):
            raise ValueError('cannot resume unsettled or exceeded ledger')
        if any(budget.charged[k] > budget.limits[k] for k in budget.limits):
            raise ValueError('cannot resume exhausted ledger')
        budget.stopped = False


def preflight(protocol, manifest, profile):
    if protocol.get('schema_version') != 'recovery-study-v1':
        raise ValueError('unsupported recovery protocol')
    if protocol.get('implementation_sha256') != implementation_fingerprint():
        raise ValueError('frozen implementation changed')
    if protocol.get('manifest_sha256') != digest(asdict(manifest)) or protocol.get('profile_sha256') != digest(profile):
        raise ValueError('frozen inputs changed')
    if protocol.get('failure_policy') != 'settled-output-only-stop-on-infrastructure':
        raise ValueError('unsupported failure policy')
    limit = validate_fallback_limit(protocol['max_switches'])
    models = {m.model_id: m for m in manifest.candidates}
    order = protocol['model_order']
    if (not isinstance(order, list) or len(order) != limit + 1 or len(set(order)) != len(order)
            or not set(order) <= set(models)):
        raise ValueError('model order must contain initial model and bounded replacements')
    if manifest.judge.api_model in {models[m].api_model for m in order}:
        raise ValueError('judge must be independent')
    profiles = load_profile(profile, manifest)
    policy = ExecutionPolicy.from_request(protocol['execution_policy'])
    for key in ('costMax', 'latencyMaxMs'):
        number(protocol['constraints'][key], key, positive=True)
    number(protocol['constraints']['qualityMin'], 'qualityMin', maximum=100)
    repeats = protocol['repeats']
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError('invalid repeats')
    if type(protocol['order_seed']) is not int:
        raise ValueError('invalid order seed')
    cap = protocol['judge_input_cap']
    if type(cap) is not int or not 256 <= cap <= 262144:
        raise ValueError('invalid judge input cap')
    def ceiling(model, input_cap):
        output = output_token_limit(model)
        if input_cap + output > model.context_window:
            raise ValueError('input/output envelope exceeds context')
        return input_cap / 1000 * model.input_cost_per_1k + output / 1000 * model.output_cost_per_1k
    ids, runs = set(), []
    for task in protocol['tasks']:
        tid = task['task_id']
        if not isinstance(tid, str) or not tid or tid in ids or not task.get('task', '').strip():
            raise ValueError('invalid task')
        ids.add(tid)
        if tid in set(profile.get('calibration_task_ids', [])) | set(profile.get('held_out_task_ids', [])):
            raise ValueError('task overlaps previously exposed calibration or test IDs')
        plan = validate_plan(task['plan'], require_v2=True)
        caps = [plan.contracts[n.node_id]['capability']['input_budget_tokens'] for n in plan.nodes]
        route = route_nodes(plan, profiles, method='A', quality_min=protocol['constraints']['qualityMin'],
            cost_max=protocol['constraints']['costMax'], latency_max_ms=protocol['constraints']['latencyMaxMs'],
            eligible_models={n.node_id: order[:1] for n in plan.nodes}, execution_policy=policy,
            model_providers={m: c.provider for m, c in models.items()}, assignment_mode='single-model')
        if route['status'] != 'selected':
            raise ValueError('initial frozen assignment is infeasible')
        for arm in ARMS:
            selected = order[:1] if arm == ARMS[0] else order
            production = sum(ceiling(models[mid], c) for c in caps for mid in selected)
            for repeat in range(1, repeats + 1):
                runs.append({'task_id': tid, 'repeat': repeat, 'arm': arm,
                    'production_ceiling': production, 'evaluation_ceiling': ceiling(manifest.judge, cap),
                    'maximum_calls': len(caps) * len(selected) + 1})
    if not ids:
        raise ValueError('empty tasks')
    return {'schema_version': 'recovery-preflight-v1', 'real_model_calls': 0,
        'protocol_sha256': digest(protocol), 'runs': runs,
        'maximum_calls': sum(r['maximum_calls'] for r in runs),
        'budget': {'billing_unit': manifest.billing_unit,
            **{k: sum(r[k + '_ceiling'] for r in runs) for k in ('production', 'evaluation')}},
        'limitations': ['调用包络不等于执行授权；预留失败也计入调用次数上限。',
            '两恢复组均按每节点最多遍历全部冻结模型估算；每个样本最多一次独立最终评审。']}


def run_trial(task, arm, protocol, manifest, profiles, budget, *, persist=lambda: None,
              cancel_event=None, dispatch_history=None, result_sink=None):
    if arm not in ARMS:
        raise ValueError('unknown recovery arm')
    plan = validate_plan(task['plan'], require_v2=True)
    policy = ExecutionPolicy.from_request(protocol['execution_policy'])
    candidates = {m.model_id: m for m in manifest.candidates}
    order = protocol['model_order']
    limits = protocol['constraints']
    start = time.monotonic()
    deadline = start + limits['latencyMaxMs'] / 1000
    before, previous = budget.snapshot()
    cap = min(budget.limits['production'], before['production'] + limits['costMax'])
    history = dispatch_history if dispatch_history is not None else {}
    result = result_sink if result_sink is not None else {}
    result.update(arm=arm, status='started', attempts=[], evaluation=None,
                  final_output='', recovery_triggers=0, fatal=False)
    eligible = {n.node_id: [mid for mid in order if
        plan.contracts[n.node_id]['capability']['input_budget_tokens']
        + output_token_limit(candidates[mid]) <= candidates[mid].context_window] for n in plan.nodes}
    def checkpoint():
        _, records = budget.snapshot()
        result['calls'] = records[len(previous):]
        result['cost'] = sum(r['charged'] for r in result['calls'])
        result['wall_time_ms'] = (time.monotonic() - start) * 1000
        try:
            persist()
        except Exception as exc:
            budget.stop()
            raise EvidenceFailure('study evidence checkpoint failed') from exc
    try:
        attempts = order if arm == ARMS[2] else order[:1]
        for index, mid in enumerate(attempts):
            if cancel_event is not None and cancel_event.is_set():
                result['status'] = 'cancelled'
                break
            remaining = max(0, (deadline - time.monotonic()) * 1000)
            route = route_nodes(plan, profiles, method='A', quality_min=limits['qualityMin'],
                cost_max=max(0, cap - budget.snapshot()[0]['production']), latency_max_ms=remaining,
                eligible_models={n.node_id: [mid] if mid in eligible[n.node_id] else [] for n in plan.nodes},
                execution_policy=policy, model_providers={m: c.provider for m, c in candidates.items()},
                assignment_mode='single-model')
            if route['status'] != 'selected':
                result['status'] = 'no-feasible-route'
                break
            # 下一整图须把上一尝试的提供方派发间隔计入剩余时限。
            now = time.monotonic()
            schedule = estimate_schedule(plan, {n: p['latency_ms'] for n, p in route['nodes'].items()},
                {n: candidates[mid].provider for n in route['assignments']}, policy,
                last_start={p: (t - now) * 1000 for p, t in history.items()})
            if schedule['makespan_ms'] > (deadline - now) * 1000:
                result['status'] = 'deadline-admission-failed'
                break
            attempt = {'nodes': [], 'assignments': dict(route['assignments']), 'routing': route,
                       'status': 'started'}
            result['attempts'].append(attempt)
            recovery = None
            if arm == ARMS[1]:
                recovery = OrderedRecovery(plan, profiles, candidates,
                    {**route, 'eligible_models': eligible}, policy,
                    max_fallbacks=protocol['max_switches'], model_order=order)
            try:
                result['final_output'] = execute_nodes(plan, task['task'], route['assignments'],
                    candidates, budget, policy, attempt, checkpoint, started=start, deadline=deadline,
                    cancel_event=cancel_event, label_prefix=f"{len(previous)}:dag-{index + 1}:",
                    recovery=recovery, production_cap=cap, classify_failure=True, dispatch_history=history)
                attempt['status'] = 'completed'
            except RecoveryEligibleFailure as exc:
                attempt.update(status='invalid-output', error=str(exc))
                resume_settled(budget, exc)
                result['status'] = 'failed'
                if time.monotonic() >= deadline:
                    break
                continue
            if cancel_event is not None and cancel_event.is_set():
                result['status'] = 'cancelled'
                break
            result['evaluation'] = evaluate_text(budget, manifest.judge, task['task'], result['final_output'],
                criteria=plan.acceptance_criteria, label=f'{len(previous)}:final-judge', deadline=deadline,
                input_cap=protocol['judge_input_cap'])
            judged = result['evaluation']
            result['status'] = ('completed' if judged['passed'] and judged['score'] >= limits['qualityMin']
                                else 'quality-failed')
            break
    except Exception as exc:
        budget.stop()
        result.update(status='failed', fatal=True, error=type(exc).__name__)
        try:
            # 只结束当前样本；绝不因评审、容量、预算或截止失败进入同任务换模型循环。
            resume_settled(budget, exc, next_sample=True)
            result['fatal'] = False
        except ValueError:
            pass
    finally:
        result['recovery_triggers'] = sum(
            r['status'] == 'invalid-output' or r.get('error_type') == 'InvalidModelOutput'
            for a in result['attempts'] for r in a.get('node_attempts', a['nodes']))
        checkpoint()
    return result


def summarize(runs, *, simulated, seed=38):
    """交付分母包含未执行样本；质量、成本、时延固定为相同已评分配对集合。"""
    groups = {arm: [r for r in runs if r['arm'] == arm] for arm in ARMS}
    summary = {'simulated': simulated, 'arms': {}, 'comparisons': []}
    for arm, rows in groups.items():
        delivered = sum(r['status'] == 'completed' for r in rows)
        calls = [c for r in rows for c in r.get('calls', [])]
        summary['arms'][arm] = {'planned': len(rows), 'delivered': delivered,
            'delivery_rate': delivered / len(rows) if rows else None,
            'not_run': sum(r['status'] == 'not-run' for r in rows),
            'total_cost': sum(r.get('cost', 0) for r in rows),
            'billed_cost': sum(c['charged'] for c in calls if c['status'] == 'billed'),
            'unknown_usage_reserved': sum(c['charged'] for c in calls if c['status'] == 'unknown-usage'),
            'recovery_triggers': sum(r.get('recovery_triggers', 0) for r in rows)}
    for baseline in (ARMS[0], ARMS[2]):
        baseline_rows = {(r['task_id'], r['repeat']): r for r in groups[baseline]}
        pairs = []
        for a in groups[ARMS[1]]:
            b = baseline_rows[(a['task_id'], a['repeat'])]
            if a.get('evaluation') is None or b.get('evaluation') is None:
                continue
            pairs.append({'task_id': a['task_id'], 'repeat': a['repeat'],
                'quality_delta': a['evaluation']['score'] - b['evaluation']['score'],
                'cost_delta': a['cost'] - b['cost'], 'latency_delta_ms': a['wall_time_ms'] - b['wall_time_ms']})
        metrics = ('quality_delta', 'cost_delta', 'latency_delta_ms')
        tasks = sorted({p['task_id'] for p in pairs})
        means = {k: statistics.mean(p[k] for p in pairs) for k in metrics} if pairs else None
        intervals = None
        if len(tasks) >= 2:
            rng = random.Random(seed)
            boots = []
            for _ in range(2000):
                sample = [p for tid in rng.choices(tasks, k=len(tasks)) for p in pairs if p['task_id'] == tid]
                boots.append({k: statistics.mean(p[k] for p in sample) for k in metrics})
            intervals = {k: [sorted(b[k] for b in boots)[50], sorted(b[k] for b in boots)[1949]] for k in metrics}
        summary['comparisons'].append({'candidate': ARMS[1], 'baseline': baseline, 'pairs': pairs,
            'excluded_pairs': len(groups[ARMS[1]]) - len(pairs), 'independent_tasks': len(tasks),
            'mean': means, 'task_bootstrap_interval_95': intervals})
    summary['limitations'] = ['模拟不支持真实收益结论；无真实恢复触发时不能估计恢复收益。',
        '已评分配对集合排除了失败与缺失，可能存在选择偏差；须同时查看全部计划样本交付率及费用。',
        '按独立任务聚类的区间仅作探索描述；少于两个已配对任务不计算区间。',
        'total_cost 为累计账本值，未知用量保留预留；未执行样本没有实际观测，不能把部分采集总费用解释为完整运行成本。']
    return summary


def run_study(protocol, manifest, profile, output_dir, *, simulated=True, client=None):
    preview = preflight(protocol, manifest, profile)
    if not simulated:
        if profile['kind'] != 'empirical' or client is None or getattr(client, 'max_retries', None) != 0:
            raise ValueError('live study requires empirical profile and explicit zero-retry client')
        if manifest.billing_unit != 'AFP' or any(m.provider != 'ark-plan'
                or not m.base_url.rstrip('/').endswith('/api/plan/v3') for m in manifest.models):
            raise ValueError('live study requires Ark Agent Plan endpoint')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    for name, value in (('protocol', protocol), ('manifest', asdict(manifest)), ('profile', profile), ('preflight', preview)):
        write_json(out / f'{name}.json', value)
    budget = TaskCallBudget(client or StudyDemoClient(), preview['budget']['production'],
        preview['budget']['evaluation'], max_calls=preview['maximum_calls'], capture_payload=True)
    rows = [{**r, 'status': 'not-run'} for r in preview['runs']]
    random.Random(protocol['order_seed']).shuffle(rows)
    result = {'simulated': simulated, 'status': 'started', 'runs': rows}
    def persist():
        result['charged'], result['calls'] = budget.snapshot()
        try:
            write_json(out / 'result.json', result)
        except Exception as exc:
            budget.stop()
            raise EvidenceFailure('study evidence checkpoint failed') from exc
    budget.on_reserve = lambda reservation: persist()
    def response(row, value):
        write_json(out / ('response-' + hashlib.sha256(row['label'].encode()).hexdigest() + '.json'), asdict(value))
    budget.on_response = response
    tasks = {t['task_id']: t for t in protocol['tasks']}
    history = {}
    for row in rows:
        trial = run_trial(tasks[row['task_id']], row['arm'], protocol, manifest,
            load_profile(profile, manifest), budget, persist=persist, dispatch_history=history,
            result_sink=row)
        persist()
        if trial['fatal']:
            break
    result['status'] = 'stopped' if any(r.get('fatal') for r in rows) else 'completed'
    result['summary'] = summarize(rows, simulated=simulated)
    persist()
    write_json(out / 'artifact-index.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.iterdir()) if p.is_file()})
    return result
