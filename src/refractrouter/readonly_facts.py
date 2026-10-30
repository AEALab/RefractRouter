"""宿主调用的只读局部事实；不运行仓库代码，不解释自然语言质量。"""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from threading import RLock
import time

VERSION = "readonly-local-facts-v1"
PARSER_VERSION = f"python-{sys.version_info.major}.{sys.version_info.minor}"
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_AST_BYTES = 512 * 1024
MAX_FACT_BYTES = 48000
MAX_FACTS = 256
MAX_CACHED_FACTS = 4096
MAX_CANDIDATE_BYTES = 256 * 1024
LIMITS = ("只证明可见快照中的原文和词法结构；不证明可达性、运行时值、跨文件动态派发、"
          "finally 后的结果或自然语言整题正确性。")


class Unavailable(ValueError):
    def __init__(self, code, parse_status='not-confirmed'):
        super().__init__(code)
        self.code, self.parse_status = code, parse_status


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def check_json_value(value, maximum_bytes=1024 * 1024):
    """先检查原生 JSON 值、Unicode 与容量，再序列化/摘要；不调用用户对象方法。"""
    pending, size, nodes = [(value, 0)], 0, 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 64 or nodes > 100000:
            raise Unavailable('json-capacity')
        typ = type(item)
        if typ is str:
            if len(item) > maximum_bytes:
                raise Unavailable('json-capacity')
            try:
                size += len(item.encode('utf-8')) + 2
            except UnicodeError as exc:
                raise Unavailable('invalid-json-value') from exc
        elif typ is dict:
            if len(item) * 2 > 100000 - nodes:
                raise Unavailable('json-capacity')
            if any(type(k) is not str for k in item):
                raise Unavailable('invalid-json-value')
            size += len(item) * 2 + 2
            pending.extend((v, depth + 1) for pair in item.items() for v in pair)
        elif typ is list:
            if len(item) > 100000 - nodes:
                raise Unavailable('json-capacity')
            size += len(item) + 2
            pending.extend((v, depth + 1) for v in item)
        elif typ is float:
            if not math.isfinite(item):
                raise Unavailable('invalid-json-value')
            size += 32
        elif typ is int:
            if item.bit_length() > 4096:
                raise Unavailable('json-capacity')
            size += max(1, item.bit_length())
        elif item is None or typ is bool:
            size += 5
        else:
            raise Unavailable('invalid-json-value')
        if size > maximum_bytes:
            raise Unavailable('json-capacity')


def validate_candidate(candidate_id, candidate):
    if (type(candidate_id) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', candidate_id) is None
            or type(candidate) is not dict or set(candidate) != {'content', 'toolCalls', 'finishReason'}
            or type(candidate['content']) is not str or type(candidate['toolCalls']) is not list
            or candidate['toolCalls'] or candidate['finishReason'] != 'stop'):
        raise Unavailable('candidate-shape-or-not-final')
    check_json_value(candidate)
    if len(candidate['content'].encode()) > MAX_CANDIDATE_BYTES:
        raise Unavailable('candidate-capacity')
    return sha(wire(candidate))


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('JSON 包含重复字段')
            result[key] = value
        return result
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('JSON 数值必须有限')
        return number
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_float=finite_float,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON 数值无效')))
        check_json_value(result)
        return result
    except RecursionError as exc:
        raise ValueError('JSON 嵌套超过处理容量') from exc


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def valid_path(path):
    if (type(path) is not str or not path or '\\' in path or '\x00' in path
            or PurePosixPath(path).is_absolute() or any(p in {'', '.', '..'} for p in path.split('/'))):
        raise ValueError("路径必须是允许清单内的精确相对路径")
    return path


def interval(raw, start, end):
    """字符指 Python Unicode 码点，字节指原始 UTF-8；保持 CRLF 和组合字符原样。"""
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw):
        raise ValueError("来源区间无效")
    prefix, selected = raw[:start].decode('utf-8'), raw[start:end].decode('utf-8')
    starts = [0, *(m.end() for m in re.finditer(rb'\r\n|\r|\n', raw))]
    return {'startUtf8Byte': start, 'endUtf8Byte': end, 'startChar': len(prefix),
            'endChar': len(prefix) + len(selected), 'quote': selected,
            'startLine': sum(pos <= start for pos in starts),
            'endLine': sum(pos < end for pos in starts)}


def node_interval(raw, node):
    starts = [0, *(m.end() for m in re.finditer(rb'\r\n|\r|\n', raw))]
    return interval(raw, starts[node.lineno - 1] + node.col_offset,
                    starts[node.end_lineno - 1] + node.end_col_offset)


class ReadonlyFacts:
    """root 和 manifest 由宿主固定，模型只能提出精确来源请求。

    允许清单必须由宿主预先排除隐藏评估材料；不从仓库全量自动生成。
    文件在每次提取和断言复核时重新验哈希，事实 ID 只属于本实例的可见快照。
    """
    def __init__(self, root, manifest, *, visible_ranges=None, workspace_root=None):
        self.root = Path(root).resolve(strict=True)
        if type(manifest) is not dict or not manifest or len(manifest) > 1000:
            raise ValueError('需要宿主固定的可见文件清单')
        for path, hashed in manifest.items():
            valid_path(path)
            if type(hashed) is not str or re.fullmatch('[0-9a-f]{64}', hashed) is None:
                raise ValueError('可见文件必须绑定原始字节哈希')
        self.manifest = deepcopy(manifest)
        if visible_ranges is not None:
            if type(visible_ranges) is not dict or set(visible_ranges) != set(manifest):
                raise ValueError('可见范围必须明确覆盖清单中的每个文件')
            for ranges in visible_ranges.values():
                if type(ranges) is not list or not ranges or len(ranges) > 128:
                    raise ValueError('可见范围须为有界非空区间列表')
                for pair in ranges:
                    if (type(pair) is not list or len(pair) != 2 or any(type(n) is not int for n in pair)
                            or not 0 <= pair[0] < pair[1] <= MAX_FILE_BYTES):
                        raise ValueError('可见字节区间无效')
        self.visible_ranges = deepcopy(visible_ranges)
        self.snapshot_id = sha(wire({'version': VERSION, 'parser': PARSER_VERSION,
                                    'files': manifest, 'visibleRanges': visible_ranges}))
        self._facts = {}
        self.lock = RLock()
        # 先锚定宿主工作区，再用 dir_fd/O_NOFOLLOW 逐段打开根目录，防止祖先目录换成链接。
        anchor = Path(workspace_root).resolve(strict=True) if workspace_root is not None else self.root
        if not self.root.is_relative_to(anchor):
            raise ValueError('事实根目录超出宿主工作区')
        opened = []
        try:
            fd = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            opened.append(fd)
            for part in self.root.relative_to(anchor).parts:
                fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                opened.append(fd)
            self._root_fd = os.dup(fd)
        finally:
            for fd in reversed(opened):
                os.close(fd)

    def close(self):
        with self.lock:
            if getattr(self, '_root_fd', None) is not None:
                os.close(self._root_fd)
                self._root_fd = None

    def __del__(self):
        if hasattr(self, 'lock'):
            self.close()

    def _visible(self, path, span):
        if self.visible_ranges is not None and not any(start <= span['startUtf8Byte']
                and span['endUtf8Byte'] <= end for start, end in self.visible_ranges[path]):
            raise Unavailable('visible-range-insufficient')

    def _publish(self, facts):
        if len(facts) > MAX_FACTS or len(wire(facts)) > MAX_FACT_BYTES:
            raise Unavailable('fact-response-capacity')
        with self.lock:
            if len(set(self._facts) | {f['factId'] for f in facts}) > MAX_CACHED_FACTS:
                raise Unavailable('fact-session-capacity')
            self._facts.update({f['factId']: deepcopy(f) for f in facts})
        return facts

    def _read(self, path):
        valid_path(path)
        if path not in self.manifest:
            raise PermissionError('路径不在宿主可见清单中')
        descriptors = []
        try:
            with self.lock:
                if self._root_fd is None:
                    raise ValueError('事实快照已关闭')
                parent = os.dup(self._root_fd)
            descriptors.append(parent)
            parts = path.split('/')
            for part in parts[:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                descriptors.append(parent)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            descriptors.append(fd)
            meta = os.fstat(fd)
            if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_FILE_BYTES:
                raise Unavailable('source-file-capacity-or-type')
            with os.fdopen(os.dup(fd), 'rb') as stream:
                raw = stream.read(MAX_FILE_BYTES + 1)
            if len(raw) > MAX_FILE_BYTES or sha(raw) != self.manifest[path]:
                raise Unavailable('source-file-drift')
            raw.decode('utf-8')
            return raw
        finally:
            for fd in reversed(descriptors):
                os.close(fd)

    def snapshot_texts(self):
        """宿主读取固定允许清单的完整 UTF-8 快照；同样逐文件拒绝链接和哈希漂移。"""
        return {path: self._read(path).decode('utf-8') for path in self.manifest}

    def _fact(self, path, kind, span, details):
        self._visible(path, span)
        fact = {'toolVersion': VERSION, 'parserVersion': PARSER_VERSION, 'snapshotId': self.snapshot_id, 'path': path,
                'fileSha256': self.manifest[path], 'kind': kind, 'span': span, 'details': details}
        fact['factId'] = sha(wire(fact))
        return fact

    def excerpt(self, path, start, end, *, unit='utf8-byte'):
        raw = self._read(path)
        if unit == 'char':
            text = raw.decode('utf-8')
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                raise ValueError('字符区间无效')
            start, end = len(text[:start].encode()), len(text[:end].encode())
        elif unit != 'utf8-byte':
            raise ValueError('不支持的来源单位')
        span = interval(raw, start, end)
        return self._publish([self._fact(path, 'source-excerpt', span, {'source': span['quote']})])

    def structure(self, path, symbol, *, definition_line=None):
        if definition_line is not None and (type(definition_line) is not int or definition_line <= 0):
            raise ValueError('定义行必须为正整数或 null')
        raw = self._read(path)
        if not path.endswith('.py') or type(symbol) is not str or not symbol:
            raise ValueError('需要 Python 文件和精确词法符号')
        if len(raw) > MAX_AST_BYTES:
            raise Unavailable('python-source-capacity', 'unavailable')
        try:
            tree = ast.parse(raw.decode('utf-8'), filename=path)
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise Unavailable('python-parse-unavailable', 'unavailable') from exc
        if sum(1 for _ in ast.walk(tree)) > 50000:
            raise Unavailable('python-ast-capacity', 'unavailable')
        matches = []
        def collect(node, owners):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified = '.'.join([*owners, node.name])
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and qualified == symbol:
                    if definition_line is None or node.lineno == definition_line:
                        matches.append(node)
                owners = [*owners, node.name]
            for child in ast.iter_child_nodes(node):
                collect(child, owners)
        collect(tree, [])
        if len(matches) != 1:
            raise Unavailable('symbol-missing-or-ambiguous', 'unavailable')
        self._visible(path, node_interval(raw, matches[0]))
        facts = []
        fact_bytes = 0
        def add(fact):
            nonlocal fact_bytes
            fact_bytes += len(wire(fact))
            if len(facts) >= MAX_FACTS or fact_bytes > MAX_FACT_BYTES - MAX_FACTS:
                raise Unavailable('fact-response-capacity', 'unavailable')
            facts.append(fact)
        def visit(node, ancestry):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                return
            if isinstance(node, ast.Return):
                value = node.value
                elements = value.elts if isinstance(value, ast.Tuple) else None
                starred = elements is not None and any(isinstance(e, ast.Starred) for e in elements)
                detail = {'symbol': symbol, 'definitionLine': matches[0].lineno,
                    'astKind': type(value).__name__ if value else None,
                    'expressionSource': node_interval(raw, value)['quote'] if value else None,
                    'fixedTupleArity': len(elements) if elements is not None and not starred else None,
                    'hasStarred': starred if elements is not None else None,
                    'components': [{'astKind': type(e).__name__, 'source': node_interval(raw, e)['quote']}
                                   for e in elements] if elements is not None else None,
                    'lexicalAncestry': deepcopy(ancestry)}
                add(self._fact(path, 'return-expression', node_interval(raw, node), detail))
            if isinstance(node, ast.If):
                add(self._fact(path, 'lexical-branch', node_interval(raw, node), {
                    'symbol': symbol, 'definitionLine': matches[0].lineno,
                    'conditionSource': node_interval(raw, node.test)['quote']}))
            for field, child in ast.iter_fields(node):
                for item in child if isinstance(child, list) else [child]:
                    if isinstance(item, ast.AST):
                        visit(item, [*ancestry, {'node': type(node).__name__, 'field': field,
                            **({'conditionSource': node_interval(raw, node.test)['quote']}
                               if isinstance(node, ast.If) and field in {'body', 'orelse'} else {})}])
        for statement in matches[0].body:
            visit(statement, [])
        return self._publish(sorted(facts, key=lambda fact: (fact['span']['startUtf8Byte'], fact['kind'])))

    def request(self, operation, arguments):
        start = time.monotonic()
        request_digest = None
        facts, status, reason, parse_status = [], 'unknown', 'unsupported-request', 'not-confirmed'
        try:
            request = {'operation': operation, 'arguments': arguments}
            check_json_value(request)
            request_digest = sha(wire(request))
            if type(arguments) is not dict:
                raise ValueError('工具参数须为对象')
            if operation == 'source-excerpt' and set(arguments) == {'path', 'start', 'end', 'unit'}:
                facts = self.excerpt(arguments['path'], arguments['start'], arguments['end'], unit=arguments['unit'])
            elif operation == 'python-structure' and set(arguments) == {'path', 'symbol', 'definitionLine'}:
                if arguments['definitionLine'] is not None and (type(arguments['definitionLine']) is not int
                        or arguments['definitionLine'] <= 0):
                    raise ValueError('定义行必须是正整数或 null')
                facts = self.structure(arguments['path'], arguments['symbol'], definition_line=arguments['definitionLine'])
            else:
                raise ValueError('工具操作字段缺失、未知或越过范围')
            status, reason = 'known', 'exact-visible-source'
            parse_status = 'parsed' if operation == 'python-structure' else 'not-applicable'
        except Unavailable as exc:
            reason, parse_status = exc.code, exc.parse_status
        except PermissionError:
            status, reason = 'denied', 'outside-host-visible-scope'
        except (OSError, ValueError, UnicodeError, SyntaxError, RecursionError):
            reason = 'unavailable-source-or-structure'
        payload = {'schemaVersion': VERSION, 'snapshotId': self.snapshot_id, 'requestSha256': request_digest,
            'status': status, 'reasonCode': reason, 'facts': facts, 'limits': LIMITS,
            'parserVersion': PARSER_VERSION, 'parseStatus': parse_status,
            'wholeTaskQualityProven': False, 'modelCalls': 0, 'addedInputTokens': None,
            'assertionContract': {'answerField': 'answer', 'declarationsField': 'structuralAssertions',
                'fields': ['factId', 'field', 'answerPointer'], 'answerCoverage': 'selected-fields-only'},
            'tokenMeasurement': 'not-provided-by-host', 'elapsedMs': (time.monotonic() - start) * 1000}
        payload['visibleUtf8Bytes'] = 0
        while payload['visibleUtf8Bytes'] != len(wire(payload)):
            payload['visibleUtf8Bytes'] = len(wire(payload))
        return payload

    def verify_candidate(self, candidate_id, candidate, assertions=None, *, allowed_fact_ids=None):
        """宿主传入实际最终候选；模型仅声明断言，不提供事实库或替代最终正文。"""
        candidate_digest = validate_candidate(candidate_id, candidate)
        answer = strict_json(candidate['content'])
        if type(answer) is not dict or 'answer' not in answer or 'structuralAssertions' not in answer:
            raise Unavailable('no-explicit-structural-assertions')
        declared = answer['structuralAssertions']
        if assertions is not None:
            check_json_value(assertions)
            if wire(assertions) != wire(declared):
                raise Unavailable('assertions-not-declared-by-candidate')
        assertions = declared
        if type(assertions) is not list or len(assertions) > 64:
            raise ValueError('显式断言须为有界列表')
        rows, seen = [], set()
        for assertion in assertions:
            if type(assertion) is not dict or set(assertion) != {'factId', 'field', 'answerPointer'}:
                raise ValueError('断言字段缺失或未知')
            fact_id, field, pointer = (assertion[k] for k in ('factId', 'field', 'answerPointer'))
            if (type(fact_id) is not str or re.fullmatch('[0-9a-f]{64}', fact_id) is None
                    or type(field) is not str or type(pointer) is not str):
                raise ValueError('断言身份或字段类型无效')
            if pointer != '/answer' and not pointer.startswith('/answer/'):
                raise Unavailable('assertion-outside-final-answer')
            identity = (fact_id, field, pointer)
            if identity in seen:
                raise ValueError('重复断言不能重复计数')
            seen.add(identity)
            row = {'assertion': deepcopy(assertion), 'verdict': 'unknown', 'reasonCode': 'fact-not-visible',
                   'observed': None, 'answerValue': None}
            with self.lock:
                fact = deepcopy(self._facts.get(fact_id)) if allowed_fact_ids is None or fact_id in allowed_fact_ids else None
            if fact is not None:
                try:
                    self._read(fact['path'])
                    target = answer
                    if pointer and not pointer.startswith('/'):
                        raise ValueError('JSON pointer 无效')
                    for segment in pointer[1:].split('/') if pointer else []:
                        if re.search(r'~(?![01])', segment):
                            raise ValueError('JSON pointer 转义无效')
                        segment = segment.replace('~1', '/').replace('~0', '~')
                        if isinstance(target, dict):
                            target = target[segment]
                        elif isinstance(target, list) and re.fullmatch('0|[1-9][0-9]*', segment):
                            target = target[int(segment)]
                        else:
                            raise ValueError('候选字段不可唯一定位')
                    supported = {'astKind', 'expressionSource', 'fixedTupleArity', 'hasStarred', 'conditionSource'}
                    observed = fact['span']['quote'] if field == 'source' else (
                        fact['details'].get(field) if field in supported else None)
                    def presented(value):
                        raw = wire(value)
                        return deepcopy(value) if len(raw) <= 128 else {
                            'sha256': sha(raw), 'utf8Bytes': len(raw), 'presentation': 'digest'}
                    row.update(observed=presented(observed), answerValue=presented(target),
                               reasonCode='unsupported-structural-field')
                    if observed is not None:
                        row.update(verdict='supported' if type(observed) is type(target) and observed == target
                                   else 'contradicted', reasonCode='exact-bound-field-comparison')
                except (OSError, ValueError, UnicodeError, KeyError, IndexError):
                    row['reasonCode'] = 'source-drift-or-unavailable-answer-binding'
            rows.append(row)
        result = {'schemaVersion': VERSION, 'snapshotId': self.snapshot_id, 'candidateId': candidate_id,
                'candidateSha256': candidate_digest, 'rows': rows,
                'allBoundFieldsSupported': bool(rows) and all(r['verdict'] == 'supported' for r in rows),
                'answerCoverage': 'selected-fields-only',
                'wholeTaskQualityProven': False, 'unboundTextSemanticsChecked': False,
                'modelCalls': 0, 'limits': LIMITS}
        if len(wire(result)) > 64000:
            raise Unavailable('assertion-response-capacity')
        return result
