"""独立评审的盲化材料、严格导入与任务完成度门槛。不自动模拟人工认可。"""
from dataclasses import asdict
import hashlib
import json
from math import isfinite
from secrets import SystemRandom, token_hex

FINAL_LIMITS = {'task_completion': 40, 'analysis': 25, 'grounding': 25, 'presentation': 10}
NODE_LIMITS = {'correctness': 40, 'grounding': 30, 'completeness': 20, 'downstream_utility': 10}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def packet(task, records, *, kind):
    if kind not in {'node', 'final', 'calibration'}:
        raise ValueError('未知评审类型')
    public = {'version': 'blind-review-v1', 'kind': kind, 'task': {
        'domain': task.domain, 'required_sections': list(task.required_sections),
        'output_constraints': list(task.output_constraints),
        'sources': [asdict(s) for s in task.source_documents]}, 'samples': []}
    public['rubric'] = {
        'limits': NODE_LIMITS if kind == 'node' else FINAL_LIMITS,
        '说明': ('节点分别评估正确性、来源支撑、完成度及下游可用性；不能只检查格式。'
                 if kind == 'node' else
                 '整份报告分别评估任务完成度、分析与取舍、来源支撑和呈现质量。'
                 '必须实际比较平台、解释选型取舍并给出有依据的结论；'
                 '任一任务检查不通过时，任务完成度最多 10 分、分析最多 5 分。'),
        '评审要求': '引用样本原文说明理由，并结合所附来源检查遗漏或无依据的断言。不要猜测模型身份。',
    }
    private = {}
    for record in records:
        sid = token_hex(12)
        sample = {k: record[k] for k in ('output', 'upstream', 'node_type', 'node_request') if k in record}
        sample.update(sample_id=sid, output_sha256=hashlib.sha256(record['output'].encode()).hexdigest())
        public['samples'].append(sample)
        private[sid] = record['record_id']
    SystemRandom().shuffle(public['samples'])
    return public, {'packet_sha256': digest(public), 'sample_records': private}


def import_reviews(public, response, *, forbidden_models, simulation=False):
    if not isinstance(response, dict):
        raise ValueError('评审文件必须是对象')
    if response.get('packet_sha256') != digest(public):
        raise ValueError('评审不属于当前冻结材料')
    reviewer = response.get('reviewer', {})
    if not isinstance(reviewer, dict) or reviewer.get('kind') not in {'human', 'model', 'fixture'} or not isinstance(reviewer.get('id'), str) or not reviewer['id'].strip():
        raise ValueError('必须声明独立评审身份')
    if reviewer['kind'] == 'fixture' and not simulation:
        raise ValueError('模拟评审不得作为真实证据')
    if reviewer['kind'] == 'model':
        normalize = lambda value: value.strip().lower().split('/')[-1]
        if normalize(reviewer['id']) in {normalize(m) for m in forbidden_models}:
            raise ValueError('评审模型不得参与基线或节点执行')
    rows = response.get('reviews')
    samples = {s['sample_id']: s for s in public['samples']}
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('评审记录必须是数组')
    ids = [r.get('sample_id') for r in rows]
    if any(not isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or set(ids) != set(samples):
        raise ValueError('评审缺失、重复或包含未知样本')
    limits = NODE_LIMITS if public['kind'] == 'node' else FINAL_LIMITS
    result = {}
    for row in rows:
        scores = row.get('scores')
        if not isinstance(scores, dict) or set(scores) != set(limits):
            raise ValueError('评审维度不完整')
        for key, value in scores.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not 0 <= value <= limits[key]:
                raise ValueError('评审分数非法')
        quote, rationale = row.get('evidence_quote'), row.get('rationale')
        if not isinstance(quote, str) or not quote.strip() or quote not in samples[row['sample_id']]['output']:
            raise ValueError('评审必须定位到实际输出中的原文')
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError('缺少评审理由')
        effective = dict(scores)
        if public['kind'] != 'node':
            checks = row.get('task_checks', {})
            required = {'substantive_comparison', 'criteria_tradeoffs', 'supported_conclusion'}
            if not isinstance(checks, dict) or set(checks) != required or any(type(v) is not bool for v in checks.values()):
                raise ValueError('缺少任务完成度判断')
            if not all(checks.values()):
                effective['task_completion'] = min(effective['task_completion'], 10)
                effective['analysis'] = min(effective['analysis'], 5)
        result[row['sample_id']] = {**row, 'effective_scores': effective,
            'final_score': sum(effective.values()), 'reviewer': reviewer}
    return result


def template(public):
    final = public['kind'] != 'node'
    limits = FINAL_LIMITS if final else NODE_LIMITS
    return {'packet_sha256': digest(public), 'reviewer': {'kind': 'human', 'id': ''},
        'reviews': [{'sample_id': s['sample_id'], 'scores': {k: None for k in limits},
                     'evidence_quote': '', 'rationale': '',
                     **({'task_checks': {k: None for k in (
                         'substantive_comparison', 'criteria_tradeoffs', 'supported_conclusion')}} if final else {})}
                    for s in public['samples']]}
