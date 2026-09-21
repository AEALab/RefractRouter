#!/usr/bin/env python3
"""生成 #112 真实绑定与预算的零调用冻结证据。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from refractrouter.security_benchmark_budget import freeze_budget, pricing_snapshot


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path,
                        default=ROOT / 'data/research/security-benchmark-v1.json')
    parser.add_argument('--bindings', type=Path,
                        default=ROOT / 'data/research/security-benchmark-bindings-v2.json')
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'reports/security-benchmark-v1/binding-preflight-02')
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    inventory = json.loads(args.bindings.read_text())
    result = freeze_budget(protocol, inventory)
    write_json(args.output / 'binding-audit.json', result['binding_audit'])
    write_json(args.output / 'call-envelope.json', {
        key: result[key] for key in (
            'schema_version', 'protocol_sha256', 'binding_sha256',
            'execution_billing_unit',
            'calls', 'role_totals', 'planned_calls', 'authorization_call_cap',
            'protocol_hard_call_cap', 'automatic_http_retries', 'node_fallbacks',
            'recovery_calls_authorized', 'cache_discount_assumed')})
    write_json(args.output / 'pricing-snapshot.json', pricing_snapshot(inventory))
    write_json(args.output / 'preflight.json', result)
    unknown = ', '.join(row['role_id']
                        for row in result['unresolved_execution_usage_roles'])
    reference_unknown = ', '.join(row['role_id']
                                  for row in result['unresolved_reference_cost_roles'])
    lines = [
        '# #112 真实绑定与零调用预算冻结', '',
        f'- 协议摘要：`{result["protocol_sha256"]}`',
        f'- 绑定摘要：`{result["binding_sha256"]}`',
        f'- 生产调用：{result["planned_calls"]["production"]}；评审调用：{result["planned_calls"]["evaluation"]}；合计：{result["planned_calls"]["total"]}',
        f'- 本次授权调用上限：{result["authorization_call_cap"]}；协议硬上限：{result["protocol_hard_call_cap"]}',
        f'- 已知绑定执行用量：{result["known_bound_execution_usage"]:.6f} {result["execution_billing_unit"]}',
        f'- 未知执行用量角色：{unknown or "无"}',
        f'- 原厂公开参考价未解析角色：{reference_unknown or "无"}',
        '- AFP 是实际执行路线的订阅资源单位；现金成本与原厂公开价格等价量均保持 `null`。',
        '- 自动 HTTP 重试、节点回退与恢复调用均为 0。',
        '- 真实模型调用：0；付费执行授权：否；实时执行就绪：否。', '',
        '## 阻断条件', '',
        *[f'- {item}' for item in result['blocking_requirements']], '',
    ]
    (args.output / 'README.md').write_text('\n'.join(lines))
    request = [
        '# #112 开发批次授权草案', '',
        '> 当前草案不可批准或执行：仍有真实模型与价格缺口。缺口补齐后必须重新生成本文件。', '',
        '## 冻结范围', '',
        f'- 计划调用：{result["planned_calls"]["total"]} 次，其中生产 {result["planned_calls"]["production"]} 次、评审 {result["planned_calls"]["evaluation"]} 次。',
        f'- 请求调用上限：{result["authorization_call_cap"]} 次；不授权使用协议剩余余量。',
        '- 自动重试、节点回退、恢复补跑：全部为 0。',
        f'- 完整执行用量上限：{"尚不可计算" if result["maximum_total_execution_usage"] is None else str(result["maximum_total_execution_usage"]) + " " + result["execution_billing_unit"]}。',
        '- 现金成本：尚不可计算；未冻结 Ark 订阅费用、包含 AFP、有效期与利用率。',
        '- 原厂公开价格等价量：尚不可计算；Ark 型号与原厂公开计价型号的版本等价性未验证。', '',
        '## 尚未满足', '',
        *[f'- {item}' for item in result['blocking_requirements']], '',
        '## 授权状态', '',
        '- `paid_execution_authorized: false`',
        '- 不得根据本草案发起任何模型调用。', '',
    ]
    (args.output / 'authorization-request.md').write_text('\n'.join(request))
    print(json.dumps({'output': str(args.output), 'real_model_calls': 0,
                      'authorization_request_ready': result['authorization_request_ready'],
                      'planned_calls': result['planned_calls']['total']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
