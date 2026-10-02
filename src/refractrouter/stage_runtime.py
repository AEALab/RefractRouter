"""Stage 协作运行时；复用核心准入、账本及异步本地 Judge。"""
from copy import deepcopy
import time

from .stage_hybrid import VERSION, initial_state, observe, decision_request, parse_answers, transition
from .task_budget import request_input_bound
from .jev_bridge import (MAX_INPUT_TOKENS as JEV_MAX_INPUT_TOKENS,
                         build_request as build_jev_request, cost_cny as jev_cost_cny)


class StageHybridRuntime:
    def start_hybrid_stage(self, run, *, stage_config=None, model_ids=None,
                           state_key="stageHybrid", rule_version=VERSION):
        c, flow, s = run["config"], run["flow"], run["state"]
        stage_config = stage_config or c["stage"]
        model_ids = model_ids or {role: c["roles"][role] for role in ("efficient", "capable")}
        flow["stageContext"] = {"config": deepcopy(stage_config), "modelIds": deepcopy(model_ids),
                                "stateKey": state_key, "ruleVersion": rule_version}
        state = s.setdefault(state_key, initial_state())
        proposed, trigger, reason = observe(state, flow["messages"], flow["tools"],
            flow["events"], s["step"], stage_config)
        flow["stagePlan"] = {"state": proposed, "trigger": trigger, "reason": reason}
        if not trigger:
            return self._emit_hybrid_stage(run, proposed, reason)
        # 派发 Judge 前保护可承受的执行路线；Jev 还需要独立现金预算。
        affordable = []
        execution_bounds = {}
        for role in ("efficient", "capable"):
            try:
                model = self.admit(run, role, deepcopy(flow["messages"]), flow["tools"],
                                   model_id=model_ids[role])
                cap = min(model.max_output_tokens, flow.get("maxTokens") or model.max_output_tokens)
                if request_input_bound(flow["messages"], flow["tools"]) + cap > model.context_window:
                    continue
                cost = self._cost_bound(model, flow["messages"], flow["tools"], flow.get("maxTokens"))
                if cost <= run["budget"].remaining(model.billing_unit):
                    affordable.append(role)
                    execution_bounds[role] = (model.billing_unit, cost)
            except ValueError:
                continue
        if not affordable or (c["max_calls"] and len(run["budget"].records) >= c["max_calls"]):
            raise ValueError("Stage 判别前没有合格且可承受的执行路线")
        if stage_config["judge"]["type"] == "jev":
            if len(affordable) != 2:
                raise ValueError("Stage Jev 判别前必须确保两条执行路线均可用")
            jev_bound = jev_cost_cny(JEV_MAX_INPUT_TOKENS, c["jev"]["fxRate"])
            # 判别可能选择任一执行路线；先保护 Judge 加最贵的互斥路线。
            required = {}
            for unit, cost in execution_bounds.values():
                required[unit] = max(required.get(unit, 0), cost)
            required["CNY"] = required.get("CNY", 0) + jev_bound
            if any(amount > run["budget"].remaining(unit) for unit, amount in required.items()):
                raise ValueError("Stage Jev 判别前预算不足以覆盖判别与可能选中的执行模型")
            if c["max_calls"] and len(run["budget"].records) + 2 > c["max_calls"]:
                raise ValueError("Stage 判别及后续执行的调用名额不足")
        judge_request = decision_request(flow["messages"], proposed["events"],
            self._resolve_model(run, model_id=model_ids["efficient"]),
            self._resolve_model(run, model_id=model_ids["capable"]),
            stage_config["maxJudgeInputBytes"])
        flow["stageRequest"] = judge_request
        if not judge_request["complete"]:
            return self._finish_hybrid_stage(run, None, issue="insufficient-context")
        judge = stage_config["judge"]
        if judge["type"] == "jev":
            try:
                build_jev_request("stage", judge_request)
            except ValueError:
                return self._finish_hybrid_stage(run, None, issue="jev-input-capacity")
            action = self.issue_jev(run, "stage", judge_request,
                                    timeout_ms=stage_config["judgeTimeoutMs"])
            state["batches"] += 1
            state["lastJudgeStep"] = s["step"]
            state["localRecords"].append({"jobId": action["callId"], "status": "pending",
                "purpose": "stage", "inputDigest": judge_request["inputDigest"],
                "sourceModel": action["payload"]["model"], "evidenceIds": judge_request["evidenceIds"],
                "ruleVersion": rule_version, "backend": "jev"})
            self.persist(run)
            return action
        job_id = self.local_service.submit("stage", self.local_judge_key(judge), judge, judge_request)
        state["batches"] += 1
        state["lastJudgeStep"] = s["step"]
        state["localRecords"].append({"jobId": job_id, "status": "pending", "apiCost": 0,
            "purpose": "stage", "inputDigest": judge_request["inputDigest"],
            "sourceModel": judge["sourceModel"], "revision": judge["revision"],
            "evidenceIds": judge_request["evidenceIds"], "ruleVersion": rule_version})
        timeout = stage_config["judgeTimeoutMs"]
        remaining = self.describe(run)["remainingMs"]
        if remaining is not None:
            timeout = min(timeout, remaining)
        now = time.monotonic()
        flow["localJudge"] = {"jobId": job_id, "kind": "stage", "submittedAt": now,
                              "deadline": now + timeout / 1000}
        self.persist(run)
        return {"action": "wait", "kind": "local-judge", "jobId": job_id,
                "pollAfterMs": 25, **self.describe(run)}

    def _finish_hybrid_stage(self, run, result, *, issue=None, elapsed_ms=None):
        flow = run["flow"]
        context = flow.get("stageContext") or {"config": run["config"]["stage"],
            "modelIds": {role: run["config"]["roles"][role] for role in ("efficient", "capable")},
            "stateKey": "stageHybrid", "ruleVersion": VERSION}
        c, state = context["config"], run["state"][context["stateKey"]]
        if issue:
            # 已知输入缺失不能成为继续廉价路线的证据。
            decision = {"verdict": "NEED_STRONG", "confidence": 0,
                        "reason": issue, "ruleVersion": VERSION}
        else:
            try:
                decision = parse_answers(result["payload"]["answers"], c)
            except (KeyError, TypeError, ValueError):
                self.stop(run, "stage-invalid-judge-output")
                raise ValueError("Stage 本地 Judge 返回非法答案，停止执行")
            if c["judge"]["type"] == "jev":
                decision["rawAnswers"] = result["payload"].get("rawAnswers")
        request = flow["stageRequest"]
        decision.update(inputDigest=request["inputDigest"], evidenceIds=request["evidenceIds"],
                        evidenceSources=request["state"]["evidence"],
                        backend="jev" if c["judge"]["type"] == "jev" else "local-decision")
        if result is not None:
            decision.update(actualModel=result["model"], latencyMs=result["latencyMs"],
                            coldStartMs=result["coldStartMs"], elapsedMs=elapsed_ms, usage=result["usage"])
            state["localRecords"][-1].update(status="local-inference", latencyMs=result["latencyMs"],
                elapsedMs=elapsed_ms, coldStartMs=result["coldStartMs"], usage=deepcopy(result["usage"]))
            if c["judge"]["type"] == "jev":
                state["localRecords"][-1].update(status="billed", apiCost=jev_cost_cny(
                    result["usage"]["input_tokens"], run["config"]["jev"]["fxRate"]),
                    billingUnit="CNY")
        elif state["localRecords"] and state["localRecords"][-1]["status"] == "pending":
            state["localRecords"][-1].update(status="capacity", elapsedMs=elapsed_ms, reason=issue)
        else:
            # 已知缺少上下文，未派发推论；轨迹单独记录，不冒充实际 forward。
            decision["usage"] = {"forwards": 0}
        proposed, reason = transition(flow["stagePlan"]["state"], decision, c)
        return self._emit_hybrid_stage(run, proposed, reason, decision)

    def _emit_hybrid_stage(self, run, proposed, reason, decision=None):
        flow = run["flow"]
        context = flow.get("stageContext") or {"config": run["config"]["stage"],
            "modelIds": {role: run["config"]["roles"][role] for role in ("efficient", "capable")},
            "stateKey": "stageHybrid", "ruleVersion": VERSION}
        state = run["state"][context["stateKey"]]
        proposed = deepcopy(proposed)
        for key in ("batches", "lastJudgeStep", "localRecords"):
            proposed[key] = deepcopy(state[key])
        hold_before = proposed["hold"]
        if proposed["role"] == "capable":
            proposed["hold"] = max(0, proposed["hold"] - 1)
        row = {"step": run["state"]["step"], "role": proposed["role"],
            "model": context["modelIds"][proposed["role"]], "reason":
                ("composite-" + reason if context["stateKey"] == "compositeStageHybrid" else reason),
            "trigger": flow["stagePlan"]["trigger"], "ruleVersion": context["ruleVersion"],
            "disposition": "selected-not-dispatched", "ruleSuggestion": flow["stagePlan"]["reason"],
            "holdBefore": hold_before, "holdAfter": proposed["hold"],
            "downgradeConfirmations": proposed["down"], "judgeBatches": proposed["batches"],
            "decision": decision, "evidenceIds": [e["id"] for e in proposed["events"]]}
        run["decisions"].append(row)
        # 预算或历史准入拒绝后仍保留判别答案，不能只保存成功派发的选模。
        self.persist(run)
        action = self.issue(run, proposed["role"], "execute", flow["messages"], flow["tools"],
            model_id=context["modelIds"][proposed["role"]], buffered=False,
            update={context["stateKey"]: proposed,
                "last_model": context["modelIds"][proposed["role"]], "last_evidence": flow["evidence"]})
        row.update(callId=action["callId"], disposition="dispatched")
        self.persist(run)
        return action
