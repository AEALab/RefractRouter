"""Stage 真实小样本：默认只预检；付费执行须给出冻结指纹和 AFP 上限。"""
import argparse
import json
from pathlib import Path

from refractrouter.stage_study import (load_protocol, pilot_preflight,
                                       prepare_live_pilot, run_live_pilot)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path,
                        default=Path("data/benchmarks/stage-routing-v1.json"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execute-paid-pilot", action="store_true")
    parser.add_argument("--approved-pilot-sha256")
    parser.add_argument("--max-production-afp", type=float)
    parser.add_argument("--dsh-profile", default="headless")
    args = parser.parse_args(argv)
    protocol = load_protocol(args.protocol)
    preview = pilot_preflight(protocol)
    if not args.execute_paid_pilot:
        if args.output_dir or args.approved_pilot_sha256 or args.max_production_afp is not None:
            parser.error("零调用预检不接受输出目录或付费授权参数")
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0
    if args.approved_pilot_sha256 != preview["pilotSha256"]:
        parser.error("真实小样本需要匹配的冻结指纹")
    if args.max_production_afp is None or args.max_production_afp < preview["maxProductionAfp"]:
        parser.error("真实小样本 AFP 上限不足")
    if not args.output_dir:
        parser.error("真实小样本需要新的输出目录")
    prepare_live_pilot(protocol, args.output_dir)
    result = run_live_pilot(protocol, args.output_dir, profile=args.dsh_profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
