"""#112 零调用预算冻结。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.security_benchmark_budget import freeze_budget, pricing_snapshot


ROOT = Path(__file__).resolve().parents[1]


def documents():
    protocol = json.loads((ROOT / 'data/research/security-benchmark-v1.json').read_text())
    bindings = json.loads((ROOT / 'data/research/security-benchmark-bindings-v1.json').read_text())
    return protocol, bindings


def test_budget_freezes_48_calls_but_refuses_an_incomplete_total_cost():
    result = freeze_budget(*documents())
    assert result['real_model_calls'] == 0
    assert result['planned_calls'] == {'production': 28, 'evaluation': 20, 'total': 48}
    assert result['authorization_call_cap'] == 48
    assert result['protocol_hard_call_cap'] == 64
    assert result['automatic_http_retries'] == result['node_fallbacks'] == 0
    assert result['maximum_total_cost'] is None
    assert result['authorization_request_ready'] is False
    assert result['paid_execution_authorized'] is False
    assert result['live_execution_ready'] is False


def test_role_token_envelopes_match_the_preregistered_matrix():
    rows = {row['role_id']: row for row in freeze_budget(*documents())['role_totals']}
    assert rows['external-strong'] == {
        'role_id': 'external-strong', 'calls': 5, 'purposes': {'production': 5},
        'input_tokens': 9300, 'output_tokens': 3720, 'projected_cost': 7.161}
    assert rows['external-cheap'] == {
        'role_id': 'external-cheap', 'calls': 5, 'purposes': {'production': 5},
        'input_tokens': 4100, 'output_tokens': 1720, 'projected_cost': 0.291}
    assert rows['trusted-strong']['calls'] == 8
    assert rows['local-worker']['calls'] == 10
    assert rows['local-judge'] == {
        'role_id': 'local-judge', 'calls': 20, 'purposes': {'evaluation': 20},
        'input_tokens': 25120, 'output_tokens': 10240, 'projected_cost': None}
    assert result_totals(rows) == (48, 68720, 27570)


def result_totals(rows):
    return (sum(row['calls'] for row in rows.values()),
            sum(row['input_tokens'] for row in rows.values()),
            sum(row['output_tokens'] for row in rows.values()))


def test_known_cost_is_partial_and_does_not_pose_as_the_total_budget():
    result = freeze_budget(*documents())
    assert result['known_bound_cost'] == pytest.approx(7.452)
    assert {row['role_id'] for row in result['unresolved_cost_roles']} == {
        'trusted-strong', 'local-worker', 'local-judge'}
    assert all('simulated-local-worker' != row['role_id']
               for row in result['unresolved_cost_roles'])


def test_pricing_snapshot_only_contains_real_bound_routes_and_no_credentials():
    _, bindings = documents()
    snapshot = pricing_snapshot(bindings)
    assert [row['role_id'] for row in snapshot['routes']] == [
        'external-strong', 'external-cheap']
    serialized = json.dumps(snapshot)
    assert 'CODEX_ARK_API_KEY' not in serialized
    assert 'credential' not in serialized.lower()


def test_protocol_call_hard_cap_remains_fail_closed():
    protocol, bindings = documents()
    protocol['constraints']['maxCalls'] = 47
    bindings['protocol_sha256'] = __import__('refractrouter.security_benchmark',
        fromlist=['digest']).digest(protocol)
    with pytest.raises(ValueError, match='CALL_ENVELOPE_EXCEEDED'):
        freeze_budget(protocol, bindings)
