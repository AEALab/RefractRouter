"""自动路由的只读展示合同；不重新判别、选模或派发模型。"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

SCHEMA = 'automatic-routing-trace-v1'
RUN_ID = re.compile(r'\d{8}T\d{6}Z-[0-9a-f]{12}\Z')
MAX_RECORD_BYTES = 32 * 1024 * 1024


def pick(value, keys):
    return {k: deepcopy(value[k]) for k in keys if k in value} if isinstance(value, dict) else {}


def amount(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def total(rows):
    values = [amount(c.get('charged')) for c in rows]
    return sum(values) if all(v is not None for v in values) else None


def project(summary, runtime=None, *, cash_limits=None):
    """白名单投影既有证据，缺失字段保留为空，不读取当前设置补写历史。"""
    runtime = runtime or {}
    gate = summary.get('complexity_gate') or runtime.get('complexity_gate') or {}
    local = gate.get('local_decision') or {}
    routing = runtime.get('routing') or {}
    comparison = summary.get('route_comparison') or runtime.get('route_comparison') or {}
    admission = summary.get('plan_admission') or runtime.get('plan_admission') or {}
    calls = []
    source_calls = runtime.get('calls')
    if source_calls is None:
        source_calls = (summary.get('cost_trace') or {}).get('calls')
    for call in source_calls or []:
        row = pick(call, ('label', 'model_id', 'category', 'billing_unit', 'unit', 'status',
            'reserved', 'charged', 'billing_mode', 'cost_basis', 'cash_cost_cny', 'cash_cost_status',
            'provider_cost_confirmed', 'input_tokens', 'output_tokens', 'cached_input_tokens',
            'reasoning_tokens', 'ttft_ms', 'latency_ms', 'request_id', 'finish_reason', 'dispatch_at'))
        row['route'] = pick(call.get('route'), ('provider', 'model', 'reasoning_effort'))
        calls.append(row)
    candidates = []
    checks = (routing.get('diagnostics') or {}).get('candidate_checks') or {}
    # 模型目录必须来自该次运行的冻结记录；不能借当前目录补全旧任务。
    directory = summary.get('candidate_models') or runtime.get('candidate_models') or {}
    for mid, model in directory.items():
        evidence = []
        sources = comparison.get('model_admission') or {'execution': {
            nid: row.get('model_reasons', {}) for nid, row in admission.items()}}
        for path, nodes in sources.items():
            for nid, reasons in nodes.items():
                evidence.append({'path': path, 'node': nid, 'reason': reasons.get(mid, 'not-recorded')})
        candidates.append({'id': mid, **pick(model, ('provider', 'model', 'reasoning_effort',
            'deployment', 'billing_mode', 'billing_unit')), 'admission': evidence,
            'assignment_checks': {nid: deepcopy(rows[mid]) for nid, rows in checks.items() if mid in rows},
            'selected_nodes': [nid for nid, row in (summary.get('model_routes') or {}).items()
                               if row.get('id') == mid]})
    costs = summary.get('cost_trace') or {}
    reference = runtime.get('reference_costs_cny', costs.get('reference_costs_cny'))
    cash = runtime.get('cash_costs_cny', costs.get('cash_costs_cny'))
    limit_snapshot = runtime.get('cash_limit_snapshot', cash_limits)
    ledger = []
    categories_known = source_calls is not None and all('category' in c for c in source_calls)
    for category in ('production', 'evaluation'):
        rows = [c for c in calls if c.get('category') == category]
        pending = [c for c in rows if c.get('status') in ('reserved', 'unknown-usage')]
        pending_cash = [c for c in pending if c.get('billing_mode') != 'subscription']
        known_cash = amount((cash or {}).get(category))
        occupied_cash = total([c for c in rows if c.get('billing_mode') != 'subscription']) if rows else known_cash
        limit = amount((limit_snapshot or {}).get(category))
        ledger.append({'category': category, 'reference_occupied_cny': amount((reference or {}).get(category)),
            'cash_occupied_cny': known_cash, 'cash_limit_cny': limit,
            'remaining_cash_cny': max(0, limit-occupied_cash) if limit and occupied_cash is not None else None,
            'unlimited_cash': limit == 0, 'pending_count': len(pending),
            'pending_cash_cny': total(pending_cash),
            'billed_cash_cny': total([c for c in rows
                if c.get('status') == 'billed' and c.get('billing_mode') != 'subscription']) if categories_known else None})
    tool = summary.get('tool_validation') or runtime.get('tool_validation') or {}
    review = summary.get('review') or runtime.get('review') or {}
    quality = summary.get('quality') or runtime.get('evaluation') or {}
    score, floor = amount(quality.get('score')), amount(routing.get('quality_min_per_node'))
    quality_gate = 'not-recorded'
    if (runtime.get('deterministic_validation') or {}).get('passed') is False:
        quality_gate = 'failed'
    elif review.get('required') is False:
        quality_gate = 'not-required'
    elif summary.get('status', runtime.get('status')) == 'quality-failed':
        quality_gate = 'failed'
    elif score is not None and floor is not None and type(quality.get('passed')) is bool:
        quality_gate = 'passed' if quality['passed'] and score >= floor else 'failed'
    return {'schema_version': SCHEMA, 'run_id': summary.get('run_id'),
        'status': summary.get('status', runtime.get('status')), 'simulated': summary.get('simulated'),
        'mode': summary.get('mode', runtime.get('mode')), 'wall_time_ms': summary.get('wall_time_ms', runtime.get('wall_time_ms')),
        'issues': summary.get('issues', runtime.get('issues', [])),
        'limitations': summary.get('limitations', runtime.get('limitations', [])),
        'structure': {**pick(gate, ('policy_version', 'rule_decision', 'decision', 'combination', 'reasons')),
            'judge': pick(local, ('contract', 'ruleVersion', 'verdict', 'rawVerdict', 'confidence',
                'probabilities', 'probabilityBasis', 'signals', 'model', 'revision', 'queueMs', 'latencyMs',
                'rawAnswers', 'costCny', 'backend', 'provider', 'experimental', 'reason'))},
        'plan_origin': summary.get('plan_origin', runtime.get('plan_origin')),
        'comparison': pick(comparison, ('status', 'route', 'reason', 'selected_candidate',
            'generated_node_count', 'selected_node_count', 'multi_node_selected', 'direct', 'dag',
            'decision_factors', 'estimate_scope', 'complete_task_cost_bound', 'tool_call_limit',
            'billing_unit', 'prediction_source', 'latency_scope', 'latency_evidence', 'candidate_diagnostics', 'budget_shortfalls')),
        'selection_rule': summary.get('model_selection_rule', routing.get('cost_preference')),
        'quality_min': routing.get('quality_min_per_node'),
        'profile_scope': summary.get('profile_scope', runtime.get('profile_scope')),
        'candidates': candidates, 'routing_diagnostics': pick(routing.get('diagnostics'),
            ('rule_version', 'remaining_cash', 'remaining_cost', 'remaining_latency_ms', 'rejected_combinations', 'counts_may_overlap')),
        'calls': calls, 'ledger': ledger, 'call_order_basis': 'reservation-order',
        'accounting_basis': runtime.get('accounting_basis', costs.get('accounting_basis')),
        'external_judge_cost_cny': amount(local.get('costCny')) if local.get('backend') == 'jev' else None,
        'external_judge_called': local.get('backend') == 'jev' and local.get('model') is not None,
        'review': pick(review, ('policy', 'required', 'reason', 'status', 'score', 'passed',
            'time_reserve_ms', 'output_cap', 'limits_version', 'contract_version','timeout_ms','task_timeout_ms','effective_wait_ms','model','reasoning_effort')),
        'deterministic_validation': pick(runtime.get('deterministic_validation'), ('passed', 'reason')),
        'planning_budget': pick(runtime.get('planning_budget'), ('version', 'task_remaining_ms',
            'review_reserve_ms', 'planner_allowance_ms', 'execution_after_planner_ms',
            'estimates_are_guarantees', 'max_nodes', 'node_limit_basis')),
        'planner_normalizations': [pick(attempt, ('identifier_normalization', 'type_normalization','json_normalization'))
            for attempt in (runtime.get('compact_planning') or {}).get('attempts', [])
            if attempt.get('identifier_normalization') or attempt.get('type_normalization') or attempt.get('json_normalization')],
        'quality': pick(quality, ('score', 'passed', 'rationale')), 'quality_gate': quality_gate,
        'tools': {**pick(tool, ('required', 'required_tools', 'passed', 'reason', 'message', 'missing_tools')),
            'records': [pick(r, ('node', 'call_id', 'tool', 'outcome')) for r in tool.get('records', [])]},
        'missing_evidence': [name for name, present in (
            ('candidate-directory', bool(directory)),
            ('per-candidate-budget-check', bool(checks)), ('frozen-cash-limits', limit_snapshot is not None),
            ('call-ledger', source_calls is not None)) if not present]}


def _read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
        raise ValueError('运行证据不可读取或超过展示容量')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('运行证据格式错误')
    return value


def history(root, run_ids):
    """只读取显式引用的受管运行 ID；不接受路径，不枚举其他会话。"""
    if not isinstance(run_ids, list) or len(run_ids) > 20 or any(
            not isinstance(rid, str) or not RUN_ID.fullmatch(rid) for rid in run_ids):
        raise ValueError('自动路由记录 ID 不合法（每次最多 20 条）')
    records, errors = [], []
    for rid in dict.fromkeys(run_ids):
        directory = Path(root) / rid
        try:
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError('运行证据不存在')
            summary = _read(directory / 'summary.json') if (directory / 'summary.json').exists() else {'run_id': rid}
            if summary.get('run_id') != rid or summary.get('strategy', 'auto') != 'auto':
                raise ValueError('运行证据身份或策略不匹配')
            runtime = _read(directory / 'result.json') if (directory / 'result.json').exists() else {}
            limits = None
            # 仅迁移展示字段，不写回原始文件、不使用当前设置或重新运行规则。
            if (directory / 'provider-config.json').exists():
                limits = _read(directory / 'provider-config.json').get('cashLimits')
            records.append(project(summary, runtime, cash_limits=limits))
        except (OSError, ValueError) as exc:
            errors.append({'run_id': rid, 'message': str(exc)[:200]})
    return {'schema_version': SCHEMA, 'records': records, 'errors': errors}
