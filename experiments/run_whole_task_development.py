"""固定三组整任务研究；默认零调用，付费执行必须显式 --execute。"""
import argparse
import json
import os

from refractrouter.development_study import load_suite, preflight, run_generation, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root, suite = load_suite(args.suite, args.manifest_sha256)
    if args.execute:
        result = run_generation(args.suite, args.manifest_sha256, args.output, os.environ)
    else:
        result = preflight(root, suite, environment=os.environ)
        save(args.output, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
