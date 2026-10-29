"""冻结整任务配对声明；只读摘要，不读取隐藏答案、不提供付费执行开关。"""
import argparse
import json
from pathlib import Path

from refractrouter.whole_task_protocol import HASH, freeze_study


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--exposed-materials", type=Path, required=True,
                        help="已经暴露的材料SHA-256列表；提供空列表仍不证明来源审查通过")
    parser.add_argument("--output", type=Path, required=True, help="全新冻结文件")
    args = parser.parse_args(argv)
    study = json.loads(args.study.read_text(encoding="utf-8"))
    exposed = json.loads(args.exposed_materials.read_text(encoding="utf-8"))
    if (type(exposed) is not list or any(type(h) is not str or HASH.fullmatch(h) is None for h in exposed)):
        raise ValueError("已暴露材料必须是完整SHA-256列表")
    if type(study) is not dict or set(study) != {"contract", "tasks", "arms", "comparisons"}:
        raise ValueError("实验声明字段不完整或包含未知数据")
    result = freeze_study(**study, exposed_materials=set(exposed))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"sha256": result["sha256"], "modelCalls": 0, "liveExecutionReady": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
