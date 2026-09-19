"""冻结的任务配对统计；不把重复调用当独立任务，不从成功子集挑选前沿。"""
from collections import defaultdict
import math
import random
import statistics

from .moa_review import MOA_POLICY, final_quality_status
from .quality_runtime import ARMS, human_gate, moa_gate
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
    'descriptive_strata': ['category', 'structure_stratum'],
    'setup_accounting': '共享图准备单列，并按1/3/10/100次复用分配；不是冷启动墙钟实测。',
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


def _finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _review_time(records):
    """单独汇总真人复核时间；缺失不填零，也不并入模型 AFP。"""
    rows = [r for r in records if isinstance(r, dict) and r.get('origin') == 'human']
    known = 0; missing = invalid = 0
    for record in rows:
        value = record.get('review_time_ms')
        if _finite_nonnegative(value):
            known += value
        elif value is None:
            missing += 1
        else:
            invalid += 1
    complete = bool(rows) and not missing and not invalid
    return {'records': len(rows), 'known_ms': known, 'missing_records': missing,
            'invalid_records': invalid, 'total_ms': known if complete else None}


def _task_cost(rows, setup, *, shared):
    """按任务聚合在线执行、离线研究与共享图准备 AFP。"""
    unknown = (not rows or any(not row or row.get('cost_known') is not True
                               or not _finite_nonnegative(row.get('online_afp'))
                               or not _finite_nonnegative(row.get('offline_afp'))
                               for row in rows))
    if shared and (not setup or setup.get('status') != 'ready'
                   or not _finite_nonnegative(setup.get('offline_afp'))):
        unknown = True
    if unknown:
        return {'known': False, 'online_afp': None, 'research_afp': None,
                'setup_afp': None, 'total_afp': None}
    online = sum(row['online_afp'] for row in rows)
    research = sum(row['offline_afp'] for row in rows)
    setup_afp = setup['offline_afp'] if shared else 0
    return {'known': True, 'online_afp': online, 'research_afp': research,
            'setup_afp': setup_afp, 'total_afp': online + research + setup_afp}


def _bound_moa_output_review(reviews, row, task):
    """返回与 run、任务哈希和输出哈希同时绑定的 MoA 交付评审记录。"""
    for record in reviews:
        if (record.get('run_id') == row['run_id'] and record.get('task_id') == row['task_id']
                and record.get('task_sha256') == task['task_sha256']
                and record.get('output_sha256') == digest(row['output'])
                and record.get('policy_sha256') == digest(MOA_POLICY)
                and isinstance(record.get('consensus'), dict)):
            return record
    return None


def _moa_review_cost(material_reviews, output_reviews, purpose):
    """汇总 MoA 评审调用成本；外部用量未知，不填零、不并入 Ark AFP。"""
    categories = (('material', material_reviews), ('output', output_reviews),
                  ('purpose', [purpose] if purpose else ()))
    calls = failed = missing_time = 0
    known_ms = 0.0
    by_reviewer = {}
    for _, records in categories:
        for record in records:
            for phase in ('primary', 'escalation'):
                for call in record.get(phase, ()):
                    calls += 1
                    key = (call.get('cli'), call.get('model'), call.get('thinking_effort'))
                    counts = by_reviewer.setdefault(key, {'calls': 0, 'failed_calls': 0})
                    counts['calls'] += 1
                    if call.get('status') != 'reviewed':
                        counts['failed_calls'] += 1
                        failed += 1
                    value = call.get('wall_time_ms')
                    if _finite_nonnegative(value):
                        known_ms += value
                    else:
                        missing_time += 1
    return {'real_model_calls': calls, 'failed_calls': failed,
            'known_wall_time_ms': known_ms if not missing_time else None,
            'records_missing_wall_time': missing_time,
            'calls_by_reviewer': [{'cli': cli, 'model': model, 'thinking_effort': effort, **counts}
                                  for (cli, model, effort), counts in sorted(by_reviewer.items())],
            'included_in_ark_afp': False, 'external_usage': 'unknown',
            'policy_sha256': digest(MOA_POLICY),
            'scope': 'MoA 评审消耗本机 CLI 账号；外部用量未知，不折算为零，也不并入 Ark AFP。'}


def analyze(frozen, result, tasks, *, references=None, human_reviews=(), purpose_review=None,
            moa_material_reviews=(), moa_output_reviews=(), moa_purpose_review=None,
            human_tiebreaks=()):
    if frozen['statistics_policy'] != POLICY:
        raise ValueError('analysis policy differs from frozen protocol')
    if result['frozen_sha256'] != digest(frozen):
        raise ValueError('results bound to another protocol')
    expected = {r['run_id']: r for r in frozen['schedule']}
    rows = {}; by_id = {t['task_id']: t for t in tasks}
    moa_bound_runs = []
    for row in result['runs']:
        if row['run_id'] not in expected or row['run_id'] in rows:
            raise ValueError('unknown or duplicated result row')
        if any(row[k] != expected[row['run_id']][k] for k in ('task_id', 'repeat', 'arm')):
            raise ValueError('result pairing changed')
        row = dict(row)
        if references is not None:
            if row.get('status') == 'delivered-unconfirmed' and 'output' in row:
                adjudication = adjudicate(by_id[row['task_id']], references[row['task_id']],
                                          row['output'], human_reviews)
                moa_record = _bound_moa_output_review(moa_output_reviews, row, by_id[row['task_id']])
                if moa_record is not None:
                    row['quality_status'] = final_quality_status(
                        adjudication['deterministic']['status'], moa_record['consensus']['overall'])
                    row['quality_status_source'] = 'deterministic-and-moa-consensus'
                    moa_bound_runs.append(row['run_id'])
                else:
                    row['quality_status'] = adjudication['status']
                    row['quality_status_source'] = 'deterministic-and-human-records'
            else:
                row['quality_status'] = 'fail' if row.get('status') in ('failed', 'withheld', 'deadline-failed') else 'pending'
                row['quality_status_source'] = 'run-status'
        rows[row['run_id']] = row
    arms = frozen['selection']['arms']; tids = frozen['selection']['task_ids']
    groups = defaultdict(list)
    for spec in frozen['schedule']:
        groups[spec['arm'], spec['task_id']].append(rows.get(spec['run_id']))
    setups = {}
    for setup in result.get('setups', []):
        if setup['task_id'] in setups:
            raise ValueError('duplicated setup row')
        setups[setup['task_id']] = setup
    gate_evidence = result.get('human_gate_evidence') or {}
    purpose_review = purpose_review or gate_evidence.get('purpose_review')
    approved = bool(purpose_review and purpose_review.get('origin') == 'human'
        and purpose_review.get('reviewer') and purpose_review.get('evidence')
        and purpose_review.get('policy_sha256') == digest(POLICY)
        and purpose_review.get('task_bindings') == frozen['task_bindings']
        and purpose_review.get('verdict') == 'pass'
        and purpose_review['reviewer'] not in {t['provenance']['creator'] for t in tasks})
    material_reviews = gate_evidence.get('material_reviews') or ()
    material_gate_ready = references is not None and human_gate(
        frozen, tasks, references, material_reviews, purpose_review)
    moa_gate_evidence = result.get('moa_gate_evidence') or {}
    moa_material_reviews = moa_material_reviews or moa_gate_evidence.get('material_reviews') or ()
    moa_purpose_review = moa_purpose_review or moa_gate_evidence.get('purpose_review')
    moa_purpose = moa_purpose_review or {}
    moa_purpose_approved = bool(moa_purpose.get('policy_sha256') == digest(MOA_POLICY)
        and moa_purpose.get('statistics_policy_sha256') == digest(POLICY)
        and moa_purpose.get('task_bindings') == frozen['task_bindings']
        and (moa_purpose.get('consensus') or {}).get('overall') == 'pass')
    moa_gate_ready = references is not None and moa_gate(
        frozen, tasks, references, moa_material_reviews, moa_purpose_review,
        human_tiebreaks=human_tiebreaks)
    human_gate_active = bool(approved and material_gate_ready)
    moa_gate_active = bool(moa_purpose_approved and moa_gate_ready)
    quality_gate_active = human_gate_active or moa_gate_active
    issue52_gate_ready = bool(references is not None and quality_gate_active
                              and not result['simulated'])
    full_design = (frozen['selection']['repeats'] == POLICY['repeats']
                   and len(tids) == POLICY['sample_size']['holdout_candidate']
                   and set(frozen['splits'].values()) == {'holdout-candidate'})
    summaries = {}; outcomes = {}; metrics = {}
    for arm in arms:
        sample = [row for tid in tids for row in groups[arm, tid]]
        counts = {s: sum((r.get('quality_status', 'pending') if r else 'pending') == s for r in sample) for s in ('pass', 'fail', 'pending')}
        robust = [all(r and r.get('quality_status') == 'pass' for r in groups[arm, tid]) for tid in tids]
        failed_tasks = [any(r and r.get('quality_status') == 'fail' for r in groups[arm, tid]) for tid in tids]
        accepted_tasks = [accepted and issue52_gate_ready for accepted in robust]
        pending_tasks = [not accepted and not failed
                         for accepted, failed in zip(accepted_tasks, failed_tasks)]
        lower = binomial_lower(sum(robust), len(tids), POLICY['quality_tail_alpha'])
        complete = all(r and r.get('cost_known') and all(type(r.get(k)) in (int, float) and math.isfinite(r[k]) and r[k] >= 0
                                                      for k in ('online_afp', 'online_finished_ms')) for r in sample)
        costs = {tid: _task_cost(groups[arm, tid], setups.get(tid), shared=arm.startswith('shared-'))
                 for tid in tids}
        unknown_costs = [not cost['known'] for cost in costs.values()]
        accepted_count = sum(accepted_tasks)
        costs_complete = not any(unknown_costs)
        accepted_costs_complete = accepted_count and all(
            cost['known'] for accepted, cost in zip(accepted_tasks, costs.values()) if accepted)
        accepted_online = sum(costs[tid]['online_afp'] for tid, accepted
                              in zip(tids, accepted_tasks) if accepted) if accepted_costs_complete else None
        accepted_research = sum(costs[tid]['research_afp'] for tid, accepted
                                in zip(tids, accepted_tasks) if accepted) if accepted_costs_complete else None
        accepted_setup = sum(costs[tid]['setup_afp'] for tid, accepted
                             in zip(tids, accepted_tasks) if accepted) if accepted_costs_complete else None
        accepted_total = (accepted_online + accepted_research + accepted_setup
                          if accepted_costs_complete else None)
        total_all = sum(cost['total_afp'] for cost in costs.values()) if not any(unknown_costs) else None
        total_online_all = (sum(cost['online_afp'] for cost in costs.values())
                            if not any(unknown_costs) else None)
        summaries[arm] = {'run_counts': counts, 'planned_runs': len(sample), 'robust_pass_tasks': sum(robust),
            'tasks': len(tids), 'observed_robust_pass_rate': sum(robust) / len(tids),
            'adjudicated_pass_task_count': sum(robust), 'adjudicated_pass_rate': sum(robust) / len(tids),
            'accepted_task_count': accepted_count, 'quality_pass_rate': accepted_count / len(tids),
            'failed_task_count': sum(failed_tasks), 'pending_task_count': sum(pending_tasks),
            'unknown_afp_task_count': sum(unknown_costs),
            'conditional_binomial_lower': lower,
            'confirmed_quality_feasible': bool(quality_gate_active and full_design and not result['simulated']
                and references is not None and counts['pending'] == 0
                and sum(robust) / len(tids) >= POLICY['pass_rate_floor']),
            'performance_complete': complete,
            'mean_online_afp': statistics.mean(r['online_afp'] for r in sample) if complete else None,
            'mean_online_ms': statistics.mean(r['online_finished_ms'] for r in sample) if complete else None,
            'median_online_ms': statistics.median(r['online_finished_ms'] for r in sample) if complete else None,
            'accepted_task_metrics': {
                'quality_gate_status': ('active' if issue52_gate_ready else
                                        'pending-issue-52' if references is not None and not result['simulated']
                                        else 'simulated-or-references-unavailable'),
                'total_afp_all_tasks': total_all,
                'accepted_task_online_afp': accepted_online,
                'accepted_task_research_afp': accepted_research,
                'accepted_task_setup_afp': accepted_setup,
                'accepted_task_total_afp': accepted_total,
                'successful_sample_afp': accepted_total,
                'online_afp_per_accepted_task': total_online_all / accepted_count if total_online_all is not None and accepted_count else None,
                'afp_per_accepted_task': total_all / accepted_count if total_all is not None and accepted_count else None,
                'successful_sample_afp_per_accepted_task': accepted_total / accepted_count if accepted_total is not None else None,
                'cost_conclusion_available': bool(accepted_count and costs_complete),
                'cost_scope': '主指标分子为全部任务 Ark AFP（含失败、pending、规划、执行、Ark 内评审与共享图准备）；'
                              'MoA 评审外部成本单列，不混入；成功样本AFP另行单列。',
            }}
        outcomes[arm] = robust
        metrics[arm] = {key: {tid: statistics.mean(r[key] for r in groups[arm, tid]) for tid in tids}
                        for key in ('online_afp', 'online_finished_ms')} if complete else None
    comparisons = []
    for candidate, reference in POLICY['primary_pairs']:
        if candidate not in arms or reference not in arms: continue
        row = {'candidate': candidate, 'reference': reference,
               'quality_difference_lower': paired_quality_lower(outcomes[candidate], outcomes[reference], POLICY['quality_tail_alpha']),
               'conclusion': 'human-quality-or-exploratory-evidence-pending'}
        row['conditional_noninferiority_supported'] = bool(quality_gate_active and full_design
            and references is not None and not result['simulated']
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
    strata = {}
    for field in POLICY['descriptive_strata']:
        strata[field] = {}
        for value in sorted({by_id[t][field] for t in tids}):
            selected = [t for t in tids if by_id[t][field] == value]
            strata[field][value] = {}
            for arm in arms:
                sample = [r for tid in selected for r in groups[arm, tid]]
                complete = all(r and r.get('cost_known') and all(type(r.get(k)) in (int, float)
                    and math.isfinite(r[k]) and r[k] >= 0 for k in ('online_afp', 'online_finished_ms')) for r in sample)
                strata[field][value][arm] = {'tasks': len(selected), 'planned_runs': len(sample),
                    'run_counts': {s: sum((r.get('quality_status', 'pending') if r else 'pending') == s for r in sample)
                                   for s in ('pass', 'fail', 'pending')},
                    'mean_online_afp': statistics.mean(r['online_afp'] for r in sample) if complete else None,
                    'mean_online_ms': statistics.mean(r['online_finished_ms'] for r in sample) if complete else None,
                    'scope': '描述性分层，不作选择最有利子群的主检验。'}
    shared_setup_complete = (len(setups) == len(result.get('setups', [])) and set(setups) == set(tids)
        and all(r.get('status') == 'ready' and all(type(r.get(k)) in (int, float) and math.isfinite(r[k])
               and r[k] >= 0 for k in ('offline_afp', 'wall_time_ms')) for r in setups.values()))
    amortized = {}
    for arm in arms:
        shared = arm.startswith('shared-')
        complete = summaries[arm]['performance_complete'] and (not shared or shared_setup_complete)
        amortized[arm] = {str(n): {'mean_afp_with_setup_allocation': summaries[arm]['mean_online_afp'] +
            (statistics.mean(r['offline_afp'] for r in setups.values()) / n if shared else 0) if complete else None,
            'mean_ms_with_setup_allocation': summaries[arm]['mean_online_ms'] +
            (statistics.mean(r['wall_time_ms'] for r in setups.values()) / n if shared else 0) if complete else None}
            for n in frozen['offline_setup']['amortization_reuses']}
    output_reviews = _review_time(human_reviews)
    material_review_time = _review_time(material_reviews)
    purpose_review_time = _review_time([purpose_review] if purpose_review else [])
    human_review_time = {'output_reviews': output_reviews, 'material_reviews': material_review_time,
                         'purpose_review': purpose_review_time, 'included_in_afp': False,
                         'scope': '仅汇总记录中显式提供的review_time_ms；缺失为null，不填零。'}
    return {'schema_version': 'quality-statistics-report-v2', 'policy': POLICY,
            'simulated': result['simulated'], 'planned_runs': len(expected), 'observed_runs': len(rows),
            'missing_runs': sorted(set(expected) - set(rows)), 'arms': summaries, 'comparisons': comparisons,
            'confirmed_pareto_frontier': frontier, 'frontier_scope': '仅本批有限候选及真人确认样本的经验前沿',
            'descriptive_strata': strata, 'setup_amortization': amortized,
            'setup_amortization_scope': '单一路线复用的分配情景；不把准备在四条共享路线间重复求和，不是真实冷启动时间。',
            'human_review_pending': not approved or not material_gate_ready
                                    or any(s['run_counts']['pending'] for s in summaries.values()),
            'quality_gate_pending': not quality_gate_active
                                    or any(s['run_counts']['pending'] for s in summaries.values()),
            'moa_review': {
                'gate_status': 'active' if moa_gate_active else 'pending',
                'material_gate_ready': moa_gate_ready,
                'human_tiebreaks': [{'task_id': row['task_id'], 'criterion': row['criterion'],
                                     'verdict': row['verdict'], 'adjudicator': row['adjudicator'],
                                     'evidence': row['evidence']} for row in human_tiebreaks],
                'human_tiebreak_scope': ('对冻结机械规则的显式例外：MoA 平票 pending 的 criterion '
                                         '由研究负责人定向裁决替代；逐条留痕，不构成对规则本身的修改。'),
                'purpose_overall': (moa_purpose.get('consensus') or {}).get('overall') if moa_purpose else None,
                'output_review_bound_runs': len(moa_bound_runs),
                'reviewer_identity_verified': False,
                'cost': _moa_review_cost(moa_material_reviews, moa_output_reviews, moa_purpose_review),
            },
            'human_review_time': human_review_time,
            'accepted_task_metric_definition': {
                'afp_per_accepted_task': 'total_afp_all_tasks / accepted_task_count；口径为 Ark AFP per accepted task，'
                                         '不含 MoA 评审外部成本。',
                'successful_sample_afp': '仅通过质量门槛任务的online_afp+research_afp+setup_afp',
                'successful_sample_afp_per_accepted_task': 'successful_sample_afp / accepted_task_count',
                'failure_policy': '失败、pending与未知AFP任务保留在总AFP和任务分母；未知AFP阻止成本结论。',
                'human_review_time': '单独报告，不计入AFP。',
                'moa_review_cost': 'MoA 评审调用次数、评审者与耗时单独报告；外部用量未知，不并入 Ark AFP。'
            },
            'reviewer_identity_authenticated_by_code': False,
            'limitations': ['固定构造任务不是从业务分布随机抽样，二项界仅展示条件假设下的不确定性。',
                            '三次重复先在任务内汇总；不把重复调用当成三个独立任务。',
                            '退化重采样区间不构成零不确定性或性能优势证明。']}
