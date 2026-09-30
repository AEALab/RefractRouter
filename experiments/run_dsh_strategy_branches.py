"""运行 DSH 四个复杂策略的真实关键分支验收；默认只生成零调用预检。"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
from threading import Thread

from refractrouter.dsh_strategy_branches import (
    AUTHORIZED_AFP, STRATEGY_COUNTS, configuration, preflight, verify_runs,
)
from refractrouter.model_gateway import HttpModelCaller, ModelGateway, create_server
from refractrouter.openai_compatible import ChatResponse


ROOT = Path(__file__).resolve().parents[1]
DSH_MODULES = Path.home() / ".local/lib/node_modules/@deepseek-ai/dsh/node_modules"


def _fixture_response(action):
    model = action["model"]["model"]
    messages = action["messages"]
    if model == "composite-task-judge-fixture":
        payload = {"answers": {"candidates": {
            "C1": {"score": .95, "missingInformation": 0},
            "C2": {"score": .95, "missingInformation": 0}}}}
        return ChatResponse(json.dumps(payload, ensure_ascii=False), 1, 1, 0, 0, 1, 1,
            "stop", "controlled-composite-task")
    if model == "advisor-executor-fixture":
        if action["purpose"] == "redo":
            call = {"id": "advisor-redo-" + action["runId"][:16], "type": "function",
                "function": {"name": "refract_branch_echo", "arguments": "{}"}}
            return ChatResponse("", 1, 1, 0, 0, 1, 1, "tool_calls",
                "controlled-advisor-redo", tool_calls=(call,))
        has_tool = any(block.get("type") == "tool-result"
            for message in messages for block in message.get("content", [])
            if isinstance(message.get("content"), list) and isinstance(block, dict))
        text = "BRANCH_OK" if has_tool else "错误候选：没有执行要求的工具，却声称任务已经完成。"
        return ChatResponse(text, 1, 1, 0, 0, 1, 1, "stop", "controlled-advisor")
    if model == "escalation-initial-fixture":
        return ChatResponse("错误候选：没有执行要求的工具，却声称任务已经完成。",
            1, 1, 0, 0, 1, 1, "stop", "controlled-escalation")
    raise ValueError("未知受控夹具模型")


class BranchCaller:
    def __init__(self, providers, maximum_real_calls):
        self.real = HttpModelCaller(providers)
        self.maximum_real_calls = maximum_real_calls
        self.real_calls = 0
        self.fixture_calls = 0

    def _guard(self, action):
        if action["model"]["provider"] == "controlled-fixture":
            self.fixture_calls += 1
            return False
        if action["model"]["provider"] != "ark":
            raise ValueError("关键分支批次只允许 Ark 或受控本地夹具")
        if self.real_calls >= self.maximum_real_calls:
            raise ValueError("真实模型调用超过冻结上限")
        self.real_calls += 1
        return True

    def __call__(self, action, options):
        return self.real(action, options) if self._guard(action) else _fixture_response(action)

    def stream(self, action, options, on_text):
        if not self._guard(action):
            response = _fixture_response(action)
            if response.content:
                on_text(response.content)
            return response
        return self.real.stream(action, options, on_text)


def _providers():
    return {"ark": {"baseURL": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "apiKeyEnv": "CODEX_ARK_API_KEY"},
        "controlled-fixture": {"baseURL": "http://127.0.0.1:1/v1"}}


def _run_strategy(output: Path, strategy: str):
    target = output / strategy
    target.mkdir(parents=True, exist_ok=False)
    config = configuration(strategy)
    maximum = {"stage": 30, "composite": 30, "advisor": 12, "escalation": 18}[strategy]
    caller = BranchCaller(_providers(), maximum)
    gateway = ModelGateway({"planningRouting": config, "providers": _providers()},
                           target / "runs", caller)
    server = create_server(gateway, port=0)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        command = ["node", "--experimental-strip-types",
            "validation/dsh/plugin/scripts/check-gateway-branch-tools.ts",
            str(DSH_MODULES), base, str(256), strategy, str(STRATEGY_COUNTS[strategy])]
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=900)
        (target / "client-stdout.txt").write_text(result.stdout)
        (target / "client-stderr.txt").write_text(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"{strategy} DSH 客户端失败；保留证据且不自动重跑")
        runs = list(gateway.runtime.runs.values())
        compact = verify_runs(strategy, runs)
        summary = {"strategy": strategy, "success": True, "runs": len(compact),
            "realModelCalls": sum(row["realModelCalls"] for row in compact),
            "fixtureCalls": sum(row["fixtureCalls"] for row in compact),
            "productionAfp": round(sum(row["productionAfp"] for row in compact), 8),
            "records": compact}
        (target / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return summary
    finally:
        server.shutdown()
        server.server_close()
        gateway.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-digest")
    parser.add_argument("--approved-afp", type=float, default=0)
    args = parser.parse_args()
    output = args.output.resolve()
    frozen = preflight()
    if not args.execute_paid_run:
        output.mkdir(parents=True, exist_ok=False)
        (output / "preflight.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + "\n")
        for strategy in STRATEGY_COUNTS:
            (output / f"config-{strategy}.json").write_text(
                json.dumps(configuration(strategy), ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(frozen, ensure_ascii=False, indent=2))
        return
    if json.loads((output / "preflight.json").read_text()) != frozen:
        raise ValueError("冻结预检已变化，拒绝派发")
    if args.approved_digest != frozen["preflightDigest"]:
        raise ValueError("授权摘要与冻结预检不一致")
    if not math.isfinite(args.approved_afp) or args.approved_afp < AUTHORIZED_AFP:
        raise ValueError("累计 AFP 授权不足")
    if not DSH_MODULES.is_dir() or not os.environ.get("CODEX_ARK_API_KEY"):
        raise ValueError("DSH 模块或 Ark 凭证未就绪")
    marker = output / "dispatch.started"
    if marker.exists():
        raise ValueError("已有派发证据，拒绝覆盖或自动重发")
    marker.write_text(frozen["preflightDigest"] + "\n")
    summaries = []
    for strategy in STRATEGY_COUNTS:
        summaries.append(_run_strategy(output, strategy))
    total = {"schemaVersion": "dsh-strategy-branch-summary-v1", "complete": True,
        "runs": sum(row["runs"] for row in summaries),
        "realModelCalls": sum(row["realModelCalls"] for row in summaries),
        "fixtureCalls": sum(row["fixtureCalls"] for row in summaries),
        "productionAfp": round(sum(row["productionAfp"] for row in summaries), 8),
        "strategies": summaries}
    (output / "summary.json").write_text(json.dumps(total, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(total, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
