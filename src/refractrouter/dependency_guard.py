"""对有明确句法的排程材料做零模型依赖复算；未识别的自然语言不冒充已验证。"""
from graphlib import TopologicalSorter, CycleError
import json
import re


class NodeSemanticFailure(ValueError):
    """已结算输出与确定性事实检查冲突。"""


class NeedsDecomposition(ValueError):
    """模型明确请求把当前职责拆细；不是已完成的交付。"""


def decomposition_request(content):
    try:
        value = json.loads(content)
    except ValueError:
        return None
    if isinstance(value, dict) and value.get('status') == 'needs-decomposition':
        reason = value.get('reason')
        return reason[:500] if isinstance(reason, str) and reason.strip() else '节点请求再拆分'
    return None


def schedule(nodes, increments=None):
    increments = increments or {}
    order = tuple(TopologicalSorter({nid: row['parents'] for nid, row in nodes.items()}).static_order())
    times, paths = {}, {}
    for nid in order:
        parents = nodes[nid]['parents']
        start = max((times[p]['end'] for p in parents), default=0)
        times[nid] = {'start': start, 'end': start + nodes[nid]['duration'] + increments.get(nid, 0)}
        paths[nid] = [p + [nid] for parent in parents if times[parent]['end'] == start for p in paths[parent]] if parents else [[nid]]
        if len(paths[nid]) > 128:
            raise ValueError('too many critical paths')
    makespan = max(t['end'] for t in times.values())
    return {'times': times, 'makespan': makespan,
        'critical_paths': [p for nid in order if times[nid]['end'] == makespan for p in paths[nid]]}


class DependencyGuard:
    def __init__(self, task):
        self.nodes, self.scenarios = {}, {}
        self.status = 'not-applicable'
        # 只覆盖显式「A 需要 N 天；B 需要 N 天且必须等 A 完成」的封闭材料。
        # 句法不明、重复定义、额外依赖表达或不明确起点都拒绝推断。
        matches = list(re.finditer(r'\b([A-Z])\s*需要\s*(\d+)\s*天([^；。\n]*)', task))
        if not matches:
            return
        self.status = 'unsupported-source'
        if not 2 <= len(matches) <= 26 or not re.search(r'第\s*0\s*天开始', task):
            return
        nodes = {}
        for i, m in enumerate(matches):
            nid, duration, clause = m.group(1), int(m.group(2)), m.group(3)
            if nid in nodes or duration < 1 or duration > 10000:
                return
            dep = re.fullmatch(r'[，,且\s]*必须等\s*([A-Z](?:\s*(?:和|、|及)\s*[A-Z])*)\s*都?完成[，,\s]*', clause)
            independent = re.fullmatch(r'[，,\s]*可在第\s*0\s*天独立开始[，,\s]*', clause)
            if dep:
                parents = re.findall(r'[A-Z]', dep.group(1))
            elif independent or (i == 0 and not clause.strip(' ，,')):
                parents = []
            else:
                return
            nodes[nid] = {'duration': duration, 'parents': parents, 'source_quote': m.group(0)}
        if any(p not in nodes for row in nodes.values() for p in row['parents']):
            return
        try:
            original = schedule(nodes)
            scenarios = {'original': original}
            for m in re.finditer(r'\b([A-Z])\s*(?:额外)?延误\s*(\d+)\s*天', task):
                nid, days = m.group(1), int(m.group(2))
                if nid not in nodes or days > 10000 or nid in scenarios:
                    return
                scenarios[nid] = schedule(nodes, {nid: days})
        except (ValueError, CycleError):
            return
        self.nodes, self.scenarios, self.status = nodes, scenarios, 'supported'

    def evidence(self):
        return {'kind': 'explicit-schedule-dependencies-v1', 'source_status': self.status,
            'nodes': self.nodes, 'scenarios': self.scenarios,
            'scope': '只核对受支持材料的显式箭头依赖和关键链覆盖，不等于完整正文事实验收。'}

    def instruction(self):
        if self.status != 'supported':
            return ''
        return ('\n\n以下由 Python 按原文明确依赖计算，保留原文为依据；不要创造不存在的边。'
            '涉及排程时，用 A→B 的箭头形式列出原始及延误后的完整关键链；不得保留错误链再补一句修正。'
            + json.dumps(self.evidence(), ensure_ascii=False))

    def check(self, content, *, final=False):
        result = {'source_status': self.status, 'passed': None, 'invalid_edges': [], 'missing_paths': []}
        if self.status != 'supported':
            return result
        # 去掉 Markdown 强调和代码标记；不把出现「错误」字样当作豁免，否则会再次放过自相矛盾。
        normalized = re.sub(r'[*`_]', '', content)
        chains = [re.findall(r'[A-Z]', m.group(0)) for m in re.finditer(
            r'(?<![A-Za-z])[A-Z](?:\s*(?:→|->|=>|➔|⟶|－|—|–|-)\s*[A-Z](?![A-Za-z]))+', normalized)]
        for chain in chains:
            if not any(n in self.nodes for n in chain):
                continue
            for parent, child in zip(chain, chain[1:]):
                if child not in self.nodes or parent not in self.nodes[child]['parents']:
                    result['invalid_edges'].append([parent, child])
        if final:
            for name, scenario in self.scenarios.items():
                if not any(path in chains for path in scenario['critical_paths']):
                    result['missing_paths'].append({'scenario': name, 'expected': scenario['critical_paths']})
        result['passed'] = not (result['invalid_edges'] or result['missing_paths'])
        return result

    def validate(self, content, *, final=False):
        verdict = self.check(content, final=final)
        if verdict['passed'] is False:
            raise NodeSemanticFailure('dependency-check-failed: ' + json.dumps(verdict, ensure_ascii=False))
        return verdict
