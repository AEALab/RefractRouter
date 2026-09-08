"""Issue #32 多任务对照零调用预检；不读取凭证、不发起模型请求。"""
import argparse
import json
from pathlib import Path

from refractrouter.dag_study import load_study, study_preflight


def main():
    parser = argparse.ArgumentParser(description='冻结 DAG 对照实验的零调用预检')
    parser.add_argument('--protocol', type=Path, default=Path('data/benchmarks/dag-routing-v1.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    raw, manifest = load_study(args.protocol)
    result = study_preflight(raw, manifest)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / 'protocol.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2)+'\n')
    (args.output_dir / 'preflight.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
