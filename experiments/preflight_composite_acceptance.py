"""Composite 有限验收的零调用冻结预检。"""
import argparse
import json
from pathlib import Path


def preflight():
    return {"schemaVersion": "composite-acceptance-preflight-v1", "strategy": "composite",
        "configuration": {"schemaVersion": "refractagent-planning-v6",
            "taskJudge": "deterministic-fixture", "stageModes": ["rules", "hybrid-local-laya"],
            "executionOutputLimit": 2048, "httpRetries": 0, "delegation": False},
        "flows": {"clientNormal": {"clients": ["dsh", "codex", "hermes"],
                "maximumUpstreamCallsEach": 3, "paidCalls": 0},
            "trustedFailure": {"interface": "standard-base-url-with-versioned-tool-evidence",
                "maximumUpstreamCalls": 6, "paidCalls": 0},
            "localLaya": {"cases": 2, "maximumForwards": 2, "paidCalls": 0}},
        "billingUpperBounds": {"AFP": 0, "CNY": 0},
        "existingAuthorizationAFP": 2000,
        "notes": ["所有远程模型均为本地确定性夹具。", "本地 Laya 无 API 费用。",
                  "纯标准客户端不自动提供可信工具退出状态；动态切换由扩展证据合同单独验收。"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = preflight()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
