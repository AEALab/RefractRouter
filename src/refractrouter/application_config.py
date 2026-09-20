"""User-owned provider/model configuration for the installed application.

This compiles configuration into the existing Python manifest and routing profile.
Configured predictions have zero observations and are never empirical evidence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
import re
from urllib.parse import urlsplit

from .configured_routing import compile_routing, configured_profile
from .manifest import ModelManifest
from .node_routing import number
from .privacy_placement import (DEPLOYMENTS, ZERO_COST_DEPLOYMENTS, MAX_MAX_PROMPT_BYTES,
                                MAX_SENSITIVE_TERMS, MAX_SENSITIVE_TERM_CHARS, MIN_MAX_PROMPT_BYTES,
                                DEFAULT_MAX_PROMPT_BYTES, allows_sensitive, default_privacy, marginal_pricing)
from .schemas import ModelSpec
from .task_plan import text, validate_plan
from .task_execution import node_messages
from .task_inputs import prepare_inputs

SCHEMA_V1 = 'refractagent-providers-v1'
SCHEMA_V2 = 'refractagent-providers-v2'
SCHEMA_V3 = 'refractagent-providers-v3'
SCHEMA_V4 = 'refractagent-providers-v4'
SCHEMA = SCHEMA_V1
SCHEMAS = (SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4)
ARK_PLAN_URL = 'https://ark.cn-beijing.volces.com/api/plan/v3'
STRATEGIES = ('economy', 'balanced', 'quality')
V4_ROLES = ('planner', 'worker', 'judge', 'classifier')
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$')
_ENV = re.compile(r'^[A-Z][A-Z0-9_]*$')


def obj(value, fields, label):
    if not isinstance(value, dict) or set(value) - fields:
        raise ValueError(f'invalid {label} fields')
    return value


def identifier(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f'invalid {label}')
    return value


def integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'invalid {label}')
    return value


def strategy_rows(raw):
    """Validate optional per-strategy overrides shared by all three presets."""
    strategies = raw.get('strategies')
    if strategies is None:
        return {}
    if not isinstance(strategies, dict) or set(strategies) - set(STRATEGIES):
        raise ValueError('strategies may only configure economy, balanced and quality')
    rows = {}
    for name, row in strategies.items():
        if not isinstance(row, dict) or set(row) - {'reasoningEffort', 'models', 'maxAfpCoefficient'}:
            raise ValueError(f'invalid {name} strategy fields')
        entry = {}
        if 'maxAfpCoefficient' in row:
            entry['maxAfpCoefficient'] = number(row['maxAfpCoefficient'], f'{name} maxAfpCoefficient', positive=True)
        if 'reasoningEffort' in row:
            entry['reasoningEffort'] = text(row['reasoningEffort'], f'{name} reasoningEffort', 100)
        if 'models' in row:
            ids = row['models']
            if (not isinstance(ids, list) or not ids or len(set(ids)) != len(ids)
                    or any(not isinstance(value, str) for value in ids)):
                raise ValueError(f'{name} models must be a non-empty list of unique model ids')
            entry['models'] = ids
        rows[name] = entry
    return rows


def apply_reasoning_effort(effort, options, provider_type, *, label):
    """Map an effort onto the provider's native request options."""
    native = options.setdefault('reasoning', {}) if provider_type == 'openai-responses' else options
    key = 'effort' if provider_type == 'openai-responses' else 'reasoning_effort'
    if key in native and native[key] != effort:
        raise ValueError(f'{label} conflicts with requestOptions')
    native[key] = effort
    return options


def has_request_effort(options, provider_type):
    if provider_type == 'openai-responses':
        return isinstance(options.get('reasoning'), dict) and 'effort' in options['reasoning']
    return 'reasoning_effort' in options


def deployment_value(value, *, provider_deployment, schema_version, label):
    """模型行部署域：缺省继承 provider 行；本地 provider 不允许把模型改回云端。"""
    if value is None:
        return provider_deployment
    if schema_version not in {SCHEMA_V2, SCHEMA_V3, SCHEMA_V4}:
        raise ValueError(f'{label} requires schemaVersion {SCHEMA_V2}, {SCHEMA_V3} or {SCHEMA_V4}')
    if value not in DEPLOYMENTS:
        raise ValueError(f'invalid {label}')
    if provider_deployment in ZERO_COST_DEPLOYMENTS and value in {'cloud', 'external-cloud', 'trusted-cloud'}:
        raise ValueError(f'{label}: a local provider cannot declare cloud models')
    return value


def compile_privacy(raw, *, models, schema_version, require_local_candidate=True,
                    enforce_zero_cost_classifier=True):
    """编译可选的隐私约束；未配置时返回关闭形态，路由行为与现状一致。"""
    if raw is None:
        return default_privacy()
    if schema_version != SCHEMA_V2:
        raise ValueError(f'privacy requires schemaVersion {SCHEMA_V2}')
    if not isinstance(raw, dict) or set(raw) - {'enabled', 'sensitiveTerms', 'classifier', 'maxPromptBytes'}:
        raise ValueError('invalid privacy fields')
    enabled = raw.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('privacy.enabled must be a boolean')
    terms = raw.get('sensitiveTerms', [])
    if (not isinstance(terms, list) or len(terms) > MAX_SENSITIVE_TERMS or len(set(map(str, terms))) != len(terms)
            or any(not isinstance(term, str) or not 0 < len(term) <= MAX_SENSITIVE_TERM_CHARS for term in terms)):
        raise ValueError('privacy.sensitiveTerms must be unique non-empty strings within configuration limits')
    classifier = raw.get('classifier', {})
    if not isinstance(classifier, dict) or set(classifier) - {'enabled', 'modelId'}:
        raise ValueError('invalid privacy.classifier fields')
    classifier_enabled = classifier.get('enabled', False)
    if not isinstance(classifier_enabled, bool):
        raise ValueError('privacy.classifier.enabled must be a boolean')
    model_id = classifier.get('modelId')
    if model_id is not None:
        model_id = identifier(model_id, 'privacy.classifier.modelId')
        target = next((model for model in models if model.model_id == model_id), None)
        if target is None:
            raise ValueError('privacy.classifier.modelId must reference a configured model')
        if enforce_zero_cost_classifier and target.deployment not in ZERO_COST_DEPLOYMENTS:
            raise ValueError('privacy.classifier.modelId must reference a local or simulated-local model')
    elif classifier_enabled:
        raise ValueError('privacy.classifier.modelId is required when the local classifier is enabled')
    limit = raw.get('maxPromptBytes', DEFAULT_MAX_PROMPT_BYTES)
    if type(limit) is not int or not MIN_MAX_PROMPT_BYTES <= limit <= MAX_MAX_PROMPT_BYTES:
        raise ValueError('privacy.maxPromptBytes is out of range')
    if enabled and require_local_candidate and not any(model.deployment in ZERO_COST_DEPLOYMENTS and model.role == 'candidate'
                           for model in models):
        raise ValueError('privacy requires at least one local or simulated-local candidate model')
    return {'enabled': enabled, 'sensitiveTerms': list(terms),
            'classifier': {'enabled': classifier_enabled, 'modelId': model_id},
            'maxPromptBytes': limit}


def compile_security(raw, *, models):
    """编译 v3 强制安全合同；安全可行性不可由质量、费用或时延抵消。"""
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {'dataMode', 'sensitiveTerms', 'classifier', 'maxPromptBytes'}:
        raise ValueError('invalid security fields')
    data_mode = raw.get('dataMode', 'live')
    if data_mode not in {'live', 'synthetic', 'desensitized'}:
        raise ValueError('security.dataMode must be live, synthetic or desensitized')
    compatibility = {'enabled': True, 'sensitiveTerms': raw.get('sensitiveTerms', []),
                     'classifier': raw.get('classifier', {}),
                     'maxPromptBytes': raw.get('maxPromptBytes', DEFAULT_MAX_PROMPT_BYTES)}
    compiled = compile_privacy(compatibility, models=models, schema_version=SCHEMA_V2,
                               require_local_candidate=False, enforce_zero_cost_classifier=False)
    compiled['dataMode'] = data_mode
    classifier_id = compiled['classifier'].get('modelId')
    if classifier_id is not None:
        classifier_model = next(model for model in models if model.model_id == classifier_id)
        if not allows_sensitive(classifier_model.deployment, compiled):
            raise ValueError('security.classifier.modelId must reference a local or trusted-cloud model')
    if not any(model.role == 'candidate' and allows_sensitive(model.deployment, compiled) for model in models):
        raise ValueError('security requires at least one local or trusted-cloud candidate; simulated-local is allowed only for synthetic or desensitized data')
    return compiled


@dataclass(frozen=True)
class ApplicationModelSpec(ModelSpec):
    token_limit_parameter: str = "max_completion_tokens"
    authentication_required: bool = True
    declared_pricing: dict | None = None
    # deployment 只属于 providerConfig 行；不放进 ModelSpec，避免改动模型清单的冻结摘要。
    deployment: str = "cloud"
    # v4 职责是配置合同，不覆盖旧 manifest 的 candidate/judge 兼容字段。
    roles: tuple[str, ...] = ()
    trust_policy: str | None = None


@dataclass(frozen=True)
class ExecutionModelSpec(ApplicationModelSpec):
    unrestricted_execution_output: bool = True


def execution_capacity_model(model):
    """应用执行节点使用已知模型容量；未知供应商遵循用户声明，保留历史模型类型。"""
    from dataclasses import fields
    from .ark_plan import catalog
    capacity = model.max_output_tokens
    if model.base_url == ARK_PLAN_URL:
        entry = next((m for m in catalog()['models'] if m['model_id'] == model.api_model), None)
        if entry:
            capacity = entry['max_output_tokens']
    values = {f.name: getattr(model, f.name) for f in fields(ApplicationModelSpec) if hasattr(model, f.name)}
    return ExecutionModelSpec(**{**values, 'max_output_tokens': capacity})


@dataclass(frozen=True)
class ApplicationConfiguration:
    manifest: ModelManifest
    predictions: dict
    quality_min: float
    snapshot: dict
    privacy: dict | None = None
    objective: dict | None = None
    role_pools: dict | None = None


def compile_v4_objective(raw):
    """验证 v4 的单一自动路由目标；安全和质量门槛不是可交换权重。"""
    objective = obj(raw, {'qualityMin', 'primary', 'secondary', 'dagMode'}, 'objective')
    quality = number(objective.get('qualityMin'), 'objective.qualityMin', maximum=100)
    if objective.get('primary') != 'cost' or objective.get('secondary') != 'latency':
        raise ValueError('v4 objective must optimize cost first and latency second')
    if objective.get('dagMode') not in {'auto', 'never', 'force'}:
        raise ValueError('objective.dagMode must be auto, never or force')
    return {**objective, 'qualityMin': quality}


def migrate_v3_to_v4(raw, *, planner_model_id=None):
    """显式迁移 v3 配置；返回新对象，不改写来源或推断部署、价格和能力。"""
    if not isinstance(raw, dict) or raw.get('schemaVersion') != SCHEMA_V3:
        raise ValueError(f'migration requires schemaVersion {SCHEMA_V3}')
    migrated = deepcopy(raw)
    migrated['schemaVersion'] = SCHEMA_V4
    migrated['objective'] = {
        'qualityMin': migrated.pop('qualityMin', 80), 'primary': 'cost',
        'secondary': 'latency', 'dagMode': 'auto',
    }
    migrated.pop('strategies', None)
    classifier_id = ((migrated.get('security') or {}).get('classifier') or {}).get('modelId')
    planner_id = planner_model_id or migrated.pop('plannerModelId', None)
    if planner_id is None:
        raise ValueError('v3 to v4 migration requires an explicit planner model id')
    if planner_id not in {model.get('id') for model in migrated.get('models', [])}:
        raise ValueError('planner model id must reference a configured model')
    for model in migrated.get('models', []):
        role = model.pop('role', 'candidate')
        roles = ['worker'] if role == 'candidate' else ['judge']
        if model.get('id') == planner_id and 'planner' not in roles:
            roles.append('planner')
        if model.get('id') == classifier_id and 'classifier' not in roles:
            roles.append('classifier')
        model['roles'] = roles
    return migrated


def compile_security_v4(raw, *, models, policies):
    """编译 v4 安全合同，并把 simulated-local 的真实外传授权写入审计快照。"""
    raw = {} if raw is None else raw
    if not isinstance(raw, dict) or set(raw) - {'dataMode', 'sensitiveTerms', 'classifier', 'maxPromptBytes'}:
        raise ValueError('invalid security fields')
    data_mode = raw.get('dataMode', 'live')
    if data_mode not in {'live', 'synthetic', 'desensitized'}:
        raise ValueError('security.dataMode must be live, synthetic or desensitized')
    compatibility = {'enabled': True, 'sensitiveTerms': raw.get('sensitiveTerms', []),
                     'classifier': raw.get('classifier', {}),
                     'maxPromptBytes': raw.get('maxPromptBytes', DEFAULT_MAX_PROMPT_BYTES)}
    compiled = compile_privacy(compatibility, models=models, schema_version=SCHEMA_V2,
                               require_local_candidate=False, enforce_zero_cost_classifier=False)
    compiled['dataMode'] = data_mode
    simulated = [model for model in models if model.deployment == 'simulated-local']
    acknowledged = all(
        model.trust_policy in policies
        and policies[model.trust_policy].get('allowsSensitiveData') is True
        and policies[model.trust_policy].get('acknowledgeExternalTransmission') is True
        for model in simulated
    )
    compiled['allowSimulatedLocalSensitive'] = bool(simulated and acknowledged)
    compiled['simulatedLocalExternalTransmissionAcknowledged'] = bool(simulated and acknowledged)
    if data_mode == 'live' and simulated and not acknowledged:
        raise ValueError('live simulated-local requires an explicit sensitive-data trust policy and acknowledgeExternalTransmission')
    classifier_id = compiled['classifier'].get('modelId')
    if classifier_id is not None:
        classifier_model = next(model for model in models if model.model_id == classifier_id)
        if 'classifier' not in classifier_model.roles:
            raise ValueError('security.classifier.modelId must reference a classifier model')
        if not allows_sensitive(classifier_model.deployment, compiled):
            raise ValueError('security.classifier.modelId must reference a local, trusted-cloud or authorized simulated-local model')
    for role in ('planner', 'worker', 'judge'):
        if not any(role in model.roles and allows_sensitive(model.deployment, compiled) for model in models):
            raise ValueError(f'security requires at least one sensitive-data-capable {role} model')
    return compiled


def compile_configuration(raw, strategy=None):
    raw = obj(raw, {'schemaVersion', 'billingUnit', 'providers', 'models', 'qualityMin',
                    'defaultReasoningEffort', 'plannerThinking', 'strategies', 'privacy',
                    'security', 'trustPolicies', 'objective'},
              'provider configuration')
    schema_version = raw.get('schemaVersion')
    if schema_version not in SCHEMAS:
        raise ValueError('provider configuration requires a supported schemaVersion')
    if schema_version in {SCHEMA_V3, SCHEMA_V4} and 'privacy' in raw:
        raise ValueError(f'schemaVersion {schema_version} uses security instead of the optional privacy switch')
    if schema_version not in {SCHEMA_V3, SCHEMA_V4} and ({'security', 'trustPolicies'} & set(raw)):
        raise ValueError(f'security and trustPolicies require schemaVersion {SCHEMA_V3} or {SCHEMA_V4}')
    if schema_version == SCHEMA_V4:
        if 'objective' not in raw:
            raise ValueError('schemaVersion v4 requires objective')
        if {'qualityMin', 'strategies'} & set(raw):
            raise ValueError('schemaVersion v4 uses objective and does not expose legacy strategies')
    elif 'objective' in raw:
        raise ValueError(f'objective requires schemaVersion {SCHEMA_V4}')
    objective = compile_v4_objective(raw['objective']) if schema_version == SCHEMA_V4 else None
    policies = {}
    for policy in raw.get('trustPolicies', []):
        fields = ({'id', 'residency', 'auditLogging', 'allowsSensitiveData', 'expiresOn',
                   'acknowledgeExternalTransmission'} if schema_version == SCHEMA_V4 else
                  {'id', 'residency', 'auditLogging', 'allowsSensitiveData'})
        policy = obj(policy, fields, 'trust policy')
        policy_id = identifier(policy.get('id'), 'trust policy id')
        if policy_id in policies:
            raise ValueError('trust policy ids must be unique')
        if policy.get('allowsSensitiveData') is not True or policy.get('auditLogging') is not True:
            raise ValueError('trusted-cloud policy must explicitly allow sensitive data and audit logging')
        residency = text(policy.get('residency'), 'trust policy residency', 100)
        if 'acknowledgeExternalTransmission' in policy and not isinstance(policy['acknowledgeExternalTransmission'], bool):
            raise ValueError('trust policy acknowledgeExternalTransmission must be a boolean')
        if policy.get('expiresOn') is not None:
            try:
                expires = date.fromisoformat(policy['expiresOn'])
            except (TypeError, ValueError):
                raise ValueError('trust policy expiresOn must be an ISO date') from None
            if expires < date.today():
                raise ValueError('trust policy is expired')
        policies[policy_id] = {**policy, 'residency': residency}
    unit = raw.get('billingUnit')
    if not isinstance(unit, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,15}', unit):
        raise ValueError('billingUnit must be one declared accounting unit')
    if raw.get('plannerThinking', 'inherit') not in {'inherit', 'enabled', 'disabled'}:
        raise ValueError('invalid plannerThinking')
    default_effort = None
    if 'defaultReasoningEffort' in raw:
        default_effort = text(raw['defaultReasoningEffort'], 'defaultReasoningEffort', 100)
    strategies = {} if schema_version == SCHEMA_V4 else strategy_rows(raw)
    if any('maxAfpCoefficient' in row for row in strategies.values()) and unit != 'AFP':
        raise ValueError('maxAfpCoefficient requires AFP billingUnit')
    scoped = {}
    if strategy is not None:
        allowed = ('auto',) if schema_version == SCHEMA_V4 else STRATEGIES
        if strategy not in allowed:
            raise ValueError('v4 strategy must be auto' if schema_version == SCHEMA_V4 else
                             'strategy must be economy, balanced or quality')
        scoped = strategies.get(strategy, {})
    effective_effort = scoped.get('reasoningEffort', default_effort) if strategy is not None else None
    provider_rows = raw.get('providers')
    if not isinstance(provider_rows, list) or not 1 <= len(provider_rows) <= 32:
        raise ValueError('configure between 1 and 32 providers')
    providers = {}
    for row in provider_rows:
        p = obj(row, {'id', 'type', 'baseUrl', 'credentialEnv', 'dshProvider', 'maxTokensParameter',
                      'deployment', 'trustPolicy'}, 'provider')
        pid = identifier(p.get('id'), 'provider id')
        if pid in providers:
            raise ValueError('provider ids must be unique')
        if schema_version in {SCHEMA_V3, SCHEMA_V4} and 'deployment' not in p:
            raise ValueError(f'schemaVersion {schema_version} requires an explicit provider deployment')
        provider_deployment = p.get('deployment', 'cloud')
        if 'deployment' in p and schema_version not in {SCHEMA_V2, SCHEMA_V3, SCHEMA_V4}:
            raise ValueError(f'deployment requires schemaVersion {SCHEMA_V2}, {SCHEMA_V3} or {SCHEMA_V4}')
        if provider_deployment not in DEPLOYMENTS:
            raise ValueError('invalid provider deployment')
        trust_policy = p.get('trustPolicy')
        if trust_policy is not None:
            if schema_version not in {SCHEMA_V3, SCHEMA_V4}:
                raise ValueError(f'trustPolicy requires schemaVersion {SCHEMA_V3} or {SCHEMA_V4}')
            trust_policy = identifier(trust_policy, 'provider trustPolicy')
        if provider_deployment == 'trusted-cloud':
            if trust_policy not in policies:
                raise ValueError('trusted-cloud requires a configured trustPolicy')
        elif provider_deployment == 'simulated-local' and schema_version == SCHEMA_V4:
            if raw.get('security', {}).get('dataMode', 'live') == 'live' and trust_policy not in policies:
                raise ValueError('live simulated-local requires a configured trustPolicy')
        elif trust_policy is not None:
            raise ValueError('trustPolicy is only valid for trusted-cloud or v4 simulated-local providers')
        kind = p.get('type')
        if kind not in {'openai-compatible', 'openai-responses', 'ark-agent-plan', 'dsh'}:
            raise ValueError('provider type must be openai-compatible, openai-responses, ark-agent-plan or dsh')
        if kind == 'dsh':
            if set(p) - {'id', 'type', 'dshProvider', 'deployment', 'trustPolicy'}:
                raise ValueError('DSH providers use host configuration and credentials')
            target = identifier(p.get('dshProvider', pid), 'DSH provider')
            if target == 'refractagent':
                raise ValueError('RefractAgent cannot route recursively to itself')
            providers[pid] = {**p, 'dshProvider': target, 'deployment': provider_deployment}
            continue
        if 'dshProvider' in p:
            raise ValueError('dshProvider requires type dsh')
        key = p.get('credentialEnv')
        if key is not None and (not isinstance(key, str) or not _ENV.fullmatch(key)):
            raise ValueError('HTTP providers require a credentialEnv reference, never a key value')
        url = p.get('baseUrl', ARK_PLAN_URL if kind == 'ark-agent-plan' else
                    'https://api.openai.com/v1' if kind == 'openai-responses' else None)
        if not isinstance(url, str) or not url:
            raise ValueError('HTTP providers require baseUrl')
        parsed = urlsplit(url)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or any(c.isspace() for c in url)):
            raise ValueError('baseUrl must be an HTTP(S) API root without credentials, query or fragment')
        url = url.rstrip('/')
        if kind == 'ark-agent-plan' and url != ARK_PLAN_URL:
            raise ValueError('Ark Agent Plan requires its /api/plan/v3 endpoint')
        if kind == 'openai-responses' and 'maxTokensParameter' in p:
            raise ValueError('Responses uses max_output_tokens; omit maxTokensParameter')
        parameter = p.get('maxTokensParameter', 'max_completion_tokens')
        if parameter not in {'max_tokens', 'max_completion_tokens'}:
            raise ValueError('invalid maxTokensParameter')
        providers[pid] = {**p, 'baseUrl': url, 'maxTokensParameter': parameter,
                          'deployment': provider_deployment}
    model_rows = raw.get('models')
    if not isinstance(model_rows, list) or not 2 <= len(model_rows) <= 65:
        raise ValueError('configure at least two models with the required execution roles')
    models, predictions, model_ids = [], {}, set()
    for row in model_rows:
        m = obj(row, {'id', 'provider', 'model', 'role', 'roles', 'contextWindow', 'maxOutputTokens',
                     'pricing', 'routing', 'requestOptions', 'jsonMode', 'reasoningEffort',
                     'deployment'}, 'model')
        mid = identifier(m.get('id'), 'model id')
        if mid in model_ids:
            raise ValueError('model ids must be unique')
        model_ids.add(mid)
        pid = identifier(m.get('provider'), 'model provider')
        if pid not in providers:
            raise ValueError('model references an unknown provider')
        p = providers[pid]
        if schema_version == SCHEMA_V4:
            if 'role' in m:
                raise ValueError('schemaVersion v4 uses roles instead of role')
            roles = m.get('roles')
            if (not isinstance(roles, list) or not roles or len(roles) != len(set(roles))
                    or any(role not in V4_ROLES for role in roles)):
                raise ValueError('v4 model roles must be a non-empty unique subset of planner, worker, judge and classifier')
            roles = tuple(roles)
            # 旧执行器只识别 candidate/judge；完整职责池另存于 roles，judge 优先保证评审隔离。
            role = 'judge' if 'judge' in roles else 'candidate' if 'worker' in roles else roles[0]
        else:
            if 'roles' in m:
                raise ValueError('model roles require schemaVersion v4')
            role = m.get('role', 'candidate')
            if role not in {'candidate', 'judge'}:
                raise ValueError('model role must be candidate or judge')
            roles = ('worker',) if role == 'candidate' else ('judge',)
        api_model = text(m.get('model'), 'API model', 200)
        pricing = obj(m.get('pricing'), {'unit', 'inputPer1k', 'outputPer1k', 'cachedInputPer1k'}, 'pricing')
        if pricing.get('unit') != unit:
            raise ValueError('all model prices must use billingUnit; convert explicitly before combining providers')
        inp = number(pricing.get('inputPer1k'), 'input price')
        out = number(pricing.get('outputPer1k'), 'output price')
        cached = number(pricing.get('cachedInputPer1k', inp), 'cached input price', maximum=inp)
        deployment = deployment_value(m.get('deployment'),
                                      provider_deployment=p.get('deployment', 'cloud'),
                                      schema_version=schema_version, label=f'{mid} deployment')
        effective = marginal_pricing(deployment, inp, cached, out)
        # 本地与模拟本地按边际成本 0 参与求解与记账；申报价保留供敏感性分析复核。
        declared = (None if effective == (inp, cached, out) else
                    {'unit': unit, 'inputPer1k': inp, 'outputPer1k': out, 'cachedInputPer1k': cached})
        context = integer(m.get('contextWindow'), 'contextWindow', 1024, 10_000_000)
        output = integer(m.get('maxOutputTokens', 2048), 'maxOutputTokens', 1000,
                         10_000_000)
        if context <= output:
            raise ValueError('contextWindow must leave space for model input')
        options = deepcopy(m.get('requestOptions', {}))
        allowed_options = ({'reasoning', 'text', 'temperature', 'top_p'} if p['type']=='openai-responses'
                           else {'temperature', 'top_p', 'thinking', 'reasoning_effort', 'seed'})
        obj(options, allowed_options, 'requestOptions')
        if 'reasoning' in options:
            reasoning = obj(options['reasoning'], {'effort', 'summary'}, 'Responses reasoning')
            if 'effort' in reasoning:
                text(reasoning['effort'], 'reasoning.effort', 100)
            if 'summary' in reasoning and reasoning['summary'] not in {'auto', 'concise', 'detailed'}:
                raise ValueError('invalid reasoning.summary')
        if 'text' in options:
            text_options = obj(options['text'], {'verbosity'}, 'Responses text')
            if text_options.get('verbosity') not in {'low', 'medium', 'high'}:
                raise ValueError('invalid text.verbosity')
        for key in ('temperature', 'top_p'):
            if key in options:
                number(options[key], key, maximum=2 if key=='temperature' else 1)
        if 'thinking' in options:
            thinking = obj(options['thinking'], {'type'}, 'thinking')
            if thinking.get('type') not in {'enabled', 'disabled', 'auto'}:
                raise ValueError('invalid thinking mode')
            if p['type'] == 'ark-agent-plan':
                from .ark_plan import validate_thinking_auto
                validate_thinking_auto(api_model, options)
        if 'reasoning_effort' in options:
            text(options['reasoning_effort'], 'reasoning_effort', 100)
        if 'seed' in options and type(options['seed']) is not int:
            raise ValueError('seed must be an integer')
        if len(json.dumps(options, allow_nan=False)) > 4096:
            raise ValueError('requestOptions exceeds configuration limit')
        json_mode = m.get('jsonMode', 'json-object-hint')
        if json_mode not in {'json-object-hint', 'prompt-only'}:
            raise ValueError('jsonMode must be json-object-hint or prompt-only')
        if p['type'] == 'dsh' and set(options) - {'temperature', 'reasoning_effort'}:
            raise ValueError('DSH model options support temperature and reasoning_effort')
        if 'reasoningEffort' in m:
            apply_reasoning_effort(text(m['reasoningEffort'], 'reasoningEffort', 100), options, p['type'],
                                   label='reasoningEffort')
        elif effective_effort is not None and not has_request_effort(options, p['type']):
            apply_reasoning_effort(effective_effort, options, p['type'], label='default reasoning effort')
        if 'worker' in roles:
            predictions[mid] = compile_routing(m.get('routing'), output)
        elif 'routing' in m:
            raise ValueError('only worker models use routing predictions')
        models.append(ApplicationModelSpec(model_id=mid, provider=p.get('dshProvider', pid), api_model=api_model,
            role=role, capability=predictions.get(mid, {}).get('quality', 100)/100,
            billing_unit=unit, input_cost_per_1k=effective[0], cached_input_cost_per_1k=effective[1],
            output_cost_per_1k=effective[2], deployment=deployment, declared_pricing=declared,
            base_url=p.get('baseUrl'), api_key_env=p.get('credentialEnv'),
            context_window=context, max_output_tokens=output, snapshot_date=date.today().isoformat(),
            wire_api='dsh-llm' if p['type']=='dsh' else 'responses' if p['type']=='openai-responses' else 'chat-completions',
            request_options=deepcopy(options), json_mode_strategy=json_mode,
            token_limit_parameter=p.get('maxTokensParameter', 'max_completion_tokens'),
            authentication_required=p.get('credentialEnv') is not None,
            roles=roles, trust_policy=p.get('trustPolicy')))
    if schema_version == SCHEMA_V4:
        for required in ('planner', 'worker', 'judge'):
            if not any(required in model.roles for model in models):
                raise ValueError(f'v4 requires at least one {required} model')
        if sum('judge' in model.roles for model in models) != 1:
            raise ValueError('v4 currently requires exactly one judge model')
    elif not predictions or sum(m.role=='judge' for m in models) != 1:
        raise ValueError('configure at least one candidate and exactly one judge')
    # 隐私约束在策略收窄之前编译，分类器引用与本地候选要求按声明的完整模型池判定。
    privacy = (compile_security_v4(raw.get('security'), models=tuple(models), policies=policies)
               if schema_version == SCHEMA_V4 else
               compile_security(raw.get('security'), models=tuple(models)) if schema_version == SCHEMA_V3
               else compile_privacy(raw.get('privacy'), models=tuple(models), schema_version=schema_version))
    candidate_ids = {m.model_id for m in models if 'worker' in m.roles}
    for name, row in strategies.items():
        unknown = set(row.get('models', ())) - candidate_ids
        if unknown:
            raise ValueError(f'{name} models must reference candidate models: {sorted(unknown)}')
    if strategy is not None and 'models' in scoped:
        pool = set(scoped['models'])
        models = [m for m in models if m.role != 'candidate' or m.model_id in pool]
        predictions = {mid: row for mid, row in predictions.items() if mid in pool}
    if 'maxAfpCoefficient' in scoped:
        ceiling = scoped['maxAfpCoefficient']
        models = [m for m in models if m.role != 'candidate'
                  or max(m.input_cost_per_1k, m.output_cost_per_1k) * 10 <= ceiling + 1e-10]
        pool = {m.model_id for m in models if m.role == 'candidate'}
        if not pool:
            raise ValueError('AFP ceiling and selected models leave no candidate model')
        predictions = {mid: row for mid, row in predictions.items() if mid in pool}
    return ApplicationConfiguration(ModelManifest(schema_version, date.today().isoformat(), unit, tuple(models)),
        predictions, objective['qualityMin'] if objective else number(raw.get('qualityMin', 0), 'qualityMin', maximum=100),
        deepcopy(raw), privacy=privacy if schema_version in {SCHEMA_V3, SCHEMA_V4} or raw.get('privacy') is not None else None,
        objective=objective,
        role_pools={role: tuple(model.model_id for model in models if role in model.roles)
                    for role in V4_ROLES} if schema_version == SCHEMA_V4 else None)


def prepare_configured_plan(request, context, *, explicit_plan, output_cap, input_cap=131072):
    """Size generated plans for the input; explicit user contracts stay authoritative."""
    if explicit_plan:
        return
    raw = deepcopy(request['plan'])
    _, task, _ = prepare_inputs(request, context, for_node=True)
    plan = validate_plan(raw)
    for node in raw['nodes']:
        spec = next(n for n in plan.nodes if n.node_id==node['node_id'])
        contract = node['contract']
        upstream = {parent: {field: '' for field in info['fields']} for parent,info in contract['inputs'].items()}
        # Sizing must measure the real envelope before the budget is rewritten;
        # the template's initial budget is not a limit for this measurement.
        messages = node_messages(task, spec, contract, upstream, check_input_budget=False, prefix_policy=request.get("prefixPolicy", "legacy"))
        size = len(json.dumps(messages).encode()) + 512 + len(spec.parents)*output_cap*8
        contract['capability']['input_budget_tokens'] = max(256, min(input_cap, size))
    request['plan'] = validate_plan(raw).to_dict()
