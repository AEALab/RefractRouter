"""开发阶段的时间、费用与消融审计；未确认质量的点不构成合格前沿。"""
from collections import Counter, defaultdict
import hashlib
import json
import math
import statistics

from .openai_compatible import ChatResponse, model_response_cost
from .quality_statistics import paired_performance
from .quality_study import adjudicate, digest


DIAGNOSTIC_POLICY = {
    'schema_version': 'pareto-development-v1',
    'scope': '六个构造开发任务；仅诊断，不据此推广业务总体或确认可接受质量。',
    'repeats': 2, 'task_count': 6, 'bootstrap_draws': 10000, 'bootstrap_seed': 53053,
    'comparisons': [
        ['shared-single-2', 'shared-single-1', '同图单模型并行'],
        ['shared-heterogeneous-2', 'shared-heterogeneous-1', '同图异构并行'],
        ['shared-heterogeneous-1', 'shared-single-1', '同图串行选模'],
        ['shared-heterogeneous-2', 'shared-single-2', '同图并行选模'],
        ['auto-heterogeneous', 'direct-strong', '自动全链路对直接回答'],
        ['auto-heterogeneous', 'task-selector', '自动全链路对整任务选模']],
    'pairing': '同任务同重复；同图对照另验证计划和串并行模型分配相同。',
    'failure_denominator': '全部预定任务；缺失或未知阻断比较，不只取成功子集。',
    'timing': '任务进入至在线终止的单调时钟；首次进度为CLI服务端发出，不代表客户端看到。',
    'cold': '每任务第一条共享路线紧接计划创建，实测该次计划创建加执行；其他复用为warm。',
    'amortization_reuses': [1, 3, 10, 100],
    'break_even': 'ceil(准备开销/(直接执行-复用执行))，只在完整同任务集合且分母为正时计算。',
    'quality': '格式偏差、规范化后字段事实及真人语义分开；没有真人确认不生成质量合格前沿。',
    'minimum_useful_gain': .10,
    'budget_scan': '固定已运行候选的观测费用/时间约束筛选，不冒充不同预算下重新执行。',
    'budget_points_afp': [.5, 1, 2, 4, 8], 'deadline_points_seconds': [10, 20, 40, 80],
}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _union_length(intervals):
    total, right = 0.0, -math.inf
    for a, b in sorted(intervals):
        total += max(0.0, b - max(a, right)); right = max(right, b)
    return total


def _break_even(setup, direct, reused):
    if direct <= reused: return None
    return max(1, math.ceil(setup / (direct - reused)))


def audit_and_analyze(frozen, result, tasks, references, manifest):
    if frozen.get('diagnostic_policy') != DIAGNOSTIC_POLICY or result['frozen_sha256'] != digest(frozen):
        raise ValueError('diagnostic policy or result binding changed')
    specs = {r['run_id']: r for r in frozen['schedule']}
    if len(specs) != len(frozen['schedule']): raise ValueError('duplicate schedule')
    rows = {}
    for row in result['runs']:
        rid = row['run_id']
        if rid not in specs or rid in rows or any(row[k] != specs[rid][k] for k in ('task_id', 'arm', 'repeat')):
            raise ValueError('unknown, duplicate or mismatched result row')
        rows[rid] = row
    task_map = {t['task_id']: t for t in tasks}
    models = {m.model_id: m for m in manifest.models}
    totals = {'production': 0.0, 'evaluation': 0.0}
    call_groups = defaultdict(list); stages = defaultdict(float); seen = set(); call_table = []
    for call in result['calls']:
        label = call['label']
        if label in seen: raise ValueError('duplicate call label')
        seen.add(label)
        if label.startswith('setup:'):
            tid = label.removeprefix('setup:'); rid = None
        else:
            matches = [key for key in specs if label.startswith(key + ':')]
            if len(matches) != 1: raise ValueError('unattributed model call')
            rid = matches[0]; tid = specs[rid]['task_id']
        payload = json.loads(call['request_messages'][-1]['content'])
        public = payload['task']
        if isinstance(public, str): public = json.loads(public)
        if public != frozen['public_tasks'][tid]: raise ValueError('non-public task reached model')
        expected_category = 'evaluation' if rid is None or call['stage'] == 'research-judge' else 'production'
        if call['category'] != expected_category: raise ValueError('online cost moved offline')
        encoded = json.dumps(call['request_messages'], ensure_ascii=False).encode()
        if call['input_sha256'] != hashlib.sha256(encoded).hexdigest(): raise ValueError('request changed')
        known = call['status'] in ('billed', 'cancelled-before-dispatch')
        if call['status'] == 'billed':
            response = ChatResponse(**call['response'])
            if response.attempts != 1 or not response.usage_available: raise ValueError('retry or unknown response usage')
            expected = model_response_cost(models[call['model_id']], response)
            if (abs(expected - call['charged']) > 1e-8 or expected > call['reserved'] + 1e-8
                    or hashlib.sha256(response.content.encode()).hexdigest() != call['output_sha256']):
                raise ValueError('charge or output mismatch')
        elif call['status'] == 'cancelled-before-dispatch':
            if call['charged'] != 0: raise ValueError('cancelled call charged')
        elif call['status'] != 'unknown-usage':
            raise ValueError('unfinished reservation cannot be treated as a finished batch')
        totals[call['category']] += call['charged']
        if known: stages[call['stage']] += call['charged']
        if call['status'] == 'billed':
            if not (call.get('invocation_started_monotonic', math.inf) <= call['dispatch_monotonic']
                    <= call.get('invocation_finished_monotonic', -math.inf)):
                raise ValueError('call timing incomplete or reversed')
        call_groups[rid].append(call)
        call_table.append({'run_id': rid, 'task_id': tid, 'label': label, 'model': call['model_id'],
            'stage': call['stage'], 'category': call['category'], 'status': call['status'],
            'actual_afp': call['charged'] if known else None, 'reserved_afp': call['reserved'],
            'started_monotonic': call.get('dispatch_monotonic'),
            'finished_monotonic': call.get('invocation_finished_monotonic'),
            'input_tokens': call.get('input_tokens'), 'output_tokens': call.get('output_tokens')})
    if any(abs(totals[k] - result['charged_or_reserved'][k]) > 1e-8 for k in totals):
        raise ValueError('batch ledger mismatch')
    actual = None if any(c['status'] == 'unknown-usage' for c in result['calls']) else sum(totals.values())
    if not result['simulated'] and ((actual is None) != (result['actual_afp'] is None)
            or actual is not None and abs(actual - result['actual_afp']) > 1e-8):
        raise ValueError('actual AFP total mismatch')
    flat = []; shared = defaultdict(list)
    for rid, spec in specs.items():
        row = rows.get(rid); calls = call_groups[rid]
        entry = {**spec, 'status': 'missing', 'quality_status': 'pending', 'field_status': 'unverified',
                 'encoding_status': 'unverified', 'online_afp': None, 'offline_afp': None,
                 'online_ms': None, 'cold_plan_and_execution_ms': None}
        if row is not None:
            online = row.get('online_finished_ms')
            known = all(c['status'] in ('billed', 'cancelled-before-dispatch') for c in calls)
            entry.update(status=row['status'], online_afp=sum(c['charged'] for c in calls if c['category'] == 'production') if known else None,
                         offline_afp=sum(c['charged'] for c in calls if c['category'] == 'evaluation') if known else None,
                         online_ms=online if _finite(online) else None,
                         first_progress_emitted_ms=row.get('first_progress_emitted_ms'),
                         plan_ready_ms=row.get('plan_ready_ms'), final_text_ready_ms=row.get('final_text_ready_ms'),
                         cold_plan_and_execution_ms=row.get('cold_plan_and_execution_ms'))
            if known and 'online_afp' in row and abs(entry['online_afp'] - row['online_afp']) > 1e-8:
                raise ValueError('trial ledger mismatch')
            if 'output' in row:
                decision = adjudicate(task_map[spec['task_id']], references[spec['task_id']], row['output'])
                checks = decision['deterministic']
                entry.update(field_status=checks.get('fact_status', checks['status']),
                    encoding_status=checks.get('encoding', {}).get('status', 'legacy'),
                    quality_status=decision['status'] if row['status'] == 'delivered-unconfirmed' else 'fail')
            elif row['status'] in ('failed', 'withheld', 'deadline-failed'):
                entry['quality_status'] = 'fail'
            if _finite(online):
                ready, text = row.get('plan_ready_ms'), row.get('final_text_ready_ms')
                if not (0 <= (ready if ready is not None else online) <= (text if text is not None else online) <= online):
                    raise ValueError('stage time ordering changed')
                entry['planning_ms'] = ready if ready is not None else online
                entry['execution_ms'] = ((text if text is not None else online) - ready) if ready is not None else 0
                entry['delivery_ms'] = online - text if text is not None else 0
                events = {e['name']: e['elapsed_ms'] for e in row.get('events', [])}
                if (events.get('task-entered') != 0 or events.get('online-finished') != online
                        or ready is not None and events.get('plan-ready') != ready
                        or text is not None and events.get('final-text-ready') != text):
                    raise ValueError('missing or mismatched timing event')
                origin = row['entered_monotonic']
                for call in calls:
                    if call['status'] != 'billed': continue
                    a = (call['dispatch_monotonic'] - origin) * 1000
                    b = (call['invocation_finished_monotonic'] - origin) * 1000
                    if call['category'] == 'production' and (a < 0 or b > online + .01):
                        raise ValueError('online call excluded from online timing')
                    if call['category'] == 'evaluation' and a < online - .01:
                        raise ValueError('research judge ran before online finish')
            intervals = [(n['start_ms'], n['end_ms']) for n in row.get('nodes', [])
                         if 'start_ms' in n and n['status'] != 'cancelled-before-dispatch']
            if any(b < a for a, b in intervals): raise ValueError('negative node interval')
            resource = sum(b-a for a, b in intervals); union = _union_length(intervals)
            entry.update(node_count=len(row.get('nodes', [])), node_resource_ms=resource,
                         node_active_union_ms=union, node_overlap_ms=max(0, resource-union),
                         peak_nodes=row.get('execution', {}).get('peak_running_nodes'),
                         node_queue_ms=sum(n.get('queue_ms', 0) for n in row.get('nodes', [])))
            if spec['arm'].startswith('shared-') and 'plan_sha256' in row:
                if digest(row['plan']) != row['plan_sha256']: raise ValueError('plan digest changed')
                shared[spec['task_id']].append(row)
        flat.append(entry)
    for group in shared.values():
        if len({r['plan_sha256'] for r in group}) != 1: raise ValueError('same-graph comparison replanned')
        for prefix in ('shared-single-', 'shared-heterogeneous-'):
            if len({digest(r['assignments']) for r in group if r['arm'].startswith(prefix)}) > 1:
                raise ValueError('parallel comparison changed model assignment')
    arms = frozen['selection']['arms']; tids = frozen['selection']['task_ids']; summaries = {}
    for arm in arms:
        group = [r for r in flat if r['arm'] == arm]
        complete = all(_finite(r['online_afp']) and _finite(r['online_ms']) for r in group)
        summaries[arm] = {'planned_runs': len(group), 'quality': dict(Counter(r['quality_status'] for r in group)),
            'fields': dict(Counter(r['field_status'] for r in group)), 'encoding': dict(Counter(r['encoding_status'] for r in group)),
            'complete': complete, 'mean_online_afp': statistics.mean(r['online_afp'] for r in group) if complete else None,
            'mean_online_ms': statistics.mean(r['online_ms'] for r in group) if complete else None,
            'median_online_ms': statistics.median(r['online_ms'] for r in group) if complete else None}
        for phase in ('planning_ms', 'execution_ms', 'delivery_ms'):
            summaries[arm]['mean_' + phase] = statistics.mean(r[phase] for r in group) if complete else None
    comparisons = []
    for candidate, reference, purpose in DIAGNOSTIC_POLICY['comparisons']:
        if candidate not in arms or reference not in arms: continue
        item = {'candidate': candidate, 'reference': reference, 'purpose': purpose, 'performance': None,
                'quality_conclusion': 'pending-human; no acceptable-quality advantage claimed'}
        if summaries[candidate]['complete'] and summaries[reference]['complete']:
            item['performance'] = {}
            for metric in ('online_afp', 'online_ms'):
                values = {arm: {tid: statistics.mean(r[metric] for r in flat if r['arm'] == arm and r['task_id'] == tid)
                                for tid in tids} for arm in (candidate, reference)}
                item['performance'][metric] = paired_performance(values[candidate], values[reference],
                    {t: task_map[t]['source_family'] for t in tids}, seed=DIAGNOSTIC_POLICY['bootstrap_seed'],
                    draws=DIAGNOSTIC_POLICY['bootstrap_draws'])
        comparisons.append(item)
    setup_rows = {r['task_id']: r for r in result['setups']}
    if len(setup_rows) != len(result['setups']): raise ValueError('duplicated setup')
    for tid, setup in setup_rows.items():
        charges = [c for c in call_groups[None] if c['label'] == 'setup:' + tid]
        if len(charges) != 1 or abs(setup['offline_afp'] - sum(c['charged'] for c in charges if c['status'] == 'billed')) > 1e-8:
            raise ValueError('setup accounting mismatch')
        if setup['status'] == 'ready' and (digest(setup['plan']) != setup['plan_sha256']
                or any(r['plan_sha256'] != setup['plan_sha256'] for r in shared[tid])):
            raise ValueError('setup and reused plan differ')
    amortization = []
    for arm in arms:
        if not arm.startswith('shared-'): continue
        for tid in tids:
            setup = setup_rows.get(tid); group = [r for r in flat if r['arm'] == arm and r['task_id'] == tid]
            direct = [r for r in flat if r['arm'] == 'direct-strong' and r['task_id'] == tid]
            if (not setup or setup['status'] != 'ready' or not direct
                    or not all(_finite(r['online_afp']) and _finite(r['online_ms']) for r in group + direct)): continue
            cost, latency = statistics.mean(r['online_afp'] for r in group), statistics.mean(r['online_ms'] for r in group)
            reference_cost, reference_ms = statistics.mean(r['online_afp'] for r in direct), statistics.mean(r['online_ms'] for r in direct)
            amortization.append({'arm': arm, 'task_id': tid,
                'afp_break_even_reuses': _break_even(setup['offline_afp'], reference_cost, cost),
                'time_allocation_break_even_reuses': _break_even(setup['wall_time_ms'], reference_ms, latency),
                'allocations': {str(n): {'afp': cost + setup['offline_afp']/n, 'ms': latency + setup['wall_time_ms']/n}
                                for n in DIAGNOSTIC_POLICY['amortization_reuses']},
                'scope': '费用/时间分配诊断，未确认相同质量；不等于实测冷启动时间'})
    scans = [{'afp_limit': cap, 'deadline_seconds': seconds,
              'mean_resource_fitting_arms': [a for a in arms if summaries[a]['complete']
                    and summaries[a]['mean_online_afp'] <= cap and summaries[a]['mean_online_ms'] <= seconds * 1000],
              'confirmed_quality_feasible_arms': [],
              'observed_run_violations': {a: sum(r['online_afp'] > cap or r['online_ms'] > seconds * 1000
                    for r in flat if r['arm'] == a) if summaries[a]['complete'] else None for a in arms}}
             for cap in DIAGNOSTIC_POLICY['budget_points_afp'] for seconds in DIAGNOSTIC_POLICY['deadline_points_seconds']]
    return {'schema_version': 'pareto-development-report-v1', 'policy': DIAGNOSTIC_POLICY,
        'frozen_sha256': digest(frozen), 'simulated': result['simulated'],
        'actual_model_calls': result['actual_model_calls'], 'actual_afp': result['actual_afp'],
        'ledger_audit': 'verified' if actual is not None else 'incomplete-unknown-usage',
        'charged_or_reserved': totals, 'known_stage_afp': dict(stages), 'call_table': call_table,
        'rows': flat, 'summaries': summaries, 'comparisons': comparisons, 'amortization': amortization,
        'observed_constraint_scan': scans, 'confirmed_pareto_frontier': [],
        'human_quality_confirmed': False, 'missing_runs': sorted(set(specs) - set(rows)),
        'next_step_rule': '先看完整开发配对和失败原因；未确认质量不启动收益策略扩张，正式留出仍需真人。'}
