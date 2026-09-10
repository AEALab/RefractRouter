"""冻结的任务配对统计；不把重复调用当独立任务，不从成功子集挑选前沿。"""
from collections import defaultdict
import math
import random
import statistics

from .quality_runtime import ARMS
from .quality_study import adjudicate, digest


POLICY = {
    'schema_version': 'quality-statistics-v1',
    'study_tier': 'controlled-exploratory', 'confirmatory_population_claims': False,
    'repeats': 3, 'pass_rate_floor': .90, 'noninferiority_margin': .05,
    'threshold_meaning': '研究操作门槛：至少九成任务三次均确认通过；非劣容忍五个百分点。'
                         '不是用户可接受性的实证结论，真人用途确认单独待办。',
    'quality_unit': 'task:all-frozen-repeats-confirmed-pass',
    'familywise_alpha': .05,
    'quality_tail_alpha': .05 / (len(ARMS) + 4),
    'primary_pairs': [['direct-or-dag', 'direct-strong'], ['direct-or-dag', 'task-selector']],
    'quality_interval': '精确二项下界；配对差使用正负不一致概率的精确上下界及并集界。',
    'bootstrap_draws': 10000, 'bootstrap_seed': 52053,
    'performance_interval': '先在任务内汇总全部重复，再按来源族配对百分位重采样；只作探索诊断。',
    'minimum_useful_relative_gain': .10,
    'sample_size': {'development': 6, 'holdout_candidate': 12,
                    'purpose': '固定控制题的有限候选探索，不为总体非劣、SLA或p95提供把握度保证。'},
    'failures': '失败及pending留在预定分母；费用和时延使用同一完整任务集合；缺失或未知阻止比较。',
    'human_gate': '真人语义判定与用途门槛确认未完成前，不生成确认质量可行的前沿。',
    'sources': ['https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm',
                'https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html'],
}


def binomial_lower(successes, total, alpha=.05):
    """反演二项上尾得到一侧 Clopper–Pearson 下界，使用标准库避免近似正态。"""
    if type(total) is not int or type(successes) is not int or total < 1 or not 0 <= successes <= total or not 0 < alpha < 1:
        raise ValueError('invalid binomial counts or tail probability')
    if successes == 0:
        return 0.0
    if successes == total:
        return alpha ** (1 / total)
    lo, hi = 0.0, 1.0
    for _ in range(80):
        p = (lo + hi) / 2
        tail = sum(math.comb(total, k) * p ** k * (1 - p) ** (total - k) for k in range(successes, total + 1))
        if tail < alpha: lo = p
        else: hi = p
    return (lo + hi) / 2


def paired_quality_lower(candidate, reference, alpha):
    if not candidate or len(candidate) != len(reference) or any(type(v) is not bool for v in candidate + reference):
        raise ValueError('paired binary task outcomes required')
    n = len(candidate)
    positive = sum(a and not b for a, b in zip(candidate, reference))
    negative = sum(b and not a for a, b in zip(candidate, reference))
    # P(候选独过)-P(参考独过)。两条一侧界无需假设两种不一致事件独立。
    return binomial_lower(positive, n, alpha) - (1 - binomial_lower(n - negative, n, alpha))


def paired_performance(candidate, reference, clusters, *, seed=52053, draws=10000):
    if not candidate or set(candidate) != set(reference) or set(candidate) != set(clusters):
        raise ValueError('performance requires an identical complete paired task cohort')
    if any(not math.isfinite(v) or v < 0 for values in (candidate, reference) for v in values.values()):
        raise ValueError('non-finite or negative performance metric')
    grouped = defaultdict(list)
    for tid in sorted(candidate): grouped[clusters[tid]].append(tid)
    ids = sorted(grouped); rng = random.Random(seed)
    means = []
    for _ in range(draws):
        sample = [tid for _ in ids for tid in grouped[rng.choice(ids)]]
        means.append(statistics.mean(candidate[t] - reference[t] for t in sample))
    means.sort()
    ref = statistics.mean(reference.values()); observed = statistics.mean(candidate.values()) - ref
    return {'task_count': len(candidate), 'source_count': len(ids), 'mean_difference': observed,
            'relative_gain': None if ref == 0 else -observed / ref,
            'interval': [means[int(.025 * (draws - 1))], means[int(.975 * (draws - 1))]],
            'degenerate': means[0] == means[-1], 'inference': 'exploratory-only'}


def analyze(frozen, result, tasks, *, references=None, human_reviews=(), purpose_review=None):
    if result['frozen_sha256'] != digest(frozen):
        raise ValueError('results bound to another protocol')
    expected = {r['run_id']: r for r in frozen['schedule']}
    rows = {}; by_id = {t['task_id']: t for t in tasks}
    for row in result['runs']:
        if row['run_id'] not in expected or row['run_id'] in rows:
            raise ValueError('unknown or duplicated result row')
        if any(row[k] != expected[row['run_id']][k] for k in ('task_id', 'repeat', 'arm')):
            raise ValueError('result pairing changed')
        row = dict(row)
        if references is not None and row.get('status') == 'delivered-unconfirmed' and 'output' in row:
            row['quality_status'] = adjudicate(by_id[row['task_id']], references[row['task_id']],
                                               row['output'], human_reviews)['status']
        rows[row['run_id']] = row
    arms = frozen['selection']['arms']; tids = frozen['selection']['task_ids']
    groups = defaultdict(list)
    for spec in frozen['schedule']:
        groups[spec['arm'], spec['task_id']].append(rows.get(spec['run_id']))
    approved = bool(purpose_review and purpose_review.get('origin') == 'human'
        and purpose_review.get('reviewer') and purpose_review.get('evidence')
        and purpose_review.get('policy_sha256') == digest(POLICY)
        and purpose_review.get('task_bindings') == frozen['task_bindings']
        and purpose_review.get('verdict') == 'pass'
        and purpose_review['reviewer'] not in {t['provenance']['creator'] for t in tasks})
    full_design = (frozen['selection']['repeats'] == POLICY['repeats']
                   and len(tids) == POLICY['sample_size']['holdout_candidate']
                   and set(frozen['splits'].values()) == {'holdout-candidate'})
    summaries = {}; outcomes = {}; metrics = {}
    for arm in arms:
        sample = [row for tid in tids for row in groups[arm, tid]]
        counts = {s: sum((r.get('quality_status', 'pending') if r else 'pending') == s for r in sample) for s in ('pass', 'fail', 'pending')}
        robust = [all(r and r.get('quality_status') == 'pass' for r in groups[arm, tid]) for tid in tids]
        lower = binomial_lower(sum(robust), len(tids), POLICY['quality_tail_alpha'])
        complete = all(r and r.get('cost_known') and all(type(r.get(k)) in (int, float) and math.isfinite(r[k]) and r[k] >= 0
                                                      for k in ('online_afp', 'online_finished_ms')) for r in sample)
        summaries[arm] = {'run_counts': counts, 'planned_runs': len(sample), 'robust_pass_tasks': sum(robust),
            'tasks': len(tids), 'observed_robust_pass_rate': sum(robust) / len(tids),
            'conditional_binomial_lower': lower,
            'confirmed_quality_feasible': bool(approved and full_design and not result['simulated']
                and references is not None and counts['pending'] == 0 and sum(robust) / len(tids) >= POLICY['pass_rate_floor']),
            'performance_complete': complete,
            'mean_online_afp': statistics.mean(r['online_afp'] for r in sample) if complete else None,
            'mean_online_ms': statistics.mean(r['online_finished_ms'] for r in sample) if complete else None,
            'median_online_ms': statistics.median(r['online_finished_ms'] for r in sample) if complete else None}
        outcomes[arm] = robust
        metrics[arm] = {key: {tid: statistics.mean(r[key] for r in groups[arm, tid]) for tid in tids}
                        for key in ('online_afp', 'online_finished_ms')} if complete else None
    comparisons = []
    for candidate, reference in POLICY['primary_pairs']:
        if candidate not in arms or reference not in arms: continue
        row = {'candidate': candidate, 'reference': reference,
               'quality_difference_lower': paired_quality_lower(outcomes[candidate], outcomes[reference], POLICY['quality_tail_alpha']),
               'conclusion': 'human-quality-or-exploratory-evidence-pending'}
        row['conditional_noninferiority_supported'] = bool(approved and full_design
            and not summaries[candidate]['run_counts']['pending'] and not summaries[reference]['run_counts']['pending']
            and row['quality_difference_lower'] >= -POLICY['noninferiority_margin'])
        if row['conditional_noninferiority_supported']:
            row['conclusion'] = '条件二项假设下支持非劣；构造样本不支持业务总体推广。'
        if metrics[candidate] is not None and metrics[reference] is not None:
            row['performance'] = {k: paired_performance(metrics[candidate][k], metrics[reference][k],
                {tid: by_id[tid]['source_family'] for tid in tids}, draws=POLICY['bootstrap_draws']) for k in metrics[candidate]}
        else: row['performance'] = None
        comparisons.append(row)
    feasible = [a for a in arms if summaries[a]['confirmed_quality_feasible'] and summaries[a]['performance_complete']]
    frontier = [a for a in feasible if not any(b != a and
        summaries[b]['mean_online_afp'] <= summaries[a]['mean_online_afp'] and
        summaries[b]['mean_online_ms'] <= summaries[a]['mean_online_ms'] and
        (summaries[b]['mean_online_afp'] < summaries[a]['mean_online_afp'] or
         summaries[b]['mean_online_ms'] < summaries[a]['mean_online_ms']) for b in feasible)]
    return {'schema_version': 'quality-statistics-report-v1', 'policy': POLICY,
            'simulated': result['simulated'], 'planned_runs': len(expected), 'observed_runs': len(rows),
            'missing_runs': sorted(set(expected) - set(rows)), 'arms': summaries, 'comparisons': comparisons,
            'confirmed_pareto_frontier': frontier, 'frontier_scope': '仅本批有限候选及真人确认样本的经验前沿',
            'human_review_pending': not approved or any(s['run_counts']['pending'] for s in summaries.values()),
            'reviewer_identity_authenticated_by_code': False,
            'limitations': ['固定构造任务不是从业务分布随机抽样，二项界仅展示条件假设下的不确定性。',
                            '三次重复先在任务内汇总；不把重复调用当成三个独立任务。',
                            '退化重采样区间不构成零不确定性或性能优势证明。']}
