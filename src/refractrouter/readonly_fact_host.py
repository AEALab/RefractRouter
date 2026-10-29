"""宿主固定范围的事实工具入口；不由 Router 派发，不读取模型凭据或执行仓库代码。"""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
import time

from .readonly_facts import (ReadonlyFacts, Unavailable, VERSION, LIMITS, sha, wire,
                             check_json_value, validate_candidate, strict_json)

HOST_VERSION = 'readonly-facts-host-v1'
MAX_REQUEST_BYTES = 1024 * 1024


def load_host(path, pinned_sha256, workspace):
    if type(pinned_sha256) is not str or re.fullmatch('[0-9a-f]{64}', pinned_sha256) is None:
        raise ValueError('宿主必须固定清单原始字节哈希')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('宿主清单必须为常规文件')
        raw = stream.read(MAX_REQUEST_BYTES + 1)
    if len(raw) > MAX_REQUEST_BYTES or sha(raw) != pinned_sha256:
        raise ValueError('宿主清单哈希不符或超过容量，禁止自动扩大可见范围')
    config = strict_json(raw)
    if (type(config) is not dict or set(config) - {'schemaVersion', 'root', 'files', 'visibleRanges'}
            or not {'schemaVersion', 'root', 'files'} <= set(config) or config['schemaVersion'] != HOST_VERSION
            or type(config['root']) is not str):
        raise ValueError('宿主事实清单版本或字段无效')
    workspace = Path(workspace).resolve(strict=True)
    root = (workspace / config['root']).resolve(strict=True)
    if not root.is_dir() or not root.is_relative_to(workspace):
        raise ValueError('事实根目录必须位于宿主实际工作区内')
    return ReadonlyFacts(root, config['files'], visible_ranges=config.get('visibleRanges'), workspace_root=workspace)


def identity(value):
    if (type(value) is not dict or set(value) != {'session', 'agent', 'turn'}
            or any(type(v) not in (str, int) or not str(v) or len(str(v)) > 256 for v in value.values())):
        raise ValueError('事实工具需要可信宿主任务身份')
    return deepcopy(value)


def tool_schemas():
    return [
        {'name': 'refract_source_excerpt', 'description': '按宿主固定的可见快照提取精确原文及字符/UTF-8字节区间，不解释语义。',
         'parameters': {'type': 'object', 'additionalProperties': False,
            'required': ['path', 'start', 'end', 'unit'], 'properties': {
                'path': {'type': 'string'}, 'start': {'type': 'integer', 'minimum': 0},
                'end': {'type': 'integer', 'minimum': 1}, 'unit': {'type': 'string', 'enum': ['char', 'utf8-byte']}}}},
        {'name': 'refract_python_structure', 'description': '读取可见Python词法符号的分支/return原文与明确语法结构；不能证明运行时结果或整题正确。',
         'parameters': {'type': 'object', 'additionalProperties': False,
            'required': ['path', 'symbol', 'definitionLine'], 'properties': {
                'path': {'type': 'string'}, 'symbol': {'type': 'string'},
                'definitionLine': {'type': ['integer', 'null'], 'minimum': 1}}}},
    ]


def execute(host, request):
    if type(request) is not dict or 'op' not in request:
        raise ValueError('事实工具请求须为带操作的对象')
    try:
        check_json_value(request)
    except Unavailable as exc:
        if request.get('op') == 'query':
            payload = {'schemaVersion': VERSION, 'snapshotId': host.snapshot_id, 'requestSha256': None,
                'status': 'unknown', 'reasonCode': exc.code, 'facts': [], 'parseStatus': 'not-confirmed',
                'wholeTaskQualityProven': False, 'modelCalls': 0, 'limits': LIMITS}
            text = wire(payload).decode()
            return {'schemaVersion': HOST_VERSION, 'snapshotId': host.snapshot_id, 'receipt': None,
                    'modelText': text, 'visibleUtf8Bytes': len(text.encode()), 'addedInputTokens': None,
                    'tokenMeasurement': 'not-provided-by-host', 'elapsedMs': 0, 'modelCalls': 0}
        return {'schemaVersion': HOST_VERSION, 'verification': unavailable(host, exc.code)}
    owner = identity(request.get('identity'))
    started = time.monotonic()
    if request['op'] == 'query' and set(request) == {'op', 'identity', 'operation', 'arguments'}:
        result = host.request(request['operation'], request['arguments'])
        receipt = {'identity': owner, 'snapshotId': host.snapshot_id,
            'operation': request['operation'], 'arguments': deepcopy(request['arguments']),
            'returnedFactIds': [f['factId'] for f in result['facts']]}
        return {'schemaVersion': HOST_VERSION, 'snapshotId': host.snapshot_id, 'receipt': receipt,
                'modelText': wire(result).decode(), 'visibleUtf8Bytes': result['visibleUtf8Bytes'],
                'elapsedMs': result['elapsedMs'], 'addedInputTokens': None,
                'tokenMeasurement': 'not-provided-by-host', 'modelCalls': 0}
    if request['op'] != 'verify' or set(request) != {'op', 'identity', 'candidateId', 'candidate', 'receipts'}:
        raise ValueError('事实工具操作或字段无效')
    receipts = request['receipts']
    if type(receipts) is not list or len(receipts) > 64:
        raise ValueError('宿主事实回执须为有界列表')
    allowed_fact_ids = set()
    for receipt in receipts:
        if (type(receipt) is not dict or set(receipt) != {'identity', 'snapshotId', 'operation', 'arguments', 'returnedFactIds'}
                or receipt['identity'] != owner or receipt['snapshotId'] != host.snapshot_id):
            raise ValueError('事实回执不属于当前宿主任务或固定快照')
        # 回执来自宿主实际工具返回；重新读取验证，不接受模型提供的事实正文。
        result = host.request(receipt['operation'], receipt['arguments'])
        if receipt['returnedFactIds'] != [f['factId'] for f in result['facts']]:
            raise Unavailable('fact-receipt-replay-mismatch')
        allowed_fact_ids.update(receipt['returnedFactIds'])
    candidate = request['candidate']
    candidate_digest = None
    try:
        candidate_digest = validate_candidate(request['candidateId'], candidate)
        result = host.verify_candidate(request['candidateId'], candidate, allowed_fact_ids=allowed_fact_ids)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        result = {'schemaVersion': VERSION, 'snapshotId': host.snapshot_id,
            'candidateId': request['candidateId'], 'candidateSha256': candidate_digest,
            'rows': [], 'allBoundFieldsSupported': False, 'wholeTaskQualityProven': False,
            'unboundTextSemanticsChecked': False, 'modelCalls': 0,
            'answerCoverage': 'selected-fields-only',
            'reasonCode': exc.code if isinstance(exc, Unavailable) else 'candidate-or-assertions-unavailable',
            'limits': LIMITS}
    result.update(identity=owner, elapsedMs=(time.monotonic() - started) * 1000)
    return {'schemaVersion': HOST_VERSION, 'verification': result}


def unavailable(host, reason):
    return {'schemaVersion': VERSION, 'snapshotId': host.snapshot_id, 'candidateId': None,
        'candidateSha256': None, 'bindingStatus': 'unavailable', 'rows': [],
        'allBoundFieldsSupported': False, 'wholeTaskQualityProven': False,
        'unboundTextSemanticsChecked': False, 'modelCalls': 0, 'reasonCode': reason, 'limits': LIMITS}


def run(path, pinned_sha256, workspace, request):
    host = load_host(path, pinned_sha256, workspace)
    try:
        result = execute(host, request)
    finally:
        host.close()
    if len(wire(result)) > 131072:
        raise Unavailable('host-response-capacity')
    return result
