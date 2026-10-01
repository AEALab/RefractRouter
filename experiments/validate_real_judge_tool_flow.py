"""用真实 Ark Judge、确定性执行夹具和 DSH 原生工具验证路由闭环。"""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
from threading import Thread

from refractrouter.model_gateway import (HttpModelCaller, ModelGateway,
                                         create_server)
from refractrouter.planning_config import compile_config, preview
from refractrouter.task_budget import request_input_bound


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("advisor-normal", "advisor-redo", "escalation-normal", "escalation-defect")
PRICE_AFP_PER_1K = .05
MAX_JUDGE_INPUT_TOKENS = 65536
MAX_JUDGE_OUTPUT_TOKENS = 1024
MAX_JUDGE_CALLS_PER_FLOW = 2
MAX_AFP_PER_FLOW = (MAX_JUDGE_INPUT_TOKENS + MAX_JUDGE_OUTPUT_TOKENS) / 1000 * PRICE_AFP_PER_1K * MAX_JUDGE_CALLS_PER_FLOW


def model(identity, provider, api_model, *, executor):
    return {"id": identity, "provider": provider, "model": api_model,
        "contextWindow": 1000000, "maxOutputTokens": 1024 if not executor else 256,
        "inputPer1k": PRICE_AFP_PER_1K if not executor else 0,
        "outputPer1k": PRICE_AFP_PER_1K if not executor else 0,
        "billingUnit": "AFP", "deployment": "trusted-cloud" if not executor else "local",
        **({"trustPolicy": "ark-accepted"} if not executor else {}),
        "capabilityCard": "结构化回复审核" if not executor else "文本与原生工具",
        "capabilities": {"mainExecutor": executor,
                         "toolCalling": "verified" if executor else "unknown",
                         "modalities": {}}}


def configuration(scenario):
    strategy = scenario.split("-", 1)[0]
    cfg = {"schemaVersion": "refractagent-planning-v6", "enabled": True,
        "defaultStrategy": strategy, "maxProductionCostByUnit": {"AFP": 10},
        "timeoutMs": 120000, "maxCalls": 8,
        "models": [model("initial", "fixture", "executor-fixture", executor=True),
                   model("takeover", "fixture", "takeover-fixture", executor=True),
                   model("judge", "ark", "deepseek-v4-flash", executor=False)],
        "roles": {"efficient": "initial", "capable": "takeover",
                  "classifier": "judge", "advisor": "judge"},
        "trustPolicies": [{"id": "ark-accepted", "residency": "CN",
                           "auditLogging": True, "allowsSensitiveData": True}],
        "compatiblePairs": [["initial", "takeover"], ["takeover", "initial"]],
        "security": {"maxPromptBytes": 65536}}
    if strategy == "advisor":
        cfg["advisor"] = {"executor": "initial",
            "judge": {"type": "llm", "modelId": "judge"},
            "judgeTimeoutMs": 30000, "maxJudgeInputBytes": 65536,
            "maxExecutionOutputTokens": 256, "maxJudgeOutputTokens": 1024}
    else:
        cfg["escalation"] = {"initial": "initial", "takeover": "takeover",
            "judge": {"type": "llm", "modelId": "judge"},
            "stallConfirmations": 2, "threshold": .8,
            "judgeTimeoutMs": 30000, "maxJudgeInputBytes": 65536,
            "maxExecutionOutputTokens": 256, "maxJudgeOutputTokens": 1024}
    compile_config(cfg)
    row = next(row for row in preview(cfg)["strategies"] if row["id"] == strategy)
    if not row["available"]:
        raise ValueError("零调用诊断失败：" + "；".join(row["issues"]))
    return cfg


def preflight(scenario):
    cfg = configuration(scenario)
    frozen = {"schemaVersion": "real-judge-tool-flow-preflight-v1",
        "scenario": scenario, "client": "DSH 0.1.5-rc.3", "strategy": scenario.split("-", 1)[0],
        "executor": "local deterministic fixture", "judge": "ark/deepseek-v4-flash",
        "maxRemoteJudgeCalls": MAX_JUDGE_CALLS_PER_FLOW,
        "maxInputTokensPerJudgeCall": MAX_JUDGE_INPUT_TOKENS,
        "maxOutputTokensPerJudgeCall": MAX_JUDGE_OUTPUT_TOKENS,
        "maximumAfp": round(MAX_AFP_PER_FLOW, 6),
        "maximumFourFlowsAfp": round(MAX_AFP_PER_FLOW * len(SCENARIOS), 6),
        "httpRetries": 0, "hostTool": "refract_local_echo",
        "fixtureCallsHaveApiCost": False,
        "configSha256": hashlib.sha256(json.dumps(cfg, ensure_ascii=False,
            sort_keys=True).encode()).hexdigest(),
        "coreSha256": hashlib.sha256(b"".join((ROOT / file).read_bytes() for file in (
            "src/refractrouter/planning_runtime.py",
            "src/refractrouter/model_gateway.py",
            "src/refractrouter/advisor_decision.py",
            "src/refractrouter/escalation_decision.py",
            "validation/dsh/plugin/scripts/check-gateway-tools.ts",
            "experiments/validate_real_judge_tool_flow.py"))).hexdigest()}
    return cfg, frozen


def make_fixture(scenario, observations):
    state = {"initial": 0, "takeover": 0}

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            api_model = request["model"]
            if api_model not in ("executor-fixture", "takeover-fixture"):
                raise ValueError("执行夹具收到非执行模型调用")
            role = "initial" if api_model == "executor-fixture" else "takeover"
            state[role] += 1
            found = any(message.get("role") == "tool" and "REFRACT_HOST_TOOL_OK"
                        in str(message.get("content")) for message in request["messages"])
            names = [tool["function"]["name"] for tool in request.get("tools", [])]
            if found:
                delta, finish = {"content": "GATEWAY_CLIENT_OK"}, "stop"
            elif (scenario == "advisor-redo" and role == "initial" and state[role] == 1):
                delta, finish = {"content": "工具已经执行并返回 REFRACT_HOST_TOOL_OK。GATEWAY_CLIENT_OK"}, "stop"
            elif scenario == "escalation-defect" and role == "initial":
                delta, finish = {"content": "未经调用工具，结果已经核验：GATEWAY_CLIENT_OK"}, "stop"
            else:
                if "refract_local_echo" not in names:
                    raise ValueError("DSH 原生工具没有传入执行模型")
                delta = {"tool_calls": [{"index": 0, "id": "judge_flow_tool_1",
                    "type": "function", "function": {"name": "refract_local_echo",
                                                   "arguments": "{}"}}]}
                finish = "tool_calls"
            observations.append({"role": role, "toolResultInHistory": found,
                                 "emittedToolCall": finish == "tool_calls"})
            if request.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for value in ({"choices": [{"index": 0, "delta": delta,
                                             "finish_reason": None}]},
                              {"choices": [{"index": 0, "delta": {},
                                             "finish_reason": finish}]},
                              {"choices": [], "usage": {"prompt_tokens": 100,
                                                        "completion_tokens": 20}}):
                    self.wfile.write(b"data: " + json.dumps(value).encode() + b"\n\n")
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            else:
                message = {key: value for key, value in delta.items() if key != "tool_calls"}
                if "tool_calls" in delta:
                    message["tool_calls"] = [{key: value for key, value in call.items()
                                              if key != "index"} for call in delta["tool_calls"]]
                body = json.dumps({"choices": [{"index": 0, "message": message,
                    "finish_reason": finish}], "usage": {"prompt_tokens": 100,
                                                          "completion_tokens": 20}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

    return Fixture


def execute(scenario, output, modules):
    cfg, frozen = preflight(scenario)
    if json.loads((output / "preflight.json").read_text()) != frozen:
        raise ValueError("配置或代码与冻结预检不一致")
    if (output / "dispatch.started").exists():
        raise ValueError("批次已经派发，拒绝重复调用")
    if not os.environ.get("CODEX_ARK_API_KEY"):
        raise ValueError("Ark 凭证未就绪")
    if not modules.is_dir():
        raise ValueError("DSH 实际模块目录不存在")
    observations = []
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), make_fixture(scenario, observations))
    Thread(target=fixture.serve_forever, daemon=True).start()
    class Bounded(HttpModelCaller):
        judge_calls = 0

        def guard(self, action):
            if action["model"]["provider"] != "ark":
                return
            if self.judge_calls >= MAX_JUDGE_CALLS_PER_FLOW:
                raise ValueError("真实 Judge 调用数超过冻结上限")
            if action["model"]["model"] != "deepseek-v4-flash" or action["model"]["maxTokens"] > MAX_JUDGE_OUTPUT_TOKENS:
                raise ValueError("真实 Judge 模型或输出范围已变化")
            if request_input_bound(action["messages"], action["tools"]) > MAX_JUDGE_INPUT_TOKENS:
                raise ValueError("真实 Judge 输入超过冻结上限")
            self.judge_calls += 1

        def __call__(self, action, options):
            self.guard(action)
            return super().__call__(action, options)

        def stream(self, action, options, on_text):
            self.guard(action)
            return super().stream(action, options, on_text)

    providers = {"fixture": {"baseURL": f"http://127.0.0.1:{fixture.server_port}/v1"},
        "ark": {"baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
                "apiKeyEnv": "CODEX_ARK_API_KEY", "timeoutSeconds": 30,
                "requestOptions": {"thinking": {"type": "disabled"}}}}
    caller = Bounded(providers)
    gateway = ModelGateway({"planningRouting": cfg, "providers": providers},
                           output / "runs", caller)
    server = create_server(gateway, port=0)
    Thread(target=server.serve_forever, daemon=True).start()
    (output / "dispatch.started").write_text(frozen["coreSha256"] + "\n")
    try:
        command = ["node", "--experimental-strip-types",
            "validation/dsh/plugin/scripts/check-gateway-tools.ts", str(modules),
            f"http://127.0.0.1:{server.server_port}/v1", "256", scenario.split("-", 1)[0]]
        result = subprocess.run(command, text=True, capture_output=True, timeout=130)
        (output / "client-stdout.txt").write_text(result.stdout)
        (output / "client-stderr.txt").write_text(result.stderr)
        (output / "fixture-observations.json").write_text(json.dumps(
            observations, ensure_ascii=False, indent=2) + "\n")
        summary = summarize_existing(scenario, output)
        if summary["chargedJudgeAfp"] > MAX_AFP_PER_FLOW or caller.judge_calls > MAX_JUDGE_CALLS_PER_FLOW:
            raise RuntimeError("真实 Judge 超过冻结费用或调用数")
        if not summary["clientCompleted"] or not summary["hostToolResultReceived"]:
            raise RuntimeError("DSH 工具闭环未通过；查看保存的原始记录")
        return summary
    finally:
        server.shutdown()
        server.server_close()
        gateway.close()
        fixture.shutdown()
        fixture.server_close()


def summarize_existing(scenario, output):
    """从已落盘的宿主与 Router 证据结算，绝不重新派发。"""
    stdout = (output / "client-stdout.txt").read_text()
    stderr = (output / "client-stderr.txt").read_text()
    try:
        client = json.loads(stdout.splitlines()[-1])
    except (ValueError, IndexError):
        client = {}
    files = list((output / "runs/planning").glob("*.json"))
    records = [json.loads(path.read_text()) for path in files]
    calls = [call for record in records for call in record.get("calls", [])]
    judge_calls = [call for call in calls if call.get("purpose") in ("advisor", "escalation")]
    observed = (json.loads((output / "fixture-observations.json").read_text())
                if (output / "fixture-observations.json").exists() else [])
    summary = {"scenario": scenario, "clientExitCode": 0 if client.get("status") == "pass" else None,
        "clientCompleted": client.get("status") == "pass",
        "remoteJudgeCalls": len(judge_calls),
        "chargedJudgeAfp": round(sum(call.get("charged", 0) for call in judge_calls), 8),
        "purposes": [call.get("purpose") for call in calls],
        "dispositions": [call.get("disposition") for call in calls],
        "decisionReasons": [row.get("reason") for record in records
                            for row in record.get("decisions", [])],
        "fixture": observed,
        "hostToolResultReceived": client.get("hostTools", 0) == 1,
        "routerTasks": len(records), "httpRetries": 0,
        "clientErrorType": "none" if not stderr else "stderr-present"}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False,
                                                    indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dsh-modules", type=Path,
                        default=Path.home() / ".local/lib/node_modules/@deepseek-ai/dsh/node_modules")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--summarize-existing", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.summarize_existing:
        print(json.dumps(summarize_existing(args.scenario, output), ensure_ascii=False))
        return
    _, frozen = preflight(args.scenario)
    if not args.execute:
        output.mkdir(parents=True, exist_ok=False)
        (output / "preflight.json").write_text(json.dumps(frozen, ensure_ascii=False,
                                                           indent=2) + "\n")
        print(json.dumps({"remoteCalls": 0, **frozen}, ensure_ascii=False))
    else:
        print(json.dumps(execute(args.scenario, output, args.dsh_modules),
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
