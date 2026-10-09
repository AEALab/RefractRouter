"""Text-task orchestration with explicit planning, assignment, execution and judging."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import time
from typing import Callable

from .responses_api import output_token_limit, available_output_limit
from .model_selection import Weights
from .routing_actions import action_identity
from .node_routing import load_profile, number, route_nodes
from .node_recovery import NodeRecovery, validate_fallback_limit
from .openai_compatible import ChatResponse, ModelInvocationError
from threading import RLock
from .tool_runtime import ToolTurnConcluded
from .task_budget import TaskCallBudget, request_input_bound
from .automatic_budget import AutomaticMixedBudget
from .automatic_mixed_assignment import route_nodes_mixed
from .task_scheduling import ExecutionPolicy
from .task_execution import execute_nodes
from .task_evaluation import evaluate_text, evaluation_messages
from .task_tool_evidence import (MAX_EVIDENCE_BYTES, collect_tool_evidence,
                                 tool_requirements, validation_message)
from .output_constraints import check_output_constraints, validate_output_constraints
from concurrent.futures import CancelledError
from .task_plan import PLANNER_SYSTEM, preview_plan, text, validate_plan
from .task_contracts import decode_output, string_list
from .planning_support import (execution_support, compile_generated_capacity, admission_diagnostics,
                               placement_admission_diagnostics, generate_plan)
from .configured_routing import configured_profile, selected_quality_basis
from .compact_planning import planner_model, generate_compact, planner_system, planning_node_limit
from .cost_first import verify_cost_drivers
from .selective_context import build_node_context
from .task_materials import validate_materials
from .privacy_placement import (PlacementGuard, PrivacyRouteViolation, judge_isolation, new_record,
                                privacy_enabled, resolve_placement, restricted_eligible_models,
                                role_isolation, safe_tool_audit, static_node_views)
from .dependency_guard import NodeSemanticFailure
from .task_inputs import prepare_inputs
from .dynamic_decomposition import DynamicDecomposition
from .automatic_routing import compare_executable_routes, choose_mixed_billing_route
from .final_correction import correct_final, VERSION as CORRECTION_VERSION
from .review_evidence import receipt as deterministic_receipt
from .review_time_guard import check_review_time
from .source_state_guard import check_source_state

AGENT_PLAN_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"


def _shared_judge_forecast(judge, task, criteria, candidates, *, tool_evidence=False,
                           expected_answer_tokens=None):
    """旧合同保留容量上界；新版费用排序使用独立预期用量，不改变实际预留。"""
    max_answer = max(output_token_limit(model) for model in candidates.values())
    if expected_answer_tokens is not None:
        if type(expected_answer_tokens) is not int or expected_answer_tokens < 1:
            raise ValueError('invalid expected final answer tokens')
        max_answer = min(max_answer, expected_answer_tokens)
    input_bound = request_input_bound(evaluation_messages(task, '', criteria or [])) + max_answer * 8
    if tool_evidence:
        input_bound += MAX_EVIDENCE_BYTES
    if expected_answer_tokens is not None:
        # 与执行节点共用现有字节比例估计；不当作 tokenizer 保证或安全包络。
        input_bound = max(1, (input_bound + 3) // 4)
        judge_output = min(output_token_limit(judge), 1024)
    else:
        judge_output = output_token_limit(judge)
    return (input_bound * judge.input_cost_per_1k
            + judge_output * judge.output_cost_per_1k) / 1000


def _bounded_tool_allowance(routing, candidates, max_calls, input_cap, *, cash_only=False):
    """把宿主工具续接的全局调用名额按本路线最贵的执行器保守计入。"""
    if routing.get('status') != 'selected' or not max_calls:
        return 0.0
    return max_calls * max(
        0 if cash_only and getattr(model, "billing_mode", "metered") == "subscription" else
        (min(input_cap, model.context_window - output_token_limit(model))
         * model.input_cost_per_1k + output_token_limit(model) * model.output_cost_per_1k) / 1000
        for mid in set(routing['assignments'].values()) for model in (candidates[mid],))


def _route_budget_shortfall(route, *, reference_allowance, cash_allowance,
                            judge_reference, judge_is_metered, remaining_production,
                            remaining_evaluation, remaining_cash, remaining_evaluation_cash):
    """二次选路同时核对工具续接及最终评审的参考额度和新增现金。"""
    shortage = {}
    worker_and_tool = route['prediction']['cost'] + reference_allowance
    if worker_and_tool > remaining_production + 1e-12:
        shortage['production'] = worker_and_tool - remaining_production
    if judge_reference > remaining_evaluation + 1e-12:
        shortage['evaluation'] = judge_reference - remaining_evaluation
    if remaining_cash is not None:
        cash_total = route['prediction']['cash_cost'] + cash_allowance
        if cash_total > remaining_cash + 1e-12:
            shortage['production_cash'] = cash_total - remaining_cash
    if judge_is_metered and remaining_evaluation_cash is not None:
        if judge_reference > remaining_evaluation_cash + 1e-12:
            shortage['evaluation_cash'] = judge_reference - remaining_evaluation_cash
    return shortage


def _compare_mixed_execution(routes, *, candidates, charged_calls, judge, judge_cost,
                             review_required, tool_count, input_cap, remaining_production,
                             remaining_evaluation):
    """比较可执行直答与 DAG；两类单位各自准入，共同已花的规划费只入总账。"""
    planner_rows = [row for row in charged_calls if row['label'] in {'planner', 'planner-repair'}]
    if any(row['status'] != 'billed' for row in planner_rows):
        raise ValueError('planner usage is unconfirmed; route comparison stopped')
    planner_costs = {unit: sum(row['charged'] for row in planner_rows
                              if row['billing_unit'] == unit) for unit in ('AFP', 'CNY')}
    planner_latency = (sum(row['latency_ms'] for row in planner_rows)
        if all(isinstance(row.get('latency_ms'), (int, float)) for row in planner_rows) else None)
    choices, views, shortfalls = [], {}, {}
    for name, routing in routes.items():
        if routing.get('status') != 'selected':
            views[name] = None
            continue
        worker = routing['prediction']['costs_by_unit']
        allowance = {'AFP': 0.0, 'CNY': 0.0}
        if tool_count:
            for mid in set(routing['assignments'].values()):
                model = candidates[mid]
                amount = tool_count * (
                    min(input_cap, model.context_window - output_token_limit(model))
                    * model.input_cost_per_1k + output_token_limit(model)
                    * model.output_cost_per_1k) / 1000
                allowance[model.billing_unit] = max(allowance[model.billing_unit], amount)
        judge_vector = {'AFP': 0.0, 'CNY': 0.0}
        if review_required:
            judge_vector[judge.billing_unit] = judge_cost
        shortage = {}
        for unit in ('AFP', 'CNY'):
            if remaining_production[unit] and worker[unit] + allowance[unit] > remaining_production[unit] + 1e-12:
                shortage[f'{unit}.production'] = worker[unit] + allowance[unit] - remaining_production[unit]
            if judge_vector[unit] > remaining_evaluation[unit] + 1e-12:
                shortage[f'{unit}.evaluation'] = judge_vector[unit] - remaining_evaluation[unit]
        if shortage:
            shortfalls[name] = shortage
            views[name] = None
            continue
        total = {unit: worker[unit] + allowance[unit] + judge_vector[unit] + planner_costs[unit]
                 for unit in ('AFP', 'CNY')}
        quality = routing['prediction']['minimum_node_quality_proxy']
        views[name] = {'worker_costs_by_unit': dict(worker), 'tool_allowance_by_unit': allowance,
                       'judge_estimate_by_unit': judge_vector, 'planner_actual_by_unit': planner_costs,
                       'total_estimated_by_unit': total, 'worker_scheduled_latency_ms':
                       routing['prediction']['scheduled_latency_ms'],
                       'known_latency_ms': routing['prediction']['scheduled_latency_ms'] + planner_latency
                           if planner_latency is not None else None,
                       'quality_proxy': quality, 'assignments': dict(routing['assignments'])}
    for name, row in views.items():
        if row:
            choices.append({'id': name, 'qualityQualified': True,
                # 节点画像只用于各路线的质量下限准入；不同图的节点分数不能
                # 当成已校准的整任务质量比较，否则更高的 DAG 先验会排除
                # 已达到质量下限、且成本更低的 direct 路线。
                'qualityNonInferior': None,
                'qualityBasis': 'configured-profile-threshold-only',
                'costsByUnit': row['total_estimated_by_unit'],
                'latencyMs': row['worker_scheduled_latency_ms']})
    selected = choose_mixed_billing_route(choices, {'AFP': 0, 'CNY': 0}) if choices else None
    direct_row, dag_row = views.get('direct'), views.get('dag')
    net_savings = ({unit: direct_row['total_estimated_by_unit'][unit]
        - planner_costs[unit] - dag_row['total_estimated_by_unit'][unit]
        for unit in ('AFP', 'CNY')} if direct_row and dag_row else None)
    return {'policy_version': 'automatic-live-comparison-mixed-v1',
            'prediction_source': 'compiled-user-declared-node-profiles',
            'latency_scope': 'worker-schedule-plus-observed-planner; shared-judge-latency-unforecast',
            'billing_unit': 'MIXED', 'direct': views.get('direct'), 'dag': views.get('dag'),
            'status': 'selected' if selected and selected['selected'] else 'infeasible',
            'route': selected['selected'] if selected else 'infeasible',
            'reason': selected['reason'] if selected else 'no-qualified-affordable-route',
            'quality_noninferiority_verified': False,
            'quality_basis': 'configured-profile-threshold-only', 'budget_shortfalls': shortfalls,
            'planner_actual_costs_by_unit': planner_costs,
            'dag_net_estimated_savings_vs_unprobed_direct_by_unit': net_savings,
            'dag_net_savings_forecast_no_unit_worse_and_some_better': (
                all(amount >= -1e-9 for amount in net_savings.values())
                and any(amount > 1e-9 for amount in net_savings.values()) if net_savings else None)}


def validate_request(raw):
    allowed = {"task", "mode", "method", "qualityMin", "costMax", "costMaxByUnit", "latencyMaxMs", "weights",
               "plan", "plannerModelId", "maxProductionCost", "maxEvaluationCost", "acceptanceCriteria",
               "maxConcurrency", "providerConcurrency", "providerMinIntervalMs", "maxNodeFallbacks", "outputConstraints", "maxPlanRepairs",
               "planningMode", "plannerPolicy", "contextPolicy", "prefixPolicy", "materials", "unlimitedTime", "unrestrictedPlanning", "boundedPlannerLimits", "plannerThinking", "plannerMaxOutputTokens", "plannerTimeoutMs", "maxDynamicSplits", "verifyDependencies", "maxTotalOutputTokens", "adaptiveOutputBudget", "reviewReserveMs", "reviewMaxOutputTokens", "reviewTimeoutMs", "maxFinalRevisions"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("unknown task request fields")
    if raw.get('prefixPolicy', 'legacy') not in ('legacy', 'stable-v1'):
        raise ValueError('invalid prefixPolicy')
    validate_materials(raw.get('materials', []))
    if raw.get('contextPolicy', 'full') not in ('full', 'selective-v1'):
        raise ValueError('invalid contextPolicy')
    if raw.get('contextPolicy') == 'selective-v1':
        if raw.get('plannerPolicy') not in ('minimal-v1', 'minimal-v2') or raw.get('maxDynamicSplits', 0):
            raise ValueError('selective-v1 requires minimal planning and no dynamic splitting')
    ExecutionPolicy.from_request(raw)
    if type(raw.get('maxFinalRevisions', 0)) is not int or raw.get('maxFinalRevisions', 0) not in (0, 1):
        raise ValueError('maxFinalRevisions must be an integer in 0..1')
    validate_fallback_limit(raw.get('maxNodeFallbacks', 0))
    if type(raw.get('maxPlanRepairs', 0)) is not int or not 0 <= raw.get('maxPlanRepairs', 0) <= 1:
        raise ValueError('maxPlanRepairs must be an integer in 0..1')
    if type(raw.get('unlimitedTime', False)) is not bool:
        raise ValueError('unlimitedTime must be boolean')
    if type(raw.get('unrestrictedPlanning', False)) is not bool:
        raise ValueError('unrestrictedPlanning must be boolean')
    if type(raw.get('boundedPlannerLimits', False)) is not bool:
        raise ValueError('boundedPlannerLimits must be boolean')
    if raw.get('boundedPlannerLimits') and raw.get('unrestrictedPlanning'):
        raise ValueError('bounded planner limits cannot enable unrestricted planning')
    if type(raw.get('adaptiveOutputBudget', False)) is not bool:
        raise ValueError('adaptiveOutputBudget must be boolean')
    if 'maxTotalOutputTokens' in raw and (type(raw['maxTotalOutputTokens']) is not int
            or not 1000 <= raw['maxTotalOutputTokens'] <= 1_000_000):
        raise ValueError('maxTotalOutputTokens must be an integer in 1000..1000000')
    if raw.get('plannerThinking', 'inherit') not in {'inherit', 'enabled', 'disabled'}:
        raise ValueError('invalid plannerThinking')
    if raw.get('planningMode', 'full') not in ('full', 'compact'):
        raise ValueError('planningMode must be full or compact')
    if raw.get('plannerPolicy', 'legacy') not in ('legacy', 'minimal-v1', 'minimal-v2'):
        raise ValueError('invalid plannerPolicy')
    if raw.get('plannerPolicy') in ('minimal-v1', 'minimal-v2'):
        if 'plan' in raw or raw.get('planningMode') != 'compact':
            raise ValueError('minimal planning requires automatic compact planning')
        if raw.get('maxPlanRepairs', 0):
            raise ValueError('minimal planning requires one call without repairs')
    for key, default, low, high in (
            ('reviewReserveMs',0,0,300000),
            ('reviewTimeoutMs',0,0,3600000),
            ('reviewMaxOutputTokens',8192,256,128000),
            ('plannerMaxOutputTokens',1200,256,128000 if raw.get('boundedPlannerLimits') else 2048),
            ('plannerTimeoutMs',12000,1000,300000 if raw.get('boundedPlannerLimits') else 30000),
            ('maxDynamicSplits',0,0,2)):
        if type(raw.get(key, default)) is not int or not low <= raw.get(key, default) <= high:
            raise ValueError(f'{key} must be an integer in {low}..{high}')
    if type(raw.get('verifyDependencies', False)) is not bool:
        raise ValueError('verifyDependencies must be a boolean')
    if raw.get('maxDynamicSplits',0) and raw.get('maxNodeFallbacks',0):
        raise ValueError('dynamic decomposition v1 cannot combine with model fallback')
    if 'outputConstraints' in raw:
        validate_output_constraints(raw['outputConstraints'])
    text(raw.get("task"), "task")
    mode = raw.get("mode", "preflight")
    if mode not in {"preflight", "demo", "plan", "run"}:
        raise ValueError("mode must be preflight, demo, plan or run")
    if raw.get("method") not in {"A", "B"}:
        raise ValueError("method must be A or B")
    number(raw.get("qualityMin"), "qualityMin", maximum=100)
    number(raw.get("costMax"), "costMax")
    if 'costMaxByUnit' in raw:
        limits = raw['costMaxByUnit']
        if not isinstance(limits, dict) or set(limits) != {'AFP', 'CNY'}:
            raise ValueError('costMaxByUnit requires AFP and CNY')
        for unit, value in limits.items():
            number(value, f'{unit} costMax')
    number(raw.get("latencyMaxMs"), "latencyMaxMs", positive=True)
    weights = raw.get("weights")
    if raw["method"] == "B":
        if not isinstance(weights, dict) or set(weights) != {"quality", "cost", "latency"}:
            raise ValueError("B requires quality/cost/latency weights")
        Weights(**weights).normalized()
    elif weights is not None:
        raise ValueError("A does not accept weights")
    if "acceptanceCriteria" in raw:
        string_list(raw["acceptanceCriteria"], "acceptanceCriteria")
    if "plan" in raw:
        validate_plan(raw["plan"], required_criteria=raw.get("acceptanceCriteria"))
    if "plannerModelId" in raw:
        text(raw["plannerModelId"], "plannerModelId", 100)
    return {**raw, "mode": mode}


def validate_models(manifest, *, configured_application=False):
    for model in manifest.models:
        for field in ("input_cost_per_1k", "output_cost_per_1k", "cached_input_cost_per_1k"):
            value = getattr(model, field)
            if value is not None:
                number(value, field)
        if model.cached_input_cost_per_1k is not None and model.cached_input_cost_per_1k > model.input_cost_per_1k:
            raise ValueError("cached pricing must not exceed the uncached reserve")
        if not configured_application and (model.provider == "ark-plan" or model.billing_unit == "AFP" or (model.base_url and "volces.com" in model.base_url)):
            if model.provider != "ark-plan" or model.base_url != AGENT_PLAN_URL or model.wire_api != "chat-completions":
                raise ValueError("Ark tasks require the exact Agent Plan /api/plan/v3 endpoint")
        if set(model.request_options) & {"model", "messages", "stream", "max_tokens", "max_completion_tokens"}:
            raise ValueError("request_options cannot override budgeted request fields")
        if not model.context_window or model.context_window <= 0 or not model.max_output_tokens or model.max_output_tokens <= 0:
            raise ValueError("task execution requires positive context and output caps")


class DemoTaskClient:
    """Explicit fixture outputs; does not attempt to solve the user task."""
    def complete(self, model, messages, *, json_mode=False):
        content = "[SIMULATED] " + messages[-1]["content"][:500]
        if json_mode:
            contract = json.loads(messages[-1]["content"])["contract"]
            content = json.dumps({key: "[SIMULATED] " + description
                                  for key, description in contract["output"]["fields"].items()}, ensure_ascii=False)
        return ChatResponse(content, 20, 30, 0, 0, 1, 1, "stop", None)


def run_task(request, manifest, profile, *, client=None, production_limit=None, evaluation_limit=None,
             checkpoint: Callable[[dict], None] = lambda result: None, cancel_event=None, conversation_context='',
             configured_application=False, configuration=None, context_limit_bytes=120_000, input_cap=131_072,
             tool_runtime=None, privacy=None, classifier=None, decision_evidence=None, review_evidence=None,
             max_model_calls=None, alternative_direct_plan=None, final_validator=None):
    request = validate_request(request)
    if final_validator is not None and not callable(final_validator):
        raise ValueError('final_validator must be callable')
    review_judge = (replace(manifest.judge, max_output_tokens=min(
        output_token_limit(manifest.judge), request['reviewMaxOutputTokens']))
        if 'reviewMaxOutputTokens' in request else manifest.judge)
    if request.get('contextPolicy') == 'selective-v1' and tool_runtime is not None:
        raise ValueError('selective-v1 currently requires text-only material tasks without native tools')
    if not isinstance(conversation_context, str) or len(conversation_context.encode()) > context_limit_bytes:
        raise ValueError('invalid conversation context')
    planning_task, execution_task, content_guard = prepare_inputs(request, conversation_context)
    _, node_task, _ = prepare_inputs(request, conversation_context, for_node=True)
    if tool_runtime is not None:
        planning_task += '\n执行节点可使用宿主原生工具，实际查询须先取得工具证据，不得假装已经检索。可用工具：' + ', '.join(s['name'] for s in tool_runtime.schemas)
    validate_models(manifest, configured_application=configured_application)
    profiles = load_profile(profile, manifest)
    policy = ExecutionPolicy.from_request(request)
    known_providers = {m.provider for m in manifest.models}
    if (set(policy.provider_concurrency) | set(policy.provider_min_interval_ms)) - known_providers:
        raise ValueError("unknown provider in execution policy")
    host_capabilities = None
    if (policy.max_concurrency > 1 and request['mode'] in {'plan', 'run'}
            and any(m.wire_api == 'dsh-llm' for m in manifest.models)):
        bridge = getattr(client, 'dsh_bridge', None)
        if bridge is None or not callable(getattr(bridge, 'capabilities', None)):
            raise ValueError('parallel DSH calls require a multiplex host bridge')
        host_capabilities = bridge.capabilities()
        if policy.max_concurrency > host_capabilities['maxParallelModelCalls']:
            raise ValueError('requested concurrency exceeds DSH host capability')
    mode = request["mode"]
    live = mode in {"plan", "run"}
    if live and profile["kind"] != "empirical" and not (configured_application and profile["kind"] == "configured"):
        raise ValueError("live tasks require an empirical routing profile, not synthetic metrics")
    if live and client is None:
        raise ValueError("live execution requires a model client")
    if live and getattr(client, "max_retries", 0) != 0:
        raise ValueError("text tasks require a zero-retry client")
    candidates = {m.model_id: m for m in manifest.candidates}
    planner_candidates = ({m.model_id: m for m in manifest.models
                           if m.model_id in configuration.role_pools['planner']}
                          if configuration is not None and configuration.role_pools is not None
                          else candidates)
    planner, planner_basis = planner_model(planner_candidates, configuration=configuration,
        explicit=request.get('plannerModelId'), output_cap=request.get('plannerMaxOutputTokens',1200),
        compact=request.get('planningMode') == 'compact', unrestricted=request.get('unrestrictedPlanning', False),
        thinking=request.get('plannerThinking','inherit'))
    planner_id = planner.model_id
    if planner_id not in planner_candidates:
        raise ValueError("plannerModelId must be available in the planner role pool")
    if max_model_calls is not None and (type(max_model_calls) is not int or max_model_calls < 1):
        raise ValueError('max_model_calls must be a positive integer')
    runtime_call_limit = (max_model_calls if max_model_calls is not None else
                          10 + request.get('maxPlanRepairs',0) + 2*request.get('maxDynamicSplits',0)
                          if request.get('maxDynamicSplits',0) and tool_runtime is None else None)
    currency_reference = configuration is not None and configuration.snapshot.get('schemaVersion') == 'refractagent-providers-v6'
    mixed = manifest.billing_unit == 'MIXED'
    if mixed and request.get('maxFinalRevisions', 0):
        raise ValueError('final correction requires the currency reference contract; legacy mixed units remain unchanged')
    if mixed:
        if request['method'] != 'A' or request.get('maxNodeFallbacks', 0) or request.get('maxDynamicSplits', 0):
            raise ValueError('mixed automatic routing currently requires method A without node fallback or dynamic splits')
        if 'costMaxByUnit' not in request:
            raise ValueError('mixed automatic routing requires costMaxByUnit')
        if not isinstance(production_limit, dict) or not isinstance(evaluation_limit, dict):
            raise ValueError('mixed automatic routing requires separate production and evaluation limits')
        enforce_limits = live or mode == 'preflight'
        budget = AutomaticMixedBudget(client if live else DemoTaskClient(),
            {unit: {'production': production_limit[unit] if enforce_limits else 1e12,
                    'evaluation': evaluation_limit[unit] if enforce_limits else 1e12}
             for unit in ('AFP', 'CNY')}, max_calls=runtime_call_limit,
            max_total_output_tokens=request.get('maxTotalOutputTokens'),
            adaptive_output_reservation=request.get('adaptiveOutputBudget', False))
    else:
        budget = TaskCallBudget(client if live else DemoTaskClient(),
            production_limit if live else 1e12, evaluation_limit if live else 1e12,
            cash_limits=configuration.snapshot['cashLimits'] if currency_reference else None,
            max_calls=runtime_call_limit, capture_payload=True,
            max_total_output_tokens=request.get('maxTotalOutputTokens'),
            adaptive_output_reservation=request.get('adaptiveOutputBudget', False))
    started = time.monotonic()
    required_tools = tool_requirements('\n'.join([request['task'], *request.get('acceptanceCriteria', [])]),
                                       tool_runtime.schemas if tool_runtime else ())
    tool_record_start = len(tool_runtime.snapshot()) if tool_runtime else 0
    deadline_ms = float("inf") if request.get("unlimitedTime") else request["latencyMaxMs"]
    result = {"schema_version": "task-run-v1", "mode": mode, "status": "started", "task": request["task"],
              "plan_origin": ("direct-gate" if decision_evidence and decision_evidence.get('decision') == 'direct'
                              else "provided" if "plan" in request else "model" if live else "template-preview"),
              "planner_output": None, "planner_prompt_sha256": hashlib.sha256(PLANNER_SYSTEM.encode()).hexdigest(),
              "plan": None, "plan_analysis": None, "routing": None, "nodes": [], "final_output": "", "evaluation": None,
              "conversation_context_sha256": hashlib.sha256(conversation_context.encode()).hexdigest(),
              "billing_unit": manifest.billing_unit, "charged": {},
              "calls": [], "issues": [], "profile_scope": profile["scope"],
              "generation_status": "not-started",
              "model_call_limit": runtime_call_limit,
              "max_total_output_tokens": request.get('maxTotalOutputTokens'),
              'host_capabilities': host_capabilities,
              "complexity_gate": decision_evidence,
              "review": ({**review_evidence, "status": "pending"} if review_evidence else
                         {"policy": "always", "required": True, "reason": "legacy-always-review", "status": "pending"}),
              "format_validation": check_output_constraints(request.get('outputConstraints')),
              "profile_provenance": profile["provenance"],
              "limitations": [("执行节点通过宿主权限管线调用工具；规划与评审不执行工具。" if tool_runtime else "Text generation only; no shell, retrieval or filesystem actions."),
                              "Node profile estimates may not transfer to this task; quality is a proxy, not a guarantee.",
                              "调度受并发上限和派发间隔约束；预测不是任务 p95。取消不保证已派发请求停止计费。"]}
    planning_model = planner if request.get('planningMode') == 'compact' else planner_candidates[planner_id]
    review_reserve = (request.get('reviewReserveMs', 0) / 1000
        if result['review']['required'] and not request.get('unlimitedTime') else 0)
    execution_deadline = started + deadline_ms / 1000 - review_reserve
    result['review'].update(time_reserve_ms=round(review_reserve * 1000),
        output_cap=output_token_limit(review_judge), limits_version='automatic-review-envelope-v2',
        timeout_ms=request.get('reviewTimeoutMs') or None,
        model={'provider':review_judge.provider,'model':review_judge.api_model,'id':review_judge.model_id},
        reasoning_effort=(review_judge.request_options or {}).get('reasoning_effort','default'),
        task_timeout_ms=None if request.get('unlimitedTime') else deadline_ms)
    result['planner_selection'] = {'model_id': planner_id, 'basis': planner_basis,
        'output_cap': output_token_limit(planning_model),
        'timeout_ms': None if request.get('unlimitedTime') or request.get('unrestrictedPlanning') else request.get('plannerTimeoutMs',12000) if request.get('planningMode')=='compact' else deadline_ms,
        'thinking': request.get('plannerThinking','inherit'), 'output_policy': 'model-capacity' if request.get('unrestrictedPlanning') else 'explicit-cap'}
    if content_guard is not None:
        result['dependency_evidence'] = content_guard.evidence()
    if configuration is not None and not configured_application:
        raise ValueError('automatic configuration requires configured application mode')
    # v3 安全合同始终启用；历史 v1/v2 只有显式 privacy.enabled 才进入这条路径。
    placement = new_record(privacy, manifest.models) if privacy_enabled(privacy) else None
    guard = (PlacementGuard(placement, candidates.values(), classifier=classifier)
             if placement is not None else None)
    if placement is not None:
        result['privacy_placement'] = placement
        result['input_classification_state'] = 'pending'
        result['placement_state'] = 'pending'
    persist_lock = RLock()
    def persist():
        with persist_lock:
            result["charged"], result["calls"] = budget.snapshot()
            if currency_reference:
                result['accounting_basis'] = 'public-reference-valuation'
                result['reference_costs_cny'] = dict(result['charged'])
                result['cash_costs_cny'] = budget.cash_snapshot()
                result['cash_limit_snapshot'] = dict(configuration.snapshot['cashLimits'])
                result['cost_note'] = '参考成本包含按量调用，两项不相加；订阅费未按调用分摊。'
            if placement is not None:
                # 安全运行只保存摘要；完整输入已由 input_sha256 关联，敏感原文不落盘。
                for call in result['calls']:
                    call.pop('request_messages', None)
            if tool_runtime is not None:
                records = tool_runtime.snapshot()
                result["tool_calls"] = (safe_tool_audit(records, privacy=privacy)
                                        if placement is not None else records)
            if configured_application:
                actions = {m.model_id: action_identity(m) for m in manifest.models}
                directory = configuration.manifest.candidates if configuration else manifest.candidates
                result['candidate_models'] = {m.model_id: {**action_identity(m),
                    'deployment': m.deployment, 'billing_mode': m.billing_mode,
                    'billing_unit': m.billing_unit} for m in directory}
                for call in result['calls']:
                    call['route'] = actions[call['model_id']]
            result["wall_time_ms"] = round((time.monotonic() - started) * 1000)
            checkpoint(result)
    budget.on_reserve = lambda reservation: persist()
    budget.on_dispatch = lambda reservation: persist()

    def privacy_block(rows, append=True):
        """启用约束后无法在本地候选内完成时明确失败，不静默放行云端。"""
        placement['status'] = 'blocked'
        if append:
            placement['blocked'].extend(rows)
        for row in rows:
            result['issues'].append(f"{row.get('node_id') or row.get('role')}: {row['detail']}")
        result['status'] = 'privacy-route-blocked'
        persist()
        return result

    def before_call():
        remaining = deadline_ms / 1000 - (time.monotonic() - started - budget.planning_elapsed)
        if cancel_event is not None and cancel_event.is_set():
            budget.stop()
            raise CancelledError("task-cancelled")
        if remaining <= 0:
            raise ValueError("task-deadline-exhausted")
        return remaining
    node_context = None
    try:
        if live and before_call() <= review_reserve:
            result['review'].update(status='not-dispatched-insufficient-time', passed=False,
                reason='planning-would-consume-review-reserve')
            raise ValueError('task-deadline-exhausted')
        if "plan" in request:
            plan = validate_plan(request["plan"], required_criteria=request.get("acceptanceCriteria"))
            if configuration is not None and (result['plan_origin'] == 'direct-gate' or currency_reference):
                plan, estimates = compile_generated_capacity(plan, node_task, candidates,
                    output_constraints=request.get('outputConstraints'), input_cap=input_cap,
                    prefix_policy=request.get('prefixPolicy', 'legacy'), source_faithfulness=bool(request.get('maxFinalRevisions', 0)),
                    tools=tool_runtime.schemas if tool_runtime is not None else None)
                result['compiled_input_estimates'] = estimates
                profile = configured_profile(configuration, manifest, plan.to_dict(), task=request['task'],
                    input_forecasts={nid: row['forecast_input_tokens'] for nid, row in estimates.items()},
                    cost_input_forecasts=({nid: row['routing_input_forecast_tokens'] for nid, row in estimates.items()}
                                          if mixed or currency_reference else None))
                profiles = load_profile(profile, manifest)
                result['routing_profile'] = profile
            if request.get('maxDynamicSplits',0) and not plan.contracts:
                raise ValueError('dynamic decomposition requires v2 node contracts')
        elif live:
            before_call()
            if placement is not None:
                result['input_classification_state'] = 'running'
                persist()
                check = role_isolation(view=planning_task, privacy=privacy, classifier=classifier,
                                       model=planner, role='planner', source='planner-view')
                placement['role_checks'].append(check)
                if not check['satisfied']:
                    check['detail'] = 'planner-not-local'
                    result['input_classification_state'] = 'blocked'
                    return privacy_block([check])
                result['input_classification_state'] = 'ok'
                persist()
            result['planning_state'] = 'running'
            persist()
            if request.get('planningMode') == 'compact':
                result['compact_planning'] = {}
                minimal = request.get('plannerPolicy') in ('minimal-v1', 'minimal-v2')
                selective = request.get('contextPolicy') == 'selective-v1'
                system = planner_system(request.get('plannerPolicy', 'legacy'), request.get('contextPolicy', 'full'))
                result['planner_prompt_sha256'] = hashlib.sha256(system.encode()).hexdigest()
                planning_payload = {'task': planning_task, 'parallel_capacity': policy.max_concurrency}
                if 'reviewReserveMs' in request:
                    remaining_ms = before_call() * 1000
                    planner_ms = (0 if request.get('unrestrictedPlanning') else
                        request.get('plannerTimeoutMs', 12000))
                    estimates = ({mid: configuration.predictions.get(mid, {}).get('latency_ms')
                        for mid in candidates} if configuration is not None else {})
                    planning_payload['planning_budget'] = {
                        'version': 'automatic-planning-time-envelope-v1',
                        'task_remaining_ms': None if request.get('unlimitedTime') else remaining_ms,
                        'review_reserve_ms': round(review_reserve * 1000),
                        'planner_allowance_ms': None if request.get('unrestrictedPlanning') else planner_ms,
                        'execution_after_planner_ms': (None if request.get('unlimitedTime') else
                            max(0, remaining_ms - review_reserve * 1000 - planner_ms)),
                        'latency_prior_ms': estimates,
                        'estimates_are_guarantees': False}
                    result['planning_budget'] = deepcopy(planning_payload['planning_budget'])
                if minimal:
                    providers = {m.provider for m in candidates.values()}
                    planning_payload.update(
                        parallel_capacity=min(policy.max_concurrency, sum(policy.limit(p) for p in providers)),
                        tools_available=bool(tool_runtime is not None and tool_runtime.schemas),
                        acceptance_criteria=request.get('acceptanceCriteria'))
                if selective:
                    planning_payload['material_catalog'] = [{k: v for k, v in item.items() if k != 'text'}
                        for item in request.get('materials', [])]
                node_limit = planning_node_limit(planning_payload.get('planning_budget'),
                                                planning_payload['parallel_capacity'])
                if 'planning_budget' in planning_payload:
                    planning_payload['planning_budget'].update(max_nodes=node_limit,
                        node_limit_basis='serial-latency-prior-v1')
                    result['planning_budget'] = deepcopy(planning_payload['planning_budget'])
                if node_limit == 0:
                    result['planning_state'] = 'not-dispatched-insufficient-time'
                    raise ValueError('task-deadline-exhausted')
                gate = None
                if request.get('plannerPolicy') == 'minimal-v2':
                    gate = lambda plan, decision: verify_cost_drivers(  # noqa: E731
                        plan, decision, candidates=candidates, limit_fn=available_output_limit)
                plan = generate_compact(budget, planner, planning_payload, result['compact_planning'],
                    criteria=request.get('acceptanceCriteria'), cost_limit=None if mixed else request['costMax'],
                    deadline=None if request.get('unrestrictedPlanning') else min(started+deadline_ms/1000, time.monotonic()+request.get('plannerTimeoutMs',12000)/1000),
                    persist=persist, max_nodes=node_limit, repairs=request.get('maxPlanRepairs',0), policy=request.get('plannerPolicy', 'legacy'),
                    context_policy=request.get('contextPolicy', 'full'),
                    output_cap=max(output_token_limit(m) for m in candidates.values()), gate=gate)
                result['planner_output'] = result['compact_planning']['attempts'][0]['output']
            else:
                support = execution_support(manifest, profiles, configuration=configuration)
                result['planning_support'] = support
                messages = [
                    {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": json.dumps({"task": execution_task,
                 "acceptance_criteria": request.get("acceptanceCriteria"), "execution_policy": policy.to_dict(),
                 "execution_support": support, "output_constraints": request.get('outputConstraints'),
                 "minimum_node_quality": request['qualityMin'],
                 "remaining_production_cost": ({unit: min(request['costMaxByUnit'][unit], budget.remaining(unit))
                     if request['costMaxByUnit'][unit] else 0
                     for unit in ('AFP', 'CNY')} if mixed else min(request['costMax'], budget.remaining())),
                 "remaining_time_ms": before_call() * 1000}, ensure_ascii=False)},
                ]
                plan = generate_plan(budget, planning_model, messages, result,
                    required_criteria=request.get('acceptanceCriteria'), max_repairs=request.get('maxPlanRepairs',0),
                    cost_limit=None if mixed else request['costMax'], remaining=before_call, persist=persist)
            if request.get('contextPolicy') == 'selective-v1':
                node_context = build_node_context(plan, request, conversation_context,
                    result['compact_planning']['context_selection'])
                result['context_selection'] = node_context.record
            result['generated_plan'] = plan.to_dict()
            if configuration is not None:
                plan, estimates = compile_generated_capacity(plan, node_task, candidates,
                    output_constraints=request.get('outputConstraints'), input_cap=input_cap,
                    prefix_policy=request.get('prefixPolicy', 'legacy'), source_faithfulness=bool(request.get('maxFinalRevisions', 0)), node_tasks=node_context.tasks if node_context else None, tools=tool_runtime.schemas if tool_runtime is not None else None)
                result['compiled_input_estimates'] = estimates
                profile = configured_profile(configuration, manifest, plan.to_dict(), task=request['task'],
                    input_forecasts={nid: row['forecast_input_tokens'] for nid, row in estimates.items()},
                    cost_input_forecasts=({nid: row['routing_input_forecast_tokens'] for nid, row in estimates.items()}
                                          if mixed or currency_reference else None))
                profiles = load_profile(profile, manifest)
                result['routing_profile'] = profile
        else:
            plan = preview_plan(request["task"], required_criteria=request.get("acceptanceCriteria"))
            if configuration is not None:
                # 自动预览也必须按真实会话和工具包络编译容量。preview_plan 的静态值
                # 只是通用模板预算，不能成为长会话在模拟模式下的隐含上限。
                plan, estimates = compile_generated_capacity(plan, node_task, candidates,
                    output_constraints=request.get('outputConstraints'), input_cap=input_cap,
                    prefix_policy=request.get('prefixPolicy', 'legacy'), source_faithfulness=bool(request.get('maxFinalRevisions', 0)),
                    tools=tool_runtime.schemas if tool_runtime is not None else None)
                result['compiled_input_estimates'] = estimates
                profile = configured_profile(configuration, manifest, plan.to_dict(), task=request['task'],
                    input_forecasts={nid: row['forecast_input_tokens'] for nid, row in estimates.items()},
                    cost_input_forecasts=({nid: row['routing_input_forecast_tokens'] for nid, row in estimates.items()}
                                          if mixed or currency_reference else None))
                profiles = load_profile(profile, manifest)
                result['routing_profile'] = profile
        before_call()
        result["prefix_policy"] = request.get("prefixPolicy", "legacy")
        result["plan"] = plan.to_dict()
        if live and result.get('plan_origin') == 'model':
            result['planning_state'] = 'ok'
        result['plan_ready_ms'] = round((time.monotonic()-started)*1000)
        result["plan_analysis"] = plan.diagnostics()
        result["plan_analysis"]["execution_mode"] = "bounded-parallel" if policy.max_concurrency > 1 else "serial"
        result["execution_policy"] = policy.to_dict()
        persist()
        eligible_models = {}
        for node in plan.nodes:
            capability = plan.contracts.get(node.node_id, {}).get("capability")
            eligible_models[node.node_id] = [mid for mid, model in candidates.items() if not capability or (
                capability["input_budget_tokens"] + available_output_limit(model, capability["input_budget_tokens"]) <= model.context_window
                and capability["expected_output_tokens"] <= available_output_limit(model, capability["input_budget_tokens"]))]
        if live and ('plan' not in request or configured_application):
            result['plan_admission'] = admission_diagnostics(plan, node_task, candidates, profiles,
                request['qualityMin'], output_constraints=request.get('outputConstraints'),
                prefix_policy=request.get('prefixPolicy', 'legacy'), source_faithfulness=bool(request.get('maxFinalRevisions', 0)), node_tasks=node_context.tasks if node_context else None, tools=tool_runtime.schemas if tool_runtime is not None else None)
            eligible_models = {nid: row['eligible_models'] for nid, row in result['plan_admission'].items()}
        if placement is not None:
            result['placement_state'] = 'running'
            persist()
            resolve_placement(plan=plan, models=candidates.values(), privacy=privacy, classifier=classifier,
                              node_views=static_node_views(plan, node_task, node_context.tasks if node_context else None),
                              record=placement)
            if placement['status'] == 'no-local-candidate':
                result['placement_state'] = 'blocked'
                if alternative_direct_plan is None or not live:
                    return privacy_block(placement['blocked'], append=False)
                eligible_models = {nid: [] for nid in eligible_models}
            else:
                result['placement_state'] = 'ok'
                persist()
                eligible_models = restricted_eligible_models(eligible_models, placement)
                starved = [{'node_id': nid, 'grade': placement['grades'][nid]['grade'],
                            'reasons': placement['grades'][nid]['reasons'], 'detail': 'no-local-candidate'}
                           for nid in placement['eligible_models'] if not eligible_models.get(nid)]
                if starved:
                    result['placement_state'] = 'blocked'
                    if alternative_direct_plan is None or not live:
                        return privacy_block(starved)
                    eligible_models = {nid: [] for nid in eligible_models}
            # 评审会读到节点输出；预检按静态视图先给出结论，真实运行前以运行期分级重算。
            placement['judge_isolation'] = judge_isolation(placement, review_judge)
            placement_admission_diagnostics(result.get('plan_admission', {}), eligible_models, placement)
            if not live and not placement['judge_isolation']['satisfied']:
                result['issues'].append('final-judge: privacy-judge-not-local')
        if mixed:
            charged_by_unit = budget.snapshot()[0]
            remaining_cost = {unit: min(
                max(0, request['costMaxByUnit'][unit] - charged_by_unit[unit]['production']),
                budget.remaining(unit)) if request['costMaxByUnit'][unit] else 0
                for unit in ('AFP', 'CNY')}
        else:
            remaining_cost = min(max(0, request["costMax"] - budget.snapshot()[0]['production']), budget.remaining())
        remaining_latency = max(0, deadline_ms - review_reserve * 1000
            - (time.monotonic() - started - budget.planning_elapsed) * 1000) if live else deadline_ms
        if mixed:
            result['routing'] = route_nodes_mixed(plan, profiles,
                model_units={mid: model.billing_unit for mid, model in candidates.items()},
                quality_min=request['qualityMin'], budgets=remaining_cost,
                latency_max_ms=None if request.get('unlimitedTime') else remaining_latency,
                eligible_models=eligible_models, execution_policy=policy,
                model_providers={mid: model.provider for mid, model in candidates.items()})
        else:
            result["routing"] = route_nodes(plan, profiles, method=request["method"],
                quality_min=request["qualityMin"], cost_max=remaining_cost, latency_max_ms=None if request.get("unlimitedTime") else remaining_latency,
                weights=Weights(**request["weights"]) if request["method"] == "B" else None,
                eligible_models=eligible_models, execution_policy=policy, reduce_dominated=configured_application,
                model_billing_modes={mid: model.billing_mode for mid, model in candidates.items()} if currency_reference else None,
                cash_max=budget.remaining_cash() if currency_reference else None,
                model_providers={mid: model.provider for mid, model in candidates.items()})
        if alternative_direct_plan is not None and live:
            if configuration is None or configuration.objective is None:
                raise ValueError('live route comparison requires a compiled v4 configuration')
            if request.get('contextPolicy') == 'selective-v1':
                result['route_comparison'] = {'policy_version': 'automatic-live-comparison-v1',
                    'status': 'unavailable', 'route': 'dag' if len(plan.nodes) > 1 else 'direct',
                    'reason': 'selective-context-direct-envelope-unverified',
                    'selected_candidate': 'generated-plan', 'generated_node_count': len(plan.nodes),
                    'selected_node_count': len(plan.nodes), 'multi_node_selected': len(plan.nodes) > 1}
            else:
                def prepare_direct_candidate():
                    direct_raw = deepcopy(alternative_direct_plan)
                    # 两条路线交付同一任务；不能用固定 1000 的 Direct 与更长的 DAG
                    # 最终交付比较，也不能把 DAG 中间产物相加当成 Direct 的输出。
                    final_forecast = plan.contracts[plan.final_node_id]['capability']['expected_output_tokens']
                    for row in direct_raw['nodes']:
                        if row['node_id'] == direct_raw['final_node_id']:
                            capability = row['contract']['capability']
                            capability['expected_output_tokens'] = final_forecast
                    direct = validate_plan(direct_raw,
                        required_criteria=request.get('acceptanceCriteria'))
                    direct, estimates = compile_generated_capacity(direct, node_task, candidates,
                        output_constraints=request.get('outputConstraints'), input_cap=input_cap,
                        prefix_policy=request.get('prefixPolicy', 'legacy'), source_faithfulness=bool(request.get('maxFinalRevisions', 0)),
                        tools=tool_runtime.schemas if tool_runtime is not None else None)
                    direct_profile = configured_profile(configuration, manifest, direct.to_dict(), task=request['task'],
                        input_forecasts={nid: row['forecast_input_tokens']
                                         for nid, row in estimates.items()},
                        cost_input_forecasts=({nid: row['routing_input_forecast_tokens']
                                               for nid, row in estimates.items()} if mixed or currency_reference else None))
                    direct_profiles = load_profile(direct_profile, manifest)
                    direct_admission = admission_diagnostics(direct, node_task, candidates, direct_profiles,
                        request['qualityMin'], output_constraints=request.get('outputConstraints'),
                        prefix_policy=request.get('prefixPolicy', 'legacy'), source_faithfulness=bool(request.get('maxFinalRevisions', 0)),
                        tools=tool_runtime.schemas if tool_runtime is not None else None)
                    direct_eligible = {nid: row['eligible_models'] for nid, row in direct_admission.items()}
                    direct_placement = None
                    if placement is not None:
                        direct_placement = new_record(privacy, manifest.models)
                        resolve_placement(plan=direct, models=candidates.values(), privacy=privacy,
                            classifier=classifier, node_views=static_node_views(direct, node_task),
                            record=direct_placement)
                        if direct_placement['status'] == 'no-local-candidate':
                            direct_eligible = {nid: [] for nid in direct_eligible}
                        else:
                            direct_eligible = restricted_eligible_models(direct_eligible, direct_placement)
                            direct_placement['judge_isolation'] = judge_isolation(direct_placement, review_judge)
                        placement_admission_diagnostics(direct_admission, direct_eligible, direct_placement)
                    if mixed:
                        direct_routing = route_nodes_mixed(direct, direct_profiles,
                            model_units={mid: model.billing_unit for mid, model in candidates.items()},
                            quality_min=request['qualityMin'], budgets=remaining_cost,
                            latency_max_ms=None if request.get('unlimitedTime') else remaining_latency,
                            eligible_models=direct_eligible, execution_policy=policy,
                            model_providers={mid: model.provider for mid, model in candidates.items()})
                    else:
                        direct_routing = route_nodes(direct, direct_profiles, method=request['method'],
                            quality_min=request['qualityMin'], cost_max=remaining_cost,
                            latency_max_ms=None if request.get('unlimitedTime') else remaining_latency,
                            weights=Weights(**request['weights']) if request['method'] == 'B' else None,
                            eligible_models=direct_eligible, execution_policy=policy,
                            reduce_dominated=configured_application,
                            model_billing_modes={mid: model.billing_mode for mid, model in candidates.items()} if currency_reference else None,
                            cash_max=budget.remaining_cash() if currency_reference else None,
                            model_providers={mid: model.provider for mid, model in candidates.items()})
                    return (direct, estimates, direct_profile, direct_profiles, direct_admission,
                            direct_eligible, direct_placement, direct_routing)
                try:
                    (direct, direct_estimates, direct_profile, direct_profiles, direct_admission,
                     direct_eligible, direct_placement, direct_routing) = prepare_direct_candidate()
                except ValueError as exc:
                    if not str(exc).startswith('automatic-plan-input-capacity-exceeded:'):
                        raise
                    direct_routing = {'status': 'no-feasible-route'}
                    direct_admission = {'answer': {'reason': 'input-capacity', 'detail': str(exc)}}
                    direct_eligible = {'answer': []}
                if mixed:
                    _, charged_calls = budget.snapshot()
                    judge_cost = (_shared_judge_forecast(review_judge, execution_task,
                        request.get('acceptanceCriteria'), candidates,
                        tool_evidence=tool_runtime is not None,
                        expected_answer_tokens=(plan.contracts[plan.final_node_id]['capability']['expected_output_tokens']
                            if currency_reference else None)) if result['review']['required'] else 0.0)
                    tool_limit = tool_runtime.max_calls if tool_runtime is not None else 0
                    tool_count = 0 if tool_limit == 'unlimited' else tool_limit
                    comparison = _compare_mixed_execution(
                        {'direct': direct_routing, 'dag': result['routing']},
                        candidates=candidates, charged_calls=charged_calls, judge=review_judge,
                        judge_cost=judge_cost, review_required=result['review']['required'],
                        tool_count=tool_count, input_cap=input_cap,
                        remaining_production=remaining_cost,
                        remaining_evaluation={unit: budget.remaining(unit, 'evaluation')
                            for unit in ('AFP', 'CNY')})
                    qualified_workers = {mid for routes in (direct_eligible, eligible_models)
                        for models in routes.values() for mid in models}
                    comparison['decision_factors'] = {
                        'qualified_execution_model_count': len(qualified_workers),
                        'quality_basis': selected_quality_basis(profile, result['routing'].get('assignments')),
                        'task_specific_dag_quality_gain_verified': False}
                    comparison['candidate_diagnostics'] = {
                        'direct': deepcopy(direct_routing.get('rejected_combinations', {})),
                        'dag': deepcopy(result['routing'].get('rejected_combinations', {}))}
                    comparison['excluded'] = {
                        'direct': {nid: row['reason'] for nid, row in direct_admission.items()},
                        'dag': {nid: row['reason'] for nid, row in result.get('plan_admission', {}).items()}}
                    comparison['model_admission'] = {
                        'direct': {nid: row.get('model_reasons', {}) for nid, row in direct_admission.items()},
                        'dag': {nid: row.get('model_reasons', {}) for nid, row in result.get('plan_admission', {}).items()}}
                    comparison['judge_forecast'] = 'same-final-answer-envelope-for-both-routes'
                    comparison['tool_call_limit'] = tool_limit
                    if comparison['status'] != 'selected':
                        result['routing']['status'] = 'no-feasible-route'
                else:
                    _, charged_calls = budget.snapshot()
                    planner_rows = [row for row in charged_calls if row['label'] in {'planner', 'planner-repair'}]
                    if any(row['status'] != 'billed' for row in planner_rows):
                        raise ValueError('planner usage is unconfirmed; route comparison stopped')
                    planner_cost = sum(row['charged'] for row in planner_rows)
                    planner_latency = (sum(row['latency_ms'] for row in planner_rows)
                        if all(isinstance(row.get('latency_ms'), (int, float)) for row in planner_rows) else None)
                    judge_cost = (_shared_judge_forecast(review_judge, execution_task,
                        request.get('acceptanceCriteria'), candidates,
                        tool_evidence=tool_runtime is not None,
                        expected_answer_tokens=(plan.contracts[plan.final_node_id]['capability']['expected_output_tokens']
                            if currency_reference else None)) if result['review']['required'] else 0.0)
                    tool_limit = tool_runtime.max_calls if tool_runtime is not None else 0
                    tool_count = 0 if tool_limit == 'unlimited' else tool_limit
                    allowances = {name: _bounded_tool_allowance(route, candidates, tool_count, input_cap)
                                  for name, route in (('direct', direct_routing), ('dag', result['routing']))}
                    cash_allowances = ({name: _bounded_tool_allowance(route, candidates, tool_count,
                        input_cap, cash_only=True)
                        for name, route in (('direct', direct_routing), ('dag', result['routing']))}
                        if currency_reference else None)
                    production_cash_remaining = budget.remaining_cash() if currency_reference else None
                    evaluation_cash_remaining = budget.remaining_cash('evaluation') if currency_reference else None
                    budget_shortfalls = {}
                    evaluation_remaining = budget.remaining('evaluation')
                    for name, route in (('direct', direct_routing), ('dag', result['routing'])):
                        if route['status'] == 'selected':
                            shortage = _route_budget_shortfall(route,
                                reference_allowance=allowances[name],
                                cash_allowance=cash_allowances[name] if currency_reference else 0,
                                judge_reference=judge_cost,
                                judge_is_metered=(currency_reference and review_judge.billing_mode != 'subscription'),
                                remaining_production=remaining_cost,
                                remaining_evaluation=evaluation_remaining,
                                remaining_cash=production_cash_remaining,
                                remaining_evaluation_cash=evaluation_cash_remaining)
                            if shortage:
                                budget_shortfalls[name] = shortage
                                route['status'] = 'no-feasible-route'
                    comparison = compare_executable_routes(direct_routing, result['routing'],
                        planner_cost=planner_cost, judge_cost=judge_cost,
                        planner_latency_ms=planner_latency, tool_allowances=allowances,
                        cash_costs={name: route['prediction']['cash_cost'] + cash_allowances[name]
                            if route.get('prediction') else 0
                            for name, route in (('direct', direct_routing), ('dag', result['routing']))}
                        if currency_reference else None)
                    qualified_workers = {mid for routes in (direct_eligible, eligible_models)
                        for models in routes.values() for mid in models}
                    direct_row, dag_row = comparison['direct'], comparison['dag']
                    comparison['decision_factors'] = {
                        'qualified_execution_model_count': len(qualified_workers),
                        'quality_basis': selected_quality_basis(profile, result['routing'].get('assignments')),
                        'task_specific_dag_quality_gain_verified': False,
                        'dag_extra_worker_cost': (dag_row['worker_cost'] - direct_row['worker_cost']
                            if direct_row is not None and dag_row is not None else None),
                    }
                    comparison['candidate_diagnostics'] = {
                        'direct': deepcopy(direct_routing.get('diagnostics', {})),
                        'dag': deepcopy(result['routing'].get('diagnostics', {}))}
                    comparison['quality_evidence_basis'] = {
                        'direct': selected_quality_basis(direct_profile if direct_routing.get('assignments') else None,
                            direct_routing.get('assignments')),
                        'dag': selected_quality_basis(profile, result['routing'].get('assignments'))}
                    comparison['latency_evidence'] = {
                        'direct': {nid: {mid: row.get('latency', {'source': 'configured-fixed', 'calibrated_sla': False})
                                    for mid, row in models.items()}
                                   for nid, models in (direct_profile.get('forecast_basis', {}) if direct_routing.get('prediction') else {}).items()},
                        'dag': {nid: {mid: row.get('latency', {'source': 'configured-fixed', 'calibrated_sla': False})
                                 for mid, row in models.items()}
                                for nid, models in result.get('routing_profile', {}).get('forecast_basis', {}).items()}}
                    comparison['billing_unit'] = manifest.billing_unit
                    comparison['judge_forecast'] = 'same-final-answer-envelope-for-both-routes'
                    comparison['tool_call_limit'] = tool_limit
                    comparison['budget_shortfalls'] = budget_shortfalls
                    comparison['excluded'] = {'direct': {nid: row['reason'] for nid, row in direct_admission.items()},
                                               'dag': {nid: row['reason'] for nid, row in result.get('plan_admission', {}).items()}}
                    comparison['model_admission'] = {
                        'direct': {nid: row.get('model_reasons', {}) for nid, row in direct_admission.items()},
                        'dag': {nid: row.get('model_reasons', {}) for nid, row in result.get('plan_admission', {}).items()}}
                comparison['estimate_scope'] = ('known-calls-only-unbounded-tool-continuations'
                    if tool_limit == 'unlimited' else 'known-calls-and-bounded-tool-continuations')
                comparison['complete_task_cost_bound'] = tool_limit != 'unlimited'
                if currency_reference:
                    comparison['judge_forecast'] = 'shared-planned-answer-usage-v1'
                    comparison['cost_forecast'] = {
                        'version': 'planned-usage-cost-v1',
                        'input_source': 'observed-byte-ratio-v1',
                        'output_source': 'explicit-profile-or-planned-node-output',
                        'judge_output_forecast': min(output_token_limit(review_judge), 1024),
                        'safety_reservations_unchanged': True,
                        'calibrated': False,
                    }
                    comparison['complete_task_cost_bound'] = False
                comparison['generated_node_count'] = len(plan.nodes)
                if comparison['route'] == 'dag' and len(plan.nodes) == 1:
                    # A planner call is not itself a split. Keep the generated plan and its
                    # actual forecast, but classify the selected execution as direct.
                    comparison['comparison_reason'] = comparison['reason']
                    comparison.update(route='direct', reason='generated-single-node',
                                      selected_candidate='generated-plan')
                elif comparison['route'] == 'direct':
                    comparison['selected_candidate'] = 'direct-template'
                elif comparison['route'] == 'dag':
                    comparison['selected_candidate'] = 'generated-plan'
                comparison['selected_node_count'] = (len(direct.nodes) if comparison.get('selected_candidate') == 'direct-template'
                    else len(plan.nodes) if comparison.get('selected_candidate') == 'generated-plan' else None)
                comparison['multi_node_selected'] = (comparison['selected_node_count'] > 1
                    if comparison['selected_node_count'] is not None else None)
                selected_direct = comparison.get('selected_candidate') == 'direct-template'
                comparison['decision_factors']['quality_basis'] = selected_quality_basis(
                    direct_profile if selected_direct else profile,
                    direct_routing.get('assignments') if selected_direct else result['routing'].get('assignments'))
                comparison['output_forecast'] = {
                    'version': 'shared-final-delivery-v1',
                    'generated_final_tokens': plan.contracts[plan.final_node_id]['capability']['expected_output_tokens'],
                    'direct_final_tokens': (direct.contracts[direct.final_node_id]['capability']['expected_output_tokens']
                        if direct_routing.get('assignments') else None),
                    'intermediate_outputs_added_to_direct': False,
                    'calibrated': False,
                }
                result['route_comparison'] = comparison
                if comparison.get('selected_candidate') == 'direct-template':
                    plan, profile, profiles = direct, direct_profile, direct_profiles
                    result['plan_origin'] = 'direct-after-probe'
                    result['plan'] = plan.to_dict()
                    result['plan_analysis'] = plan.diagnostics()
                    result['plan_analysis']['execution_mode'] = 'bounded-parallel' if policy.max_concurrency > 1 else 'serial'
                    result['routing_profile'] = profile
                    result['compiled_input_estimates'] = direct_estimates
                    result['plan_admission'] = direct_admission
                    result['routing'] = direct_routing
                    eligible_models = direct_eligible
                    if direct_placement is not None:
                        placement = direct_placement
                        result['privacy_placement'] = direct_placement
                        result['placement_state'] = 'ok'
                        guard = PlacementGuard(placement, candidates.values(), classifier=classifier)
                persist()
        if configured_application:
            result['routing']['actions'] = {nid: action_identity(candidates[mid])
                for nid, mid in result['routing']['assignments'].items()}
        persist()
        if result["routing"]["status"] != "selected":
            result["status"] = "no-feasible-route"
            for nid, row in result.get('plan_admission', {}).items():
                if row['reason']:
                    result['issues'].append(f"{nid}: {row['reason']}")
            if not result['issues']:
                result['issues'].append('no assignment satisfies quality, total cost and remaining time constraints')
            return result
        if mixed and result['review']['required']:
            selected_models = {mid: candidates[mid] for mid in result['routing']['assignments'].values()}
            judge_upper = _shared_judge_forecast(
                review_judge, execution_task, plan.acceptance_criteria,
                selected_models, tool_evidence=tool_runtime is not None)
            judge_unit = review_judge.billing_unit
            result['review']['cost_upper_bound'] = {'unit': judge_unit, 'amount': judge_upper}
            if judge_upper > budget.remaining(judge_unit, 'evaluation') + 1e-12:
                result['status'] = 'no-feasible-route'
                result['issues'].append(
                    f'final-judge: {judge_unit} evaluation budget below required upper bound '
                    f'({judge_upper:.6f})')
                persist()
                return result
            if live:
                try:
                    result['review']['protection'] = budget.protect_review(
                        review_judge, judge_upper, min_execution_calls=len(plan.nodes))
                except ValueError as exc:
                    result['status'] = 'no-feasible-route'
                    result['issues'].append(f'final-judge: {exc}')
                    persist()
                    return result
                persist()
        fallback_limit = request.get('maxNodeFallbacks', 0)
        result['recovery_policy'] = {'policy_version': 'node-fallback-v1', 'max_node_fallbacks': fallback_limit}
        recovery = NodeRecovery(plan, profiles, candidates, result['routing'], policy,
                                max_fallbacks=fallback_limit) if fallback_limit else None
        if mode in {"preflight", "plan"}:
            result["status"] = "preview" if mode == "preflight" else "planned"
            result["review"]["status"] = "not-run"
            return result
        result['generation_status'] = 'running'
        if live and before_call() <= review_reserve:
            result['review'].update(status='not-dispatched-insufficient-time', passed=False,
                reason='execution-would-consume-review-reserve')
            raise ValueError('task-deadline-exhausted')
        dynamic = DynamicDecomposition(request=request, manifest=manifest, configuration=configuration,
            profiles=profiles, planner=planner, budget=budget, policy=policy, task=node_task,
            result=result, persist=persist, deadline=execution_deadline,
            cancel_event=cancel_event, input_cap=input_cap,
            tools=tool_runtime.schemas if tool_runtime is not None else None,
            placement=placement, privacy=privacy, classifier=classifier) if live and request.get('maxDynamicSplits',0) else None
        dispatch_history = {candidates[c['model_id']].provider:c['dispatch_monotonic'] for c in budget.snapshot()[1]
            if 'dispatch_monotonic' in c and c['model_id'] in candidates}
        result["final_output"] = execute_nodes(plan, node_task, result["routing"]["assignments"],
            candidates, budget, policy, result, persist, started=started,
            deadline=execution_deadline, cancel_event=cancel_event, recovery=recovery,
            production_cap=None if mixed else request["costMax"],
            output_constraints=request.get('outputConstraints'), dynamic=dynamic, content_guard=content_guard,
            dispatch_history=dispatch_history, tool_runtime=tool_runtime, guard=guard,
            eligible_models=eligible_models,
            context_policy=node_context, prefix_policy=request.get("prefixPolicy", "legacy"), source_faithfulness=bool(request.get('maxFinalRevisions', 0)))
        result['generation_status'] = 'completed' if live else 'simulated'
        if live:
            known_failure = None
            if request.get('maxFinalRevisions', 0):
                result['time_contract_validation'] = check_review_time(request['task'], result['final_output'])
                if not result['time_contract_validation']['passed']:
                    result['issues'].append('review-time-contract-failed')
                    known_failure = {'passed': False, 'score': 0,
                        'review_contract': result['time_contract_validation']['version'],
                        'rationale': result['time_contract_validation']['reason']}
                    if not result['review']['required']:
                        result['status'] = 'quality-failed'
                        persist()
                        return result
            if content_guard is not None:
                result['content_validation'] = content_guard.validate(result['final_output'], final=True)
            result['format_validation'] = check_output_constraints(request.get('outputConstraints'), result['final_output'])
            if result['format_validation']['passed'] is False:
                result['issues'].append('output-length-exceeded')
                if request.get('maxFinalRevisions', 0) and result['review']['required']:
                    known_failure = {'passed': False, 'score': 0,
                        'rationale': (known_failure['rationale'] + ' ' if known_failure else '')
                            + '输出格式或长度不符合原任务限制，请按原任务重新整理完整答复。'}
            persist()  # 评审异常或进程中断不能丢失已生成的正文与确定性检查。
            if final_validator is not None:
                validation = final_validator(result['final_output'])
                if not isinstance(validation, dict) or type(validation.get('passed')) is not bool:
                    raise ValueError('invalid deterministic final validation')
                result['deterministic_validation'] = deepcopy(validation)
                if not validation['passed']:
                    result['status'] = 'quality-failed'
                    result['review'].update(status='blocked-deterministic-check', passed=False,
                        reason='known-answer-contract-failed')
                    result['issues'].append('deterministic-final-check-failed')
                    persist()
                    if not (request.get('maxFinalRevisions', 0) and result['review']['required']):
                        return result
                    # 校验器可能包含隐藏标准答案；不给纠正模型泄露 expected／actual。
                    known_failure = {'passed': False, 'score': 0,
                        'rationale': '确定性输出校验未通过，请依据原任务和材料独立复核计算及格式。'}
                    result['status'] = 'started'
            tool_evidence = None
            if tool_runtime is not None or required_tools['required']:
                tool_evidence, validation = collect_tool_evidence(required_tools,
                    tool_runtime.snapshot()[tool_record_start:] if tool_runtime else [], available=tool_runtime is not None)
                validation['message'] = validation_message(validation)
                result['tool_validation'] = validation
                if not validation['passed']:
                    result['status'] = 'tool-requirement-failed'
                    result['review'].update(status='blocked-tool-evidence', passed=False,
                                            reason=validation['reason'])
                    result['issues'].append(validation['message'])
                    persist()
                    return result  # 无法验收时不再花费最终 Judge，也不替宿主补跑工具。
            if request.get('maxFinalRevisions', 0):
                result['source_state_validation'] = check_source_state(request['task'], result['final_output'],
                    tool_evidence=tool_evidence)
                if not result['source_state_validation']['passed']:
                    result['issues'].append('source-state-attribution-failed')
                    known_failure = {'passed': False, 'score': 0,
                        'review_contract': result['source_state_validation']['version'],
                        'rationale': (known_failure['rationale'] + ' ' if known_failure else '')
                            + result['source_state_validation']['reason']}
                    if not result['review']['required']:
                        result['status'] = 'quality-failed'
                        persist()
                        return result
            if result['review']['required'] and placement is not None:
                isolation = judge_isolation(placement, review_judge)
                placement['judge_isolation'] = isolation
                if not isolation['satisfied']:
                    # 评审会读到节点输出；不满足隔离时不发起调用，明确失败并记录。
                    isolation['detail'] = 'judge-not-local'
                    placement['violations'].append({**isolation, 'action': 'blocked'})
                    result['issues'].append('final-judge: privacy-judge-not-local')
                    result['status'] = 'privacy-route-blocked'
                    persist()
                    return result
                if tool_evidence is not None:
                    evidence_isolation = role_isolation(view=json.dumps(tool_evidence, ensure_ascii=False),
                        privacy=privacy, model=review_judge, role='judge', classifier=classifier,
                        source='tool-evidence')
                    placement['tool_evidence_isolation'] = evidence_isolation
                    if not evidence_isolation['satisfied']:
                        result['status'] = 'privacy-route-blocked'
                        result['issues'].append('final-judge: privacy-tool-evidence-blocked')
                        persist()
                        return result
            if result['review']['required']:
                if before_call() < review_reserve:
                    result['status'] = 'review-time-exhausted'
                    result['review'].update(status='not-dispatched-insufficient-time', passed=False,
                        reason='final-judge-insufficient-time')
                    result['issues'].append('final-judge-insufficient-time')
                    persist()
                    return result
                result['review']['status'] = 'running'
                persist()
                review_deadline = budget.deadline(started + deadline_ms / 1000)
                if request.get('reviewTimeoutMs'):
                    review_deadline = min(review_deadline, time.monotonic() + request['reviewTimeoutMs'] / 1000)
                result['review']['effective_wait_ms'] = (None if review_deadline == float('inf') else
                    max(0, round((review_deadline-time.monotonic())*1000)))
                persist()
                judged = known_failure or evaluate_text(budget, review_judge, execution_task, result["final_output"],
                    criteria=plan.acceptance_criteria, label="final-judge", deadline=review_deadline,
                    tool_evidence=tool_evidence, evidence_refs=bool(request.get('maxFinalRevisions', 0)),
                    deterministic_receipt=deterministic_receipt(result.get('deterministic_validation'), result['final_output']))
                result["evaluation"] = judged
                result["review"].update(status="completed", score=judged['score'], passed=judged['passed'],
                                        contract_version=judged.get('review_contract'))
                persist()
                result["status"] = "completed" if judged["passed"] and judged['score'] >= request['qualityMin'] else "quality-failed"
                if result['status'] == 'quality-failed' and request.get('maxFinalRevisions', 0):
                    record = {'version': CORRECTION_VERSION, 'maximum': 1, 'attempt': 0,
                              'status': 'pending', 'initial_evaluation': deepcopy(judged)}
                    if result.get('deterministic_validation') is not None:
                        record['initial_deterministic_validation'] = deepcopy(result['deterministic_validation'])
                    record['initial_format_validation'] = deepcopy(result['format_validation'])
                    if result.get('time_contract_validation') is not None:
                        record['initial_time_contract_validation'] = deepcopy(result['time_contract_validation'])
                    if result.get('source_state_validation') is not None:
                        record['initial_source_state_validation'] = deepcopy(result['source_state_validation'])
                    result['final_correction'] = record
                    result['status'] = 'started'
                    result['review']['status'] = 'correcting'
                    persist()
                    def check_corrected(answer):
                        rows = [check_output_constraints(request.get('outputConstraints'), answer)]
                        if content_guard is not None:
                            rows.append(content_guard.validate(answer, final=True))
                        rows.append(check_review_time(request['task'], answer))
                        rows.append(check_source_state(request['task'], answer, tool_evidence=tool_evidence))
                        if final_validator is not None:
                            rows.append(final_validator(answer))
                        return {'passed': all(row.get('passed') is not False for row in rows), 'checks': rows}
                    corrected, revised = correct_final(budget,
                        candidates[result['routing']['assignments'][plan.final_node_id]], review_judge,
                        execution_task, result['final_output'], judged, plan.acceptance_criteria,
                        record=record, persist=persist,
                        execution_deadline=budget.deadline(execution_deadline),
                        task_deadline=budget.deadline(started+deadline_ms/1000),
                        review_timeout_ms=request.get('reviewTimeoutMs'), cancel_event=cancel_event,
                        tool_evidence=tool_evidence, output_constraints=request.get('outputConstraints'),
                        validate=check_corrected,
                        admit=(None if guard is None else lambda messages: guard.require(plan.final_node_id,
                            result['routing']['assignments'][plan.final_node_id], messages, stage='final-correction')),
                        production_cap=request['costMax'])
                    result['final_output'] = corrected
                    result['format_validation'] = check_output_constraints(request.get('outputConstraints'), corrected)
                    result['time_contract_validation'] = check_review_time(request['task'], corrected)
                    result['source_state_validation'] = check_source_state(request['task'], corrected,
                        tool_evidence=tool_evidence)
                    if final_validator is not None:
                        result['deterministic_validation'] = deepcopy(record['validation']['checks'][-1])
                    if revised is not None:
                        result['evaluation'] = revised
                        result['review'].update(status='completed', score=revised['score'], passed=revised['passed'],
                            contract_version=revised.get('review_contract'), correction_count=1)
                        result['review'].pop('reason', None)
                        result['status'] = ('completed' if revised['passed'] and revised['score'] >= request['qualityMin']
                                            else 'quality-failed')
                    else:
                        result['status'] = 'quality-failed'
                        result['review'].update(status='blocked-deterministic-check', passed=False)
                    record['accepted'] = result['status'] == 'completed'
                    if record['accepted']:
                        result['issues'] = [issue for issue in result['issues']
                            if issue not in {'deterministic-final-check-failed','output-length-exceeded',
                                             'review-time-contract-failed','source-state-attribution-failed'}]
                    if record['status'] == 'reviewed':
                        record['status'] = 'accepted' if record['accepted'] else 'rejected'
                    persist()
            else:
                result["evaluation"] = None
                result["review"]["status"] = "skipped"
                result["status"] = "completed"
            if result['format_validation']['passed'] is False:
                result['status'] = 'output-constraint-failed'
        else:
            result["status"] = "simulated"
            result["review"]["status"] = "not-run"
        before_call()  # Detect a final response that arrived after the task deadline.
    except ToolTurnConcluded as exc:
        result.update(status='completed', generation_status='tool-concluded', final_output=exc.content)
        result['issues'].append('host-tool-concluded-turn; remaining DAG and evaluation skipped')
    except Exception as exc:
        if result['generation_status'] == 'running':
            result['generation_status'] = 'failed'
        result["status"] = ("cancelled" if isinstance(exc, CancelledError) else
            'privacy-route-blocked' if isinstance(exc, PrivacyRouteViolation) else
            'content-verification-failed' if isinstance(exc, NodeSemanticFailure) else "failed")
        # Provider exception strings may contain credentials or response bodies.
        detail = str(exc) if isinstance(exc, (ValueError, json.JSONDecodeError, CancelledError)) else type(exc).__name__
        if isinstance(exc, ModelInvocationError):
            failure = exc.public_details()
            detail = 'ModelInvocationError: ' + str(failure['failure_type'])
            if 'http_status' in failure:
                detail += ' (HTTP ' + str(failure['http_status']) + ')'
            if 'timeout_ms' in failure:
                detail += ' (request timeout_ms=' + str(failure['timeout_ms']) + ')'
            if 'phase' in failure:
                detail += ' (phase=' + str(failure['phase']) + ')'
        if isinstance(exc, ValueError) and str(exc) == 'task-deadline-exhausted':
            completed = [n['node_id'] for n in result['nodes'] if n.get('status') == 'ok']
            planned = [n['node_id'] for n in (result.get('plan') or {}).get('nodes', [])]
            pending = [node_id for node_id in planned if node_id not in completed]
            result['deadline_failure'] = {
                'limit_ms': deadline_ms,
                'elapsed_execution_ms': round((time.monotonic() - started - budget.planning_elapsed) * 1000),
                'excluded_planning_ms': round(budget.planning_elapsed * 1000),
                'completed_nodes': completed, 'unfinished_nodes': pending,
            }
            detail += f" (任务执行期限 {deadline_ms / 1000:g} 秒；已完成 {len(completed)}/{len(planned)} 节点；预算及上下文放开不解除时间限制)"
        if result.get('review', {}).get('status') in {'running', 'correcting'}:
            result['review'].update(status='failed', passed=False, reason=detail[:500])
        correction = result.get('final_correction')
        if correction and correction['status'] == 'pending':
            correction.update(status='not-dispatched', reason=detail[:500], accepted=False)
        result["issues"].append(detail[:500])
    finally:
        if mixed:
            budget.release_review_protection()
        persist()
    return result
