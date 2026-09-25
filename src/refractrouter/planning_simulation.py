"""离线模拟协议回执，不调用模型或工具；模拟费用不证明收益。"""
from tempfile import TemporaryDirectory
from .planning_runtime import PlanningRuntime


def simulate(config):
    with TemporaryDirectory(prefix="refract-planning-simulation-") as directory:
        runtime = PlanningRuntime(directory)
        begin = runtime.handle({"op": "begin", "config": config,
            "identity": {"session": "simulation", "agent": "simulation", "turn": 1}})
        run_id = begin["runId"]
        for _ in range(3):
            action = runtime.handle({"op": "step", "runId": run_id,
                "messages": [{"role": "user", "content": "离线协议模拟任务"}], "tools": []})
            while action["action"] == "call":
                purpose = action["purpose"]
                content = ('{"p_solve":0.8,"capability_boundary":"supported","crux":"模拟"}'
                    if purpose == "task" else '{"verdict":"APPROVE","feedback":"模拟通过"}'
                    if purpose == "advisor" else '{"escalate":true,"reason":"模拟困难"}'
                    if purpose == "escalation" else "模拟回复")
                action = runtime.handle({"op": "complete", "runId": run_id, "callId": action["callId"],
                    "response": {"content": content, "inputTokens": 20, "outputTokens": 20,
                        "usageAvailable": True, "finishReason": "stop", "latencyMs": 0}})
        record = runtime.handle({"op": "query", "runId": run_id})
        return {"simulated": True, "actualModelCalls": 0, "strategy": begin["strategy"],
            "simulatedCalls": len(record["calls"]), "models": [r["model_id"] for r in record["calls"]],
            "simulatedCost": record["costs"]["production"], "billingUnit": record["billingUnit"],
            "simulatedCostsByUnit": record["costsByUnit"],
            "message": "仅模拟协议与状态；费用为模拟用量，不能证明实际质量、成本或时延收益。"}
