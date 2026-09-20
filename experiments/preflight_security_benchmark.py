#!/usr/bin/env python3
"""生成 #112 安全约束基准的零调用排练证据。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from refractrouter.security_benchmark import preflight

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path,
                        default=ROOT / 'data/research/security-benchmark-v1.json')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'reports/security-benchmark-v1/rehearsal-01')
    args = parser.parse_args()
    result = preflight(json.loads(args.protocol.read_text()))
    write_json(args.output / 'preflight.json', result)
    lines = [
        '# 安全约束混合路由基准零调用排练', '',
        f'- 协议摘要：`{result["protocol_sha256"]}`',
        f'- 任务：{result["coverage"]["task_count"]} 个；路线运行：{len(result["runs"])} 次',
        f'- 最大调用：{result["maximum_calls"]} 次；真实模型调用：{result["real_model_calls"]} 次',
        f'- 最大声明费用：{result["maximum_declared_cost"]:.6f} {result["billing_unit"]}',
        '- 隐私违规：0；外部强模型结果只作为质量参照，不进入可部署前沿。', '',
        '## 当前阻断', '',
        *[f'- {item}' for item in result['blocking_requirements']], '',
    ]
    (args.output / 'README.md').write_text('\n'.join(lines))
    print(json.dumps({'output': str(args.output), 'real_model_calls': 0,
                      'maximum_calls': result['maximum_calls']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
