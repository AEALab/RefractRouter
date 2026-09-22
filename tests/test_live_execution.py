"""单任务真实执行门禁；全部使用确定性模拟客户端。"""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from refractrouter.agent import run_agent
from refractrouter.live_execution import (authorization_binding, complexity_gate,
                                           create_authorization_preview,
                                           review_decision, validate_authorization)
from tests.test_text_tasks import Client


ROOT = Path(__file__).resolve().parents[1]


def config():
    raw = json.loads((ROOT / 'data/schema/refractagent-providers-v4-example.json').read_text())
    raw['security']['dataMode'] = 'synthetic'
    raw['providers'][1] = {'id': 'local', 'type': 'openai-compatible',
                           'baseUrl': 'https://local.example/v1', 'deployment': 'local'}
    return raw


def authorization(preview):
    return {key: preview[key] for key in (
        'schema_version', 'authorization_id', 'issued_at', 'expires_at', 'preview_sha256')}


def test_zero_call_gate_is_deterministic_and_forced_direct_cannot_bypass_tools():
    simple = complexity_gate({'task': '现在应该可以了吧'}, '', policy='auto')
    assert simple['decision'] == 'direct' and simple['reasons'] == ['short-single-deliverable']
    assert complexity_gate({'task': '分别比较两个方案，然后汇总'}, '', policy='auto')['decision'] == 'dag'
    assert complexity_gate({'task': '简短回答', 'outputConstraints': {'maxCharacters': 20}}, '', policy='auto')['decision'] == 'dag'
    assert complexity_gate({'task': '根据材料回答', 'materials': [{'id': 'one'}]}, '', policy='auto')['decision'] == 'direct'
    assert complexity_gate({'task': '根据材料回答', 'materials': [{'id': 'one'}, {'id': 'two'}]}, '', policy='auto')['decision'] == 'dag'
    assert complexity_gate({'task': '读取仓库并运行测试'}, '', policy='direct')['decision'] == 'blocked-tools'


def test_adaptive_review_only_skips_unforced_low_risk_direct():
    payload = {'task': '简单回答'}
    direct = complexity_gate(payload, '', policy='auto')
    assert review_decision(payload, direct, policy='adaptive') == {
        'policy': 'adaptive', 'required': False, 'reason': 'adaptive-low-risk-direct'}
    forced = complexity_gate(payload, '', policy='direct')
    assert review_decision(payload, forced, policy='adaptive')['required'] is True
    assert review_decision(payload, direct, policy='always')['required'] is True


def test_preview_digest_binds_request_configuration_and_expiry():
    payload = {'task': '简单回答', 'strategy': 'auto'}
    gate = complexity_gate(payload, '', policy='auto')
    review = review_decision(payload, gate, policy='adaptive')
    binding = authorization_binding(payload, provider_config={'schemaVersion': 'v4'},
        catalog_snapshot={'routes': []}, production_budget=1, evaluation_budget=2,
        max_output_tokens=2048, gate=gate, review=review, data_mode='synthetic',
        billing_unit='USD')
    now = datetime(2026, 9, 22, tzinfo=timezone.utc)
    preview = create_authorization_preview(binding, billing_unit='USD',
        production_estimate=.1, evaluation_estimate=0, now=now)
    approved = authorization(preview)
    assert validate_authorization(approved, binding, now=now + timedelta(minutes=1)) == approved
    with pytest.raises(ValueError, match='configuration changed'):
        validate_authorization(approved, {**binding, 'production_budget': 3}, now=now)
    with pytest.raises(ValueError, match='expired'):
        validate_authorization(approved, binding, now=now + timedelta(minutes=11))


def test_simple_v4_preflight_then_live_uses_one_worker_and_skips_judge(tmp_path):
    raw = config()
    payload = {'task': '现在应该可以了吧', 'strategy': 'auto',
               'complexityPolicy': 'auto', 'reviewPolicy': 'adaptive'}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'runs',
                        production_budget=1, evaluation_budget=1)
    assert preview['status'] == 'preview'
    assert preview['complexity_gate']['decision'] == 'direct'
    assert preview['live_authorization_preview']['calls']['maximum'] == 1
    assert preview['costs'] == {'production': 0, 'evaluation': 0, 'unconfirmed': 0}
    client = Client()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'runs', mode='live', execute_paid_run=True,
        client=client, production_budget=1, evaluation_budget=1)
    assert result['status'] == 'completed' and len(client.calls) == 1
    assert result['plan_origin'] == 'direct-gate'
    assert result['review']['status'] == 'skipped' and result['quality'] is None
    assert result['costs']['evaluation'] == 0


def test_dag_preview_and_forced_direct_have_bounded_call_envelopes(tmp_path):
    raw = config()
    dag = run_agent({'task': '分别比较两个方案，然后汇总', 'strategy': 'auto',
                     'complexityPolicy': 'auto', 'reviewPolicy': 'adaptive'},
                    provider_config=raw, runs_dir=tmp_path / 'dag')
    assert dag['complexity_gate']['decision'] == 'dag'
    assert dag['review']['required'] is True
    assert dag['live_authorization_preview']['calls']['maximum'] == 8
    direct = run_agent({'task': '简单回答', 'strategy': 'auto',
                        'complexityPolicy': 'direct', 'reviewPolicy': 'adaptive'},
                       provider_config=raw, runs_dir=tmp_path / 'direct')
    assert direct['complexity_gate']['decision'] == 'direct'
    assert direct['review']['required'] is True
    assert direct['live_authorization_preview']['calls']['maximum'] == 2


def test_live_rejects_missing_preview_wrong_data_mode_and_tools_before_dispatch(tmp_path):
    raw = config()
    client = Client()
    with pytest.raises(ValueError, match='PREVIEW_MISMATCH'):
        run_agent({'task': '简单回答', 'strategy': 'auto'}, provider_config=raw,
            runs_dir=tmp_path / 'missing', mode='live', execute_paid_run=True, client=client)
    raw['security']['dataMode'] = 'live'
    with pytest.raises(ValueError, match='DATA_MODE_UNSUPPORTED'):
        run_agent({'task': '简单回答', 'strategy': 'auto'}, provider_config=raw,
            runs_dir=tmp_path / 'live-data', mode='live', execute_paid_run=True, client=client)
    with pytest.raises(ValueError, match='TOOLS_DISABLED'):
        run_agent({'task': '请搜索网页', 'strategy': 'auto', 'complexityPolicy': 'direct'},
            provider_config=config(), runs_dir=tmp_path / 'tools', mode='live',
            execute_paid_run=True, client=client)
    assert not client.calls


def test_live_relax_budget_cannot_bypass_authorized_hard_limit(tmp_path):
    raw = config()
    local_router = next(model for model in raw['models'] if model['id'] == 'local-router')
    local_router['roles'] = ['planner', 'classifier']
    local_router.pop('routing')
    external = next(provider for provider in raw['providers'] if provider['id'] == 'external')
    external.update(deployment='trusted-cloud', trustPolicy='test-policy')
    raw['trustPolicies'] = [{'id': 'test-policy', 'residency': 'test',
                             'auditLogging': True, 'allowsSensitiveData': True}]
    payload = {'task': '简单回答', 'strategy': 'auto',
               'complexityPolicy': 'auto', 'reviewPolicy': 'adaptive',
               'limits': {'relaxBudget': True, 'relaxContext': False}}
    preview = run_agent(payload, provider_config=raw, runs_dir=tmp_path / 'preview',
                        production_budget=0.000001, evaluation_budget=1)
    client = Client()
    result = run_agent({**payload, 'authorization': authorization(preview['live_authorization_preview'])},
        provider_config=raw, runs_dir=tmp_path / 'live', mode='live', execute_paid_run=True,
        client=client, production_budget=0.000001, evaluation_budget=1)
    assert result['status'] == 'no-feasible-route'
    assert not client.calls
