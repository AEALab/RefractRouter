"""#112 真实模型绑定合同。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.security_benchmark_bindings import audit_bindings


ROOT = Path(__file__).resolve().parents[1]


def documents():
    protocol = json.loads((ROOT / 'data/research/security-benchmark-v1.json').read_text())
    bindings = json.loads((ROOT / 'data/research/security-benchmark-bindings-v1.json').read_text())
    return protocol, bindings


def test_inventory_binds_external_roles_and_fails_closed_on_missing_private_routes():
    result = audit_bindings(*documents())
    assert result['real_model_calls'] == 0
    assert result['bound_roles'] == ['external-cheap', 'external-strong']
    assert {row['role_id'] for row in result['blocked_roles']} == {
        'local-judge', 'local-worker', 'simulated-local-worker', 'trusted-strong'}
    assert result['live_execution_ready'] is False
    assert result['billing_unit'] == 'AFP'


def test_inventory_is_bound_to_the_exact_protocol_digest():
    protocol, bindings = documents()
    protocol['constraints']['qualityMin'] = 81
    with pytest.raises(ValueError, match='digest mismatch'):
        audit_bindings(protocol, bindings)


def test_bound_role_cannot_silently_change_deployment():
    protocol, bindings = documents()
    bindings['bindings'][0]['binding']['deployment'] = 'trusted-cloud'
    with pytest.raises(ValueError, match='deployment'):
        audit_bindings(protocol, bindings)


def test_trusted_cloud_requires_a_named_trust_policy():
    protocol, bindings = documents()
    row = next(item for item in bindings['bindings'] if item['roleId'] == 'trusted-strong')
    row['status'] = 'bound'
    row['blockers'] = []
    row['binding'] = deepcopy(bindings['bindings'][0]['binding'])
    row['binding'].update(model='glm-5.3', deployment='trusted-cloud', qualityProxy=95)
    with pytest.raises(ValueError, match='trust policy'):
        audit_bindings(protocol, bindings)


def test_blocked_role_requires_an_explicit_reason():
    protocol, bindings = documents()
    bindings['bindings'][2]['blockers'] = []
    with pytest.raises(ValueError, match='requires at least one blocker'):
        audit_bindings(protocol, bindings)


def test_simulated_local_cannot_be_promoted_by_a_binding():
    protocol, bindings = documents()
    row = next(item for item in bindings['bindings']
               if item['roleId'] == 'simulated-local-worker')
    row['status'] = 'bound'
    row['blockers'] = []
    row['binding'] = deepcopy(bindings['bindings'][0]['binding'])
    row['binding'].update(model='simulated', deployment='simulated-local', qualityProxy=95)
    with pytest.raises(ValueError, match='simulated-local'):
        audit_bindings(protocol, bindings)


def test_bound_role_rejects_unknown_pricing_evidence():
    protocol, bindings = documents()
    bindings['bindings'][0]['binding']['pricing']['sourceId'] = 'missing'
    with pytest.raises(ValueError, match='pricing unit or source'):
        audit_bindings(protocol, bindings)
