"""封闭开发任务的独立评分；只解析数据和语法树，不执行候选补丁或调用模型。"""
import ast
from copy import deepcopy
import hashlib
import math

from .readonly_facts import strict_json, check_json_value

VERSION = 'closed-development-evaluation-v1'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


def tree_sha(text):
    # 以真实 UTF-8 文件字节解析，不能让无效 coding 声明被字符串解析忽略。
    return sha(ast.dump(ast.parse(text.encode('utf-8')), include_attributes=False).encode())


def repair_decorator_ranges(files, oracle):
    """只修复旧符号范围漏掉装饰器的错误；原冻结 oracle 不变，不修改评分语义。"""
    repaired, changes = deepcopy(oracle), []
    if oracle['filesSha256'] != {p: sha(t.encode()) for p, t in files.items()}:
        raise ValueError('诊断重放来源不匹配')
    for field, groups in repaired['evidence'].items():
        for group in groups:
            path = group['path']
            if not path.endswith('.py'): continue
            text = files[path]; lines = text.splitlines(keepends=True)
            for node in ast.walk(ast.parse(text.encode('utf-8'))):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or not node.decorator_list:
                    continue
                old_start = sum(map(len, lines[:node.lineno-1]))
                end = sum(map(len, lines[:node.end_lineno]))
                first = min(d.lineno for d in node.decorator_list)
                new_start = sum(map(len, lines[:first-1]))
                if group['start'] == old_start and group['end'] == end:
                    group['start'] = new_start
                    changes.append({'field': field, 'path': path, 'oldStart': old_start,
                        'newStart': new_start, 'end': end, 'change': 'include-existing-decorators'})
                    break
    return repaired, changes


def apply_edits(files, edits):
    """只在内存内替换已可见的原文；后续语法树检查限制可变行为，不执行代码。"""
    if type(edits) is not list or len(edits) > 8:
        raise ValueError('补丁必须为最多8项原文替换')
    changed = deepcopy(files)
    for row in edits:
        if (type(row) is not dict or set(row) != {'path', 'before', 'after'}
                or any(type(row[k]) is not str or not row[k] for k in row)
                or row['path'] not in changed
                or any(len(row[k].encode()) > 8192 for k in ('before', 'after'))):
            raise ValueError('补丁路径、原文或容量不合法')
        text = changed[row['path']]
        if text.count(row['before']) != 1:
            raise ValueError('补丁原文必须唯一匹配当前可见文件')
        changed[row['path']] = text.replace(row['before'], row['after'], 1)
    return changed


def _supports(text, quote, group):
    if (type(quote) is not str or not quote or len(quote.encode()) > 4096
            or not all(part in quote for part in group['allOf'])
            or group.get('anyOf') is not None and not any(part in quote for part in group['anyOf'])):
        return False
    start = text.find(quote)
    while start >= 0:
        if group['start'] <= start and start + len(quote) <= group['end']:
            return True
        start = text.find(quote, start + 1)
    return False


def evaluate(content, files, oracle):
    """oracle 仅由隔离评估器持有；完整通过只适用于这里明确定义的封闭任务。"""
    check_json_value(oracle)
    if (type(oracle) is not dict or set(oracle) != {
            'criteriaSha256', 'answers', 'evidence', 'expectedTrees', 'filesSha256'}
            or type(oracle['answers']) is not dict or not oracle['answers']
            or set(oracle['evidence']) != set(oracle['answers'])
            or oracle['filesSha256'] != {p: sha(t.encode()) for p, t in files.items()}
            or not set(oracle['expectedTrees']) <= set(files)):
        raise ValueError('评分合同、材料或完整要求与冻结来源不符')
    for groups in oracle['evidence'].values():
        if type(groups) is not list or not 1 <= len(groups) <= 8:
            raise ValueError('每个事实必须冻结完整证据要求')
        for g in groups:
            if (type(g) is not dict or set(g) not in ({'path', 'start', 'end', 'allOf'},
                    {'path', 'start', 'end', 'allOf', 'anyOf'})
                    or g['path'] not in files or type(g['start']) is not int or type(g['end']) is not int
                    or not 0 <= g['start'] < g['end'] <= len(files[g['path']])
                    or type(g['allOf']) is not list or not (g['allOf'] or g.get('anyOf'))
                    or any(type(p) is not str or not p for p in g['allOf'])
                    or 'anyOf' in g and (type(g['anyOf']) is not list or not g['anyOf']
                        or any(type(p) is not str or not p for p in g['anyOf']))):
                raise ValueError('证据要求缺失或范围无效')
    if type(content) is not str:
        raise ValueError('评分需要完整候选原文')
    try:
        candidate_digest = sha(content.encode())
    except UnicodeError:
        candidate_digest = None
    result = {'schemaVersion': VERSION, 'candidateSha256': candidate_digest,
        'criteriaSha256': oracle['criteriaSha256'], 'passed': False, 'status': 'FAIL',
        'dimensions': {'format': False, 'answers': False, 'citations': False, 'patch': False},
        'answerChecks': {}, 'citationChecks': {}, 'failureCodes': [], 'modelCalls': 0,
        'scope': 'complete-closed-task-only', 'openTaskQualityProven': False}
    try:
        if candidate_digest is None:
            raise ValueError('候选不是有效 UTF-8')
        value = strict_json(content)
        if (type(value) is not dict or set(value) != {'answers', 'evidence', 'edits'}
                or type(value['answers']) is not dict or type(value['evidence']) is not dict
                or set(value['answers']) != set(oracle['answers'])
                or set(value['evidence']) != set(oracle['answers'])
                or any(type(value['answers'][k]) is not type(v) for k, v in oracle['answers'].items())
                or type(value['edits']) is not list or len(value['edits']) > 8):
            raise ValueError('输出必须完整且没有附加字段')
        for refs in value['evidence'].values():
            if type(refs) is not list or not 1 <= len(refs) <= 8 or any(
                    type(r) is not dict or set(r) != {'path', 'quote'}
                    or any(type(r[k]) is not str or not r[k] for k in r) for r in refs):
                raise ValueError('引用结构或数量无效')
        for edit in value['edits']:
            if (type(edit) is not dict or set(edit) != {'path', 'before', 'after'}
                    or any(type(edit[k]) is not str or not edit[k] for k in edit)):
                raise ValueError('替换结构无效')
        result['dimensions']['format'] = True
    except (ValueError, TypeError, UnicodeError, OverflowError):
        result['failureCodes'].append('output-format')
        return result
    result['answerChecks'] = {k: same(value['answers'][k], expected) for k, expected in oracle['answers'].items()}
    result['dimensions']['answers'] = all(result['answerChecks'].values())
    for key, groups in oracle['evidence'].items():
        references, covered, valid = value['evidence'][key], set(), True
        if type(references) is not list or not 1 <= len(references) <= 8:
            result['citationChecks'][key] = False
            continue
        seen = set()
        for reference in references:
            if (type(reference) is not dict or set(reference) != {'path', 'quote'}
                    or type(reference['path']) is not str or reference['path'] not in files
                    or type(reference['quote']) is not str):
                valid = False
                continue
            pair = reference['path'], reference['quote']
            matched = {i for i, group in enumerate(groups)
                       if reference['path'] == group['path'] and _supports(files[reference['path']], reference['quote'], group)}
            if not matched or pair in seen:
                valid = False
            seen.add(pair); covered.update(matched)
        result['citationChecks'][key] = valid and covered == set(range(len(groups)))
    result['dimensions']['citations'] = all(result['citationChecks'].values())
    try:
        if oracle['expectedTrees']:
            updated = apply_edits(files, value['edits'])
            result['dimensions']['patch'] = all(
                tree_sha(updated[path]) == expected for path, expected in oracle['expectedTrees'].items())
            result['dimensions']['patch'] &= all(
                updated[p] == text for p, text in files.items() if p not in oracle['expectedTrees'])
        else:
            result['dimensions']['patch'] = value['edits'] == []
    except (ValueError, TypeError, SyntaxError, RecursionError, MemoryError, UnicodeError):
        result['dimensions']['patch'] = False
    result['passed'] = all(result['dimensions'].values())
    result['status'] = 'PASS' if result['passed'] else 'FAIL'
    result['failureCodes'] = [key for key, passed in result['dimensions'].items() if not passed]
    return result


def paired_screen(rows, *, minimum_savings=.2, quality_margin=.03):
    """任务是统计单位；零损失也须报告精度，未完成或未知费用不计算整批节省。"""
    if (type(rows) is not list or not 1 <= len(rows) <= 1000
            or any(type(r) is not dict or type(r.get('taskId')) is not str or not r['taskId'] for r in rows)
            or len({r['taskId'] for r in rows}) != len(rows)):
        raise ValueError('配对必须包含非空且唯一的冻结任务')
    if (type(minimum_savings) not in (int, float) or not .2 <= minimum_savings < 1
            or type(quality_margin) not in (int, float) or not 0 < quality_margin <= .03
            or any(type(r.get('half')) is not int or r['half'] not in (0, 1)
                   or any(r.get(k) is not None and type(r.get(k)) is not bool
                          for k in ('baselinePassed', 'candidatePassed'))
                   or any(type(r.get(k)) is not bool for k in ('completedPair', 'knownCost')) for r in rows)):
        raise ValueError('配对划分、状态或验收门槛无效')
    n = len(rows)
    losses = sum(r['baselinePassed'] is True and r['candidatePassed'] is not True for r in rows)
    gains = sum(r['baselinePassed'] is False and r['candidatePassed'] is True for r in rows)
    quality_complete = all(r['completedPair'] and type(r['baselinePassed']) is bool
        and type(r['candidatePassed']) is bool for r in rows)
    if losses == 0:
        upper = -math.expm1(math.log(.05) / n)
    else:
        low, high = 0., 1.
        for _ in range(80):
            mid = (low + high) / 2
            cdf = sum(math.comb(n, i) * mid**i * (1 - mid)**(n - i) for i in range(losses + 1))
            if cdf > .05:
                low = mid
            else:
                high = mid
        upper = high
    complete = all(r.get('completedPair') is True and r.get('knownCost') is True for r in rows)
    savings = None
    halves = []
    if complete:
        from .task_cost_observation import amount
        old = sum(amount(r['baselineCost']) for r in rows)
        new = sum(amount(r['candidateCost']) for r in rows)
        savings = float((old - new) / old) if old else None
        for half in (0, 1):
            group = [r for r in rows if r['half'] == half]
            a = sum(amount(r['baselineCost']) for r in group)
            b = sum(amount(r['candidateCost']) for r in group)
            halves.append(float((a - b) / a) if a else None)
    quality_evidence = quality_complete and -upper >= -quality_margin
    return {'schemaVersion': 'closed-development-paired-screen-v1', 'taskCount': n,
        'strongCompletedCandidateNotCompleted': losses, 'candidateImproved': gains,
        'qualityLabelsComplete': quality_complete,
        'qualityDifferenceObserved': (gains - losses) / n if quality_complete else None,
        'qualityDifferenceLower95': -upper if quality_complete else None,
        'intervalMethod': 'conservative-one-sided-clopper-pearson-loss-bound',
        'independentTaskAssumptionRequiresSourceAudit': True,
        'batchCostComparable': complete, 'savingsFraction': savings, 'halfSavings': halves,
        'qualityIntervalWithinMargin': quality_evidence, 'qualityMaintainedProven': False,
        'costTargetObserved': savings is not None and savings >= minimum_savings
            and len(halves) == 2 and all(h is not None and h > 0 for h in halves),
        'releaseAllowed': False, 'scope': 'screening-no-automatic-expansion'}
