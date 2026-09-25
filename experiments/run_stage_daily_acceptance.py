"""Stage 两项日常验收：默认零调用预检；真实执行需要冻结指纹与 AFP 上限。"""
import argparse
import json
from pathlib import Path

from refractrouter.stage_daily_acceptance import TASK_IDS, preflight, prepare, run
from refractrouter.stage_study import load_protocol


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path,
                        default=Path("data/benchmarks/stage-routing-v1.json"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execute-paid-run", action="store_true")
    parser.add_argument("--approved-acceptance-sha256")
    parser.add_argument("--max-production-afp", type=float)
    parser.add_argument("--dsh-profile", default="headless")
    parser.add_argument("--task-id", action="append",
                        help="只运行指定的冻结任务；可重复传入。默认运行两项日常验收。")
    args = parser.parse_args(argv)
    protocol = load_protocol(args.protocol)
    task_ids = tuple(args.task_id) if args.task_id else TASK_IDS
    preview = preflight(protocol, task_ids)
    if not args.execute_paid_run:
        if args.output_dir or args.approved_acceptance_sha256 or args.max_production_afp is not None:
            parser.error("零调用预检不接受输出目录或付费授权参数")
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0
    if args.approved_acceptance_sha256 != preview["acceptanceSha256"]:
        parser.error("真实日常验收需要匹配的冻结指纹")
    required = preview["limits"]["maxProductionAfpTotal"]
    if args.max_production_afp is None or args.max_production_afp < required:
        parser.error(f"真实日常验收 AFP 上限不足，至少需要 {required}")
    if not args.output_dir:
        parser.error("真实日常验收需要新的输出目录")
    prepare(protocol, args.output_dir, task_ids)
    result = run(protocol, args.output_dir, profile=args.dsh_profile,
                 task_ids=task_ids)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
