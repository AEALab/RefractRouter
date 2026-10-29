"""零调用重放分用途评审已知反例；新输出目录，不修改历史或产品配置。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.historical_judge_replay import replay


ROOT = Path(__file__).resolve().parents[1]


def snapshot(directory):
    paths = sorted(p for p in directory.iterdir() if p.is_file())
    paths += [Path(__file__), *(ROOT / "src/refractrouter" / name for name in (
        "purpose_review.py", "judge_qualification.py", "historical_judge_replay.py"))]
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(history, output):
    history, output = Path(history).resolve(), Path(output).resolve()
    if output.is_relative_to(history) or history.is_relative_to(output):
        raise ValueError("输出不能覆盖或混入历史材料")
    output.mkdir(parents=True, exist_ok=False)
    before = snapshot(history)
    (output / "inputs-before.json").write_text(json.dumps(before, ensure_ascii=False, indent=2) + "\n")
    try:
        result = replay(history)
        after = snapshot(history)
        if before != after:
            raise ValueError("重放期间输入或实现发生变化")
        (output / "inputs-after.json").write_text(json.dumps(after, ensure_ascii=False, indent=2) + "\n")
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({"status": "failed", "errorType": type(exc).__name__,
            "reason": str(exc), "modelCalls": 0}, ensure_ascii=False, indent=2) + "\n")
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-dir", type=Path, default=ROOT / "data/judge-regression-v1")
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.history_dir, args.output_dir)
    print(json.dumps({"状态": "重放完成，评审后端未取得新准入资格", "确定缺陷数": result["confirmedDefectCount"],
        "确定有错答卷数": result["defectiveCandidateCount"],
        "原评审漏放答卷数": result["confirmedDefectiveCandidatesApproved"], "模型调用": 0,
        "证据目录": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
