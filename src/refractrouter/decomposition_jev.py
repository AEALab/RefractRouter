"""自动路由的云端结构判别：零调用预检、单次派发及独立现金账本。"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import time

from .decomposition_decision import (build_request, input_digest, parse_noul_answers,
                                    unknown_evidence, validate_limits, trivial_workload)
from .jev_bridge import cost_cny, settled_cost_cny, validate_result, validate_usage
from .jev_transport import wire_payload
from .planning_budget import PlanningBudget
from .planning_config import compile_config, SCHEMA_V6
from .privacy_placement import allows_sensitive, classify_view


class DecompositionJevRuntime:
    """由外层进程锁串行调用；接入层只负责带凭证 HTTP，不解释答案。"""

    def __init__(self, root):
        self.root = Path(root)
        self.jobs = {}

    def prepare(self, request):
        settings = request.get("config", {})
        # 复用渠道、信任和价格编译，不依赖规划路由的策略及模型角色是否完整。
        config = compile_config({"schemaVersion": SCHEMA_V6, "enabled": False,
            **{key: settings[key] for key in ("jev", "trustPolicies", "security") if key in settings}})
        spec = config["jev"]
        task, context = request.get("task"), request.get("context")
        input_digest(task, context)
        threshold, maximum = request.get("threshold", .65), request.get("maxInputBytes", 65536)
        validate_limits(threshold, maximum)
        timeout = request.get("timeoutMs", 30000)
        if type(timeout) is not int or not 100 <= timeout <= 300000:
            raise ValueError("拆分判别期限必须是 100..300000 的整数")
        cap = request.get("maxCostCny")
        if type(cap) not in (int, float) or not math.isfinite(cap) or cap <= 0:
            raise ValueError("自动拆分 Jev 需要明确的正数 CNY 单任务上限")
        if trivial_workload(task):
            return {"action": "complete", "evidence": unknown_evidence(task, context, "trivial-workload")}
        if len(task.encode()) > maximum:
            return {"action": "complete", "evidence": unknown_evidence(task, context, "input-too-long")}
        built = build_request(task, context, threshold=threshold, max_input_bytes=maximum)
        if built["state"]["contextDependency"] == "referenced":
            return {"action": "complete", "evidence": unknown_evidence(task, context, "context-dependent")}
        payload = wire_payload(built["state"], built["questions"], spec["route"])
        # 实际发送内容才是数据域检查对象；完整宿主上下文仅参与本地绑定，不外发。
        grade = classify_view(json.dumps(payload, ensure_ascii=False), privacy=config["security"])
        if grade["grade"] != "S3" and not allows_sensitive(spec["deployment"], config["security"]):
            raise ValueError("拆分 Jev 输入不允许发送到当前数据域")
        bound = cost_cny(spec["maxInputTokens"], spec["fxRate"])
        if bound > cap:
            raise ValueError(f"拆分 Jev 预算不足：需要保护 {bound:.8f} CNY")
        return {"action": "ready", "request": built, "payload": payload, "spec": spec,
                "maximumCostCny": bound, "maxCostCny": cap, "timeoutMs": timeout,
                "inputSha256": built["inputSha256"], "maximumCalls": 1}

    def persist(self, job):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / (job["id"] + ".json")
        costs, calls = job["budget"].snapshot()
        record = {key: deepcopy(job[key]) for key in
                  ("id", "status", "frozen", "result", "evidence") if key in job}
        record.update(costsByUnit=costs, calls=calls)
        temporary = path.with_suffix(".tmp")
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception:
            job["status"] = "evidence-failed"
            job["budget"].stop()
            raise
        return str(path)

    def begin(self, request):
        identity = request.get("identity")
        if not isinstance(identity, str) or not identity or len(identity) > 4096:
            raise ValueError("拆分 Jev 需要宿主调用身份")
        key = hashlib.sha256(identity.encode()).hexdigest()
        if key in self.jobs or (self.root / (key + ".json")).exists():
            raise ValueError("拆分判别已派发或需核对；不会重复调用")
        frozen = self.prepare(request)
        if frozen["action"] == "complete":
            return frozen
        budget = PlanningBudget({"CNY": frozen["maxCostCny"]}, max_calls=1)
        spec = frozen["spec"]
        row = budget.reserve_non_token("CNY", frozen["maximumCostCny"], label=key,
            purpose="decomposition", usage={"basis": "input-token", "maximumUnits": spec["maxInputTokens"],
                "model": spec["model"], "provider": spec["route"]})
        row.update(source_billing_unit="USD", conversion_rate=spec["fxRate"],
                   conversion_source=spec["fxSource"], conversion_as_of=spec["fxAsOf"],
                   pricing_source=spec["pricingSource"])
        budget.dispatch_non_token(row, operation_id=key)
        job = {"id": key, "status": "dispatched", "frozen": frozen, "budget": budget,
               "deadline": time.monotonic() + frozen["timeoutMs"] / 1000}
        self.jobs[key] = job
        self.persist(job)
        return {"action": "jev", "callId": key, "payload": frozen["payload"],
                "route": spec["route"], "endpoint": spec["endpoint"],
                "credentialRef": spec["credentialRef"], "timeoutMs": frozen["timeoutMs"]}

    def stop(self, key):
        job = self.jobs[key]
        job["status"] = "stopped"
        job["budget"].stop()
        self.persist(job)
        return {"action": "stop", "reason": "stopped; unconfirmed reservation retained"}

    def complete(self, request):
        job = self.jobs[request["callId"]]
        frozen, budget = job["frozen"], job["budget"]
        result = request.get("result")
        row = budget.records[0]
        if row["status"] != "unknown-usage":
            raise ValueError("拆分判别回执已经结算")
        try:
            usage = validate_usage(frozen["payload"], result)
            job["result"] = deepcopy(result)
            amount = settled_cost_cny(frozen["payload"], result, frozen["spec"]["fxRate"])
            budget.settle_non_token(row, amount, usage)
            row.update(actual_model=result["model"], provider_request_id=result.get("id"),
                       latency_ms=request.get("latencyMs"))
            if job["status"] != "dispatched" or time.monotonic() > job["deadline"]:
                self.stop(job["id"])
                return {"action": "stop", "reason": "cancelled-or-expired"}
            answers, _ = validate_result(frozen["payload"], result)
            if any(answer.get("type") != "noul" for answer in answers.values() if isinstance(answer, dict)):
                raise ValueError("拆分 Jev 需要 Noul 答案")
            decision = parse_noul_answers(answers, threshold=frozen["request"]["threshold"])
            evidence = {**{key: frozen["request"][key] for key in
                            ("contract", "ruleVersion", "inputSha256")}, **decision,
                        "backend": "jev", "provider": frozen["spec"]["route"],
                        "model": result["model"], "revision": result["model"],
                        "latencyMs": request.get("latencyMs"), "queueMs": 0,
                        "usage": usage, "rawAnswers": answers, "costCny": amount,
                        "callId": job["id"], "experimental": True}
            job.update(status="completed", evidence=evidence)
            evidence["recordPath"] = self.persist(job)
            return {"action": "complete", "evidence": deepcopy(evidence)}
        except Exception:
            self.stop(job["id"])
            raise
