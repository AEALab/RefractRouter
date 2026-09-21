"""#112 安全基准的真实模型绑定合同；只做静态审计，不创建模型客户端。"""
from __future__ import annotations

from copy import deepcopy
import re

from .security_benchmark import digest, validate_protocol


SCHEMA = 'security-benchmark-bindings-v1'
STATUSES = {'bound', 'blocked'}
DEPLOYMENTS = {'local', 'trusted-cloud', 'external-cloud', 'simulated-local'}
SOURCE_KINDS = {'official-documentation', 'frozen-catalog', 'frozen-manifest',
                'operator-attestation'}
PROFILE_PROVENANCE = {'frozen-public-profile', 'protocol-prior',
                      'user-declared-uncalibrated'}
ENV_NAME = re.compile(r'^[A-Z][A-Z0-9_]*$')


def _record(value, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _keys(value, expected, label):
    if set(value) != set(expected):
        raise ValueError(f'invalid {label} fields')


def _number(value, label, *, maximum=None):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f'invalid {label}')
    if maximum is not None and value > maximum:
        raise ValueError(f'invalid {label}')
    return float(value)


def _validate_sources(raw):
    sources = {}
    for row in raw:
        row = _record(row, 'binding source')
        _keys(row, {'id', 'kind', 'uri', 'retrievedAt', 'sha256'}, 'binding source')
        if (not isinstance(row['id'], str) or not row['id'] or row['id'] in sources
                or row['kind'] not in SOURCE_KINDS or not isinstance(row['uri'], str)
                or not row['uri'] or not isinstance(row['retrievedAt'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', row['sha256'])):
            raise ValueError('invalid or duplicate binding source')
        sources[row['id']] = deepcopy(row)
    if not sources:
        raise ValueError('binding inventory requires sources')
    return sources


def _validate_endpoints(raw):
    endpoints = {}
    for row in raw:
        row = _record(row, 'endpoint policy')
        _keys(row, {'id', 'provider', 'type', 'baseUrl', 'credentialEnv', 'region',
                    'trustPolicyId'}, 'endpoint policy')
        if (not isinstance(row['id'], str) or not row['id'] or row['id'] in endpoints
                or not isinstance(row['provider'], str) or not row['provider']
                or row['type'] not in {'openai-compatible', 'dsh', 'local'}
                or not isinstance(row['baseUrl'], str) or not row['baseUrl']
                or not isinstance(row['credentialEnv'], str)
                or (row['credentialEnv'] and not ENV_NAME.fullmatch(row['credentialEnv']))
                or not isinstance(row['region'], str) or not row['region']
                or (row['trustPolicyId'] is not None
                    and (not isinstance(row['trustPolicyId'], str) or not row['trustPolicyId']))):
            raise ValueError('invalid or duplicate endpoint policy')
        if not (row['baseUrl'].startswith('https://')
                or row['baseUrl'].startswith('http://127.0.0.1:')
                or row['baseUrl'].startswith('http://localhost:')):
            raise ValueError('endpoint policy requires HTTPS or a loopback URL')
        endpoints[row['id']] = deepcopy(row)
    return endpoints


def _validate_binding(value, role, endpoints, sources, billing_unit):
    value = _record(value, 'model binding')
    _keys(value, {'provider', 'model', 'version', 'endpointPolicyId', 'deployment',
                  'contextWindow', 'maxOutputTokens', 'qualityProxy', 'latencyMs',
                  'pricing', 'profileProvenance', 'evidenceSources'}, 'model binding')
    if not isinstance(value['provider'], str) or not value['provider']:
        raise ValueError('binding requires provider')
    if not isinstance(value['model'], str) or not value['model']:
        raise ValueError('binding requires model')
    version = _record(value['version'], 'model version')
    _keys(version, {'kind', 'value', 'observedAt'}, 'model version')
    if (version['kind'] not in {'immutable-version', 'documented-model-name', 'rolling-alias'}
            or not isinstance(version['value'], str) or not version['value']
            or not isinstance(version['observedAt'], str) or not version['observedAt']):
        raise ValueError('invalid model version')
    endpoint = endpoints.get(value['endpointPolicyId'])
    if endpoint is None or endpoint['provider'] != value['provider']:
        raise ValueError('binding references an incompatible endpoint policy')
    if value['deployment'] not in DEPLOYMENTS or value['deployment'] != role['deployment']:
        raise ValueError('binding deployment does not match the frozen role')
    if value['deployment'] == 'trusted-cloud' and not endpoint['trustPolicyId']:
        raise ValueError('trusted-cloud binding requires a trust policy')
    if value['deployment'] == 'local' and endpoint['type'] != 'local':
        raise ValueError('local binding requires a local endpoint')
    if value['deployment'] == 'simulated-local':
        raise ValueError('simulated-local cannot become a real benchmark binding')
    for field in ('contextWindow', 'maxOutputTokens'):
        if type(value[field]) is not int or value[field] < 1:
            raise ValueError(f'invalid binding {field}')
    _number(value['qualityProxy'], 'qualityProxy', maximum=100)
    _number(value['latencyMs'], 'latencyMs')
    if value['qualityProxy'] < role['qualityProxy']:
        raise ValueError('binding quality proxy is below the frozen role')
    pricing = _record(value['pricing'], 'binding pricing')
    _keys(pricing, {'unit', 'inputPer1k', 'cachedInputPer1k', 'outputPer1k',
                    'sourceId'}, 'binding pricing')
    if pricing['unit'] != billing_unit or pricing['sourceId'] not in sources:
        raise ValueError('binding pricing unit or source is invalid')
    for field in ('inputPer1k', 'cachedInputPer1k', 'outputPer1k'):
        _number(pricing[field], field)
    if pricing['cachedInputPer1k'] > pricing['inputPer1k']:
        raise ValueError('cached input price cannot exceed input price')
    if value['profileProvenance'] not in PROFILE_PROVENANCE:
        raise ValueError('invalid profile provenance')
    if (not isinstance(value['evidenceSources'], list) or not value['evidenceSources']
            or any(source not in sources for source in value['evidenceSources'])):
        raise ValueError('binding requires known evidence sources')
    return deepcopy(value)


def audit_bindings(protocol, raw):
    """审计真实绑定覆盖率；允许显式 blocked 条目，但永远不把它们视为可运行。"""
    validate_protocol(protocol)
    raw = _record(raw, 'binding inventory')
    _keys(raw, {'schema_version', 'issue', 'protocol_sha256', 'frozen_at',
                'pricing_snapshot_date', 'billing_unit', 'sources', 'endpointPolicies',
                'bindings'}, 'binding inventory')
    if raw['schema_version'] != SCHEMA or raw['issue'] != 112:
        raise ValueError('invalid binding inventory schema')
    if raw['protocol_sha256'] != digest(protocol):
        raise ValueError('binding inventory protocol digest mismatch')
    if (not isinstance(raw['frozen_at'], str) or not raw['frozen_at']
            or not isinstance(raw['pricing_snapshot_date'], str)
            or not raw['pricing_snapshot_date'] or not isinstance(raw['billing_unit'], str)
            or not raw['billing_unit']):
        raise ValueError('binding inventory requires snapshot metadata')
    sources = _validate_sources(raw['sources'])
    endpoints = _validate_endpoints(raw['endpointPolicies'])
    roles = {row['id']: row for row in protocol['models']}
    bindings, blocked = {}, []
    for row in raw['bindings']:
        row = _record(row, 'role binding')
        _keys(row, {'roleId', 'status', 'blockers', 'binding'}, 'role binding')
        role_id = row['roleId']
        if role_id not in roles or role_id in bindings or row['status'] not in STATUSES:
            raise ValueError('invalid or duplicate role binding')
        if (not isinstance(row['blockers'], list)
                or any(not isinstance(item, str) or not item for item in row['blockers'])):
            raise ValueError('invalid binding blockers')
        binding = None
        if row['binding'] is not None:
            binding = _validate_binding(row['binding'], roles[role_id], endpoints, sources,
                                        raw['billing_unit'])
        if row['status'] == 'bound' and (binding is None or row['blockers']):
            raise ValueError('bound role cannot contain blockers or omit its binding')
        if row['status'] == 'blocked' and not row['blockers']:
            raise ValueError('blocked role requires at least one blocker')
        bindings[role_id] = {'status': row['status'], 'binding': binding,
                             'blockers': list(row['blockers'])}
        if row['status'] == 'blocked':
            blocked.append({'role_id': role_id, 'requirements': list(row['blockers'])})
    if set(bindings) != set(roles):
        raise ValueError('binding inventory must cover every frozen model role')
    bound_identities = {}
    for role_id, row in bindings.items():
        if row['status'] == 'bound':
            identity = (row['binding']['provider'], row['binding']['model'])
            bound_identities.setdefault(identity, []).append(role_id)
    judges = [role_id for role_id, role in roles.items() if role['role'] == 'judge']
    for judge_id in judges:
        judge = bindings[judge_id]
        if judge['status'] == 'bound':
            identity = (judge['binding']['provider'], judge['binding']['model'])
            if bound_identities.get(identity) != [judge_id]:
                raise ValueError('judge binding must be independent from production roles')
    bound_roles = sorted(role_id for role_id, row in bindings.items()
                         if row['status'] == 'bound')
    return {
        'schema_version': 'security-benchmark-binding-audit-v1',
        'real_model_calls': 0,
        'protocol_sha256': raw['protocol_sha256'],
        'binding_sha256': digest(raw),
        'billing_unit': raw['billing_unit'],
        'roles_total': len(roles),
        'bound_roles': bound_roles,
        'blocked_roles': blocked,
        'live_execution_ready': not blocked,
    }
