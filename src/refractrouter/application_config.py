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
from .schemas import ModelSpec
from .task_plan import text, validate_plan
from .task_execution import node_messages
from .task_inputs import prepare_inputs

SCHEMA = 'refractagent-providers-v1'
ARK_PLAN_URL = 'https://ark.cn-beijing.volces.com/api/plan/v3'
STRATEGIES = ('economy', 'balanced', 'quality')
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


@dataclass(frozen=True)
class ApplicationModelSpec(ModelSpec):
    token_limit_parameter: str = "max_completion_tokens"
    authentication_required: bool = True


@dataclass(frozen=True)
class ApplicationConfiguration:
    manifest: ModelManifest
    predictions: dict
    quality_min: float
    snapshot: dict


def compile_configuration(raw, strategy=None):
    raw = obj(raw, {'schemaVersion', 'billingUnit', 'providers', 'models', 'qualityMin',
                    'defaultReasoningEffort', 'strategies'}, 'provider configuration')
    if raw.get('schemaVersion') != SCHEMA:
        raise ValueError(f'provider configuration requires schemaVersion {SCHEMA}')
    unit = raw.get('billingUnit')
    if not isinstance(unit, str) or not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,15}', unit):
        raise ValueError('billingUnit must be one declared accounting unit')
    default_effort = None
    if 'defaultReasoningEffort' in raw:
        default_effort = text(raw['defaultReasoningEffort'], 'defaultReasoningEffort', 100)
    strategies = strategy_rows(raw)
    if any('maxAfpCoefficient' in row for row in strategies.values()) and unit != 'AFP':
        raise ValueError('maxAfpCoefficient requires AFP billingUnit')
    scoped = {}
    if strategy is not None:
        if strategy not in STRATEGIES:
            raise ValueError('strategy must be economy, balanced or quality')
        scoped = strategies.get(strategy, {})
    effective_effort = scoped.get('reasoningEffort', default_effort) if strategy is not None else None
    provider_rows = raw.get('providers')
    if not isinstance(provider_rows, list) or not 1 <= len(provider_rows) <= 32:
        raise ValueError('configure between 1 and 32 providers')
    providers = {}
    for row in provider_rows:
        p = obj(row, {'id', 'type', 'baseUrl', 'credentialEnv', 'dshProvider', 'maxTokensParameter'}, 'provider')
        pid = identifier(p.get('id'), 'provider id')
        if pid in providers:
            raise ValueError('provider ids must be unique')
        kind = p.get('type')
        if kind not in {'openai-compatible', 'openai-responses', 'ark-agent-plan', 'dsh'}:
            raise ValueError('provider type must be openai-compatible, openai-responses, ark-agent-plan or dsh')
        if kind == 'dsh':
            if set(p) - {'id', 'type', 'dshProvider'}:
                raise ValueError('DSH providers use host configuration and credentials')
            target = identifier(p.get('dshProvider', pid), 'DSH provider')
            if target == 'refractagent':
                raise ValueError('RefractAgent cannot route recursively to itself')
            providers[pid] = {**p, 'dshProvider': target}
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
        providers[pid] = {**p, 'baseUrl': url, 'maxTokensParameter': parameter}
    model_rows = raw.get('models')
    if not isinstance(model_rows, list) or not 2 <= len(model_rows) <= 65:
        raise ValueError('configure at least one candidate and one judge model')
    models, predictions, model_ids = [], {}, set()
    for row in model_rows:
        m = obj(row, {'id', 'provider', 'model', 'role', 'contextWindow', 'maxOutputTokens',
                     'pricing', 'routing', 'requestOptions', 'jsonMode', 'reasoningEffort'}, 'model')
        mid = identifier(m.get('id'), 'model id')
        if mid in model_ids:
            raise ValueError('model ids must be unique')
        model_ids.add(mid)
        pid = identifier(m.get('provider'), 'model provider')
        if pid not in providers:
            raise ValueError('model references an unknown provider')
        p = providers[pid]
        role = m.get('role', 'candidate')
        if role not in {'candidate', 'judge'}:
            raise ValueError('model role must be candidate or judge')
        api_model = text(m.get('model'), 'API model', 200)
        pricing = obj(m.get('pricing'), {'unit', 'inputPer1k', 'outputPer1k', 'cachedInputPer1k'}, 'pricing')
        if pricing.get('unit') != unit:
            raise ValueError('all model prices must use billingUnit; convert explicitly before combining providers')
        inp = number(pricing.get('inputPer1k'), 'input price')
        out = number(pricing.get('outputPer1k'), 'output price')
        cached = number(pricing.get('cachedInputPer1k', inp), 'cached input price', maximum=inp)
        context = integer(m.get('contextWindow'), 'contextWindow', 1024, 10_000_000)
        output = integer(m.get('maxOutputTokens', 2048), 'maxOutputTokens', 1000,
                         128000 if p['type']=='openai-responses' else 8192)
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
        if role == 'candidate':
            predictions[mid] = compile_routing(m.get('routing'), output)
        elif 'routing' in m:
            raise ValueError('judge model does not need routing predictions')
        models.append(ApplicationModelSpec(model_id=mid, provider=p.get('dshProvider', pid), api_model=api_model,
            role=role, capability=predictions.get(mid, {}).get('quality', 100)/100,
            billing_unit=unit, input_cost_per_1k=inp, cached_input_cost_per_1k=cached,
            output_cost_per_1k=out, base_url=p.get('baseUrl'), api_key_env=p.get('credentialEnv'),
            context_window=context, max_output_tokens=output, snapshot_date=date.today().isoformat(),
            wire_api='dsh-llm' if p['type']=='dsh' else 'responses' if p['type']=='openai-responses' else 'chat-completions',
            request_options=deepcopy(options), json_mode_strategy=json_mode,
            token_limit_parameter=p.get('maxTokensParameter', 'max_completion_tokens'),
            authentication_required=p.get('credentialEnv') is not None))
    if not predictions or sum(m.role=='judge' for m in models) != 1:
        raise ValueError('configure at least one candidate and exactly one judge')
    candidate_ids = {m.model_id for m in models if m.role == 'candidate'}
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
    return ApplicationConfiguration(ModelManifest(SCHEMA, date.today().isoformat(), unit, tuple(models)),
        predictions, number(raw.get('qualityMin', 0), 'qualityMin', maximum=100), deepcopy(raw))


def prepare_configured_plan(request, context, *, explicit_plan, output_cap, input_cap=131072):
    """Size generated plans for the input; explicit user contracts stay authoritative."""
    if explicit_plan:
        return
    raw = deepcopy(request['plan'])
    _, task, _ = prepare_inputs(request, context)
    plan = validate_plan(raw)
    for node in raw['nodes']:
        spec = next(n for n in plan.nodes if n.node_id==node['node_id'])
        contract = node['contract']
        upstream = {parent: {field: '' for field in info['fields']} for parent,info in contract['inputs'].items()}
        # Sizing must measure the real envelope before the budget is rewritten;
        # the template's initial budget is not a limit for this measurement.
        messages = node_messages(task, spec, contract, upstream, check_input_budget=False)
        size = len(json.dumps(messages).encode()) + 512 + len(spec.parents)*output_cap*8
        contract['capability']['input_budget_tokens'] = max(256, min(input_cap, size))
    request['plan'] = validate_plan(raw).to_dict()
