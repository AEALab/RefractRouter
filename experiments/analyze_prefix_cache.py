"""分析不可变缓存诊断产物；缺失缓存/TTFT 不补成零，不作因果或质量外推。"""
import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.agent import atomic_json


def analyze(source, output):
    index = json.loads((source / 'artifact-index.json').read_text())
    for name, digest in index.items():
        path = (source / name).resolve()
        if not path.is_relative_to(source.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('证据摘要不一致：' + name)
    required = {'frozen.json', 'probe-ledger.json', 'run-status.json'}
    if (source / 'applications.json').exists():
        required.add('applications.json')
    if not required <= set(index):
        raise ValueError('关键证据未被摘要索引覆盖')
    frozen = json.loads((source / 'frozen.json').read_text())
    ledger = json.loads((source / 'probe-ledger.json').read_text())
    status = json.loads((source / 'run-status.json').read_text())
    apps = json.loads((source / 'applications.json').read_text()) if (source / 'applications.json').exists() else []
    calls = ledger['calls']
    probes = []
    for call in calls:
        model, layout, phase, repetition = call['label'].split('/')
        billed = call['status'] == 'billed'
        probes.append({'model': model, 'layout': layout, 'phase': phase, 'repetition': int(repetition),
            'status': call['status'], 'finish_reason': call.get('finish_reason'),
            'output_complete': billed and call.get('finish_reason') == 'stop' and bool(call.get('response_output', '').strip()),
            'reasoning_tokens': call.get('reasoning_tokens'), 'input_tokens': call.get('input_tokens'),
            'output_tokens': call.get('output_tokens'),
            'cached_tokens': call.get('cached_input_tokens') if call.get('cache_usage_available') else None,
            'cache_usage_source': call.get('cache_usage_source'), 'ttft_ms': call.get('ttft_ms'),
            'latency_ms': call.get('latency_ms'), 'afp': call['charged'] if billed else None,
            'unconfirmed_reserved_afp': 0 if billed else call['charged'], 'cold_state': 'unconfirmed'})
    app_rows, all_calls = [], list(calls)
    for app in apps:
        run_dir = source / app['id'] / Path(app['run_dir']).name
        if str((run_dir / 'result.json').relative_to(source)) not in index:
            raise ValueError('应用账本未被摘要索引覆盖')
        raw = json.loads((run_dir / 'result.json').read_text())
        all_calls.extend(raw['calls'])
        app_rows.append({'id': app['id'], 'status': app['status'],
            'wall_time_ms': app['wall_time_ms'], 'costs': app['costs'], 'cost_breakdown': app['cost_breakdown'],
            'calls': len(raw['calls']), 'model_judge': app['quality'],
            'peak_active_nodes': raw.get('execution', {}).get('peak_active_nodes'),
            'cached_tokens': sum(c.get('cached_input_tokens', 0) for c in raw['calls'] if c.get('cache_usage_available')),
            'cache_unknown_calls': sum(not c.get('cache_usage_available') for c in raw['calls']),
            'input_tokens': sum(c.get('input_tokens', 0) for c in raw['calls']),
            'output_tokens': sum(c.get('output_tokens', 0) for c in raw['calls'])})
    billed = [c for c in all_calls if c['status'] == 'billed']
    result = {'source_freeze_sha256': frozen['sha256'],
        'analysis_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'status': status,
        'actual_calls': status['actual_calls'], 'ledger_calls': len(all_calls),
        'billed_afp': round(sum(c['charged'] for c in billed), 8),
        'unconfirmed_reserved_afp': round(sum(c['charged'] for c in all_calls if c['status'] != 'billed'), 8),
        'input_tokens': sum(c.get('input_tokens', 0) for c in billed),
        'output_tokens': sum(c.get('output_tokens', 0) for c in billed),
        'observed_cached_tokens': sum(c.get('cached_input_tokens', 0) for c in billed if c.get('cache_usage_available')),
        'cache_unknown_calls': sum(not c.get('cache_usage_available') for c in billed),
        'human_quality_verified': False, 'pareto_claim_supported': False, 'cache_discount_verified': False,
        'probes': probes, 'applications': app_rows}
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / 'analysis.json', result)
    lines = ['# 前缀缓存开发诊断', '',
        f"冻结摘要：`{frozen['sha256']}`。原始产物摘要核对通过。", '',
        f"实际 {result['actual_calls']} 次调用，账本 {result['ledger_calls']} 条；按冻结价格计算 "
        f"{result['billed_afp']:.5f} AFP，未知用量仍预留 {result['unconfirmed_reserved_afp']:.5f} AFP。", '',
        f"输入 {result['input_tokens']}，输出 {result['output_tokens']}，已报告缓存 {result['observed_cached_tokens']} token；"
        f"{result['cache_unknown_calls']} 次已结算调用没有可确认的缓存字段。", '',
        '## 接口探针', '',
        '| 模型 | 布局 | 阶段 | 结束状态 | 缓存 token | 输入 / 输出 | 请求秒数 | AFP |',
        '|---|---|---|---|---:|---:|---:|---:|']
    for r in probes:
        elapsed = f"{r['latency_ms']/1000:.3f}" if r['latency_ms'] is not None else '未知'
        cost = f"{r['afp']:.5f}" if r['afp'] is not None else '用量未知'
        cached = str(r['cached_tokens']) if r['cached_tokens'] is not None else '未报告'
        phase = {'first-concurrent':'首次并发', 'first-sequential':'首次顺序', 'repeat-prefix':'重复前缀'}[r['phase']]
        lines.append(f"| {r['model']} | {r['layout']} | {phase} {r['repetition']} | {r['finish_reason']} | {cached} | "
                     f"{r['input_tokens']} / {r['output_tokens']} | {elapsed} | {cost} |")
    lines += ['', '## 应用对照', '',
        '| 路线 | 状态 | 端到端秒数 | 生产 AFP | 评审 AFP | 总 AFP | 调用数 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in app_rows:
        c = r['costs']
        lines.append(f"| {r['id']} | {r['status']} | {r['wall_time_ms']/1000:.3f} | "
                     f"{c['production']:.5f} | {c['evaluation']:.5f} | "
                     f"{c['production']+c['evaluation']:.5f} | {r['calls']} |")
    lines += ['', '## 解释边界', '',
        '所有冷状态未确认；不能清空服务端缓存，且跨布局/之前请求的污染不能排除。',
        '首次并发与首次顺序使用不同开发任务子集，不能直接作并发性能对照。',
        '每应用路线只有一次；记录随机性、输出长度及模型服务负载共同影响的观测，不能证明稳定提速。',
        '探针不是质量验收；应用保留原模型评审，但仍缺独立真人复核，不能声称得到 Pareto 解。',
        'TTFT 全部未知；缓存 token 不等于 AFP 折扣，AFP 是 token 与冻结系数计算值，并未核对账号控制台逐笔扣减。',
        '冻结固定图无规划调用；自动规划与选择性材料精简收益仍待另做消融。', '']
    (output / 'README.md').write_text('\n'.join(lines))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.source, args.output_dir)
    print(json.dumps({k: result[k] for k in ('actual_calls', 'billed_afp', 'unconfirmed_reserved_afp', 'observed_cached_tokens')}))


if __name__ == '__main__':
    main()
