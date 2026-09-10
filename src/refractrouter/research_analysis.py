"""研究记录的共同配对、全计划交付分母与按任务聚类的区间。"""
from collections import defaultdict
import math
import random
import statistics


def _finite(value, name, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'invalid {name}')
    if nonnegative and value < 0:
        raise ValueError(f'negative {name}')
    return value


def _interval(values, *, repeats, seed):
    """每个输入已是同一任务全部配对重复的均值，不能再次按调用重采样。"""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(repeats))
    # 两个主比较 Bonferroni：每个区间覆盖率 97.5%。不把该近似当作精度保证。
    return [samples[int((repeats - 1) * .0125)], samples[math.ceil((repeats - 1) * .9875)]]


def compare_research(preview, protocol, rows, *, simulated, setup_cost=None):
    """只分析显式记录；遗漏运行保留在交付分母，未知费用绝不补零。"""
    planned = {(r['task_id'], r['repeat'], r['arm']): r for r in preview['runs']}
    if len(planned) != len(preview['runs']):
        raise ValueError('duplicate planned run')
    observed = {}
    for row in rows:
        key = row['task_id'], row['repeat'], row['arm']
        if key not in planned or key in observed:
            raise ValueError('unknown or duplicate observed run')
        if row['cell'] != planned[key]['cell']:
            raise ValueError('observed stratum changed')
        if type(row['delivered']) is not bool:
            raise ValueError('invalid delivery status')
        if row.get('score') is not None:
            score = _finite(row['score'], 'score', nonnegative=True)
            if score > 100:
                raise ValueError('score exceeds 100')
        if row['delivered'] and (row.get('judge_passed') is not True or row.get('score') is None
                or row['score'] < protocol['constraints']['qualityMin']):
            raise ValueError('delivery requires independently graded quality')
        for field in ('deployment_cost', 'wall_time_ms'):
            if row.get(field) is not None:
                _finite(row[field], field, nonnegative=True)
        observed[key] = row
    if setup_cost is not None:
        _finite(setup_cost, 'setup cost', nonnegative=True)
    repeats = protocol['acceptance']['bootstrap_repeats']
    if type(repeats) is not int or not 100 <= repeats <= 100000:
        raise ValueError('invalid bootstrap count')
    seed = protocol['acceptance']['bootstrap_seed']
    if type(seed) is not int:
        raise ValueError('invalid bootstrap seed')

    groups = {}
    for cell in [None, *protocol['coverage_cells']]:
        selected = {k: r for k, r in planned.items() if cell is None or r['cell'] == cell}
        arms = {}
        for arm in protocol['arms']:
            keys = [k for k in selected if k[2] == arm]
            measured = [observed[k] for k in keys if k in observed]
            known = [r['deployment_cost'] for r in measured if r.get('deployment_cost') is not None]
            complete_cost = len(measured) == len(keys) == len(known)
            arms[arm] = {'planned': len(keys), 'observed': len(measured),
                'delivered': sum(r['delivered'] for r in measured),
                'delivery_rate': sum(r['delivered'] for r in measured) / len(keys) if keys else None,
                'known_cost_subtotal': sum(known), 'full_deployment_cost': sum(known) if complete_cost else None,
                'cost_complete': complete_cost, 'missing_runs': len(keys) - len(measured)}
        comparisons = []
        for left, right in protocol['acceptance']['primary_pairs']:
            # 三个指标使用同一组记录，保留质量失败但有有效评分的样本。
            clusters = defaultdict(list)
            for tid, repeat, arm in selected:
                if arm != left:
                    continue
                a, b = observed.get((tid, repeat, left)), observed.get((tid, repeat, right))
                fields = ('score', 'deployment_cost', 'wall_time_ms')
                if a is None or b is None or any(r.get(f) is None for r in (a, b) for f in fields):
                    continue
                if b['deployment_cost'] <= 0 or b['wall_time_ms'] <= 0:
                    continue
                clusters[tid].append([a[f] - b[f] for f in fields] + [
                    1-a['deployment_cost']/b['deployment_cost'], a['wall_time_ms']/b['wall_time_ms']])
            metrics = {}
            for i, field in enumerate(('score', 'deployment_cost', 'wall_time_ms','cost_saving_fraction','latency_ratio')):
                values = [statistics.mean(v[i] for v in pair_rows) for pair_rows in clusters.values()]
                metrics[field] = {'mean_delta': statistics.mean(values) if values else None,
                    'interval_97_5': _interval(values, repeats=repeats, seed=seed)}
            expected_pairs = sum(k[2]==left for k in selected)
            all_delivered = all(k in observed and observed[k]['delivered'] for k in selected if k[2] in (left,right))
            paired = sum(map(len, clusters.values()))
            limits = protocol['acceptance']
            if simulated:
                verdict = 'simulated-no-benefit-claim'
            elif paired != expected_pairs or len(clusters)<2:
                verdict = 'insufficient-paired-evidence'
            elif not {'maximum_quality_loss','minimum_cost_saving','maximum_latency_ratio'} <= limits.keys():
                verdict = 'thresholds-not-configured'
            else:
                signal = (all_delivered and metrics['score']['interval_97_5'][0] >= -limits['maximum_quality_loss']
                    and metrics['cost_saving_fraction']['interval_97_5'][0] >= limits['minimum_cost_saving']
                    and metrics['latency_ratio']['interval_97_5'][1] <= limits['maximum_latency_ratio'])
                verdict = 'supported-within-frozen-cases' if signal else 'does-not-meet-frozen-benefit-thresholds'
            comparisons.append({'left': left, 'right': right, 'task_clusters': len(clusters),
                'paired_repeats': paired, 'expected_pairs':expected_pairs, 'metrics': metrics,
                'benefit_verdict':verdict, 'all_planned_delivered':all_delivered})
        groups['overall' if cell is None else cell] = {'arms': arms, 'primary_comparisons': comparisons}
    costs = groups['overall']['arms'].values()
    complete = all(a['cost_complete'] for a in costs)
    runtime_cost = sum(a['full_deployment_cost'] for a in costs) if complete else None
    return {'schema_version': 'research-analysis-v1', 'simulated': simulated, 'groups': groups,
        'first_use_cost': runtime_cost + setup_cost if runtime_cost is not None and setup_cost is not None else None,
        'runtime_cost': runtime_cost, 'setup_cost': setup_cost,
        'benefit_verified': any(c['benefit_verdict']=='supported-within-frozen-cases'
            for c in groups['overall']['primary_comparisons']) if not simulated else False,
        'limitations': ['模拟结果不能证明路由收益；材料独立性与人工复核必须另外验收。',
            '共同配对区间是条件于已有评分的结果；必须同时阅读全计划交付率和完整费用。',
            '差值方向为左减右；重复先按任务平均，分层区间仅作探索描述，不报告小样本 p95。',
            '首次使用包含全部已提供的校准、搜索与缓存设置费；缺少设置费时不计算首次使用成本。']}
