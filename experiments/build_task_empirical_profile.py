"""从冻结的独立验收与任务结果构建经验 profile；零调用、全新输出，不在线训练。"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

from refractrouter.task_empirical import build_profile
from refractrouter.task_outcomes import digest


ROOT = Path(__file__).resolve().parents[1]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("样本 JSON 重复键")
        result[key] = value
    return result


def implementation():
    names = ("task_empirical.py", "task_cost_observation.py", "task_outcomes.py", "judge_qualification.py", "purpose_review.py")
    paths = [Path(__file__)]
    for name in names:
        module = sys.modules.get("refractrouter." + name.removesuffix(".py"))
        loaded = Path(module.__file__).resolve() if module is not None and getattr(module, "__file__", None) else None
        expected = (ROOT / "src/refractrouter" / name).resolve()
        if loaded != expected:
            raise ValueError("实际加载实现与本工作区不符：" + name)
        paths.append(loaded)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.is_relative_to(source.parent) or source.is_relative_to(output):
        raise ValueError("profile 输出须与原样本目录分离")
    if any(output.is_relative_to(ROOT / p) for p in ("src", "experiments", "data")):
        raise ValueError("profile 输出不得进入实现或冻结数据目录")
    output.mkdir(parents=True, exist_ok=False)
    try:
        raw = source.read_bytes()
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("经验输入超过16MiB，禁止截断后继续")
        inputs = {"sourceSha256": hashlib.sha256(raw).hexdigest(), "implementation": implementation(),
                  "pythonVersion": platform.python_version(), "modelCalls": 0}
        (output / "inputs-before.json").write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + "\n")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("样本含非法数值")))
        if not isinstance(value, dict) or set(value) != {"schemaVersion", "kind", "samples"} or value["schemaVersion"] != "task-calibration-input-v1":
            raise ValueError("经验输入需要版本化样本合同")
        profile = build_profile(value["samples"], kind=value["kind"])
        if hashlib.sha256(source.read_bytes()).hexdigest() != inputs["sourceSha256"] or implementation() != inputs["implementation"]:
            raise ValueError("构建期间输入或实现漂移")
        (output / "inputs-after.json").write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + "\n")
        (output / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
        summary = {"schemaVersion": "task-profile-build-result-v1", "kind": profile["kind"],
            "observations": len(profile["observations"]), "excluded": sum("excluded" in r for r in profile["observations"]),
            "profileSha256": digest(profile), "modelCalls": 0, "productionSelectionChanged": False,
            "actualModelBenefitProven": False}
        (output / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return summary
    except Exception as exc:
        (output / "failure.json").write_text(json.dumps({"status": "failed", "errorType": type(exc).__name__,
            "reason": str(exc), "modelCalls": 0}, ensure_ascii=False, indent=2) + "\n")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.input, args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
