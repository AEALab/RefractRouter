"""节点实测档案的任务适用范围；避免把有限材料成绩外推到任意任务。"""
from copy import deepcopy
import hashlib
import re


def task_digest(task):
    if not isinstance(task, str) or not task.strip():
        return None
    return hashlib.sha256(task.replace('\r\n', '\n').strip().encode()).hexdigest()


def validate_scope(raw):
    if raw is None:
        return None
    if (not isinstance(raw, dict) or set(raw) != {'version', 'description', 'taskSha256'}
            or raw['version'] != 'exact-task-v1'
            or not isinstance(raw['description'], str) or not 1 <= len(raw['description']) <= 1000
            or not isinstance(raw['taskSha256'], list) or not 1 <= len(raw['taskSha256']) <= 256
            or any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in raw['taskSha256'])
            or len(set(raw['taskSha256'])) != len(raw['taskSha256'])):
        raise ValueError('节点能力档案的任务适用范围无效')
    return deepcopy(raw)


def matches_scope(scope, task):
    return scope is None or task_digest(task) in scope['taskSha256']


def scope_receipt(scope, task):
    if scope is None:
        return None
    return {'version': scope['version'], 'description': scope['description'],
            'task_count': len(scope['taskSha256']), 'matched': matches_scope(scope, task)}
