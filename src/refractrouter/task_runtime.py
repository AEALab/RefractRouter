"""Text-task orchestration with explicit planning, assignment, execution and judging."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Callable

from .responses_api import output_token_limit
from .model_selection import Weights
from .routing_actions import action_identity
from .node_routing import load_profile, number, route_nodes
from .node_recovery import NodeRecovery, validate_fallback_limit
from .openai_compatible import ChatResponse, ModelInvocationError
from .task_budget import TaskCallBudget
from .task_scheduling import ExecutionPolicy
from .task_execution import execute_nodes
from .task_evaluation import evaluate_text
from .output_constraints import check_output_constraints, validate_output_constraints
from concurrent.futures import CancelledError
from .task_plan import PLANNER_SYSTEM, preview_plan, text, validate_plan
from .task_contracts import decode_output, string_list
from .planning_support import execution_support, compile_generated_capacity, admission_diagnostics, generate_plan
from .configured_routing import configured_profile
from .compact_planning import COMPACT_PLANNER_SYSTEM, planner_model, generate_compact
from .dependency_guard import NodeSemanticFailure
from .task_inputs import prepare_inputs
from .dynamic_decomposition import DynamicDecomposition

AGENT_PLAN_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"


def validate_request(raw):
    allowed = {"task", "mode", "method", "qualityMin", "costMax", "latencyMaxMs", "weights",
               "plan", "plannerModelId", "maxProductionCost", "maxEvaluationCost", "acceptanceCriteria",
               "maxConcurrency", "providerConcurrency", "providerMinIntervalMs", "maxNodeFallbacks", "outputConstraints", "maxPlanRepairs",
               "planningMode", "plannerMaxOutputTokens", "plannerTimeoutMs", "maxDynamicSplits", "verifyDependencies"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("unknown task request fields")
    ExecutionPolicy.from_request(raw)
    validate_fallback_limit(raw.get('maxNodeFallbacks', 0))
    if type(raw.get('maxPlanRepairs', 0)) is not int or not 0 <= raw.get('maxPlanRepairs', 0) <= 1:
        raise ValueError('maxPlanRepairs must be an integer in 0..1')
    if raw.get('planningMode', 'full') not in ('full', 'compact'):
        raise ValueError('planningMode must be full or compact')
    for key, default, low, high in (('plannerMaxOutputTokens',1200,256,2048),
            ('plannerTimeoutMs',12000,1000,30000), ('maxDynamicSplits',0,0,2)):
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
             configured_application=False, configuration=None, context_limit_bytes=120_000, input_cap=131_072):
    request = validate_request(request)
    if not isinstance(conversation_context, str) or len(conversation_context.encode()) > context_limit_bytes:
        raise ValueError('invalid conversation context')
    planning_task, execution_task, content_guard = prepare_inputs(request, conversation_context)
    validate_models(manifest, configured_application=configured_application)
    profiles = load_profile(profile, manifest)
    policy = ExecutionPolicy.from_request(request)
    known_providers = {m.provider for m in manifest.models}
    if (set(policy.provider_concurrency) | set(policy.provider_min_interval_ms)) - known_providers:
        raise ValueError("unknown provider in execution policy")
    if policy.max_concurrency > 1 and any(m.wire_api == "dsh-llm" for m in manifest.models):
        raise ValueError("parallel tasks require direct HTTP manifests; stdio bridge is synchronous")
    mode = request["mode"]
    live = mode in {"plan", "run"}
    if live and profile["kind"] != "empirical" and not (configured_application and profile["kind"] == "configured"):
        raise ValueError("live tasks require an empirical routing profile, not synthetic metrics")
    if live and client is None:
        raise ValueError("live execution requires a model client")
    if live and getattr(client, "max_retries", 0) != 0:
        raise ValueError("text tasks require a zero-retry client")
    candidates = {m.model_id: m for m in manifest.candidates}
    planner, planner_basis = planner_model(candidates, configuration=configuration,
        explicit=request.get('plannerModelId'), output_cap=request.get('plannerMaxOutputTokens',1200))
    planner_id = planner.model_id
    if planner_id not in candidates:
        raise ValueError("plannerModelId must be a candidate in the manifest")
    budget = TaskCallBudget(client if live else DemoTaskClient(),
                          production_limit if live else 1e12, evaluation_limit if live else 1e12,
                          max_calls=10 + request.get('maxPlanRepairs',0) + 2*request.get('maxDynamicSplits',0)
                              if request.get('maxDynamicSplits',0) else None,
                          capture_payload=True)
    started = time.monotonic()
    deadline_ms = request["latencyMaxMs"]
    result = {"schema_version": "task-run-v1", "mode": mode, "status": "started", "task": request["task"],
              "plan_origin": "provided" if "plan" in request else "model" if live else "template-preview",
              "planner_output": None, "planner_prompt_sha256": hashlib.sha256(PLANNER_SYSTEM.encode()).hexdigest(),
              "plan": None, "plan_analysis": None, "routing": None, "nodes": [], "final_output": "", "evaluation": None,
              "conversation_context_sha256": hashlib.sha256(conversation_context.encode()).hexdigest(),
              "billing_unit": manifest.billing_unit, "charged": {},
              "calls": [], "issues": [], "profile_scope": profile["scope"],
              "generation_status": "not-started",
              "format_validation": check_output_constraints(request.get('outputConstraints')),
              "profile_provenance": profile["provenance"],
              "limitations": ["Text generation only; no shell, retrieval or filesystem actions.",
                              "Node profile estimates may not transfer to this task; quality is a proxy, not a guarantee.",
                              "调度受并发上限和派发间隔约束；预测不是任务 p95。取消不保证已派发请求停止计费。"]}
    result['planner_selection'] = {'model_id': planner_id, 'basis': planner_basis,
        'output_cap': output_token_limit(planner if request.get('planningMode')=='compact' else candidates[planner_id]),
        'timeout_ms': request.get('plannerTimeoutMs',12000) if request.get('planningMode')=='compact' else deadline_ms}
    if content_guard is not None:
        result['dependency_evidence'] = content_guard.evidence()
    if configuration is not None and not configured_application:
        raise ValueError('automatic configuration requires configured application mode')
    def persist():
        result["charged"], result["calls"] = budget.snapshot()
        if configured_application:
            actions = {m.model_id: action_identity(m) for m in manifest.models}
            for call in result['calls']:
                call['route'] = actions[call['model_id']]
        result["wall_time_ms"] = round((time.monotonic() - started) * 1000)
        checkpoint(result)
    budget.on_reserve = lambda reservation: persist()
    def before_call():
        remaining = deadline_ms / 1000 - (time.monotonic() - started)
        if cancel_event is not None and cancel_event.is_set():
            budget.stop()
            raise CancelledError("task-cancelled")
        if remaining <= 0:
            raise ValueError("task-deadline-exhausted")
        return remaining
    try:
        if "plan" in request:
            plan = validate_plan(request["plan"], required_criteria=request.get("acceptanceCriteria"))
            if request.get('maxDynamicSplits',0) and not plan.contracts:
                raise ValueError('dynamic decomposition requires v2 node contracts')
        elif live:
            before_call()
            if request.get('planningMode') == 'compact':
                result['compact_planning'] = {}
                result['planner_prompt_sha256'] = hashlib.sha256(COMPACT_PLANNER_SYSTEM.encode()).hexdigest()
                plan = generate_compact(budget, planner, {'task': planning_task,
                    'parallel_capacity': policy.max_concurrency}, result['compact_planning'],
                    criteria=request.get('acceptanceCriteria'), cost_limit=request['costMax'],
                    deadline=min(started+deadline_ms/1000, time.monotonic()+request.get('plannerTimeoutMs',12000)/1000),
                    persist=persist, repairs=request.get('maxPlanRepairs',0),
                    output_cap=max(output_token_limit(m) for m in candidates.values()))
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
                 "remaining_production_cost": min(request['costMax'], budget.remaining()),
                 "remaining_time_ms": before_call() * 1000}, ensure_ascii=False)},
                ]
                plan = generate_plan(budget, candidates[planner_id], messages, result,
                    required_criteria=request.get('acceptanceCriteria'), max_repairs=request.get('maxPlanRepairs',0),
                    cost_limit=request['costMax'], remaining=before_call, persist=persist)
            result['generated_plan'] = plan.to_dict()
            if configuration is not None:
                plan, estimates = compile_generated_capacity(plan, execution_task, candidates,
                    output_constraints=request.get('outputConstraints'), input_cap=input_cap)
                result['compiled_input_estimates'] = estimates
                profile = configured_profile(configuration, manifest, plan.to_dict(),
                    input_forecasts={nid: row['forecast_input_tokens'] for nid, row in estimates.items()})
                profiles = load_profile(profile, manifest)
                result['routing_profile'] = profile
        else:
            plan = preview_plan(request["task"], required_criteria=request.get("acceptanceCriteria"))
        before_call()
        result["plan"] = plan.to_dict()
        result['plan_ready_ms'] = round((time.monotonic()-started)*1000)
        result["plan_analysis"] = plan.diagnostics()
        result["plan_analysis"]["execution_mode"] = "bounded-parallel" if policy.max_concurrency > 1 else "serial"
        result["execution_policy"] = policy.to_dict()
        persist()
        eligible_models = {}
        for node in plan.nodes:
            capability = plan.contracts.get(node.node_id, {}).get("capability")
            eligible_models[node.node_id] = [mid for mid, model in candidates.items() if not capability or (
                capability["input_budget_tokens"] + output_token_limit(model) <= model.context_window
                and capability["expected_output_tokens"] <= output_token_limit(model))]
        if live and 'plan' not in request:
            result['plan_admission'] = admission_diagnostics(plan, execution_task, candidates, profiles,
                request['qualityMin'], output_constraints=request.get('outputConstraints'))
            eligible_models = {nid: row['eligible_models'] for nid, row in result['plan_admission'].items()}
        remaining_cost = min(max(0, request["costMax"] - budget.snapshot()[0]['production']), budget.remaining())
        remaining_latency = max(0, deadline_ms - (time.monotonic() - started) * 1000) if live else deadline_ms
        result["routing"] = route_nodes(plan, profiles, method=request["method"],
            quality_min=request["qualityMin"], cost_max=remaining_cost, latency_max_ms=remaining_latency,
            weights=Weights(**request["weights"]) if request["method"] == "B" else None,
            eligible_models=eligible_models, execution_policy=policy,
            model_providers={mid: model.provider for mid, model in candidates.items()})
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
        fallback_limit = request.get('maxNodeFallbacks', 0)
        result['recovery_policy'] = {'policy_version': 'node-fallback-v1', 'max_node_fallbacks': fallback_limit}
        recovery = NodeRecovery(plan, profiles, candidates, result['routing'], policy,
                                max_fallbacks=fallback_limit) if fallback_limit else None
        if mode in {"preflight", "plan"}:
            result["status"] = "preview" if mode == "preflight" else "planned"
            return result
        result['generation_status'] = 'running'
        dynamic = DynamicDecomposition(request=request, manifest=manifest, configuration=configuration,
            profiles=profiles, planner=planner, budget=budget, policy=policy, task=execution_task,
            result=result, persist=persist, deadline=started+deadline_ms/1000,
            cancel_event=cancel_event) if live and request.get('maxDynamicSplits',0) else None
        dispatch_history = {candidates[c['model_id']].provider:c['dispatch_monotonic'] for c in budget.snapshot()[1]
            if 'dispatch_monotonic' in c and c['model_id'] in candidates}
        result["final_output"] = execute_nodes(plan, execution_task, result["routing"]["assignments"],
            candidates, budget, policy, result, persist, started=started,
            deadline=started + deadline_ms / 1000, cancel_event=cancel_event, recovery=recovery,
            production_cap=request["costMax"],
            output_constraints=request.get('outputConstraints'), dynamic=dynamic, content_guard=content_guard,
            dispatch_history=dispatch_history)
        result['generation_status'] = 'completed' if live else 'simulated'
        if live:
            if content_guard is not None:
                result['content_validation'] = content_guard.validate(result['final_output'], final=True)
            result['format_validation'] = check_output_constraints(request.get('outputConstraints'), result['final_output'])
            if result['format_validation']['passed'] is False:
                result['issues'].append('output-length-exceeded')
            persist()  # 评审异常或进程中断不能丢失已生成的正文与确定性检查。
            before_call()
            judged = evaluate_text(budget, manifest.judge, execution_task, result["final_output"],
                criteria=plan.acceptance_criteria, label="final-judge", deadline=started + deadline_ms / 1000)
            result["evaluation"] = judged
            result["status"] = "completed" if judged["passed"] and judged['score'] >= request['qualityMin'] else "quality-failed"
            if result['format_validation']['passed'] is False:
                result['status'] = 'output-constraint-failed'
        else:
            result["status"] = "simulated"
        before_call()  # Detect a final response that arrived after the task deadline.
    except Exception as exc:
        if result['generation_status'] == 'running':
            result['generation_status'] = 'failed'
        result["status"] = ("cancelled" if isinstance(exc, CancelledError) else
            'content-verification-failed' if isinstance(exc, NodeSemanticFailure) else "failed")
        # Provider exception strings may contain credentials or response bodies.
        detail = str(exc) if isinstance(exc, (ValueError, json.JSONDecodeError, CancelledError)) else type(exc).__name__
        if isinstance(exc, ModelInvocationError):
            failure = exc.public_details()
            detail = 'ModelInvocationError: ' + str(failure['failure_type'])
            if 'http_status' in failure:
                detail += ' (HTTP ' + str(failure['http_status']) + ')'
        result["issues"].append(detail[:500])
    finally:
        persist()
    return result
