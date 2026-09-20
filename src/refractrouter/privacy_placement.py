"""安全感知的节点放置：部署域标签、确定性分级、候选收窄与运行期守门。

本模块只做判定、候选过滤与运行期拦截，不发起模型调用。约束默认关闭：未配置 privacy
字段时调用方不进入本模块，路由行为与现状一致。契约见
docs/privacy-aware-node-placement.md（里程碑 A2）。
"""
from __future__ import annotations

import json
import hashlib
import re

POLICY_VERSION = 'security-placement-v2'
LEGACY_POLICY_VERSION = 'privacy-placement-v1'
DEPLOYMENTS = ('cloud', 'external-cloud', 'trusted-cloud', 'local', 'simulated-local')
# “零边际成本”与“可接触真实敏感材料”是两个独立维度。模拟本地只用于研究计价，
# 不能因为价格记为 0 就取得真实本地的信任资格。
ZERO_COST_DEPLOYMENTS = frozenset({'local', 'simulated-local'})
SENSITIVE_DEPLOYMENTS = frozenset({'local', 'trusted-cloud'})
NARROWED_GRADES = frozenset({'S1', 'S2', 'unknown'})
DEFAULT_MAX_PROMPT_BYTES = 1_048_576
MIN_MAX_PROMPT_BYTES = 1024
MAX_MAX_PROMPT_BYTES = 67_108_864
MAX_SENSITIVE_TERMS = 256
MAX_SENSITIVE_TERM_CHARS = 100

# 第一道为确定性规则，零成本、无模型调用。命中即整节点 S1，收窄到本地候选。
RULES = (
    ('private-key', re.compile(r'-----BEGIN(?: [A-Z0-9]+)* ?PRIVATE KEY-----')),
    ('credential-assignment', re.compile(
        r'(?i)\b(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|refresh[_-]?token'
        r'|client[_-]?secret|password|passwd)\b\s*"?\s*[:=：]\s*"?\s*[A-Za-z0-9_\-+/=]{6,}')),
    ('credential-assignment-zh', re.compile(
        r'(?:密码|口令|密钥)\s*[:=：]\s*[A-Za-z0-9_\-+/=]{6,}')),
    ('bearer-token', re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*')),
    ('email', re.compile(r'[\w.+-]+@[\w-]+\.[A-Za-z]{2,12}\b')),
    ('phone-cn', re.compile(r'(?<!\d)1[3-9]\d{9}(?!\d)')),
    ('local-absolute-path', re.compile(
        r'(?:^|[\s"\'(=:])(/(?:Users|home|root|Volumes|private|opt|srv|mnt)/[A-Za-z0-9._-]+)')),
    ('windows-absolute-path', re.compile(
        r'(?:^|[\s"\'(=:])[A-Za-z]:\\(?:Users|Documents|Desktop|AppData)\\', re.IGNORECASE)),
)


def default_privacy():
    """约束关闭时的规范形态；写进运行记录，便于回放比对。"""
    return {'enabled': False, 'sensitiveTerms': [],
            'classifier': {'enabled': False, 'modelId': None},
            'maxPromptBytes': DEFAULT_MAX_PROMPT_BYTES}


def privacy_enabled(privacy):
    return bool(privacy) and bool(privacy.get('enabled'))


def deployment_of(model):
    """模型部署域；未声明按 cloud 处理，历史配置行为不变。"""
    value = getattr(model, 'deployment', None) or 'cloud'
    if value not in DEPLOYMENTS:
        raise ValueError(f'invalid model deployment: {value!r}')
    return value


def is_local_deployment(value):
    """兼容旧调用：只表示物理本地，不再把 simulated-local 当作安全本地。"""
    return value == 'local'


def is_zero_cost_deployment(value):
    return value in ZERO_COST_DEPLOYMENTS


def allows_sensitive(deployment, privacy):
    if deployment in SENSITIVE_DEPLOYMENTS:
        return True
    return (deployment == 'simulated-local'
            and ('dataMode' not in (privacy or {})
                 or (privacy or {}).get('dataMode') in {'synthetic', 'desensitized'}))


def marginal_pricing(deployment, input_per_1k, cached_per_1k, output_per_1k):
    """本地与模拟本地候选的求解与记账价格。

    本地算力边际成本记 0；模拟本地是云端公开模型冒充本地，研究阶段按 0 计，
    申报价格保留在配置快照与模型声明的 declared_pricing 里供敏感性分析复核。
    """
    if is_zero_cost_deployment(deployment):
        return 0.0, 0.0, 0.0
    return input_per_1k, cached_per_1k, output_per_1k


def local_model_ids(models, privacy=None):
    return tuple(sorted(m.model_id for m in models
                        if allows_sensitive(deployment_of(m), privacy)))


def local_execution_model_ids(models, privacy=None):
    """可作为节点执行者的本地候选：评审与规划器等非候选角色不参与派发。"""
    return tuple(sorted(m.model_id for m in models
                        if allows_sensitive(deployment_of(m), privacy)
                        and getattr(m, 'role', 'candidate') == 'candidate'))


def scan_deterministic(text, sensitive_terms=()):
    """确定性规则 + 团队敏感词表；返回命中的规则名，顺序稳定。"""
    hits = [name for name, pattern in RULES if pattern.search(text)]
    lowered = text.lower()
    hits.extend(f'term:{term}' for term in sensitive_terms if term.lower() in lowered)
    return hits


def classify_view(view, *, privacy, classifier=None, source='static-view'):
    """对节点输入视图分级；返回 S1、S3 或 fail-safe 的 unknown。"""
    privacy = privacy or default_privacy()
    limit = privacy.get('maxPromptBytes', DEFAULT_MAX_PROMPT_BYTES)
    size = len(view.encode())
    row = {'grade': 'S3', 'reasons': [], 'source': source, 'bytes': size}
    if size > limit:
        row.update(grade='unknown', reasons=[f'prompt-bytes:{size}>{limit}'])
        return row
    hits = scan_deterministic(view, privacy.get('sensitiveTerms', ()))
    if hits:
        row.update(grade='S1', reasons=hits)
        return row
    classifier_config = privacy.get('classifier') or {}
    if classifier_config.get('enabled'):
        if classifier is None:
            row.update(grade='unknown', reasons=['classifier-unavailable'])
            return row
        try:
            verdict = classifier(view)
            label = verdict['label'] if isinstance(verdict, dict) else None
            reason = verdict.get('reason') if isinstance(verdict, dict) else None
        except Exception as exc:  # 分类失败一律按未知收窄，不静默放行到云端。
            row.update(grade='unknown', reasons=[f'classifier-failed:{type(exc).__name__}'])
            return row
        if label not in {'public', 'sensitive', 'unknown'}:
            row.update(grade='unknown', reasons=[f'classifier-label:{label!r}'])
            return row
        grade = {'sensitive': 'S1', 'public': 'S3', 'unknown': 'unknown'}[label]
        if grade != 'S3':
            row.update(grade=grade, reasons=[f'classifier:{label}', str(reason or '')[:200]])
        return row
    return row


def static_node_views(plan, task, node_tasks=None):
    """规划期的静态视图：原始任务、节点指令与契约声明。

    上游交接字段的实际内容只有执行期才存在，因此规划期视图不完整；运行期会以
    真实输入视图重新分级，升级为敏感时不会静默派发到云端。
    """
    views = {}
    for node in plan.nodes:
        view = {'node_id': node.node_id,
                'task': node_tasks[node.node_id] if node_tasks else task,
                'instruction': node.prompt_template,
                'contract': plan.contracts.get(node.node_id)}
        views[node.node_id] = json.dumps(view, ensure_ascii=False, sort_keys=True)
    return views


def new_record(privacy, models):
    """放置记录骨架；角色检查与运行期分级都写回同一个记录，便于回放审计。"""
    models = tuple(models)
    policy_version = POLICY_VERSION if privacy and 'dataMode' in privacy else LEGACY_POLICY_VERSION
    return {'policy_version': policy_version, 'enabled': privacy_enabled(privacy),
            'privacy': privacy or default_privacy(), 'status': 'disabled' if not privacy_enabled(privacy) else 'pending',
            'local_model_ids': list(local_model_ids(models, privacy)),
            'local_execution_model_ids': list(local_execution_model_ids(models, privacy)),
            'cloud_model_ids': sorted(m.model_id for m in models
                                      if not allows_sensitive(deployment_of(m), privacy)),
            'grades': {}, 'eligible_models': {}, 'blocked': [],
            'events': [], 'violations': [], 'runtime_grades': {}, 'role_checks': []}


def resolve_placement(*, plan, node_views, models, privacy, classifier=None, record=None):
    """规划期放置判定：分级、候选收窄与显式失败记录。"""
    models = tuple(models)
    record = record if record is not None else new_record(privacy, models)
    if not record['enabled']:
        record['status'] = 'disabled'
        return record
    record['grades'], record['eligible_models'], record['blocked'] = {}, {}, []
    for node in plan.nodes:
        record['grades'][node.node_id] = classify_view(
            node_views.get(node.node_id, ''), privacy=privacy, classifier=classifier,
            source='static-view')
    for node in plan.nodes:
        row = record['grades'][node.node_id]
        if row['grade'] not in NARROWED_GRADES:
            continue
        pool = record.get('local_execution_model_ids', record['local_model_ids'])
        if pool:
            record['eligible_models'][node.node_id] = list(pool)
        else:
            record['blocked'].append({'node_id': node.node_id, 'grade': row['grade'],
                'reasons': row['reasons'],
                'detail': 'no-local-candidate' if not record['local_model_ids'] else 'no-local-execution-candidate'})
    record['status'] = 'no-local-candidate' if record['blocked'] else 'selected'
    return record


def restricted_eligible_models(eligible_models, record):
    """把放置收窄叠加到既有的能力可达候选上，返回按节点合并后的完整映射。

    未命中分级的节点保持原有可行集；交集为空不静默放行，保持空集返回，由调用方
    按显式失败处理（route_nodes 只认映射中的候选，缺失即不可路由）。
    """
    merged = {node_id: list(pool) for node_id, pool in (eligible_models or {}).items()}
    for node_id, allowed in record['eligible_models'].items():
        existing = merged.get(node_id)
        merged[node_id] = sorted(set(allowed) if existing is None else set(allowed) & set(existing))
    return merged


def judge_isolation(record, judge):
    """评审会读到节点输出，因此敏感节点存在时评审同样须落在本地候选。"""
    grades = {**record.get('grades', {}), **record.get('runtime_grades', {})}
    narrowed = sorted(nid for nid, row in grades.items() if row['grade'] in NARROWED_GRADES)
    row = {'required': bool(narrowed), 'nodes': narrowed,
           'judge_model_id': judge.model_id, 'judge_deployment': deployment_of(judge)}
    row['satisfied'] = not narrowed or allows_sensitive(row['judge_deployment'], record.get('privacy'))
    return row


def role_isolation(*, view, privacy, model, role, classifier=None, source='role-view'):
    """规划器与分类器等角色接触敏感输入时，调用同样只允许本地候选。

    分类在调用之前完成，因此不满足时可以在零调用状态下明确失败，不产生外流。
    """
    row = classify_view(view, privacy=privacy, classifier=classifier, source=source)
    row.update(role=role, model_id=model.model_id, deployment=deployment_of(model),
               satisfied=row['grade'] not in NARROWED_GRADES or allows_sensitive(deployment_of(model), privacy))
    return row


def grade_nodes(record, *, nodes, node_views, privacy, classifier=None, source='static-view'):
    """对指定节点（如动态再拆新增的子节点）分级并并入记录，返回收窄后的本地候选。

    已有运行期分级的节点沿用真实输入视图的结论，避免静态视图把敏感节点降级回 S3；
    收窄结果只包含命中分级的节点，交给调用方与能力可达集求交。
    """
    narrowed = {}
    for node in nodes:
        row = record['runtime_grades'].get(node.node_id)
        if row is None:
            row = classify_view(node_views.get(node.node_id, ''), privacy=privacy, classifier=classifier,
                                source=source)
            record['grades'][node.node_id] = row
        if row['grade'] in NARROWED_GRADES:
            narrowed[node.node_id] = list(record.get('local_execution_model_ids', record['local_model_ids']))
    return narrowed


def request_view(messages):
    """节点真实输入视图：用户输入与工具结果；不含网关和模型自身输出。"""
    payload = [message.get('content', '') for message in messages
               if message.get('role') in {'user', 'tool'}]
    return '\n'.join(str(item) for item in payload)


def safe_tool_audit(records, *, privacy):
    """生成不含原文的审计摘要；持久化过程不得再次调用模型分类器。"""
    rows = []
    for record in records:
        call = record.get('call') or {}
        function = call.get('function') or {}
        raw_call = json.dumps(call, ensure_ascii=False, sort_keys=True)
        raw_result = json.dumps(record.get('result'), ensure_ascii=False, sort_keys=True)
        result_grade = classify_view(raw_result, privacy=privacy, classifier=None,
                                     source='tool-result') if 'result' in record else None
        rows.append({'node': record.get('node'), 'status': record.get('status'),
                     'tool_name': function.get('name'), 'call_id': call.get('id'),
                     'call_sha256': hashlib.sha256(raw_call.encode()).hexdigest(),
                     **({'result_sha256': hashlib.sha256(raw_result.encode()).hexdigest(),
                         'result_grade': result_grade} if result_grade is not None else {})})
    return rows


class PrivacyRouteViolation(ValueError):
    """启用约束后仍要派发到云端且没有本地候选时的显式失败。"""


class PlacementGuard:
    """运行期守门：用真实输入视图重新分级，必要时改派本地候选或明确失败。"""

    def __init__(self, record, models, *, classifier=None):
        self.record = record
        self.models = {model.model_id: model for model in models}
        self.privacy = record.get('privacy') or default_privacy()
        self.classifier = classifier

    def evaluate(self, model_id, messages):
        return classify_view(request_view(messages), privacy=self.privacy,
                             classifier=self.classifier, source='runtime-view')

    def allows(self, node_id, model_id, messages):
        model = self.models[model_id]
        if allows_sensitive(deployment_of(model), self.privacy):
            return True
        row = self.evaluate(model_id, messages)
        if row['grade'] not in NARROWED_GRADES:
            return True
        self.record['runtime_grades'].setdefault(node_id, row)
        return False

    def admit(self, node_id, messages, assignments, candidates, eligible=None):
        """返回该节点实际可派发的模型 ID；无本地候选时抛显式失败。

        eligible 为该节点在规划期已经算出的可达候选；提供时改派只在其中挑选，
        避免敏感节点掉到能力或上下文不满足的本地模型上。
        """
        model = candidates[assignments[node_id]]
        row = self.evaluate(model.model_id, messages)
        self.record['runtime_grades'][node_id] = row
        if row['grade'] not in NARROWED_GRADES:
            return model.model_id
        if allows_sensitive(deployment_of(model), self.privacy):
            return model.model_id
        pool = (candidates if eligible is None
                else {mid: candidates[mid] for mid in eligible if mid in candidates})
        choice = self.choose_local(messages, pool)
        if choice is None:
            self.record['violations'].append({'node_id': node_id, 'model_id': model.model_id,
                'grade': row['grade'], 'reasons': row['reasons'], 'action': 'blocked',
                'detail': 'no-local-candidate'})
            raise PrivacyRouteViolation(f'privacy-route-violation:{node_id}:no-local-candidate')
        self.record['events'].append({'node_id': node_id, 'from_model': model.model_id,
            'to_model': choice, 'grade': row['grade'], 'reasons': row['reasons'],
            'action': 'replaced'})
        assignments[node_id] = choice
        return choice

    def require(self, node_id, model_id, messages, *, stage):
        """同一模型续调前重新判定；状态化工具对话不跨信任域迁移，违规即阻断。"""
        model = self.models[model_id]
        row = self.evaluate(model_id, messages)
        self.record['runtime_grades'][node_id] = row
        if row['grade'] not in NARROWED_GRADES or allows_sensitive(deployment_of(model), self.privacy):
            return
        violation = {'node_id': node_id, 'model_id': model_id, 'grade': row['grade'],
                     'reasons': row['reasons'], 'action': 'blocked', 'detail': stage}
        self.record['violations'].append(violation)
        raise PrivacyRouteViolation(f'privacy-route-violation:{node_id}:{stage}')

    def choose_local(self, messages, candidates):
        """在本地候选中挑选工作节点；评审与规划器角色不参与执行派发。"""
        size = len(request_view(messages).encode())
        pool = []
        for model in candidates.values():
            if getattr(model, 'role', 'candidate') != 'candidate':
                continue
            if not allows_sensitive(deployment_of(model), self.privacy):
                continue
            if size + (model.max_output_tokens or 0) > (model.context_window or 0):
                continue
            pool.append(model)
        if not pool:
            return None
        return min(pool, key=lambda m: (m.input_cost_per_1k + m.output_cost_per_1k,
                                        -m.capability, m.model_id)).model_id
