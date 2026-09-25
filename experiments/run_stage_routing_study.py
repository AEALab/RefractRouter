"""Stage 三路线实验：默认只做零调用预检；真实执行须另行冻结 AFP 双预算。"""
import argparse
import json
from pathlib import Path

from refractrouter.stage_study import load_protocol, preflight, prepare, run_paid_batch, summarize


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path,
                        default=Path("data/benchmarks/stage-routing-v1.json"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--records", type=Path,
                        help="汇总已完成的 JSONL 运行记录，不发起模型调用")
    parser.add_argument("--prepare", action="store_true",
                        help="按冻结顺序生成 72 个隔离工作区，不发起模型调用")
    parser.add_argument("--execute-paid-run", action="store_true",
                        help="保留为显式付费门；本脚本不会绕过 DSH 宿主运行器")
    parser.add_argument("--approved-protocol-sha256")
    parser.add_argument("--max-production-afp", type=float)
    parser.add_argument("--max-evaluation-afp", type=float)
    parser.add_argument("--dsh-profile", default="headless")
    args = parser.parse_args(argv)
    protocol = load_protocol(args.protocol)
    preview = preflight(protocol)
    if args.execute_paid_run:
        if args.approved_protocol_sha256 != preview["protocolSha256"]:
            parser.error("真实实验需要匹配的冻结协议 SHA-256")
        if args.max_production_afp is None or args.max_production_afp < preview["afpUpperBound"]["production"]:
            parser.error("授权的 production AFP 必须覆盖冻结调用包络")
        if args.max_evaluation_afp is None or args.max_evaluation_afp < preview["afpUpperBound"]["evaluation"]:
            parser.error("授权的 evaluation AFP 必须覆盖冻结盲评包络")
        if not args.output_dir:
            parser.error("真实实验需要新的 --output-dir")
        prepare(protocol, args.output_dir)
        write(args.output_dir / "preflight.json", preview)
        result = run_paid_batch(protocol, args.output_dir, profile=args.dsh_profile)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if any(value is not None for value in (
            args.approved_protocol_sha256, args.max_production_afp, args.max_evaluation_afp)):
        parser.error("零调用模式不接受付费授权参数")
    if args.records:
        records = [json.loads(line) for line in args.records.read_text().splitlines() if line.strip()]
        result = summarize(protocol, records)
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=False)
            write(args.output_dir / "summary.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.prepare:
        if not args.output_dir:
            parser.error("--prepare 需要 --output-dir")
        prepare(protocol, args.output_dir)
        write(args.output_dir / "preflight.json", preview)
    elif args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write(args.output_dir / "preflight.json", preview)
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
