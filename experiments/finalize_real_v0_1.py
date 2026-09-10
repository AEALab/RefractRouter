"""为冻结 final 产物生成人工审核包，严格复核后在独立目录保存结论。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

THRESHOLD = 10
AUDIT_TASKS = ("report_011", "report_020")
STRATEGIES = ("task-oracle", "node-oracle")
DIMENSIONS = {"requirement_coverage": 25, "evidence_accuracy": 25,
              "analysis_depth": 20, "structure_readability": 15, "html_validity": 15}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, maximum=100):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= maximum):
        raise ValueError("分数必须为范围内的有限数值")
    return value


def frozen_inputs(output_dir):
    output_dir = output_dir.resolve()
    index_path = output_dir / "evidence-index.json"
    index = json.loads(index_path.read_text())
    artifacts = index.get("artifacts")
    required = {"benchmark-summary.json", "preflight.json"} | {
        f"runs/{task}/repeat-1/{strategy}.json" for task in AUDIT_TASKS for strategy in STRATEGIES}
    if not isinstance(artifacts, dict) or not required <= artifacts.keys():
        raise ValueError("索引缺少冻结摘要、预检或审核产物")
    for name, expected in artifacts.items():
        path = (output_dir / name).resolve()
        if not path.is_relative_to(output_dir) or sha256(path) != expected:
            raise ValueError("冻结产物路径或哈希不一致")
    summary = json.loads((output_dir / "benchmark-summary.json").read_text())
    if summary.get("phase") != "final" or summary.get("status") != "awaiting-human-audit":
        raise ValueError("仅接受等待人工审核的 final benchmark")
    preflight = json.loads((output_dir / "preflight.json").read_text())
    if preflight != summary["preflight"]:
        raise ValueError("摘要与冻结预检不一致")
    if preflight.get("human_audit_task_ids") != list(AUDIT_TASKS):
        raise ValueError("人工审核任务必须为冻结的 report_011、report_020")
    runs = {}
    for task in AUDIT_TASKS:
        for strategy in STRATEGIES:
            path = output_dir / f"runs/{task}/repeat-1/{strategy}.json"
            run = json.loads(path.read_text())
            if (run.get("task_id") != task or run.get("strategy") != strategy or run.get("repeat") != 1
                    or run.get("judge_error") or not run.get("judge") or not run["result"].get("final_output")
                    or run["result"].get("failure_types")):
                raise ValueError("审核产物缺少有效独立评审或运行身份不一致")
            if run["judge"].get("rubric_version") != "v0.1":
                raise ValueError("审核 rubric 与冻结评审不一致")
            claims = run["judge"].get("claim_support")
            if (not isinstance(claims, list) or not claims
                    or len({c['claim'] for c in claims}) != len(claims)):
                raise ValueError("冻结独立评审缺少完整的逐条主张记录")
            if number(run["result"]["task_score"]) != number(run["judge"]["final_score"]):
                raise ValueError("运行分数与独立评审不一致")
            runs[task, strategy] = (run, sha256(path))
    return summary, runs, sha256(index_path)


def prepare_audit(output_dir):
    _, runs, index_hash = frozen_inputs(output_dir)
    return {"schema_version": "v0.2", "rubric_version": "v0.1",
            "agreement_threshold_points": THRESHOLD, "evidence_index_sha256": index_hash,
            "records": [{"task_id": task, "strategy": strategy, "repeat": 1,
                "run_sha256": run_hash, "human_score": None, "reviewer": "", "reviewed_at": "",
                "dimensions": dict.fromkeys(DIMENSIONS), "serious_factual_error": None,
                "evidence_quote": "", "notes": "", "claim_checks": [
                    {"claim": c['claim'], "source_ids": c['source_ids'], "supported": None, "notes": ""}
                    for c in run['judge']['claim_support']]}
                for (task, strategy), (run, run_hash) in runs.items()]}


def write_result(directory, source, filename, value):
    directory = directory.resolve()
    source = source.resolve()
    if directory == source or directory.is_relative_to(source) or directory.exists():
        raise ValueError("审核输出必须使用冻结目录之外的全新目录")
    directory.mkdir(parents=True)
    (directory / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def finalize(output_dir: Path, audit_path: Path, result_dir: Path | None = None) -> dict[str, object]:
    summary, runs, index_hash = frozen_inputs(output_dir)
    audit = json.loads(audit_path.read_text())
    if audit.get("schema_version") != "v0.2" or audit.get("rubric_version") != "v0.1":
        raise ValueError("必须使用绑定冻结证据的 v0.2 审核格式与 v0.1 rubric")
    if number(audit.get("agreement_threshold_points")) != THRESHOLD:
        raise ValueError("不得修改冻结的 10 分差异门槛")
    if audit.get("evidence_index_sha256") != index_hash:
        raise ValueError("审核记录不属于当前冻结实验")
    records = audit.get("records")
    if not isinstance(records, list):
        raise ValueError("审核记录必须是数组")
    comparisons, seen = [], set()
    for record in records:
        pair = (record.get("task_id"), record.get("strategy"))
        if pair not in runs or pair in seen:
            raise ValueError("审核样本重复或不属于冻结集合")
        seen.add(pair)
        run, run_hash = runs[pair]
        if type(record.get("repeat")) is not int or record["repeat"] != 1 or record.get("run_sha256") != run_hash:
            raise ValueError("审核记录的轮次或产物哈希不一致")
        for field in ("reviewer", "notes", "reviewed_at", "evidence_quote"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"审核缺少 {field}")
        reviewed_at = datetime.fromisoformat(record["reviewed_at"].replace("Z", "+00:00"))
        if reviewed_at.tzinfo is None or reviewed_at > datetime.now(timezone.utc):
            raise ValueError("审核时间必须带时区且不得为未来时间")
        if record["evidence_quote"] not in run["result"]["final_output"]:
            raise ValueError("人工依据必须逐字定位到冻结输出")
        dimensions = record.get("dimensions")
        if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
            raise ValueError("人工审核缺少冻结评分维度")
        score = number(record.get("human_score"))
        if not math.isclose(score, sum(number(dimensions[k], cap) for k, cap in DIMENSIONS.items()), abs_tol=1e-8):
            raise ValueError("人工总分与维度分不一致")
        if type(record.get("serious_factual_error")) is not bool:
            raise ValueError("必须明确记录是否存在严重事实错误")
        expected_claims = {c['claim']: c['source_ids'] for c in run['judge']['claim_support']}
        claim_checks = record.get('claim_checks')
        if (not isinstance(claim_checks, list) or len(claim_checks) != len(expected_claims)
                or {c['claim'] for c in claim_checks} != set(expected_claims)):
            raise ValueError('必须逐条审核冻结的主张与来源')
        for claim in claim_checks:
            if (claim.get('source_ids') != expected_claims[claim['claim']]
                    or type(claim.get('supported')) is not bool
                    or not isinstance(claim.get('notes'), str) or not claim['notes'].strip()):
                raise ValueError('主张审核缺少来源、明确判断或依据')
        judged_score = run["judge"]["final_score"]
        delta = score - judged_score
        comparisons.append({**record, "judged_score": judged_score, "delta": round(delta, 3),
                            "within_threshold": abs(delta) <= THRESHOLD})
    if seen != set(runs):
        raise ValueError("人工审核未覆盖四个冻结样本")
    audit_pass = all(r["within_threshold"] and not r["serious_factual_error"] for r in comparisons)
    oracle_decision = summary["oracle_gate"]["decision"]
    if oracle_decision not in {"Go", "No-go", "Insufficient-evidence"}:
        raise ValueError("未知 oracle 判定")
    # 证据不足不能因人工一致而变成有充分证据的否定或肯定结论。
    decision = "incomplete" if oracle_decision == "Insufficient-evidence" else (
        "Go" if oracle_decision == "Go" and audit_pass else "No-go")
    result = {"schema_version": "v0.2", "status": "incomplete" if decision == "incomplete" else "complete",
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "agreement_threshold_points": THRESHOLD, "audit_pass": audit_pass,
              "evidence_index_sha256": index_hash, "audit_sha256": sha256(audit_path),
              "comparisons": comparisons, "oracle_decision": oracle_decision, "final_decision": decision}
    destination = result_dir or output_dir.with_name(output_dir.name + "-human-audit")
    write_result(destination, output_dir, "human-audit-result.json", result)
    (destination / "submitted-audit.json").write_bytes(audit_path.read_bytes())
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path, help="冻结 final benchmark 输入")
    parser.add_argument("--result-dir", required=True, type=Path, help="新的审核输出目录")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--audit", type=Path)
    mode.add_argument("--prepare-audit", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare_audit:
        write_result(args.result_dir, args.output_dir, "human-audit-template.json", prepare_audit(args.output_dir))
        result = {"status": "awaiting-human-audit", "actual_model_calls": 0}
    else:
        result = finalize(args.output_dir, args.audit, args.result_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
