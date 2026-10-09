"""审核证据编号：原文由核心保存，Judge 只返回有限选择，不重复抄写长字符串。"""
from copy import deepcopy
import hashlib
import json

VERSION = 'review-evidence-references-v2'
RECEIPT_VERSION = 'deterministic-answer-fields-v1'
MAX_SOURCE_REFS = 8


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _json_value(value):
    value = value.strip()
    if value.startswith('```json') and value.endswith('```'):
        value = value[7:-3].strip()
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return None


def _chunks(value, capacity=1200):
    """只分页，不截断；每个编号仍绑定同一完整输入中的原文。"""
    page = ''
    for line in value.splitlines(keepends=True):
        while len(line) > capacity:
            if page:
                yield page
                page = ''
            yield line[:capacity]
            line = line[capacity:]
        if len(page) + len(line) > capacity:
            yield page
            page = ''
        page += line
    if page:
        yield page


def catalog(task, answer, criteria, claims, tool_evidence=None):
    sources, candidates, seen = [], [], set()
    def add(target, prefix, value, origin):
        for chunk in _chunks(value):
            identity = (prefix, origin, chunk)
            if not chunk.strip() or identity in seen:
                continue
            seen.add(identity)
            target.append({'id': f'{prefix}{len(target)+1}', 'origin': origin, 'text': chunk,
                           'sha256': hashlib.sha256(chunk.encode()).hexdigest()})
    add(sources, 's', task, 'task')
    # 宿主可能将消息编码为 JSON。解码仅来自实际输入，不把模型引用当成来源。
    for value in _strings(_json_value(task)):
        add(sources, 's', value, 'task-json-string')
    for criterion in criteria:
        add(sources, 's', criterion, 'criterion')
    if tool_evidence is not None:
        add(sources, 's', json.dumps(tool_evidence, ensure_ascii=False), 'host-tool-evidence')
        for value in _strings(tool_evidence):
            add(sources, 's', value, 'host-tool-evidence-string')
    add(candidates, 'a', answer, 'candidate')
    for value in _strings(_json_value(answer)):
        add(candidates, 'a', value, 'candidate-json-string')
    claim_refs = {}
    for index, claim in enumerate(claims):
        key = f'ac{index+1}'
        claim_refs[claim['check_id']] = key
        candidates.append({'id': key, 'origin': 'located-candidate-claim', 'text': claim['quote'],
                           'sha256': hashlib.sha256(claim['quote'].encode()).hexdigest()})
    if len(sources) + len(candidates) > 2048:
        raise ValueError('review-evidence-reference-cap-exceeded')
    return {'version': VERSION, 'task_sha256': hashlib.sha256(task.encode()).hexdigest(),
            'candidate_sha256': hashlib.sha256(answer.encode()).hexdigest(),
            'sources': sources, 'candidate': candidates, 'claim_refs': claim_refs}


def receipt(validation, answer):
    """只接收可信 Python 校验回执；不读候选中的同名字段，不传隐藏标准答案。"""
    raw = validation.get('review_receipt') if isinstance(validation, dict) else None
    if raw is None:
        return None
    if (validation.get('passed') is not True or not isinstance(raw, dict)
            or set(raw) != {'version', 'candidate_sha256', 'checked_fields', 'scope'}
            or raw['version'] != RECEIPT_VERSION or raw['scope'] != 'answers-only'
            or raw['candidate_sha256'] != hashlib.sha256(answer.encode()).hexdigest()):
        raise ValueError('invalid deterministic review receipt')
    keys = raw['checked_fields']
    parsed = _json_value(answer)
    if (not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys)
            or len(keys) != len(set(keys)) or not isinstance(parsed, dict)
            or not isinstance(parsed.get('answers'), dict) or not set(keys) <= set(parsed['answers'])):
        raise ValueError('invalid deterministic review receipt fields')
    return deepcopy(raw)


def resolve(result, evidence, check_ids, claim_kinds):
    """校验有限引用后恢复展示文字；不修改任何结论、分数或通过状态。"""
    rows = result.get('grounding_checks')
    if not isinstance(rows, list) or len(rows) != len(check_ids):
        raise ValueError('missing or invalid final judge grounding checks')
    source = {row['id']: row for row in evidence['sources']}
    candidate = {row['id']: row for row in evidence['candidate']}
    claims = evidence['claim_refs']
    resolved, changes = [], []
    for key, row in zip(check_ids, rows):
        required = {'check_id', 'status', 'answer_ref', 'source_refs'}
        if key in claims:
            required.add('claim_kind')
        # 已观察到的多余空别名不携带判定；仅在规范字段完整时删除，不补猜任何值。
        if (isinstance(row, dict) and required <= set(row)
                and row.get('check_id') == key and 'check-id' in row and row['check-id'] is None):
            row = {name: value for name, value in row.items() if name != 'check-id'}
            changes.append({'check_id': key, 'from': 'check-id', 'to': 'removed-empty-alias'})
        if not isinstance(row, dict) or not required <= set(row) or set(row) - (required | {'rationale'}):
            raise ValueError(f'invalid reference grounding fields ({key})')
        if row['check_id'] != key or row['status'] not in {'PASS', 'FAIL', 'UNCERTAIN', 'NOT_APPLICABLE'}:
            raise ValueError('invalid final judge grounding verdict')
        if row.get('rationale') is not None and (not isinstance(row['rationale'], str) or not row['rationale'].strip()):
            raise ValueError('invalid reference grounding rationale')
        refs = row['source_refs']
        if isinstance(refs, list) and len(refs) > MAX_SOURCE_REFS:
            raise ValueError(f'invalid grounding source reference: {key} has {len(refs)} refs, maximum {MAX_SOURCE_REFS}')
        if (not isinstance(refs, list) or any(not isinstance(r, str) or r not in source for r in refs)
                or len(refs) != len(set(refs))):
            raise ValueError('invalid grounding source reference')
        answer_ref = row['answer_ref']
        if key in claims:
            if (row['claim_kind'] not in claim_kinds or answer_ref != claims[key]
                    or row['status'] == 'NOT_APPLICABLE'):
                raise ValueError('invalid grounding source claim reference')
            if row['status'] == 'PASS' and row['claim_kind'] == 'FACT' and not refs:
                raise ValueError('unsupported factual source claim pass')
        if row['status'] == 'NOT_APPLICABLE':
            if answer_ref is not None or refs:
                raise ValueError('inconsistent inapplicable grounding check')
        elif answer_ref is None and key not in claims:
            pass  # 两项总体检查由核心绑定整份候选，不要求模型任意挑选一段原文。
        elif not isinstance(answer_ref, str) or answer_ref not in candidate:
            raise ValueError('invalid grounding answer reference')
        resolved.append({**row,
            'target_scope': 'whole-candidate' if answer_ref is None else 'candidate-excerpt',
            'answer_quote': candidate[answer_ref]['text'] if answer_ref is not None else None,
            'source_quote': '\n'.join(source[r]['text'] for r in refs) if refs else None})
    if result['passed'] and any(row['status'] in {'FAIL', 'UNCERTAIN'} for row in rows):
        raise ValueError('inconsistent final judge grounding verdict')
    if rows[0]['status'] == 'PASS' and any(row['status'] in {'FAIL', 'UNCERTAIN'} for row in rows[2:]):
        raise ValueError('inconsistent final judge source-state coverage')
    return {**result, 'grounding_checks': resolved, 'response_normalization': {
        'version': 'review-reference-empty-alias-v1', 'changes': changes, 'model_calls_added': 0},
        'evidence_references': {
        'version': VERSION, 'task_sha256': evidence['task_sha256'],
        'candidate_sha256': evidence['candidate_sha256'], 'resolved_by': 'router',
        'overall_check_scope': 'whole-candidate', 'model_calls_added': 0}}
