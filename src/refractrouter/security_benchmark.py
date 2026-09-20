"""安全约束混合路由基准的冻结协议与零调用排练。"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json

from .node_routing import number

SCHEMA = 'security-benchmark-v1'
ARMS = ('external-reference', 'trusted-direct', 'constrained-direct', 'constrained-fixed-dag')
TASK_CLASSES = frozenset({'separable', 'all-sensitive', 'all-public', 'short-negative',
                          'strong-dependency-negative'})
SENSITIVE = frozenset({'S1', 'S2', 'unknown'})
TRUSTED = frozenset({'local', 'trusted-cloud'})


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _model_map(raw):
    models = {}
    for row in raw.get('models', []):
        if not isinstance(row, dict) or set(row) != {
                'id', 'deployment', 'role', 'qualityProxy', 'inputPer1k', 'outputPer1k',
                'latencyMs', 'researchOnly'}:
            raise ValueError('invalid security benchmark model')
        mid = row['id']
        if not isinstance(mid, str) or not mid or mid in models:
            raise ValueError('invalid or duplicate model id')
        if row['deployment'] not in {'local', 'trusted-cloud', 'external-cloud', 'simulated-local'}:
            raise ValueError('invalid benchmark deployment')
        if row['role'] not in {'candidate', 'judge'} or type(row['researchOnly']) is not bool:
            raise ValueError('invalid benchmark model role')
        for field in ('qualityProxy', 'inputPer1k', 'outputPer1k', 'latencyMs'):
            number(row[field], field, maximum=100 if field == 'qualityProxy' else None)
        if row['deployment'] == 'simulated-local' and row['researchOnly'] is not True:
            raise ValueError('simulated-local must remain research-only')
        models[mid] = deepcopy(row)
    if sum(row['role'] == 'judge' for row in models.values()) != 1:
        raise ValueError('security benchmark requires exactly one judge')
    return models


def _allows(grade, model):
    return grade not in SENSITIVE or model['deployment'] in TRUSTED


def _cost(model, input_tokens, output_tokens):
    return input_tokens / 1000 * model['inputPer1k'] + output_tokens / 1000 * model['outputPer1k']


def _validate_nodes(nodes, models, quality_min):
    if not isinstance(nodes, list) or not nodes:
        raise ValueError('fixed DAG requires nodes')
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {
                'id', 'parents', 'grade', 'modelId', 'inputTokens', 'outputTokens'}:
            raise ValueError('invalid fixed DAG node')
        if not isinstance(node['id'], str) or not node['id'] or node['id'] in ids:
            raise ValueError('invalid or duplicate fixed DAG node id')
        if not isinstance(node['parents'], list) or any(parent not in ids for parent in node['parents']):
            raise ValueError('fixed DAG parents must precede their child')
        if node['grade'] not in {'S1', 'S2', 'S3', 'unknown'}:
            raise ValueError('invalid node security grade')
        model = models.get(node['modelId'])
        if model is None or model['role'] != 'candidate' or model['researchOnly']:
            raise ValueError('fixed DAG references an unavailable deployable model')
        if not _allows(node['grade'], model):
            raise ValueError('fixed DAG violates a node trust boundary')
        if model['qualityProxy'] < quality_min:
            raise ValueError('fixed DAG model is below the preregistered quality proxy')
        for field in ('inputTokens', 'outputTokens'):
            if type(node[field]) is not int or node[field] < 1:
                raise ValueError('invalid fixed DAG token envelope')
        ids.add(node['id'])


def validate_protocol(raw):
    if not isinstance(raw, dict) or raw.get('schema_version') != SCHEMA or raw.get('issue') != 112:
        raise ValueError('invalid security benchmark protocol')
    if tuple(raw.get('arms', ())) != ARMS:
        raise ValueError('security benchmark arms changed')
    constraints = raw.get('constraints')
    if not isinstance(constraints, dict) or set(constraints) != {
            'qualityMin', 'maxReferenceGap', 'privacyViolations', 'repetitions', 'maxCalls'}:
        raise ValueError('invalid benchmark constraints')
    quality_min = number(constraints['qualityMin'], 'qualityMin', maximum=100)
    number(constraints['maxReferenceGap'], 'maxReferenceGap', maximum=100)
    if constraints['privacyViolations'] != 0 or type(constraints['repetitions']) is not int or constraints['repetitions'] < 1:
        raise ValueError('invalid safety or repetition constraint')
    if type(constraints['maxCalls']) is not int or constraints['maxCalls'] < 1:
        raise ValueError('invalid maxCalls')
    models = _model_map(raw)
    judge = next(row for row in models.values() if row['role'] == 'judge')
    if judge['deployment'] not in TRUSTED or judge['researchOnly']:
        raise ValueError('judge must remain in a real trusted domain')
    tasks = raw.get('tasks')
    if not isinstance(tasks, list) or {row.get('class') for row in tasks if isinstance(row, dict)} != TASK_CLASSES:
        raise ValueError('benchmark must cover every frozen task class')
    ids, sources = set(), set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {
                'id', 'class', 'sourceId', 'materialMode', 'originalGrade', 'task', 'referenceView',
                'referenceGrade', 'criteria', 'directInputTokens', 'directOutputTokens',
                'externalReferenceModel', 'trustedDirectModel', 'constrainedDirectModel', 'fixedDag'}:
            raise ValueError('invalid benchmark task fields')
        if task['id'] in ids or task['sourceId'] in sources or not task['task'].strip():
            raise ValueError('duplicate or empty benchmark material')
        ids.add(task['id']); sources.add(task['sourceId'])
        if task['materialMode'] not in {'synthetic', 'desensitized'}:
            raise ValueError('benchmark materials must be non-production')
        if task['originalGrade'] not in {'S1', 'S2', 'S3', 'unknown'} or task['referenceGrade'] != 'S3':
            raise ValueError('invalid task security grades')
        if not isinstance(task['criteria'], list) or not task['criteria']:
            raise ValueError('task requires fixed acceptance criteria')
        if task['originalGrade'] in SENSITIVE and task['referenceView'] == task['task']:
            raise ValueError('sensitive external reference requires a distinct desensitized view')
        for field in ('directInputTokens', 'directOutputTokens'):
            if type(task[field]) is not int or task[field] < 1:
                raise ValueError('invalid direct token envelope')
        for field, grade in (('externalReferenceModel', task['referenceGrade']),
                             ('trustedDirectModel', task['originalGrade']),
                             ('constrainedDirectModel', task['originalGrade'])):
            model = models.get(task[field])
            if model is None or model['role'] != 'candidate' or model['researchOnly']:
                raise ValueError('task references an unavailable deployable model')
            if not _allows(grade, model):
                raise ValueError(f'{field} violates the task trust boundary')
            if model['qualityProxy'] < quality_min:
                raise ValueError(f'{field} is below the preregistered quality proxy')
        if models[task['externalReferenceModel']]['deployment'] != 'external-cloud':
            raise ValueError('external reference must remain an external quality reference')
        if models[task['trustedDirectModel']]['deployment'] not in TRUSTED:
            raise ValueError('trusted direct baseline must stay in an allowed domain')
        _validate_nodes(task['fixedDag'], models, quality_min)
    return {'task_count': len(tasks), 'classes': sorted(TASK_CLASSES),
            'model_count': len(models), 'protocol_sha256': digest(raw)}


def preflight(raw):
    """验证全部路线并保守复算调用、成本和关键路径；不创建任何模型客户端。"""
    coverage = validate_protocol(raw)
    models = _model_map(raw)
    constraints = raw['constraints']
    judge = next(row for row in models.values() if row['role'] == 'judge')
    runs, calls = [], Counter()
    maximum_cost = 0.0
    for task in raw['tasks']:
        for repeat in range(1, constraints['repetitions'] + 1):
            for arm in ARMS:
                if arm == 'external-reference':
                    model_ids = [task['externalReferenceModel']]
                    grade, reference_only = task['referenceGrade'], True
                    production_cost = _cost(models[model_ids[0]], task['directInputTokens'], task['directOutputTokens'])
                    latency = models[model_ids[0]]['latencyMs']
                elif arm in {'trusted-direct', 'constrained-direct'}:
                    field = 'trustedDirectModel' if arm == 'trusted-direct' else 'constrainedDirectModel'
                    model_ids = [task[field]]
                    grade, reference_only = task['originalGrade'], False
                    production_cost = _cost(models[model_ids[0]], task['directInputTokens'], task['directOutputTokens'])
                    latency = models[model_ids[0]]['latencyMs']
                else:
                    nodes = task['fixedDag']
                    model_ids = [node['modelId'] for node in nodes]
                    grade, reference_only = task['originalGrade'], False
                    production_cost = sum(_cost(models[node['modelId']], node['inputTokens'], node['outputTokens'])
                                          for node in nodes)
                    finished = {}
                    for node in nodes:
                        finished[node['id']] = max((finished[parent] for parent in node['parents']), default=0) + models[node['modelId']]['latencyMs']
                    latency = max(finished.values())
                evaluation_cost = _cost(judge, task['directOutputTokens'] + 512, 512)
                total_cost = production_cost + evaluation_cost
                maximum_cost += total_cost
                calls['production'] += len(model_ids)
                calls['evaluation'] += 1
                runs.append({'task_id': task['id'], 'class': task['class'], 'repeat': repeat,
                             'arm': arm, 'reference_only': reference_only,
                             'deployable': not reference_only, 'security_grade': grade,
                             'model_ids': model_ids, 'judge_model_id': judge['id'],
                             'privacy_violations': 0, 'projected_cost': total_cost,
                             'projected_wall_time_ms': latency + judge['latencyMs'],
                             'quality_status': 'unmeasured'})
    maximum_calls = sum(calls.values())
    if maximum_calls > constraints['maxCalls']:
        raise ValueError('preflight call envelope exceeds frozen maxCalls')
    return {'schema_version': 'security-benchmark-preflight-v1', 'real_model_calls': 0,
            'protocol_sha256': coverage['protocol_sha256'], 'coverage': coverage,
            'runs': runs, 'planned_calls': dict(calls), 'maximum_calls': maximum_calls,
            'maximum_declared_cost': maximum_cost, 'billing_unit': raw['billingUnit'],
            'live_execution_ready': False,
            'blocking_requirements': ['开发批次尚未取得真实调用预算授权。',
                '开发批次完成前不冻结留出材料，也不运行 #113 在线策略。'],
            'frontier_policy': 'external-reference 只计算质量差距，不进入可部署前沿；主比较以最佳合法基线为准。'}
