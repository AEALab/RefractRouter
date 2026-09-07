"""从冻结校准观测构建分层 profile；本入口不调用模型。"""
import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.dag_study import load_study
from refractrouter.profile_calibration import build_stratified_profile


def main():
    parser = argparse.ArgumentParser(description='从校准集独立节点观测构建分层路由 profile')
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    protocol, manifest = load_study(args.protocol)
    if hashlib.sha256(args.manifest.read_bytes()).hexdigest() != protocol['manifest_sha256']:
        parser.error('观测使用的模型清单必须与冻结协议一致')
    profile = build_stratified_profile(json.loads(args.observations.read_text()), manifest,
        calibration_task_ids=[t['task_id'] for t in protocol['tasks'] if t['split'] == 'calibration'],
        test_task_ids=[t['task_id'] for t in protocol['tasks'] if t['split'] == 'test'])
    with args.output.open('x') as stream:
        stream.write(json.dumps(profile, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
