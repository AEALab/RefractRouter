"""零调用拆解已归档 AFP 成本；不发起模型调用，不作质量或收益外推。"""
import argparse
import hashlib
import json
from pathlib import Path

from refractrouter.agent import atomic_json


def _verify_artifacts(source):
    index = json.loads((source / 'artifact-index.json').read_text())
    source_root = source.resolve()
    for name, digest in index.items():
        path = (source / name).resolve()
        if not path.is_relative_to(source_root):
            raise ValueError('证据路径越界：' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('证据摘要不一致：' + name)
    required = {'frozen.json', 'probe-ledger.json', 'run-status.json', 'applications.json'}
    if not required <= set(index):
        raise ValueError('关键证据未被摘要索引覆盖')
    return index


def _pricing(frozen):
    models = {}
    configurations = [frozen['protocol']['configuration'], frozen['protocol']['application_configuration']]
    for configuration in configurations:
        if configuration.get('billingUnit') != 'AFP':
            raise ValueError('成本分解只支持 AFP 账本')
        for model in configuration['models']:
            pricing = model['pricing']
            if pricing.get('unit') != 'AFP':
                raise ValueError('模型价格单位不是 AFP：' + model['id'])
            item = {
                'input_per_1k': pricing['inputPer1k'],
                'output_per_1k': pricing['outputPer1k'],
                'cached_input_per_1k': pricing.get('cachedInputPer1k', pricing['inputPer1k']),
            }
            if model['id'] in models and models[model['id']] != item:
                raise ValueError('同一模型在不同配置中的价格不一致：' + model['id'])
            models[model['id']] = item
    return models


def _split_cost(call, pricing):
    model = pricing[call['model_id']]
    input_tokens = call['input_tokens']
    output_tokens = call['output_tokens']
    cached_tokens = call.get('cached_input_tokens') if call.get('cache_usage_available') else None
    if cached_tokens is not None:
        cached_tokens = min(cached_tokens, input_tokens)
        uncached_tokens = input_tokens - cached_tokens
        input_afp = (
            uncached_tokens / 1000 * model['input_per_1k']
            + cached_tokens / 1000 * model['cached_input_per_1k']
        )
    elif model['input_per_1k'] == model['cached_input_per_1k']:
        input_afp = input_tokens / 1000 * model['input_per_1k']
    else:
        input_afp = None
    output_afp = output_tokens / 1000 * model['output_per_1k']
    if call['status'] == 'billed' and input_afp is not None:
        if abs(input_afp + output_afp - call['charged']) > 1e-8:
            raise ValueError('调用成本与冻结价格不一致：' + call['label'])
    return {
        'input_afp': round(input_afp, 8) if input_afp is not None else None,
        'output_afp': round(output_afp, 8),
        'cached_tokens': cached_tokens,
    }


def _row(call, pricing, *, purpose, route, prefix_policy, phase=None):
    split = _split_cost(call, pricing)
    return {
        'label': call['label'],
        'model_id': call['model_id'],
        'purpose': purpose,
        'route': route,
        'prefix_policy': prefix_policy,
        'phase': phase,
        'status': call['status'],
        'charged_afp': call['charged'] if call['status'] == 'billed' else None,
        'unconfirmed_reserved_afp': 0 if call['status'] == 'billed' else call['charged'],
        'input_tokens': call['input_tokens'],
        'output_tokens': call['output_tokens'],
        'reasoning_tokens': call.get('reasoning_tokens', 0),
        'cached_tokens': split['cached_tokens'],
        'cache_usage_available': call.get('cache_usage_available', False),
        'input_afp': split['input_afp'],
        'output_afp': split['output_afp'],
        'latency_ms': call.get('latency_ms'),
        'ttft_ms': call.get('ttft_ms'),
        'finish_reason': call.get('finish_reason'),
    }


def _aggregate(rows, key_name, key_function):
    groups = {}
    for row in rows:
        key = key_function(row)
        group = groups.setdefault(key, {
            'calls': 0,
            'billed_calls': 0,
            'unknown_usage_calls': 0,
            'billed_afp': 0.0,
            'unconfirmed_reserved_afp': 0.0,
            'input_tokens': 0,
            'output_tokens': 0,
            'reasoning_tokens': 0,
            'cached_tokens': 0,
            'cache_unknown_calls': 0,
            'input_afp': 0.0,
            'output_afp': 0.0,
            'input_afp_unknown_calls': 0,
            'ttft_known_calls': 0,
            'ttft_unknown_calls': 0,
            'ttft_ms_total': 0,
            'latency_known_calls': 0,
            'latency_unknown_calls': 0,
            'latency_ms_total': 0,
        })
        group['calls'] += 1
        if row['status'] == 'billed':
            group['billed_calls'] += 1
            group['billed_afp'] += row['charged_afp']
            group['input_tokens'] += row['input_tokens']
            group['output_tokens'] += row['output_tokens']
            group['reasoning_tokens'] += row['reasoning_tokens']
            group['output_afp'] += row['output_afp']
            group['latency_ms_total'] += row['latency_ms'] or 0
            group['latency_known_calls'] += row['latency_ms'] is not None
            group['latency_unknown_calls'] += row['latency_ms'] is None
            group['ttft_ms_total'] += row['ttft_ms'] or 0
            group['ttft_known_calls'] += row['ttft_ms'] is not None
            group['ttft_unknown_calls'] += row['ttft_ms'] is None
            if row['input_afp'] is not None:
                group['input_afp'] += row['input_afp']
            else:
                group['input_afp_unknown_calls'] += 1
            if row['cached_tokens'] is not None:
                group['cached_tokens'] += row['cached_tokens']
            else:
                group['cache_unknown_calls'] += 1
        else:
            group['unknown_usage_calls'] += 1
            group['unconfirmed_reserved_afp'] += row['unconfirmed_reserved_afp']
    for group in groups.values():
        group['billed_afp'] = round(group['billed_afp'], 8)
        group['unconfirmed_reserved_afp'] = round(group['unconfirmed_reserved_afp'], 8)
        group['input_afp'] = round(group['input_afp'], 8)
        group['output_afp'] = round(group['output_afp'], 8)
        total = group['billed_afp']
        total_tokens = group['input_tokens'] + group['output_tokens']
        group['output_afp_share'] = round(group['output_afp'] / total, 8) if total else None
        group['output_token_share'] = (
            round(group['output_tokens'] / total_tokens, 8) if total_tokens else None
        )
        group['average_latency_ms'] = (
            round(group['latency_ms_total'] / group['latency_known_calls'], 8)
            if group['latency_known_calls'] else None
        )
        group['average_ttft_ms'] = (
            round(group['ttft_ms_total'] / group['ttft_known_calls'], 8)
            if group['ttft_known_calls'] else None
        )
    return [{key_name: key, **value} for key, value in sorted(groups.items())]


def _application_rows(app, raw, pricing):
    rows = []
    for call in raw['calls']:
        rows.append(_row(
            call,
            pricing,
            purpose='application-' + call['category'],
            route=app['id'],
            prefix_policy=app['prefix_policy'],
        ))
    production = [
        row for row in rows
        if row['purpose'] == 'application-production' and row['status'] == 'billed'
    ]
    evaluation = [
        row for row in rows
        if row['purpose'] == 'application-evaluation' and row['status'] == 'billed'
    ]
    billed = [row for row in rows if row['status'] == 'billed']
    unknown = [row for row in rows if row['status'] != 'billed']
    production_afp = round(sum(row['charged_afp'] for row in production), 8)
    evaluation_afp = round(sum(row['charged_afp'] for row in evaluation), 8)
    total_afp = round(sum(row['charged_afp'] for row in billed), 8)
    output_afp = round(sum(row['output_afp'] for row in billed), 8)
    unconfirmed_reserved_afp = round(sum(row['unconfirmed_reserved_afp'] for row in unknown), 8)
    return rows, {
        'route': app['id'],
        'status': app['status'],
        'prefix_policy': app['prefix_policy'],
        'node_count': len(app['plan']['nodes']),
        'calls': len(rows),
        'wall_time_ms': app['wall_time_ms'],
        'production_afp': production_afp,
        'evaluation_afp': evaluation_afp,
        'total_afp': total_afp,
        'unknown_usage_calls': len(unknown),
        'unconfirmed_reserved_afp': unconfirmed_reserved_afp,
        'input_tokens': sum(row['input_tokens'] for row in billed),
        'output_tokens': sum(row['output_tokens'] for row in billed),
        'reasoning_tokens': sum(row['reasoning_tokens'] for row in billed),
        'cached_tokens': sum(row['cached_tokens'] for row in billed if row['cached_tokens'] is not None),
        'cache_unknown_calls': sum(row['cached_tokens'] is None for row in billed),
        'output_afp': output_afp,
        'output_afp_share': round(output_afp / total_afp, 8) if total_afp else None,
        'model_judge_score': app.get('quality', {}).get('score'),
        'model_judge_passed': app.get('quality', {}).get('passed'),
        'human_quality_verified': False,
        'accepted_task': None,
        'afp_per_accepted_task': None,
    }


def analyze(source, output):
    source = Path(source)
    output = Path(output)
    _verify_artifacts(source)
    frozen = json.loads((source / 'frozen.json').read_text())
    ledger = json.loads((source / 'probe-ledger.json').read_text())
    status = json.loads((source / 'run-status.json').read_text())
    apps = json.loads((source / 'applications.json').read_text())
    pricing = _pricing(frozen)

    rows = []
    for call in ledger['calls']:
        model, layout, phase, repetition = call['label'].split('/')
        rows.append(_row(
            call,
            pricing,
            purpose='probe',
            route='probe/' + layout + '/' + phase,
            prefix_policy=layout,
            phase=phase + '/' + repetition,
        ))

    application_rows = []
    application_call_rows = []
    for app in apps:
        run_dir = source / app['id'] / Path(app['run_dir']).name
        raw = json.loads((run_dir / 'result.json').read_text())
        current, summary = _application_rows(app, raw, pricing)
        rows.extend(current)
        application_call_rows.extend(current)
        application_rows.append(summary)

    billed = [row for row in rows if row['status'] == 'billed']
    application_billed = [row for row in application_call_rows if row['status'] == 'billed']
    application_total_afp = round(sum(row['charged_afp'] for row in application_billed), 8)
    application_output_afp = round(sum(row['output_afp'] for row in application_billed), 8)
    application_input_tokens = sum(row['input_tokens'] for row in application_billed)
    application_output_tokens = sum(row['output_tokens'] for row in application_billed)
    application_reasoning_tokens = sum(row['reasoning_tokens'] for row in application_billed)
    total_afp = round(sum(row['charged_afp'] for row in billed), 8)
    input_tokens = sum(row['input_tokens'] for row in billed)
    output_tokens = sum(row['output_tokens'] for row in billed)
    input_afp = round(sum(row['input_afp'] for row in billed if row['input_afp'] is not None), 8)
    output_afp = round(sum(row['output_afp'] for row in billed), 8)

    result = {
        'schema_version': 'afp-cost-breakdown-v1',
        'source_freeze_sha256': frozen['sha256'],
        'analysis_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'actual_calls': status['actual_calls'],
        'ledger_calls': len(rows),
        'billed_calls': len(billed),
        'unknown_usage_calls': len(rows) - len(billed),
        'total_afp': total_afp,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'reasoning_tokens': sum(row['reasoning_tokens'] for row in billed),
        'cached_tokens': sum(row['cached_tokens'] for row in billed if row['cached_tokens'] is not None),
        'cache_unknown_calls': sum(row['cached_tokens'] is None for row in billed),
        'input_afp': input_afp,
        'input_afp_unknown_calls': sum(row['input_afp'] is None for row in billed),
        'output_afp': output_afp,
        'output_afp_share': round(output_afp / total_afp, 8),
        'output_token_share': round(output_tokens / (input_tokens + output_tokens), 8),
        'cache_discount_verified': False,
        'human_quality_verified': False,
        'accepted_task_count': None,
        'afp_per_accepted_task': None,
        'quality_gate_status': 'pending-issue-52',
        'by_purpose': _aggregate(rows, 'purpose', lambda row: row['purpose']),
        'by_model': _aggregate(rows, 'model', lambda row: row['model_id']),
        'by_prefix_policy': _aggregate(rows, 'prefix_policy', lambda row: row['prefix_policy']),
        'by_route': _aggregate(rows, 'route', lambda row: row['route']),
        'application_by_model': _aggregate(application_call_rows, 'model', lambda row: row['model_id']),
        'application_totals': {
            'calls': len(application_billed),
            'total_afp': application_total_afp,
            'input_tokens': application_input_tokens,
            'output_tokens': application_output_tokens,
            'reasoning_tokens': application_reasoning_tokens,
            'cached_tokens': sum(
                row['cached_tokens'] for row in application_billed
                if row['cached_tokens'] is not None
            ),
            'cache_unknown_calls': sum(row['cached_tokens'] is None for row in application_billed),
            'input_afp': round(sum(
                row['input_afp'] for row in application_billed
                if row['input_afp'] is not None
            ), 8),
            'input_afp_unknown_calls': sum(row['input_afp'] is None for row in application_billed),
            'output_afp': application_output_afp,
            'output_afp_share': (
                round(application_output_afp / application_total_afp, 8)
                if application_total_afp else None
            ),
            'reasoning_token_share_of_output': (
                round(application_reasoning_tokens / application_output_tokens, 8)
                if application_output_tokens else None
            ),
        },
        'applications': application_rows,
    }
    if result['actual_calls'] != result['ledger_calls']:
        raise ValueError('实际调用数与合并账本不一致')
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / 'analysis.json', result)
    _write_readme(output, result)
    return result


def _format_number(value):
    return f'{value:.5f}'


def _format_share(value):
    return f'{value * 100:.2f}%'


def _write_readme(output, result):
    lines = [
        '# AFP 成本分解（零调用）',
        '',
        '冻结摘要：' + result['source_freeze_sha256'] + '。原始证据摘要核对通过。',
        '',
        '合并 ' + str(result['ledger_calls']) + ' 次调用，其中 ' + str(result['billed_calls'])
        + ' 次已结算、' + str(result['unknown_usage_calls']) + ' 次用量未知；按冻结价格总计 '
        + _format_number(result['total_afp']) + ' AFP。输入 ' + str(result['input_tokens'])
        + ' token，输出 ' + str(result['output_tokens']) + ' token，其中推理 token '
        + str(result['reasoning_tokens']) + '。',
        '',
        '输入 AFP ' + _format_number(result['input_afp']) + '，输出 AFP '
        + _format_number(result['output_afp']) + '；输出占 '
        + _format_share(result['output_afp_share']) + ' AFP 和 '
        + _format_share(result['output_token_share']) + ' token。',
        '接口报告缓存命中 ' + str(result['cached_tokens'])
        + ' token，但未核实 Agent Plan 缓存折扣，不能折算为节省。',
        '',
        '## 按用途',
        '',
        '| 用途 | 调用 | AFP | 输入 token | 输出 token | 输出 AFP | 输出 AFP 占比 |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for row in result['by_purpose']:
        lines.append(
            '| ' + row['purpose'] + ' | ' + str(row['calls']) + ' | '
            + _format_number(row['billed_afp']) + ' | ' + str(row['input_tokens']) + ' | '
            + str(row['output_tokens']) + ' | ' + _format_number(row['output_afp']) + ' | '
            + _format_share(row['output_afp_share']) + ' |'
        )
    lines.extend([
        '',
        '## 按模型',
        '',
        '| 模型 | 调用 | AFP | 输入 token | 输出 token | 输出 AFP | 输出 AFP 占比 |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ])
    for row in result['by_model']:
        lines.append(
            '| ' + row['model'] + ' | ' + str(row['calls']) + ' | '
            + _format_number(row['billed_afp']) + ' | ' + str(row['input_tokens']) + ' | '
            + str(row['output_tokens']) + ' | ' + _format_number(row['output_afp']) + ' | '
            + _format_share(row['output_afp_share']) + ' |'
        )
    lines.extend([
        '',
        '## 应用路线',
        '',
        '| 路线 | 节点 | 调用 | 端到端秒数 | 生产 AFP | 评审 AFP | 总 AFP | 输出 AFP | 模型评分 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ])
    for row in result['applications']:
        lines.append(
            '| ' + row['route'] + ' | ' + str(row['node_count']) + ' | ' + str(row['calls']) + ' | '
            + f"{row['wall_time_ms'] / 1000:.3f}" + ' | ' + _format_number(row['production_afp']) + ' | '
            + _format_number(row['evaluation_afp']) + ' | ' + _format_number(row['total_afp']) + ' | '
            + _format_number(row['output_afp']) + ' | ' + str(row['model_judge_score']) + ' |'
        )
    totals = result['application_totals']
    lines.extend([
        '',
        '## 应用侧成本结构',
        '',
        '剔除接口探针后，应用路线合计 ' + str(totals['calls']) + ' 次调用、'
        + _format_number(totals['total_afp']) + ' AFP；输入 '
        + str(totals['input_tokens']) + ' token，输出 ' + str(totals['output_tokens'])
        + ' token，其中推理 token ' + str(totals['reasoning_tokens']) + '。',
        '应用侧输出 AFP ' + _format_number(totals['output_afp']) + '，占 '
        + _format_share(totals['output_afp_share']) + '；推理 token 占输出 token 的 '
        + _format_share(totals['reasoning_token_share_of_output']) + '。',
        '',
        '| 模型 | 调用 | AFP | 输入 token | 输出 token | 输出 AFP |',
        '|---|---:|---:|---:|---:|---:|',
    ])
    for row in result['application_by_model']:
        lines.append(
            '| ' + row['model'] + ' | ' + str(row['calls']) + ' | '
            + _format_number(row['billed_afp']) + ' | ' + str(row['input_tokens']) + ' | '
            + str(row['output_tokens']) + ' | ' + _format_number(row['output_afp']) + ' |'
        )
    probe = next(row for row in result['by_purpose'] if row['purpose'] == 'probe')
    cheapest = min(result['applications'], key=lambda row: row['total_afp'])
    lines.extend([
        '',
        '## 主要发现',
        '',
        '1. 诊断探针消耗 ' + _format_number(probe['billed_afp']) + ' AFP，占整批 '
        + f"{probe['billed_afp'] / result['total_afp'] * 100:.2f}" + '%。'
        + '这些是接口诊断成本，不是任何用户路线的端到端成本，不能混入直接回答与 DAG 的路线比较。',
        '2. 应用侧输出 AFP 占 ' + _format_share(totals['output_afp_share'])
        + '，推理 token 占输出 token 的 ' + _format_share(totals['reasoning_token_share_of_output'])
        + '。下一轮成本优化应优先研究结构化中间产物、评审输出压缩和推理输出控制，而不是只优化输入前缀。',
        '3. 接口报告缓存命中 ' + str(result['cached_tokens'])
        + ' token，但 cached token 按普通输入价格计入本账本。在官方折扣或控制台逐笔扣减被核实前，'
        + '不能把命中 token 解释为 AFP 节省。',
        '4. 本批应用路线各只有一次，' + cheapest['route'] + ' 的 '
        + _format_number(cheapest['total_afp']) + ' AFP 是单次最低观测值，不是稳定成本最优结论。',
        '5. #52 的独立真人质量门槛尚未完成，因此不计算「AFP per accepted task」，'
        + '也不宣称质量等价或 Pareto 改善。',
        '',
        '## 解释边界',
        '',
        '- 本分析只读取已归档证据，未发起任何模型调用；所有 AFP 均按冻结价格复算并逐调用核对。',
        '- 探针、应用生产和最终评审分开统计；探针成本不能摊入用户路线。',
        '- 输出压缩只是下一步假设，不能通过硬截断牺牲质量；任何输出约束变化都须通过 #52 质量门槛后实验。',
        '- 单次应用观察受输出长度、随机性和服务负载影响，不能用于效应估计或稳定排名。',
        '- 人工复核尚未发生；模型评审分数只能作为开发诊断信号。',
        '- 本批非流式请求未提供 TTFT；报告使用请求耗时和端到端耗时，不把总耗时冒充首 token 时延。',
        '',
        '## 下一轮可检验假设',
        '',
        '1. 在 #52 质量门槛下，把中间节点输出限制为事实、字段、来源与不确定性，'
        + '能降低输出 AFP 且不降低任务通过率。',
        '2. 缩短最终评审的结构化理由，只保留逐项判定和关键证据，'
        + '能降低评审输出 AFP 且不降低复核可用性。',
        '3. 默认直接回答、仅在预期净 AFP 降低时拆分，优于当前固定三节点图；'
        + '该假设需要独立留出样本和重复实验。',
        '',
    ])
    (output / 'README.md').write_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='已冻结的前缀缓存证据目录')
    parser.add_argument('output', type=Path, help='新的分析输出目录')
    args = parser.parse_args()
    analyze(args.source, args.output)


if __name__ == '__main__':
    main()
