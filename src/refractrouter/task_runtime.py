"""Text-task orchestration with explicit planning, assignment, execution and judging."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Callable

from .model_selection import Weights
from .node_routing import load_profile, number, route_nodes
from .openai_compatible import ChatResponse
from .task_budget import TaskCallBudget
from .task_scheduling import ExecutionPolicy
from .task_execution import execute_nodes
from .task_evaluation import evaluate_text
from concurrent.futures import CancelledError
from .task_plan import PLANNER_SYSTEM, preview_plan, text, validate_plan
from .task_contracts import decode_output, string_list

AGENT_PLAN_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"


def validate_request(raw):
    allowed = {"task", "mode", "method", "qualityMin", "costMax", "latencyMaxMs", "weights",
               "plan", "plannerModelId", "maxProductionCost", "maxEvaluationCost", "acceptanceCriteria",
               "maxConcurrency", "providerConcurrency", "providerMinIntervalMs"}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError("unknown task request fields")
    ExecutionPolicy.from_request(raw)
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


def validate_models(manifest):
    for model in manifest.models:
        for field in ("input_cost_per_1k", "output_cost_per_1k", "cached_input_cost_per_1k"):
            value = getattr(model, field)
            if value is not None:
                number(value, field)
        if model.cached_input_cost_per_1k is not None and model.cached_input_cost_per_1k > model.input_cost_per_1k:
            raise ValueError("cached pricing must not exceed the uncached reserve")
        if model.provider == "ark-plan" or model.billing_unit == "AFP" or (model.base_url and "volces.com" in model.base_url):
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
             checkpoint: Callable[[dict], None] = lambda result: None, cancel_event=None):
    request = validate_request(request)
    validate_models(manifest)
    profiles = load_profile(profile, manifest)
    policy = ExecutionPolicy.from_request(request)
    known_providers = {m.provider for m in manifest.models}
    if (set(policy.provider_concurrency) | set(policy.provider_min_interval_ms)) - known_providers:
        raise ValueError("unknown provider in execution policy")
    if policy.max_concurrency > 1 and any(m.wire_api == "dsh-llm" for m in manifest.models):
        raise ValueError("parallel tasks require direct HTTP manifests; stdio bridge is synchronous")
    mode = request["mode"]
    live = mode in {"plan", "run"}
    if live and profile["kind"] != "empirical":
        raise ValueError("live tasks require an empirical routing profile, not synthetic metrics")
    if live and client is None:
        raise ValueError("live execution requires a model client")
    if live and getattr(client, "max_retries", 0) != 0:
        raise ValueError("text tasks require a zero-retry client")
    candidates = {m.model_id: m for m in manifest.candidates}
    planner_id = request.get("plannerModelId") or min(candidates.values(), key=lambda m: (m.input_cost_per_1k + m.output_cost_per_1k, m.model_id)).model_id
    if planner_id not in candidates:
        raise ValueError("plannerModelId must be a candidate in the manifest")
    budget = TaskCallBudget(client if live else DemoTaskClient(),
                          production_limit if live else 1e12, evaluation_limit if live else 1e12, capture_payload=True)
    started = time.monotonic()
    deadline_ms = request["latencyMaxMs"]
    result = {"schema_version": "task-run-v1", "mode": mode, "status": "started", "task": request["task"],
              "plan_origin": "provided" if "plan" in request else "model" if live else "template-preview",
              "planner_output": None, "planner_prompt_sha256": hashlib.sha256(PLANNER_SYSTEM.encode()).hexdigest(),
              "plan": None, "plan_analysis": None, "routing": None, "nodes": [], "final_output": "", "evaluation": None,
              "billing_unit": manifest.billing_unit, "charged": {},
              "calls": [], "issues": [], "profile_scope": profile["scope"],
              "profile_provenance": profile["provenance"],
              "limitations": ["Text generation only; no shell, retrieval or filesystem actions.",
                              "Node profile estimates may not transfer to this task; quality is a proxy, not a guarantee.",
                              "调度受并发上限和派发间隔约束；预测不是任务 p95。取消不保证已派发请求停止计费。"]}
    def persist():
        result["charged"], result["calls"] = budget.snapshot()
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
        elif live:
            before_call()
            reply = budget.complete(candidates[planner_id], [
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user", "content": json.dumps({"task": request["task"],
                 "acceptance_criteria": request.get("acceptanceCriteria"), "execution_policy": policy.to_dict()}, ensure_ascii=False)},
            ], label="planner", json_mode=True, timeout_seconds=before_call())
            result["planner_output"] = reply.content
            plan = validate_plan(json.loads(reply.content), required_criteria=request.get("acceptanceCriteria"), require_v2=True)
        else:
            plan = preview_plan(request["task"], required_criteria=request.get("acceptanceCriteria"))
        before_call()
        result["plan"] = plan.to_dict()
        result["plan_analysis"] = plan.diagnostics()
        result["plan_analysis"]["execution_mode"] = "bounded-parallel" if policy.max_concurrency > 1 else "serial"
        result["execution_policy"] = policy.to_dict()
        eligible_models = {}
        for node in plan.nodes:
            capability = plan.contracts.get(node.node_id, {}).get("capability")
            eligible_models[node.node_id] = [mid for mid, model in candidates.items() if not capability or (
                capability["input_budget_tokens"] + min(model.max_output_tokens, 8192) <= model.context_window
                and capability["expected_output_tokens"] <= min(model.max_output_tokens, 8192))]
        remaining_cost = min(request["costMax"], budget.remaining())
        remaining_latency = max(0, deadline_ms - (time.monotonic() - started) * 1000) if live else deadline_ms
        result["routing"] = route_nodes(plan, profiles, method=request["method"],
            quality_min=request["qualityMin"], cost_max=remaining_cost, latency_max_ms=remaining_latency,
            weights=Weights(**request["weights"]) if request["method"] == "B" else None,
            eligible_models=eligible_models, execution_policy=policy,
            model_providers={mid: model.provider for mid, model in candidates.items()})
        if result["routing"]["status"] != "selected":
            result["status"] = "no-feasible-route"
            return result
        if mode in {"preflight", "plan"}:
            result["status"] = "preview" if mode == "preflight" else "planned"
            return result
        result["final_output"] = execute_nodes(plan, request["task"], result["routing"]["assignments"],
            candidates, budget, policy, result, persist, started=started,
            deadline=started + deadline_ms / 1000, cancel_event=cancel_event)
        if live:
            before_call()
            judged = evaluate_text(budget, manifest.judge, request["task"], result["final_output"],
                criteria=plan.acceptance_criteria, label="final-judge", deadline=started + deadline_ms / 1000)
            result["evaluation"] = judged
            result["status"] = "completed" if judged["passed"] else "quality-failed"
        else:
            result["status"] = "simulated"
        before_call()  # Detect a final response that arrived after the task deadline.
    except Exception as exc:
        result["status"] = "cancelled" if isinstance(exc, CancelledError) else "failed"
        # Provider exception strings may contain credentials or response bodies.
        detail = str(exc) if isinstance(exc, (ValueError, json.JSONDecodeError, CancelledError)) else type(exc).__name__
        result["issues"].append(detail[:500])
    finally:
        persist()
    return result
