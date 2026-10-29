"""验证实际核心进程的 v8 影子合同，模型由客户端确定性回执模拟。"""
import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import select
import subprocess


def configuration():
    profile = {"schemaVersion": "task-empirical-profile-v1", "kind": "simulation", "observations": []}
    profile_sha = hashlib.sha256(json.dumps(profile, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    return {"schemaVersion": "refractagent-planning-v8", "enabled": True, "defaultStrategy": "task",
        "billingUnit": "CNY", "maxProductionCostByUnit": {"CNY": 10}, "maxCalls": 10,
        "roles": {"efficient": "small", "capable": "large", "classifier": "judge", "advisor": "judge"},
        "models": [{"id": key, "provider": "fixture-local", "model": key, "revision": "fixture-r1",
                    "deployment": "local", "contextWindow": 32000, "maxOutputTokens": 1024,
                    "billingUnit": "CNY", "inputPer1k": .001 if key == "small" else .002,
                    "outputPer1k": .002 if key == "small" else .004,
                    "capabilities": {"mainExecutor": key != "judge", "toolCalling": "verified"}}
                   for key in ("small", "large", "judge")],
        "task": {"pool": ["small", "large"], "fallback": "large", "judge": {"type": "llm", "modelId": "judge"},
                 "threshold": .8},
        "taskShadow": {"schemaVersion": "task-expected-cost-shadow-v1", "profile": profile,
            "profileSha256": profile_sha, "families": [{"id": "fixture-extract", "description": "固定文本提取协议探针",
                "criteriaSha256": "a" * 64, "criterionIds": ["complete", "correct"]}],
            "routeVersion": "installed-fixture-v1", "cacheCondition": "unknown",
            "pricingDate": date.today().isoformat(), "expiresOn": (date.today() + timedelta(days=1)).isoformat(),
            "minSamples": 3, "qualityMin": .95}}


def validate(executable, workspace):
    executable, workspace = Path(executable).resolve(), Path(workspace).resolve()
    process = subprocess.Popen([str(executable), "planning-worker", "--runs-dir", str(workspace / "shadow-runs")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=workspace)
    sequence = 0
    def rpc(**request):
        nonlocal sequence
        sequence += 1
        payload = {"protocol": "refractagent-planning/4", "id": str(sequence), **request}
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.flush()
        if not select.select([process.stdout], [], [], 15)[0]:
            raise RuntimeError("影子进程回执超时")
        response = json.loads(process.stdout.readline())
        assert response.get("id") == str(sequence) and response.get("ok") is True, response
        return response["result"]
    try:
        identity = {"session": "installed-shadow", "agent": "fixture", "turn": 1}
        started = rpc(op="begin", identity=identity, config=configuration())
        run = started["runId"]
        messages = [{"role": "user", "content": "提取给定字段。"}]
        judge = rpc(op="step", runId=run, messages=messages, tools=[])
        assert judge["purpose"] == "task"
        assert json.loads(judge["messages"][1]["content"])["contract"] == "task-decision-with-family-v3"
        raw = {"taskFamily": "fixture-extract", "answers": {"candidates": {
            key: {"score": .99, "missingInformation": 0} for key in ("C1", "C2")}}}
        def reply(action, content):
            return rpc(op="complete", runId=run, callId=action["callId"], response={"content": content,
                "inputTokens": 100, "outputTokens": 20, "finishReason": "stop", "usageAvailable": True})
        execute = reply(judge, json.dumps(raw))
        assert execute["purpose"] == "execute" and execute["model"]["id"] == "small"
        reply(execute, "模拟完整交付")
        continuation = rpc(op="step", runId=run, messages=messages, tools=[])
        assert continuation["purpose"] == "execute" and continuation["model"]["id"] == "small"
        reply(continuation, "模拟继续交付")
        rpc(op="end", runId=run)
        outcome = rpc(op="outcome", runId=run, identity=identity)
        assert outcome["costContext"]["family"] == "fixture-extract"
        assert outcome["taskShadow"]["mode"] == "shadow" and outcome["taskShadow"]["actualSelectionChanged"] is False
        assert outcome["taskShadow"]["uncertain"] is True
        assert sum(c["purpose"] == "task" for c in outcome["calls"]) == 1
        return {"scope": "installed-core-v8-planning-worker", "status": "pass", "modelCalls": 0,
                "actual_model_calls": [c["actual_model"] for c in outcome["calls"]],
                "classification_calls": 1, "execution_model_fixed": True, "shadow_only": True,
                "unknown_cache_preserved": True, "actual_model_benefit_proven": False}
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        if process.returncode:
            raise RuntimeError("影子验收进程异常退出：" + process.stderr.read()[-2000:])
        process.stdout.close()
        process.stderr.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.executable, args.workspace), ensure_ascii=False))


if __name__ == "__main__":
    main()
