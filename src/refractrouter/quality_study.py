"""#52 的材料隔离、三态质量检查和零调用预检；不提供付费执行入口。"""
from collections import Counter
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import random
import re

from .manifest import load_model_manifest


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _local(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('artifact escapes study directory')
    return path


def load_study(directory):
    root = Path(directory)
    protocol = json.loads((root / 'protocol.json').read_text())
    if protocol.get('schema_version') != 'quality-protocol-v1':
        raise ValueError('unsupported quality protocol')
    required = {'public/tasks.json', 'review/references.json',
                'review/calibration-cases.json', 'review/material-reviews.json'}
    if set(protocol['artifacts']) != required:
        raise ValueError('artifact inventory changed')
    for name, expected in protocol['artifacts'].items():
        if file_digest(_local(root, name)) != expected:
            raise ValueError(f'artifact hash mismatch: {name}')
    manifest_path = (root / protocol['manifest_path']).resolve()
    if file_digest(manifest_path) != protocol['manifest_file_sha256']:
        raise ValueError('model manifest hash mismatch')
    tasks = json.loads((root / 'public/tasks.json').read_text())['tasks']
    references = json.loads((root / 'review/references.json').read_text())['tasks']
    controls = json.loads((root / 'review/calibration-cases.json').read_text())['cases']
    reviews = json.loads((root / 'review/material-reviews.json').read_text())['reviews']
    validate_materials(tasks, references, protocol)
    return protocol, tasks, references, controls, reviews, load_model_manifest(manifest_path)


def validate_materials(tasks, references, protocol):
    if len(tasks) != protocol['task_count'] or Counter(t['split'] for t in tasks) != protocol['split_counts']:
        raise ValueError('sample counts changed')
    ids, material_hashes = set(), set()
    families = {'source_family': {}, 'template_family': {}}
    coverage = Counter()
    for task in tasks:
        tid = task['task_id']
        if not re.fullmatch(r'[a-z][a-z0-9-]{1,80}', tid) or tid in ids or tid not in references:
            raise ValueError('duplicate or missing task reference')
        ids.add(tid)
        if task['split'] not in ('development', 'holdout-candidate'):
            raise ValueError('invalid split')
        if task['category'] not in ('material-analysis', 'rule-checking', 'multipart-decision'):
            raise ValueError('invalid task category')
        if task['structure_stratum'] not in ('direct', 'parallel', 'sequential'):
            raise ValueError('invalid structure stratum')
        coverage[task['category'], task['structure_stratum']] += 1
        if task['provenance']['kind'] not in ('constructed', 'real-source') or not task['provenance']['creator']:
            raise ValueError('missing provenance')
        if task['material_sha256'] != digest(task['materials']):
            raise ValueError('material hash mismatch')
        unsigned = {k: v for k, v in task.items() if k != 'task_sha256'}
        if task['task_sha256'] != digest(unsigned) or references[tid]['task_sha256'] != task['task_sha256']:
            raise ValueError('task or reference binding changed')
        source_ids = {s['source_id'] for s in task['materials']}
        if not source_ids or len(source_ids) != len(task['materials']):
            raise ValueError('duplicate or empty source ID')
        # 去除空白，避免仅重新排版就获得独立材料身份。
        for source in task['materials']:
            fingerprint = hashlib.sha256(''.join(source['text'].split()).encode()).hexdigest()
            if fingerprint in material_hashes:
                raise ValueError('duplicate source text')
            material_hashes.add(fingerprint)
        for key, seen in families.items():
            family = task[key]
            if not family or (family in seen and seen[family] != task['split']):
                raise ValueError('source or template family crosses splits')
            seen[family] = task['split']
        fields = [c['field'] for c in references[tid]['checks']]
        if len(set(fields)) != len(fields) or set(fields) != set(task['requested_findings']):
            raise ValueError('reference coverage mismatch')
        for check in references[tid]['checks']:
            if not check['required_sources'] or not set(check['required_sources']) <= source_ids:
                raise ValueError('invalid reference evidence')
    if set(references) != ids or len(coverage) != 9 or min(coverage.values()) < 1:
        raise ValueError('incomplete task coverage')


def execution_payload(task):
    """显式投影公共材料；不给模型分组、预设形状、参考值或审查记录。"""
    return deepcopy({k: task[k] for k in ('instruction', 'materials', 'requested_findings',
                                         'semantic_criteria', 'output_contract')})


def check_output(task, reference, output):
    if reference['task_sha256'] != task['task_sha256']:
        raise ValueError('reference bound to another task')
    if 'finding_types' not in task['output_contract']:
        return _check_output(task, reference, output)
    from .quality_encoding import normalize_output
    encoding = normalize_output(task, output)
    if encoding['status'] == 'invalid':
        return {'status': 'fail', 'fact_status': 'unverified', 'encoding': encoding,
                'checks': [{'check': 'public-output-encoding', 'status': 'fail',
                            'reason': '字段编码不符合公开类型/名称合同；未归因为语义错误'}],
                'unverified': ['格式不支持的字段事实、正文语义与全局一致性']}
    result = _check_output(task, reference, encoding['normalized'])
    result.update(encoding=encoding, fact_status=result['status'])
    return result


def _check_output(task, reference, output):
    """结构化事实检查。正文语义始终保留未验证，不能把字段通过当最终通过。"""
    if reference['task_sha256'] != task['task_sha256']:
        raise ValueError('reference bound to another task')
    try:
        digest(output)
    except (TypeError, ValueError):
        return {'status': 'fail', 'checks': [{'check': 'format', 'status': 'fail',
                'reason': '输出不是有效的有限值 JSON'}], 'unverified': ['正文语义与全局一致性']}
    checks = []
    def record(name, status, reason):
        checks.append({'check': name, 'status': status, 'reason': reason})
    if not isinstance(output, dict) or not isinstance(output.get('answer'), str) or not output['answer'].strip():
        return {'status': 'fail', 'checks': [{'check': 'format', 'status': 'fail', 'reason': '缺少最终正文'}],
                'unverified': ['正文语义与全局一致性']}
    rows = output.get('findings')
    if not isinstance(rows, list) or any(not isinstance(f, dict) or not isinstance(f.get('id'), str) for f in rows):
        return {'status': 'fail', 'checks': [{'check': 'format', 'status': 'fail', 'reason': 'findings 格式错误'}],
                'unverified': ['正文语义与全局一致性']}
    facts = {f['id']: f for f in rows}
    if len(facts) != len(rows) or set(facts) != set(task['requested_findings']):
        record('coverage', 'fail', '缺项、重复项或未声明字段')
    source_ids = {s['source_id'] for s in task['materials']}
    for rule in reference['checks']:
        key = rule['field']; fact = facts.get(key)
        if fact is None:
            record(key, 'fail', '缺少必需结论'); continue
        sources = fact.get('sources')
        if (not isinstance(sources, list) or any(not isinstance(s, str) for s in sources)
                or len(sources) != len(set(sources)) or not set(sources) <= source_ids
                or not set(rule['required_sources']) <= set(sources)):
            record(key + ':sources', 'fail', '引用缺失、错误或不足')
        actual, expected = fact.get('value'), rule['expected']
        # 布尔事实不是数值；允许等价的 JSON 数值表示。
        if rule['op'] == 'equal':
            if type(actual) in (int, float) and type(expected) in (int, float):
                ok = Decimal(str(actual)).is_finite() and Decimal(str(actual)) == Decimal(str(expected))
            else:
                ok = digest(actual) == digest(expected)
        elif rule['op'] == 'set_equal':
            ok = (isinstance(actual, list) and len(actual) == len(expected)
                  and len({digest(v) for v in actual}) == len(actual)
                  and {digest(v) for v in actual} == {digest(v) for v in expected})
        else:
            record(key, 'unverified', '未支持的检查操作'); continue
        record(key, 'pass' if ok else 'fail', '参考事实相符' if ok else '关键事实不符')
    status = 'fail' if any(c['status'] == 'fail' for c in checks) else (
        'unverified' if any(c['status'] == 'unverified' for c in checks) else 'pass')
    return {'status': status, 'checks': checks, 'unverified': ['正文语义、证据是否真正支持主张、全局一致性']}


def adjudicate(task, reference, output, human_reviews=()):
    result = check_output(task, reference, output)
    status = 'fail' if result['status'] == 'fail' else 'pending'
    # 接受记录不等于认证真人身份；维护者仍需核验来源证据。
    valid = []; seen = set()
    for review in human_reviews:
        reviewer = review.get('reviewer')
        if (review.get('origin') != 'human' or not reviewer or reviewer in seen
                or reviewer == task['provenance']['creator'] or not review.get('evidence')
                or review.get('task_sha256') != task['task_sha256']
                or review.get('output_sha256') != digest(output)
                or review.get('criteria') != task['semantic_criteria']
                or review.get('verdict') not in ('pass', 'fail', 'pending')
                or review.get('stage') not in ('initial', 'adjudication')):
            continue
        seen.add(reviewer); valid.append(review)
    initial = [r for r in valid if r['stage'] == 'initial']
    if status != 'fail' and result['status'] == 'pass' and len(initial) == 2:
        verdicts = [r['verdict'] for r in initial]
        if verdicts == ['pass', 'pass']:
            status = 'pass'
        elif verdicts == ['fail', 'fail']:
            status = 'fail'
        else:
            arbiters = [r for r in valid if r['stage'] == 'adjudication']
            if len(arbiters) == 1 and arbiters[0]['verdict'] in ('pass', 'fail'):
                status = arbiters[0]['verdict']
    return {'status': status, 'deterministic': result,
            'human_records_accepted': len(valid), 'reviewer_identity_verified': False}


def calibrate(tasks, references, cases):
    by_id = {t['task_id']: t for t in tasks}; rows = []; discrepancies = []
    for case in cases:
        t = by_id[case['task_id']]
        if t['split'] != 'development':
            raise ValueError('holdout material cannot calibrate the evaluator')
        result = adjudicate(t, references[t['task_id']], case['output'])
        row = {'case_id': case['case_id'], 'author_semantic_label': case['author_semantic_label'],
               'check_status': result['deterministic']['status'], 'final_status': result['status']}
        rows.append(row)
        if (row['check_status'] != case['expected_check_status']
                or row['final_status'] != case['expected_final_status']):
            discrepancies.append(case['case_id'])
    return {'cases': rows, 'expectation_mismatches': discrepancies,
            'detected_negative_cases': sum(r['author_semantic_label'] == 'unacceptable' and r['check_status'] == 'fail' for r in rows),
            'unresolved_negative_cases': sum(r['author_semantic_label'] == 'unacceptable' and r['final_status'] == 'pending' for r in rows),
            'false_rejections_on_author_positives': sum(r['author_semantic_label'] == 'acceptable' and r['check_status'] == 'fail' for r in rows),
            'human_disagreement': None, 'model_judge_evaluated': False,
            'scope': '仅作者构造样例的确定性检查；不是独立语义评审准确率。'}


MATERIAL_CRITERIA = ('来源与使用范围可追溯', '材料内部无歧义或已标记未知',
    '参考事实及计算正确', '关键错误和语义验收覆盖交付', '来源及模板族独立',
    '任务形态标注合理', '候选任务难度及代表性适合研究', '公共输入未泄漏参考答案')


def material_review_packet(tasks, references):
    return [{'task_id': t['task_id'], 'task': deepcopy(t),
             'reference': deepcopy(references[t['task_id']]),
             'review': {'origin': 'human', 'reviewer': None, 'evidence': None,
                       'task_sha256': t['task_sha256'],
                       'reference_sha256': digest(references[t['task_id']]),
                       'checks': {key: 'pending' for key in MATERIAL_CRITERIA}}} for t in tasks]


def strategy_counts(outcomes):
    """待判定和失败均留在分母；这里不产生非劣或 SLA 结论。"""
    if not outcomes or any(s not in ('pass', 'fail', 'pending') for s in outcomes):
        raise ValueError('empty or invalid outcomes')
    counts = Counter(outcomes)
    return {**{s: counts[s] for s in ('pass', 'fail', 'pending')}, 'total': len(outcomes),
            'confirmed_pass_rate': counts['pass'] / len(outcomes), 'noninferiority': 'not-assessed'}


def make_blind_packet(records, tasks, references, *, seed=52):
    """不携带路线/模型元数据；私有映射单独输出，不能发送给盲审者。"""
    shuffled = list(records); random.Random(seed).shuffle(shuffled)
    by_id = {t['task_id']: t for t in tasks}; packet = []; mapping = {}
    for i, row in enumerate(shuffled):
        t = by_id[row['task_id']]; case_id = f'case-{i+1:04d}'
        packet.append({'case_id': case_id, 'task': execution_payload(t),
                       'reference': deepcopy(references[t['task_id']]), 'output': deepcopy(row['output']),
                       'review': {'origin': 'human', 'reviewer': None, 'verdict': None, 'evidence': None,
                                  'stage': 'initial', 'criteria': t['semantic_criteria'],
                                  'task_sha256': t['task_sha256'], 'output_sha256': digest(row['output'])}})
        mapping[case_id] = {k: row.get(k) for k in ('task_id', 'arm_id', 'model_id', 'repeat')}
    return packet, mapping


def preflight(directory):
    protocol, tasks, references, controls, reviews, manifest = load_study(directory)
    p = protocol
    if p['execution']['max_node_fallbacks'] or p['execution']['max_dynamic_splits'] or p['execution']['http_retries'] or p['execution']['planner_repairs']:
        raise ValueError('recovery must be separately budgeted')
    repeats = p['execution']['repeats']
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError('invalid repeats')
    models = {m.model_id: m for m in manifest.models}; stage_specs = p['stages']
    required_stages = {'selector', 'planner', 'worker', 'final', 'delivery_judge', 'research_judge'}
    if set(stage_specs) != required_stages or manifest.billing_unit != 'AFP':
        raise ValueError('invalid stage inventory or billing unit')
    envelopes = []; arm_ids = set()
    for arm in p['arms']:
        if arm['arm_id'] in arm_ids:
            raise ValueError('duplicate arm')
        arm_ids.add(arm['arm_id'])
        online = offline = Decimal(0); ms_online = ms_offline = calls_online = calls_offline = 0
        counts = arm['maximum_stage_calls']
        if set(counts) - required_stages or counts.get('final') != 1 or counts.get('delivery_judge') != 1 or counts.get('research_judge') != 1:
            raise ValueError('missing final or judge envelope')
        for stage, count in counts.items():
            if type(count) is not int or not 0 <= count <= 6:
                raise ValueError('invalid call cap')
            spec = stage_specs[stage]
            for key in ('input_cap', 'output_cap', 'timeout_ms'):
                if type(spec[key]) is not int or spec[key] <= 0:
                    raise ValueError('invalid stage cap')
            choices = arm['candidate_models'] if spec['model'] == 'arm-candidates' else [spec['model']]
            if not choices or any(m not in models for m in choices):
                raise ValueError('unknown model')
            costs = []
            for mid in choices:
                model = models[mid]
                if spec['input_cap'] + spec['output_cap'] > model.context_window or spec['output_cap'] > model.max_output_tokens:
                    raise ValueError('stage exceeds model capacity')
                costs.append((Decimal(spec['input_cap']) * Decimal(str(model.input_cost_per_1k))
                              + Decimal(spec['output_cap']) * Decimal(str(model.output_cost_per_1k))) / 1000)
            if spec['ledger'] == 'online':
                online += count * max(costs); ms_online += count * spec['timeout_ms']; calls_online += count
            elif spec['ledger'] == 'offline':
                offline += count * max(costs); ms_offline += count * spec['timeout_ms']; calls_offline += count
            else:
                raise ValueError('invalid ledger')
        envelopes.append({'arm_id': arm['arm_id'], 'maximum_online_calls': calls_online,
                          'maximum_research_calls': calls_offline, 'online_afp_ceiling': float(online),
                          'research_afp_ceiling': float(offline),
                          'online_timeout_sum_ms': ms_online + p['execution']['drain_grace_ms'],
                          'research_timeout_sum_ms': ms_offline, 'max_concurrency': arm['max_concurrency']})
    # 原始材料先做容量检查；组合后的真实请求仍需 #53 运行器逐次检查。
    payloads = {t['task_id']: execution_payload(t) for t in tasks}
    if any(len(json.dumps(x, ensure_ascii=False).encode()) + 1024 > min(s['input_cap'] for s in stage_specs.values()) for x in payloads.values()):
        raise ValueError('raw input exceeds conservative capacity')
    schedule = []
    rng = random.Random(p['execution']['order_seed'])
    for repeat in range(1, repeats + 1):
        for t in tasks:
            arms = list(arm_ids); arms.sort(); rng.shuffle(arms)
            schedule.extend({'task_id': t['task_id'], 'split': t['split'], 'repeat': repeat, 'arm_id': arm,
                             'output_relative_path': f"runs/{t['task_id']}/repeat-{repeat}/{arm}"} for arm in arms)
    totals = {}
    for split, count in p['split_counts'].items():
        factor = count * repeats
        totals[split] = {'runs': factor * len(envelopes),
                         'maximum_calls': factor * sum(e['maximum_online_calls'] + e['maximum_research_calls'] for e in envelopes),
                         'online_afp_ceiling': round(factor * sum(e['online_afp_ceiling'] for e in envelopes), 6),
                         'research_afp_ceiling': round(factor * sum(e['research_afp_ceiling'] for e in envelopes), 6)}
    return {'schema_version': 'quality-preflight-v1', 'real_model_calls': 0,
            'protocol_sha256': digest(p), 'formal_run_ready': False,
            'blocking_requirements': ['材料及参考答案尚未独立审查，构造材料不代表真实业务分布。',
                '质量与非劣门槛未完成开发校准及真人签署。',
                '基线运行器、内部提示与逐请求容量/超时尚未绑定冻结。',
                '离线画像/训练/搜索开销未定界，当前包络不是整项研究总预算。',
                '真人盲审及辅助模型校准分歧尚未完成独立复核。'],
            'independent_review_records': len(reviews), 'material_independence_verified': False,
            'task_counts': dict(Counter(t['split'] for t in tasks)),
            'source_kinds': dict(Counter(t['provenance']['kind'] for t in tasks)),
            'envelopes': envelopes, 'totals': totals, 'schedule': schedule,
            'calibration': calibrate(tasks, references, controls),
            'limitations': ['时间为声明的调用超时之和加清理宽限，不是预计等待或已实现硬 deadline。',
                '上界使用未缓存 token 费率；调用上限包含失败尝试，但未执行任何调用。',
                '运行 payload 只从公共字段投影；仓库文件权限不是安全隔离，runner 仍需测试与封装。']}
