"""验证实际核心进程的 v8 影子合同，模型由客户端确定性回执模拟。"""
import argparse
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time


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


def stage_configuration():
    value = configuration()
    value.update(defaultStrategy="stage", stageShadow={"schemaVersion": "stage-progress-shadow-v1",
        "holdTurns": 2, "stallConfirmations": 2, "checkers": [{"id": "fixture", "revision": "fixture-r1",
        "suiteSha256": "b" * 64, "assertionIds": ["complete", "correct"]}]})
    del value["task"]
    del value["taskShadow"]
    return value


def stage_fixture(rpc, reply, run, identity, messages):
    action = rpc(op="step", runId=run, messages=messages, tools=[])
    assert action["purpose"] == "execute" and action["model"]["id"] == "small"
    reply(action, "模拟初始执行")
    initial = rpc(op="outcome", runId=run, identity=identity)
    task_sha = hashlib.sha256(json.dumps(initial["taskProjection"], ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    events = []
    for key in ("first", "second"):
        events.append({"id": key, "callId": key, "tool": "fixture-check", "kind": "observe",
            "status": "failed", "fingerprint": "same-fixture-assertion", "validation": {
                "schemaVersion": "stage-check-evidence-v1", "taskSha256": task_sha,
                "checkerId": "fixture", "checkerRevision": "fixture-r1", "suiteSha256": "b" * 64,
                "snapshotSha256": "1" * 64, "codeGeneration": 1, "phase": "acceptance", "complete": True,
                "checks": [{"id": "complete", "status": "failed"}, {"id": "correct", "status": "passed"}]}})
        action = rpc(op="step", runId=run, messages=messages, tools=[], toolEvidence=events)
        assert action["model"]["id"] == ("small" if key == "first" else "large")
        reply(action, "模拟后续执行")
    for expected in ("large", "small"):
        action = rpc(op="step", runId=run, messages=messages, tools=[], toolEvidence=events)
        assert action["model"]["id"] == expected
        reply(action, "模拟保持与到期")
    rpc(op="end", runId=run)
    outcome = rpc(op="outcome", runId=run, identity=identity)
    shadow = outcome["stageProgressShadow"]
    assert shadow["role"] == "capable" and shadow["actualSelectionChanged"] is False
    assert len(outcome["calls"]) == 5 and all(c["purpose"] == "execute" for c in outcome["calls"])
    return {"scope": "installed-core-v8-stage-worker", "status": "pass", "modelCalls": 0,
            "actual_model_calls": [c["actual_model"] for c in outcome["calls"]], "classification_calls": 0,
            "shadow_only": True, "no_evidence_keeps_strong_suggestion": True, "actual_model_benefit_proven": False}


def validate(executable, workspace, *, response_timeout=15, mode="task"):
    if mode not in ("task", "stage"):
        raise ValueError("未知影子验收模式")
    executable, workspace = Path(executable).resolve(), Path(workspace).resolve()
    process = subprocess.Popen([str(executable), "planning-worker", "--runs-dir", str(workspace / "shadow-runs" / mode)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, cwd=workspace)
    sequence = 0
    pending = bytearray()
    def rpc(**request):
        nonlocal sequence
        sequence += 1
        payload = {"protocol": "refractagent-planning/4", "id": str(sequence), **request}
        process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        process.stdin.flush()
        deadline = time.monotonic() + response_timeout
        while b"\n" not in pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise RuntimeError("影子进程完整行回执超时")
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("影子进程在完整回执前退出")
            pending.extend(chunk)
            if len(pending) > 1024 * 1024:
                raise RuntimeError("影子进程回执超过1MiB")
        line, _, remainder = pending.partition(b"\n")
        pending[:] = remainder
        response = json.loads(line)
        assert response.get("id") == str(sequence) and response.get("ok") is True, response
        return response["result"]
    try:
        identity = {"session": "installed-shadow-" + mode, "agent": "fixture", "turn": 1}
        started = rpc(op="begin", identity=identity, config=stage_configuration() if mode == "stage" else configuration())
        run = started["runId"]
        messages = [{"role": "user", "content": "提取给定字段。"}]
        def reply(action, content):
            return rpc(op="complete", runId=run, callId=action["callId"], response={"content": content,
                "inputTokens": 100, "outputTokens": 20, "finishReason": "stop", "usageAvailable": True})
        if mode == "stage":
            return stage_fixture(rpc, reply, run, identity, messages)
        judge = rpc(op="step", runId=run, messages=messages, tools=[])
        assert judge["purpose"] == "task"
        assert json.loads(judge["messages"][1]["content"])["contract"] == "task-decision-with-family-v3"
        raw = {"taskFamily": "fixture-extract", "answers": {"candidates": {
            key: {"score": .99, "missingInformation": 0} for key in ("C1", "C2")}}}
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
        failed = sys.exc_info()[0] is not None
        process.stdin.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
        error = process.stderr.read()[-2000:].decode("utf-8", errors="replace")
        process.stdout.close()
        process.stderr.close()
        if process.returncode and not failed:
            raise RuntimeError("影子验收进程异常退出：" + error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--mode", choices=("task", "stage"), default="task")
    args = parser.parse_args()
    print(json.dumps(validate(args.executable, args.workspace, mode=args.mode), ensure_ascii=False))


if __name__ == "__main__":
    main()
