"""以规划路由固定题集比较官方 Jev 与本地 Laya；默认仅零调用预检。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median

if __package__:
    from .evaluate_local_task_judge import evaluate as evaluate_task
    from .evaluate_stage_judge import evaluate as evaluate_stage
    from .evaluate_advisor_judge import evaluate as evaluate_advisor
    from .evaluate_escalation_judge import evaluate as evaluate_escalation
else:
    from evaluate_local_task_judge import evaluate as evaluate_task
    from evaluate_stage_judge import evaluate as evaluate_stage
    from evaluate_advisor_judge import evaluate as evaluate_advisor
    from evaluate_escalation_judge import evaluate as evaluate_escalation
from refractrouter.jev_decision import JEV_INPUT_USD_PER_MILLION, JEV_MODEL, JevDecisionAdapter
from refractrouter.planning_decision import LocalDecisionCapacityError


ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "task-audit": ("data/task-judge-audit-20260926.json", evaluate_task, "choice-v2"),
    "task-holdout": ("data/task-judge-holdout-20260926.json", evaluate_task, "choice-v2"),
    "stage": ("data/stage-judge-holdout-v2.json", evaluate_stage, "choice-v2"),
    "advisor": ("data/benchmarks/advisor-judge-v1.json", evaluate_advisor, "choice-v2"),
    "escalation": ("data/benchmarks/escalation-judge-v1.json", evaluate_escalation, "choice-v2"),
}
LAYER = {"task-audit": "task-audit.json", "task-holdout": "task-holdout.json",
         "stage": "stage.json", "advisor": "advisor.json", "escalation": "escalation.json"}
MAX_INPUT_TOKENS_PER_REQUEST = 64000


def load_suites():
    loaded = {}
    for name, (path, evaluator, method) in SUITES.items():
        raw = (ROOT / path).read_bytes()
        suite = json.loads(raw)
        cases = suite.get("cases")
        if not isinstance(cases, list) or len(cases) != {
                "task-audit": 6, "task-holdout": 8, "stage": 16,
                "advisor": 24, "escalation": 24}[name]:
            raise ValueError(f"{name} 固定题集数量变化，停止验收")
        loaded[name] = (suite, evaluator, method, hashlib.sha256(raw).hexdigest(), path)
    return loaded


def preflight(loaded):
    count = sum(len(suite["cases"]) for suite, *_ in loaded.values())
    return {"model": JEV_MODEL, "scope": "planning-routing-only", "caseCount": count,
        "httpRequestsMaximum": count, "httpRetries": 0,
        "maxInputTokensPerRequest": MAX_INPUT_TOKENS_PER_REQUEST,
        "conservativeUsdUpperBound": round(count * MAX_INPUT_TOKENS_PER_REQUEST
                                            * JEV_INPUT_USD_PER_MILLION / 1_000_000, 9),
        "suites": {name: {"path": path, "sha256": digest, "cases": len(suite["cases"])}
                   for name, (suite, _, _, digest, path) in loaded.items()},
        "note": "只测试规划路由 Task、Stage、Advisor、Escalation 判别；不调用 DAG 拆分。"
                "按官方每次 64k 输入 tokens 极限计算上界；实际金额依回执用量。"}


def _one_case(suite, evaluator, adapter, case):
    limited = {**suite, "cases": [case]}
    if evaluator is evaluate_task:
        return evaluator([case], adapter, .8)[0]
    return evaluator(limited, adapter)[0]


def _comparison(journal, laya_dir):
    results = {}
    for name in SUITES:
        local = json.loads((laya_dir / LAYER[name]).read_text())
        laya = {case["id"]: case for case in local["cases"]}
        remote = [entry for entry in journal if entry["suite"] == name]
        if set(laya) != {entry["case"]["id"] for entry in remote}:
            raise ValueError(f"{name} Jev 与 Laya 案例 ID 不一致")
        rows = []
        for entry in remote:
            jev, prior = entry["case"], laya[entry["case"]["id"]]
            rows.append({"id": jev["id"], "expected": jev["expected"],
                         "jev": jev["outcome"], "laya": prior["outcome"],
                         "jevMatched": jev["matched"], "layaMatched": prior["matched"],
                         "jevLatencyMs": jev.get("latencyMs", jev.get("elapsedMs")),
                         "layaLatencyMs": prior.get("latencyMs", prior.get("elapsedMs"))})
        results[name] = {"jevMatched": sum(row["jevMatched"] for row in rows),
                         "layaMatched": sum(row["layaMatched"] for row in rows),
                         "total": len(rows), "cases": rows}
    return results


def _render_markdown(report):
    names = {"task-audit": "Task 开发题", "task-holdout": "Task 留出题",
             "stage": "Stage 逐轮选模", "advisor": "Advisor 回复审核",
             "escalation": "Escalation 候选审核"}
    lines = ["# 规划路由 Jev 与 Laya-MLX 固定题对照", "",
        f"官方 Jev 固定版本：`{JEV_MODEL}`；共 {report['actualRequests']} 次请求，",
        f"依据回执输入 tokens 和官方公开单价估算费用 {report['actualUsd']:.9f} USD；账户账单尚未核对。",
        "题集、问题描述与原先 Laya 验收相同；没有修改阈值或挑选案例。", "",
        "| 用途 | 案例数 | Jev 符合预期 | Laya 符合预期 | Jev 单题中位耗时 | Laya 单题中位耗时 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, item in report["comparison"].items():
        rows = item["cases"]
        jev_ms = [row["jevLatencyMs"] for row in rows if isinstance(row["jevLatencyMs"], (int, float))]
        laya_ms = [row["layaLatencyMs"] for row in rows if isinstance(row["layaLatencyMs"], (int, float))]
        lines.append(f"| {names[name]} | {item['total']} | {item['jevMatched']} | "
                     f"{item['layaMatched']} | {median(jev_ms):.1f} ms | {median(laya_ms):.1f} ms |")
    lines.extend(["", "各用途判定语义不同，符合预期次数不能合计为统一准确率。",
        "Jev 耗时包含网络往返，Laya 耗时是本机推论；两者可作为实际等待的参考，"
        "但不能仅凭这一批固定题证明完整任务质量或成本收益。", "",
        "选择概率是当前选项的概率；Jev 返回的 `confidence` 是分布确定性。"
        "本批按原有选择概率与阈值映射，原始答案保存在 `calls.jsonl`。", "",
        "本批只覆盖规划路由的 Task、Stage、Advisor、Escalation Judge。"
        "DAG 是否拆分属于自动路由，不在这次规划路由接线范围内。", "",
        "Laya 对照原始记录见 [PR #163](https://github.com/AEALab/RefractRouter/pull/163) 的"
        " `reports/local-jev-multiscenario-20260930/`。", "",
        "参考：[官方 API](https://docs.typesafe.ai/api)、"
        "[模型、容量与价格](https://docs.typesafe.ai/models)、"
        "[置信度定义](https://docs.typesafe.ai/confidence)。", ""])
    return "\n".join(lines)


def run(loaded, *, output, laya_dir, max_usd):
    if output.exists():
        raise ValueError("输出目录已存在；不得覆盖固定验收记录")
    if not laya_dir.is_dir():
        raise ValueError("缺少既有 Laya 报告目录；无法逐题比较")
    ceiling = preflight(loaded)["conservativeUsdUpperBound"]
    if not isinstance(max_usd, (int, float)) or not math.isfinite(max_usd) or max_usd < 0:
        raise ValueError("Jev USD 上限必须是非负有限数值")
    if max_usd < ceiling:
        raise ValueError(f"本批最坏输入上界 {ceiling} USD 高于授权上限；未发起请求")
    key = getpass("Jev API key（输入不回显、不保存）：")
    if not key:
        raise ValueError("没有 Jev API key；未发起请求")
    output.mkdir(parents=True)
    journal_path = output / "calls.jsonl"
    entries, spent = [], 0.0
    try:
        with journal_path.open("x", encoding="utf-8") as journal:
            for name, (suite, evaluator, method, _, _) in loaded.items():
                adapter = JevDecisionAdapter(api_key=key, method=method)
                for case in suite["cases"]:
                    if spent + MAX_INPUT_TOKENS_PER_REQUEST * JEV_INPUT_USD_PER_MILLION / 1_000_000 > max_usd:
                        raise ValueError("授权 USD 上限不足以保护下一次调用；整批停止")
                    try:
                        row = _one_case(suite, evaluator, adapter, case)
                    except Exception as exc:
                        # 已派发但没有确认用量时保留该次调用的上界；不自动重发。
                        undispatched = isinstance(exc, LocalDecisionCapacityError)
                        journal.write(json.dumps({"suite": name, "caseId": case["id"],
                            "status": "capacity-rejected" if undispatched else "unconfirmed",
                            "errorType": type(exc).__name__,
                            "reservedUsd": 0 if undispatched else
                                MAX_INPUT_TOKENS_PER_REQUEST * JEV_INPUT_USD_PER_MILLION / 1_000_000,
                            "recordedAt": datetime.now(timezone.utc).isoformat()},
                            ensure_ascii=False) + "\n")
                        journal.flush()
                        os.fsync(journal.fileno())
                        raise
                    usage = row.get("usage") or {}
                    tokens = usage.get("input_tokens")
                    if type(tokens) is not int or tokens < 0:
                        raise ValueError("Jev 用量未确认；整批停止，不重试")
                    charged = tokens * JEV_INPUT_USD_PER_MILLION / 1_000_000
                    spent += charged
                    entry = {"suite": name, "case": row, "actualModel": JEV_MODEL,
                             "inputTokens": tokens, "costUsd": charged,
                             "recordedAt": datetime.now(timezone.utc).isoformat()}
                    journal.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    journal.flush()
                    os.fsync(journal.fileno())
                    entries.append(entry)
        comparison = _comparison(entries, laya_dir)
        report = {"schemaVersion": "planning-jev-comparison-v1",
                  "recordedAt": datetime.now(timezone.utc).isoformat(),
                  "preflight": preflight(loaded), "actualRequests": len(entries),
                  "actualUsd": spent, "comparison": comparison,
                  "limitations": "固定判别题只检验规划路由 Judge 输出；不证明完整任务质量、成本收益或 DAG 拆分。"}
        (output / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        (output / "README.md").write_text(_render_markdown(report))
        return report
    finally:
        key = ""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="实际调用 Jev；默认仅零调用预检")
    parser.add_argument("--max-usd", type=float, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--laya-dir", type=Path)
    args = parser.parse_args()
    loaded = load_suites()
    if not args.run:
        print(json.dumps(preflight(loaded), ensure_ascii=False, indent=2))
        return
    if not args.output or not args.laya_dir:
        parser.error("真实运行需要 --output 和 --laya-dir")
    report = run(loaded, output=args.output, laya_dir=args.laya_dir, max_usd=args.max_usd)
    print(json.dumps({key: value for key, value in report.items() if key != "comparison"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
