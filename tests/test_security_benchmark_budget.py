"""#112 零调用预算冻结。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.security_benchmark_budget import freeze_budget, pricing_snapshot


ROOT = Path(__file__).resolve().parents[1]


def documents():
    protocol = json.loads((ROOT / 'data/research/security-benchmark-v1.json').read_text())
    bindings = json.loads((ROOT / 'data/research/security-benchmark-bindings-v2.json').read_text())
    return protocol, bindings


def v3_documents():
    protocol = json.loads((ROOT / 'data/research/security-benchmark-v1.json').read_text())
    bindings = json.loads((ROOT / 'data/research/security-benchmark-bindings-v3.json').read_text())
    return protocol, bindings


def mock_complete_v3_bindings(bindings):
    """测试用虚构证明，不能写入真实绑定清单。"""
    attestation = {'id': 'mock-attestation', 'kind': 'operator-attestation',
                   'uri': 'test-only', 'retrievedAt': '2026-10-04', 'sha256': 'a' * 64}
    bindings['sources'].append(attestation)
    bindings['endpointPolicies'] += [
        {'id': 'mock-trusted', 'provider': 'ark-plan', 'type': 'openai-compatible',
         'baseUrl': 'https://example.invalid/v1', 'credentialEnv': 'MOCK_KEY',
         'region': 'test', 'trustPolicyId': 'mock-policy'},
        {'id': 'mock-local', 'provider': 'test-local', 'type': 'local',
         'baseUrl': 'http://127.0.0.1:9000/v1', 'credentialEnv': '',
         'region': 'test-machine', 'trustPolicyId': None},
    ]
    template = bindings['bindings'][0]['binding']
    for row in bindings['bindings']:
        if row['roleId'] not in {'trusted-strong', 'local-worker', 'local-judge'}:
            continue
        binding = deepcopy(template)
        binding['model'] = f'mock-{row["roleId"]}'
        binding['version'] = {'kind': 'immutable-version', 'value': 'mock-digest',
                              'observedAt': '2026-10-04'}
        binding['evidenceSources'] = ['mock-attestation']
        binding['qualityProxy'] = 100
        if row['roleId'] == 'trusted-strong':
            binding['deployment'] = 'trusted-cloud'
            binding['endpointPolicyId'] = 'mock-trusted'
            binding['executionPricing'] = {'unit': 'CNY', 'inputPer1k': 1,
                                           'cachedInputPer1k': 1, 'outputPer1k': 2,
                                           'sourceId': 'mock-attestation'}
        else:
            binding['provider'] = 'test-local'
            binding['deployment'] = 'local'
            binding['endpointPolicyId'] = 'mock-local'
            binding['executionPricing'] = None
            binding['localResource'] = {
                'engine': 'mock-engine', 'artifactSha256': 'b' * 64,
                'evidenceSources': ['mock-attestation'], 'resourceCostPerCall': .02,
                'resourceCostUnit': 'CNY', 'resourceCostBlockers': [],
            }
        row.update(status='bound', blockers=[], binding=binding)
    return bindings


def test_budget_freezes_48_calls_but_refuses_an_incomplete_total_cost():
    result = freeze_budget(*documents())
    assert result['real_model_calls'] == 0
    assert result['planned_calls'] == {'production': 28, 'evaluation': 20, 'total': 48}
    assert result['authorization_call_cap'] == 48
    assert result['protocol_hard_call_cap'] == 64
    assert result['automatic_http_retries'] == result['node_fallbacks'] == 0
    assert result['maximum_total_execution_usage'] is None
    assert result['authorization_request_ready'] is False
    assert result['paid_execution_authorized'] is False
    assert result['live_execution_ready'] is False


def test_v3_keeps_afp_and_local_resource_accounts_separate():
    protocol, bindings = v3_documents()
    result = freeze_budget(protocol, mock_complete_v3_bindings(bindings))
    assert result['schema_version'] == 'security-benchmark-budget-freeze-v3'
    assert result['known_execution_usage_by_unit']['AFP'] == pytest.approx(7.452)
    assert result['known_execution_usage_by_unit']['CNY'] > 0
    assert result['maximum_execution_usage_by_unit'] == result['known_execution_usage_by_unit']
    assert result['known_local_resource_cost_by_unit'] == {'CNY': pytest.approx(.6)}
    assert result['maximum_local_resource_cost_by_unit'] == result['known_local_resource_cost_by_unit']
    assert result['known_bound_execution_usage'] is None
    assert result['authorization_request_ready'] is True
    assert result['paid_execution_authorized'] is False
    assert result['live_execution_ready'] is False


def test_v3_unknown_local_resource_cost_blocks_full_authorization():
    protocol, bindings = v3_documents()
    mock_complete_v3_bindings(bindings)
    row = next(row for row in bindings['bindings'] if row['roleId'] == 'local-judge')
    row['binding']['localResource'].update(resourceCostPerCall=None,
                                           resourceCostUnit=None,
                                           resourceCostBlockers=['MOCK_RESOURCE_COST_UNKNOWN'])
    result = freeze_budget(protocol, bindings)
    assert result['maximum_execution_usage_by_unit'] is not None
    assert result['maximum_local_resource_cost_by_unit'] is None
    assert result['authorization_request_ready'] is False
    assert 'MOCK_RESOURCE_COST_UNKNOWN' in result['blocking_requirements']


def test_v3_rejects_token_pricing_for_a_local_model():
    protocol, bindings = v3_documents()
    mock_complete_v3_bindings(bindings)
    row = next(row for row in bindings['bindings'] if row['roleId'] == 'local-worker')
    row['binding']['executionPricing'] = deepcopy(bindings['bindings'][0]['binding']['executionPricing'])
    with pytest.raises(ValueError, match='cannot declare token API pricing'):
        freeze_budget(protocol, bindings)


def test_v3_local_binding_requires_a_loopback_endpoint():
    protocol, bindings = v3_documents()
    mock_complete_v3_bindings(bindings)
    local = next(row for row in bindings['endpointPolicies'] if row['id'] == 'mock-local')
    local['baseUrl'] = 'https://example.invalid/v1'
    with pytest.raises(ValueError, match='loopback local endpoint'):
        freeze_budget(protocol, bindings)


def test_role_token_envelopes_match_the_preregistered_matrix():
    rows = {row['role_id']: row for row in freeze_budget(*documents())['role_totals']}
    assert rows['external-strong'] == {
        'role_id': 'external-strong', 'calls': 5, 'purposes': {'production': 5},
        'input_tokens': 9300, 'output_tokens': 3720,
        'projected_execution_usage': 7.161, 'execution_billing_unit': 'AFP',
        'projected_reference_cost': None, 'reference_billing_unit': None}
    assert rows['external-cheap'] == {
        'role_id': 'external-cheap', 'calls': 5, 'purposes': {'production': 5},
        'input_tokens': 4100, 'output_tokens': 1720,
        'projected_execution_usage': 0.291, 'execution_billing_unit': 'AFP',
        'projected_reference_cost': None, 'reference_billing_unit': None}
    assert rows['trusted-strong']['calls'] == 8
    assert rows['local-worker']['calls'] == 10
    assert rows['local-judge'] == {
        'role_id': 'local-judge', 'calls': 20, 'purposes': {'evaluation': 20},
        'input_tokens': 25120, 'output_tokens': 10240,
        'projected_execution_usage': None, 'execution_billing_unit': 'AFP',
        'projected_reference_cost': None, 'reference_billing_unit': None}
    assert result_totals(rows) == (48, 68720, 27570)


def result_totals(rows):
    return (sum(row['calls'] for row in rows.values()),
            sum(row['input_tokens'] for row in rows.values()),
            sum(row['output_tokens'] for row in rows.values()))


def test_known_cost_is_partial_and_does_not_pose_as_the_total_budget():
    result = freeze_budget(*documents())
    assert result['known_bound_execution_usage'] == pytest.approx(7.452)
    assert result['execution_cash_cost'] is None
    assert result['execution_cash_cost_method'] is None
    assert result['execution_cash_cost_blockers']
    assert {row['role_id'] for row in result['unresolved_execution_usage_roles']} == {
        'trusted-strong', 'local-worker', 'local-judge'}
    assert all('simulated-local-worker' != row['role_id']
               for row in result['unresolved_execution_usage_roles'])
    assert {row['role_id'] for row in result['unresolved_reference_cost_roles']} == {
        'external-cheap', 'external-strong'}
    assert result['reference_cost_totals_by_unit'] == {}
    assert result['maximum_total_reference_cost'] is None
    assert result['maximum_total_reference_cost_unit'] is None


def test_pricing_snapshot_only_contains_real_bound_routes_and_no_credentials():
    _, bindings = documents()
    snapshot = pricing_snapshot(bindings)
    assert [row['role_id'] for row in snapshot['routes']] == [
        'external-strong', 'external-cheap']
    serialized = json.dumps(snapshot)
    assert 'CODEX_ARK_API_KEY' not in serialized
    assert 'credential' not in serialized.lower()
    assert all(row['execution_pricing']['unit'] == 'AFP' for row in snapshot['routes'])
    assert all(row['reference_pricing'] is None for row in snapshot['routes'])


def test_reference_prices_are_aggregated_by_unit_and_never_cross_summed():
    protocol, bindings = documents()
    for index, unit in enumerate(('USD', 'CNY')):
        binding = bindings['bindings'][index]['binding']
        source = binding['evidenceSources'][0]
        binding['referencePricingBlockers'] = []
        binding['referencePricing'] = {
            'provider': 'vendor', 'model': f'frozen-{index}',
            'version': {'kind': 'immutable-version', 'value': f'v{index}',
                        'observedAt': '2026-09-21'},
            'equivalenceEvidenceSources': [source],
            'pricing': {'unit': unit, 'inputPer1k': 1, 'cachedInputPer1k': .5,
                        'outputPer1k': 2, 'sourceId': source},
        }
    result = freeze_budget(protocol, bindings)
    assert result['reference_cost_totals_by_unit'] == {
        'CNY': pytest.approx(7.54), 'USD': pytest.approx(16.74)}
    assert result['maximum_total_reference_cost'] is None
    assert result['maximum_total_reference_cost_unit'] is None


def test_protocol_call_hard_cap_remains_fail_closed():
    protocol, bindings = documents()
    protocol['constraints']['maxCalls'] = 47
    bindings['protocol_sha256'] = __import__('refractrouter.security_benchmark',
        fromlist=['digest']).digest(protocol)
    with pytest.raises(ValueError, match='CALL_ENVELOPE_EXCEEDED'):
        freeze_budget(protocol, bindings)
