"""固定候选材料的独立计算路径；只核验声明的结构化事实，不冒充真人语义审查。"""
from collections import Counter
import itertools
import re
import statistics

from .quality_study import digest, load_study


def numbers(text):
    return [float(n) for n in re.findall(r'\d+(?:\.\d+)?', text)]


def recalculate(task):
    """不读取参考答案。解析本版候选材料的固定格式；不是任意业务文档解释器。"""
    tid = task['task_id']
    s = {r['source_id']: r['text'] for r in task['materials']}
    a, b = numbers(s['s1']), numbers(s['s2'])
    if tid == 'analysis-01':
        expected = a[0] + a[1] - a[2] - a[3]
        return dict(expected_stock=expected, observed_gap=b[0] - expected, theft_proven=False)
    if tid == 'analysis-02':
        return dict(survey_negative=a[1], service_complaints=b[0], can_pool=False)
    if tid == 'analysis-03':
        before, after = a[0] / b[0], a[1] / b[1]
        return dict(before_kwh_per_hour=before, after_kwh_per_hour=after, efficiency_improved=after < before)
    if tid == 'analysis-04':
        return dict(east_change=(a[1] - a[2]) / a[0] * 100, west_change='unknown', pooled_effect_supported=False)
    if tid == 'analysis-05':
        eligible, retained = map(int, re.search(r'A组.*?：(\d+)人，6月活跃(\d+)人', s['s2']).groups())
        numerator, denominator, *_ = numbers(s['s3'])
        return dict(eligible=eligible, retained=retained, retention_percent=retained / eligible * 100,
                    report_correct=numerator * eligible == denominator * retained)
    if tid == 'analysis-06':
        utc = [int(h) * 60 + int(m) for h, m in re.findall(r'UTC (\d+):(\d+)', s['s1'])]
        h, m = map(int, re.search(r'北京时间(\d+):(\d+)', s['s2']).groups())
        offset = int(re.search(r'UTC加(\d+)小时', s['s2'])[1]) * 60
        events = dict(start=utc[0] + offset, restore=utc[1] + offset, complaint=h * 60 + m)
        return dict(order=sorted(events, key=events.get), complaint_before_restore=events['complaint'] < events['restore'])
    if tid == 'rules-01':
        remaining = a[0] - b[0]
        return dict(remaining=remaining, requested=b[-1], full_approval=b[-1] <= remaining)
    if tid == 'rules-02':
        edges = re.findall(r'(打包|签名)(?:结束|通过)才能(签名|发布)', s['s1'])
        completed = {'打包'} if '打包已结束' in s['s2'] else set()
        active = sorted({v for edge in edges for v in edge} - completed)
        allowed = [n for n in active if all(p in completed for p, child in edges if child == n)]
        return dict(allowed_now=allowed, blocked_now=[n for n in active if n not in allowed],
                    required_edge=list(next(e for e in edges if e[1] == '发布')))
    if tid == 'rules-03':
        ordinary = int(re.search(r'购买后(\d+)天', s['s1'])[1])
        exception = int(re.search(r'可在(\d+)天', s['s1'])[1])
        rows = re.findall(r'([甲乙丙])：第(\d+)天，([有无])登记故障', s['s2'])
        accepted = [name for name, day, fault in rows if int(day) <= (exception if fault == '有' else ordinary)]
        return dict(eligible_ids=accepted, ineligible_ids=[r[0] for r in rows if r[0] not in accepted])
    if tid == 'rules-04':
        rows = re.findall(r'文件(A|B|C附件)：([^。]+)', s['s2'])
        accepted = [name for name, detail in rows if '公开' in detail and '解禁已过' in detail
                    and ('不含联系方式' in detail or '已脱敏' in detail)]
        return dict(releasable=accepted, blocked=[r[0] for r in rows if r[0] not in accepted])
    if tid == 'rules-05':
        maximum = int(re.search(r'不超过(\d+)%', s['s1'])[1])
        result = dict(accepted=[], rejected=[], unknown=[])
        for name, detail in re.findall(r'([PQR])：([^。]+)', s['s2']):
            missing = int(re.search(r'缺测(\d+)%', detail)[1])
            key = 'rejected' if '过期' in detail or missing > maximum else 'accepted' if '时钟同步' in detail else 'unknown'
            result[key].append(name)
        return result
    if tid == 'rules-06':
        rows = re.findall(r'([A-E])([^，；。]+)，优先(\d+)，(\d+:\d+)', s['s2'])
        excluded = [name for name, detail, _, _ in rows if '不完整' in detail]
        qualified = sorted((int(priority), clock, name) for name, _, priority, clock in rows if name not in excluded)
        count = int(a[0]); names = [r[2] for r in qualified]
        return dict(excluded=excluded, selected=names[:count], waitlisted=names[count:])
    if tid == 'decision-01':
        printers = [(name, int(cost)) for name, cost, detail in re.findall(r'([PQ])报价(\d+)元([^，。]+)', s['s1']) if '可双面彩色' in detail]
        days = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7}
        deadline = days[re.search(r'须周(.)前', s['s2'])[1]]
        delivery = [(name, int(cost)) for name, cost, day in re.findall(r'([DE])报价(\d+)元周(.)送达', s['s2']) if days[day] < deadline]
        maximum = int(re.search(r'总预算(\d+)', s['s2'])[1])
        total, printer, carrier = min((p[1] + d[1], p[0], d[0]) for p, d in itertools.product(printers, delivery) if p[1] + d[1] <= maximum)
        return dict(printer=printer, delivery=carrier, total_cost=total)
    if tid == 'decision-02':
        slots = {slot: [name for name, state, availability in re.findall(r'([甲乙丙])培训(有效|过期)，([^；。]+)', s['s2'])
                        if state == '有效' and slot in availability] for slot in ('早班', '晚班')}
        return dict(morning=slots['早班'][0], evening=slots['晚班'][0], feasible=len(set(slots['早班'] + slots['晚班'])) == 2)
    if tid == 'decision-03':
        minimum, maximum = a
        rows = [(name, int(capacity), passage, int(cost)) for name, capacity, passage, cost in
                re.findall(r'([A-D])可容(\d+)人、([^、]+)、(\d+)元', s['s2'])]
        valid = [(cost, name) for name, capacity, passage, cost in rows if capacity >= minimum and passage != '无通道' and cost <= maximum]
        cost, name = min(valid)
        return dict(selected=name, cost=cost, rejected_ids=[r[0] for r in rows if (r[3], r[0]) not in valid])
    if tid == 'decision-04':
        rows = [(int(hours), int(cost), name) for name, cost, hours in re.findall(r'([A-D])月费(\d+)元恢复(\d+)小时', s['s2'])]
        hours, cost, name = min(r for r in rows if r[0] <= a[1] and r[1] <= a[0])
        return dict(selected=name, monthly_cost=cost, recovery_hours=hours)
    if tid == 'decision-05':
        first = [(int(cost), name) for name, count, kind, cost in re.findall(r'([XY])为(\d+)套(无溶剂|含溶剂)(\d+)元', s['s1']) if kind == '无溶剂' and int(count) == a[0]]
        second = [(int(cost), name) for name, count, kind, cost in re.findall(r'([UV])为(\d+)套(含护目镜|不含护目镜)(\d+)元', s['s2']) if kind == '含护目镜' and int(count) == b[0]]
        x, y = min(first), min(second); maximum = numbers(s['s3'])[0]
        return dict(kits=[x[1], y[1]], total_cost=x[0] + y[0], remaining_budget=maximum - x[0] - y[0])
    if tid == 'decision-06':
        durations = re.findall(r'(备份|校验备份|部署|回归检查)(?:耗时|需)(\d+)分钟', s['s1'])
        total = sum(int(n) for _, n in durations)
        return dict(order=[name for name, _ in durations], finish_minute=total, deadline_met=total <= b[-1])
    raise ValueError('no independent calculation for task')


def audit(study_dir):
    _, tasks, refs, *_ = load_study(study_dir)
    rows = []
    for task in tasks:
        expected = {c['field']: c['expected'] for c in refs[task['task_id']]['checks']}
        actual = recalculate(task)
        # 对本版无重复、无嵌套数值列表的控制，使用字段语义区分集合与有序列表。
        mismatches = []
        for check in refs[task['task_id']]['checks']:
            left, right = actual.get(check['field']), check['expected']
            equal = set(left) == set(right) if check['op'] == 'set_equal' else left == right
            if not equal or isinstance(left, bool) != isinstance(right, bool):
                mismatches.append(check['field'])
        rows.append({'task_id': task['task_id'], 'task_sha256': task['task_sha256'],
                     'recomputed': actual, 'mismatches': mismatches,
                     'material_bytes': sum(len(s['text'].encode()) for s in task['materials']),
                     'category': task['category'], 'structure': task['structure_stratum'],
                     'origin': 'deterministic-source-recalculation', 'semantic_review': 'pending-human'})
    return {'schema_version': 'quality-material-audit-v1', 'rows': rows,
            'reference_mismatches': sum(len(r['mismatches']) for r in rows),
            'coverage': dict(Counter(t['category'] + ':' + t['structure_stratum'] for t in tasks)),
            'source_families': len({t['source_family'] for t in tasks}),
            'template_families': len({t['template_family'] for t in tasks}),
            'median_material_bytes': statistics.median(r['material_bytes'] for r in rows),
            'population_representativeness': 'not-established',
            'semantic_rule_origin': '作者形式化的固定材料规则，非独立开放语义解释器；缺证据等语义判断仍待真人审核。',
            'scope': '固定构造微任务的算术、排序、集合与显式规则复算；不证明开放语义、来源真实性或业务代表性。'}
