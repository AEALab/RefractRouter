"""冻结合成轨迹的新旧 Stage 零调用比较，不改原始证据或产品默认值。"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from refractrouter.purpose_review import decode
from refractrouter.stage_progress_replay import compare

ROOT = Path(__file__).resolve().parents[1]


def implementation():
    paths = [Path(__file__)]
    for name in ("stage_progress", "stage_progress_replay", "planning_policy", "host_evidence", "purpose_review"):
        module = sys.modules.get("refractrouter." + name)
        loaded = Path(module.__file__).resolve() if module is not None else None
        if loaded != (ROOT / "src/refractrouter" / (name + ".py")).resolve():
            raise ValueError("重放实际导入实现与冻结源码不符")
        paths.append(loaded)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if (output.is_relative_to(source.parent) or source.is_relative_to(output)
            or any(output.is_relative_to(ROOT / p) for p in ("src", "experiments", "data"))):
        raise ValueError("重放输出须与冻结输入和实现分离")
    output.mkdir(parents=True, exist_ok=False)
    try:
        raw = source.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("重放输入超过1MiB")
        before = {"inputSha256": hashlib.sha256(raw).hexdigest(), "implementation": implementation(), "modelCalls": 0}
        (output / "inputs-before.json").write_text(json.dumps(before, ensure_ascii=False, indent=2) + "\n")
        result = compare(decode(raw.decode("utf-8")))
        after = {"inputSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                 "implementation": implementation(), "modelCalls": 0}
        (output / "inputs-after.json").write_text(json.dumps(after, ensure_ascii=False, indent=2) + "\n")
        if after != before:
            raise ValueError("重放期间冻结材料或实现漂移")
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({"status": "failed", "type": type(exc).__name__,
            "reason": str(exc), "modelCalls": 0}, ensure_ascii=False, indent=2) + "\n")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.corpus, args.output_dir)
    print(json.dumps({k: result[k] for k in ("kind", "metrics", "additionalStrongCalls", "modelCalls",
        "actualCompleteCostComparison", "actualModelBenefitProven")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
