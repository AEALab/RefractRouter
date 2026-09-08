"""从独立节点观测构建分层 profile；禁止混入测试集或推断缺失质量。"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json

from .node_routing import NodeProfile, load_profile, number
from .openai_compatible import ChatResponse, model_response_cost
from .task_contracts import decode_output, nonempty

INPUT_BANDS = ((256, 8193), (8193, 32769), (32769, 131073))


def build_stratified_profile(raw, manifest, *, calibration_task_ids, test_task_ids, min_samples=3):
    if (not isinstance(raw, dict) or raw.get('schema_version') != 'node-observations-v1'
            or raw.get('kind') not in ('empirical', 'synthetic')):
        raise ValueError('invalid observation corpus')
    allowed, held_out = set(calibration_task_ids), set(test_task_ids)
    if not allowed or not held_out or allowed & held_out:
        raise ValueError('calibration/test tasks must be nonempty and disjoint')
    if type(min_samples) is not int or min_samples < 3:
        raise ValueError('min_samples must be at least 3')
    rows = raw.get('observations')
    expected = raw.get('expected_contexts')
    if not isinstance(rows, list) or not rows or not isinstance(expected, list) or not expected:
        raise ValueError('missing observation contexts')
    contexts = set()
    for context in expected:
        if not isinstance(context, dict) or set(context) != {'task_id', 'repeat', 'node_id'}:
            raise ValueError('invalid expected context')
        key = (nonempty(context['task_id'], 'task_id', 100), context['repeat'], nonempty(context['node_id'], 'node_id', 100))
        if key[0] not in allowed or type(key[1]) is not int or key[1] < 1 or key in contexts:
            raise ValueError('invalid/duplicate expected context')
        contexts.add(key)
    if {key[0] for key in contexts} != allowed:
        raise ValueError('missing calibration tasks')
    models = {m.model_id: m for m in manifest.candidates}
    seen, matched, groups, rejected = set(), defaultdict(dict), defaultdict(list), {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('invalid observation')
        nonempty(row.get('task_id'), 'task_id', 100)
        nonempty(row.get('node_id'), 'node_id', 100)
        if type(row.get('repeat')) is not int or row['repeat'] < 1:
            raise ValueError('invalid observation repeat')
        context = (row.get('task_id'), row.get('repeat'), row.get('node_id'))
        mid = row.get('model_id')
        if context not in contexts or mid not in models or (*context, mid) in seen:
            raise ValueError('unexpected, held-out or duplicate observation')
        seen.add((*context, mid))
        input_text, output = row.get('input'), row.get('output')
        nonempty(input_text, 'input', 1000000)
        nonempty(output, 'output', 1000000)
        input_hash = hashlib.sha256(input_text.encode()).hexdigest()
        output_hash = hashlib.sha256(output.encode()).hexdigest()
        if row.get('input_sha256') != input_hash or row.get('output_sha256') != output_hash:
            raise ValueError('observation hash mismatch')
        if row.get('status') != 'completed' or row.get('finish_reason') != 'stop':
            raise ValueError('unavailable execution cannot become a quality score')
        f = row.get('features')
        if not isinstance(f, dict) or set(f) != {'node_type', 'difficulty', 'risk', 'input_budget_tokens'}:
            raise ValueError('invalid observation features')
        size = f['input_budget_tokens']
        if type(size) is not int or not 256 <= size <= 131072:
            raise ValueError('invalid input budget stratum')
        lo, hi = next(b for b in INPUT_BANDS if b[0] <= size < b[1])
        key = (mid, f['node_type'], f['difficulty'], f['risk'], lo, hi)
        NodeProfile(mid, f['node_type'], 0, 0, 0, 1, f['difficulty'], f['risk'], lo, hi)
        signature = (input_hash, json.dumps(f, sort_keys=True), json.dumps(row.get('output_contract'), sort_keys=True))
        matched[context][mid] = signature
        contract = row.get('output_contract')
        if (not isinstance(contract, dict) or set(contract) != {'format', 'fields'}
                or contract.get('format') not in ('json', 'text') or not isinstance(contract.get('fields'), dict)
                or not contract['fields'] or (contract['format'] == 'text' and set(contract['fields']) != {'text'})):
            raise ValueError('invalid observed output contract')
        contract_valid = True
        try:
            decode_output(output, {'output': contract})
        except ValueError:
            contract_valid = False
        judge = row.get('evaluation')
        if not isinstance(judge, dict) or judge.get('input_sha256') != input_hash or judge.get('output_sha256') != output_hash:
            raise ValueError('missing or mismatched independent node evaluation')
        score = number(judge.get('score'), 'node quality', maximum=100)
        if contract_valid:
            if judge.get('method') != 'independent-text-node-v1' or judge.get('status') != 'completed':
                raise ValueError('missing independent node quality')
            if type(judge.get('passed')) is not bool:
                raise ValueError('missing semantic pass state')
            if not judge['passed']:
                rejected[key] = 'semantic-criterion-failure'
        elif judge.get('method') != 'deterministic-rejection' or score != 0:
            raise ValueError('known contract rejection requires explicit zero and rejection method')
        telemetry = row.get('usage')
        if not isinstance(telemetry, dict):
            raise ValueError('missing billed usage')
        for name in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens'):
            if type(telemetry.get(name)) is not int or telemetry[name] < 0:
                raise ValueError('invalid billed usage')
        if telemetry['cached_input_tokens'] > telemetry['input_tokens']:
            raise ValueError('invalid cached usage')
        latency = number(row.get('latency_ms'), 'latency_ms')
        response = ChatResponse(output, telemetry['input_tokens'], telemetry['output_tokens'],
            telemetry['cached_input_tokens'], telemetry['reasoning_tokens'], latency, 1, 'stop', None)
        cost = model_response_cost(models[mid], response)
        if not contract_valid:
            rejected[key] = 'known-contract-rejection'
        groups[key].append((score, cost, latency))
    if set(matched) != contexts or any(set(values) != set(models) or len(set(values.values())) != 1 for values in matched.values()):
        raise ValueError('incomplete matrix or different upstream contexts across candidates')
    candidates, exclusions = [], []
    for key, observations in sorted(groups.items()):
        mid, kind, difficulty, risk, lo, hi = key
        identity = {'model_id': mid, 'node_type': kind, 'difficulty': difficulty, 'risk': risk,
                    'input_min_tokens': lo, 'input_max_tokens': hi}
        if key in rejected or len(observations) < min_samples:
            exclusions.append({**identity, 'reason': rejected[key] if key in rejected else 'insufficient-samples'})
            continue
        candidates.append({**identity, 'quality': sum(r[0] for r in observations) / len(observations),
                           'cost': sum(r[1] for r in observations) / len(observations),
                           'latency_ms': max(r[2] for r in observations), 'samples': len(observations)})
    profile = {'schema_version': 'node-routing-profile-v2', 'kind': raw['kind'], 'billing_unit': manifest.billing_unit,
        'scope': '按节点主要能力、难度、风险和声明输入预算分层；质量是条件预测，不能代替最终评估。',
        'provenance': '固定校准上下文的完整候选矩阵；仅使用独立节点评分，禁止从整任务评分推断节点质量。',
        'model_bindings': {mid: m.api_model for mid, m in models.items()}, 'candidates': candidates,
        'calibration_task_ids': sorted(allowed), 'held_out_task_ids': sorted(held_out),
        'observation_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        'aggregation_policy': 'aligned-strata-mean-quality-cost-max-latency-v1', 'exclusions': exclusions}
    load_profile(profile, manifest)
    return profile
