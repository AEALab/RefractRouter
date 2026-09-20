"""隐私感知放置：配置编译、分级、候选收窄与运行期守门；全部零网络零付费调用。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.agent import run_agent
from refractrouter.application_config import (SCHEMA_V1, SCHEMA_V2, SCHEMA_V3, SCHEMA_V4,
    compile_configuration, migrate_v3_to_v4)
from refractrouter.privacy_placement import (PlacementGuard, PrivacyRouteViolation, classify_view,
    default_privacy, grade_nodes, judge_isolation, marginal_pricing, new_record, resolve_placement,
    restricted_eligible_models, role_isolation, safe_tool_audit, scan_deterministic, static_node_views)
from refractrouter.task_plan import validate_plan
from tests.test_text_tasks import Client

ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_TASK = '整理客户合同：联络人 wang@example.com，金额 120 万元，输出摘要'


def configuration(*, schema=SCHEMA_V2, local_deployment='simulated-local', privacy='enabled',
                  judge_local=True, classifier=None):
    """一个云端强候选、一个本地候选与一个评审模型的最小 v2 配置。"""
    raw = {'schemaVersion': schema, 'billingUnit': 'USD', 'qualityMin': 80,
           'providers': [
               {'id': 'cloud', 'type': 'openai-compatible', 'baseUrl': 'https://cloud.example/v1',
                'credentialEnv': 'CLOUD_KEY'},
               {'id': 'local', 'type': 'openai-compatible', 'baseUrl': 'https://local.example/v1',
                'credentialEnv': 'LOCAL_KEY',
                **({'deployment': local_deployment} if local_deployment is not None else {})}],
           'models': [
               {'id': 'cloud-strong', 'provider': 'cloud', 'model': 'CLOUD_STRONG', 'role': 'candidate',
                'contextWindow': 131072, 'maxOutputTokens': 2048,
                'pricing': {'unit': 'USD', 'inputPer1k': .01, 'outputPer1k': .02},
                'routing': {'quality': 95, 'latencyMs': 3000}},
               {'id': 'local-work', 'provider': 'local', 'model': 'LOCAL_WORK', 'role': 'candidate',
                'contextWindow': 131072, 'maxOutputTokens': 2048,
                'pricing': {'unit': 'USD', 'inputPer1k': .001, 'outputPer1k': .002},
                'routing': {'quality': 85, 'latencyMs': 20000}},
               {'id': 'judge', 'provider': 'local' if judge_local else 'cloud', 'model': 'JUDGE',
                'role': 'judge', 'contextWindow': 131072, 'maxOutputTokens': 2048,
                'pricing': {'unit': 'USD', 'inputPer1k': .001, 'outputPer1k': .002}}]}
    if privacy == 'enabled':
        raw['privacy'] = {'enabled': True, 'sensitiveTerms': [], 'maxPromptBytes': 1048576}
        if classifier is not None:
            raw['privacy']['classifier'] = classifier
    elif isinstance(privacy, dict):
        raw['privacy'] = privacy
    return raw


def security_configuration(*, local_deployment='local', data_mode='live', trusted=False):
    raw = configuration(schema=SCHEMA_V2, local_deployment=local_deployment, privacy=None)
    raw['schemaVersion'] = SCHEMA_V3
    raw['providers'][0]['deployment'] = 'external-cloud'
    raw['security'] = {'dataMode': data_mode, 'sensitiveTerms': [], 'maxPromptBytes': 1048576}
    if trusted:
        raw['providers'][1].update(deployment='trusted-cloud', trustPolicy='team-cn')
        raw['trustPolicies'] = [{'id': 'team-cn', 'residency': 'CN', 'auditLogging': True,
                                 'allowsSensitiveData': True}]
    return raw


def automatic_configuration(*, local_deployment='local', acknowledge=False):
    raw = security_configuration(local_deployment=local_deployment)
    raw['schemaVersion'] = SCHEMA_V4
    raw.pop('qualityMin')
    raw['objective'] = {'qualityMin': 80, 'primary': 'cost', 'secondary': 'latency', 'dagMode': 'auto'}
    for model in raw['models']:
        legacy = model.pop('role')
        model['roles'] = (['planner', 'worker'] if model['id'] == 'local-work' else
                          ['worker'] if legacy == 'candidate' else ['judge'])
    if local_deployment == 'simulated-local':
        raw['providers'][1]['trustPolicy'] = 'simulated-cn'
        raw['trustPolicies'] = [{'id': 'simulated-cn', 'residency': 'CN', 'auditLogging': True,
                                 'allowsSensitiveData': True,
                                 'acknowledgeExternalTransmission': acknowledge}]
    return raw


def plan():
    return validate_plan(json.loads((ROOT / 'data/task-plans/parallel-analysis-v2.json').read_text()))


def models_of(config):
    return {m.model_id: m for m in compile_configuration(config).manifest.models}


def live(payload, config, tmp_path, client):
    return run_agent(payload, provider_config=config, mode='live', execute_paid_run=True,
                     runs_dir=tmp_path, client=client)


def record_of(result):
    return json.loads((Path(result['run_dir']) / 'result.json').read_text())


# 一、配置编译：v1 保持不变，v2 才引入 deployment 与 privacy。

def test_v1_configuration_rejects_new_fields():
    for mutate in (lambda raw: raw['providers'][0].update(deployment='local'),
                   lambda raw: raw.update(privacy={'enabled': True})):
        raw = configuration(schema=SCHEMA_V1, privacy=None)
        mutate(raw)
        with pytest.raises(ValueError):
            compile_configuration(raw)


def test_v2_without_new_fields_matches_v1_compilation():
    v1 = configuration(schema=SCHEMA_V1, local_deployment=None, privacy=None)
    v2 = configuration(schema=SCHEMA_V2, local_deployment=None, privacy=None)
    first, second = compile_configuration(v1), compile_configuration(v2)
    assert (first.manifest.models == second.manifest.models
            and first.predictions == second.predictions
            and first.quality_min == second.quality_min)
    assert first.privacy is None and second.privacy is None
    assert second.manifest.schema_version == SCHEMA_V2


def test_v3_enables_security_and_requires_explicit_trust_domains():
    compiled = compile_configuration(security_configuration())
    assert compiled.privacy['enabled'] is True
    assert compiled.privacy['dataMode'] == 'live'
    assert compiled.manifest.schema_version == SCHEMA_V3
    assert {m.deployment for m in compiled.manifest.models} == {'external-cloud', 'local'}


def test_v3_rejects_simulated_local_for_live_sensitive_material():
    with pytest.raises(ValueError, match='simulated-local is allowed only'):
        compile_configuration(security_configuration(local_deployment='simulated-local'))
    compiled = compile_configuration(security_configuration(
        local_deployment='simulated-local', data_mode='synthetic'))
    assert compiled.privacy['dataMode'] == 'synthetic'
    raw = security_configuration(local_deployment='simulated-local', data_mode='live')
    raw['security']['classifier'] = {'enabled': True, 'modelId': 'local-work'}
    with pytest.raises(ValueError, match='local or trusted-cloud'):
        compile_configuration(raw)


def test_v3_trusted_cloud_requires_and_accepts_an_explicit_policy():
    raw = security_configuration(local_deployment='trusted-cloud')
    with pytest.raises(ValueError, match='configured trustPolicy'):
        compile_configuration(raw)
    compiled = compile_configuration(security_configuration(trusted=True))
    assert {m.deployment for m in compiled.manifest.models} == {'external-cloud', 'trusted-cloud'}
    record = new_record(compiled.privacy, compiled.manifest.models)
    assert record['policy_version'] == 'security-placement-v2'
    assert record['local_execution_model_ids'] == ['local-work']


def test_v3_trusted_cloud_classifier_is_decided_by_the_security_contract():
    raw = security_configuration(trusted=True)
    raw['security']['classifier'] = {'enabled': True, 'modelId': 'local-work'}
    compiled = compile_configuration(raw)
    assert compiled.privacy['classifier'] == {'enabled': True, 'modelId': 'local-work'}


def test_v4_compiles_cost_first_objective_and_multi_role_pools():
    compiled = compile_configuration(automatic_configuration(), strategy='auto')
    assert compiled.objective == {'qualityMin': 80, 'primary': 'cost',
                                  'secondary': 'latency', 'dagMode': 'auto'}
    assert compiled.role_pools == {
        'planner': ('local-work',), 'worker': ('cloud-strong', 'local-work'),
        'judge': ('judge',), 'classifier': (),
    }
    assert {model.model_id for model in compiled.manifest.candidates} == {'cloud-strong', 'local-work'}
    assert compiled.manifest.judge.model_id == 'judge'


def test_published_v4_example_compiles_without_model_calls():
    compiled = compile_configuration(json.loads(
        (ROOT / 'data/schema/refractagent-providers-v4-example.json').read_text()))
    assert compiled.manifest.schema_version == SCHEMA_V4
    assert compiled.role_pools['classifier'] == ('local-router',)


def test_v4_simulated_local_live_data_requires_explicit_external_transmission_acknowledgement():
    with pytest.raises(ValueError, match='acknowledgeExternalTransmission'):
        compile_configuration(automatic_configuration(local_deployment='simulated-local'))
    compiled = compile_configuration(automatic_configuration(
        local_deployment='simulated-local', acknowledge=True))
    assert compiled.privacy['allowSimulatedLocalSensitive'] is True
    assert compiled.privacy['simulatedLocalExternalTransmissionAcknowledged'] is True
    assert new_record(compiled.privacy, compiled.manifest.models)['local_execution_model_ids'] == ['local-work']


def test_v3_to_v4_migration_is_explicit_and_keeps_source_unchanged():
    source = security_configuration()
    before = deepcopy(source)
    migrated = migrate_v3_to_v4(source, planner_model_id='local-work')
    compiled = compile_configuration(migrated)
    assert source == before
    assert migrated['schemaVersion'] == SCHEMA_V4 and 'strategies' not in migrated
    assert compiled.role_pools['planner'] == ('local-work',)
    with pytest.raises(ValueError, match='explicit planner'):
        migrate_v3_to_v4(source)


def test_local_provider_cannot_declare_cloud_models():
    raw = configuration()
    raw['models'][1]['deployment'] = 'cloud'
    with pytest.raises(ValueError, match='local provider cannot declare cloud'):
        compile_configuration(raw)


def test_simulated_local_candidate_prices_as_zero_and_keeps_declared_price():
    compiled = compile_configuration(configuration())
    models = {m.model_id: m for m in compiled.manifest.models}
    assert models['local-work'].deployment == 'simulated-local'
    assert (models['local-work'].input_cost_per_1k, models['local-work'].output_cost_per_1k) == (0.0, 0.0)
    assert models['local-work'].declared_pricing == {'unit': 'USD', 'inputPer1k': .001,
                                                     'outputPer1k': .002, 'cachedInputPer1k': .001}
    assert models['cloud-strong'].declared_pricing is None
    assert marginal_pricing('cloud', .01, .01, .02) == (.01, .01, .02)
    assert marginal_pricing('local', .01, .01, .02) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize('privacy,message', [
    ({'enabled': True, 'classifier': {'enabled': True}}, 'modelId is required'),
    ({'enabled': True, 'classifier': {'enabled': True, 'modelId': 'cloud-strong'}}, 'local or simulated-local'),
    ({'enabled': True, 'classifier': {'enabled': True, 'modelId': 'missing'}}, 'configured model'),
    ({'enabled': True, 'maxPromptBytes': 10}, 'out of range'),
    ({'enabled': True, 'sensitiveTerms': ['a', 'a']}, 'unique'),
    ({'enabled': True, 'unknown': 1}, 'invalid privacy fields'),
    ({'enabled': 'yes'}, 'boolean')])
def test_invalid_privacy_configuration_is_rejected(privacy, message):
    with pytest.raises(ValueError, match=message):
        compile_configuration(configuration(privacy=privacy))


def test_privacy_requires_a_local_candidate():
    raw = configuration(local_deployment='cloud')
    del raw['providers'][1]['deployment']
    with pytest.raises(ValueError, match='at least one local'):
        compile_configuration(raw)


def test_classifier_must_bind_a_local_model():
    raw = configuration(classifier={'enabled': True, 'modelId': 'local-work'})
    assert compile_configuration(raw).privacy['classifier'] == {'enabled': True, 'modelId': 'local-work'}


def test_deployment_field_stays_out_of_the_manifest_model_spec():
    """deployment 属于 providerConfig 行；写进 ModelSpec 会改动 K3 冻结配置摘要。"""
    from dataclasses import asdict, fields
    from refractrouter.schemas import ModelSpec
    from refractrouter.application_config import ApplicationModelSpec
    assert 'deployment' not in {f.name for f in fields(ModelSpec)}
    assert 'deployment' not in asdict(ModelSpec(
        model_id='m', provider='p', input_cost_per_1k=1.0, output_cost_per_1k=2.0, capability=.5))
    assert {f.name for f in fields(ApplicationModelSpec)} > {'deployment', 'declared_pricing'}
    assert ApplicationModelSpec(
        model_id='m', provider='p', input_cost_per_1k=0.0, output_cost_per_1k=0.0,
        capability=.5).deployment == 'cloud'


# 二、确定性分级与 fail-safe。

@pytest.mark.parametrize('text,rule', [
    ('联系人 wang@example.com', 'email'),
    ('客户电话 13800138000', 'phone-cn'),
    ('-----BEGIN RSA PRIVATE KEY-----', 'private-key'),
    ('api_key = sk-abcdef123456', 'credential-assignment'),
    ('Authorization: Bearer abcdefghijklmnopqrstuvwx', 'bearer-token'),
    ('路径 /Users/alice/contracts/2026.docx', 'local-absolute-path'),
    ('导出到 C:\\Users\\alice\\Desktop', 'windows-absolute-path')])
def test_deterministic_rules_grade_sensitive(text, rule):
    assert rule in scan_deterministic(text)
    assert classify_view(text, privacy=default_privacy())['grade'] == 'S1'


def test_custom_terms_and_plain_text():
    privacy = {'enabled': True, 'sensitiveTerms': ['合同金额'], 'classifier': {'enabled': False, 'modelId': None},
               'maxPromptBytes': 1048576}
    assert classify_view('本合同金额为 120 万元', privacy=privacy)['reasons'] == ['term:合同金额']
    row = classify_view('比较两种公开方案的资源需求', privacy=privacy)
    assert row['grade'] == 'S3' and row['reasons'] == []


def test_oversized_view_and_classifier_failure_fall_back_to_unknown():
    privacy = {'enabled': True, 'sensitiveTerms': [], 'classifier': {'enabled': False, 'modelId': None},
               'maxPromptBytes': 1024}
    assert classify_view('x' * 2048, privacy=privacy)['grade'] == 'unknown'
    enabled = {**privacy, 'classifier': {'enabled': True, 'modelId': 'local-work'}, 'maxPromptBytes': 1048576}
    assert classify_view('公开内容', privacy=enabled)['grade'] == 'unknown'
    failed = classify_view('公开内容', privacy=enabled,
                           classifier=lambda view: (_ for _ in ()).throw(RuntimeError()))
    assert failed['reasons'] == ['classifier-failed:RuntimeError'] and failed['grade'] == 'unknown'
    assert classify_view('公开内容', privacy=enabled, classifier=lambda view: {'label': 'sensitive'})['grade'] == 'S1'
    assert classify_view('公开内容', privacy=enabled, classifier=lambda view: {'label': 'public'})['grade'] == 'S3'


# 三、规划期放置与候选收窄。

def test_resolve_placement_narrows_only_sensitive_nodes():
    privacy = configuration()['privacy']
    record = new_record(privacy, models_of(configuration()).values())
    resolve_placement(plan=plan(), node_views=static_node_views(plan(), SENSITIVE_TASK),
                      models=models_of(configuration()).values(), privacy=privacy, record=record)
    assert record['status'] == 'selected' and record['local_model_ids'] == ['judge', 'local-work']
    assert record['local_execution_model_ids'] == ['local-work']
    assert {nid: row['grade'] for nid, row in record['grades'].items()} == {'cost': 'S1', 'risk': 'S1', 'answer': 'S1'}
    assert record['eligible_models'] == {'cost': ['local-work'], 'risk': ['local-work'],
                                         'answer': ['local-work']}


def test_public_task_keeps_the_full_candidate_pool():
    privacy = configuration()['privacy']
    record = new_record(privacy, models_of(configuration()).values())
    resolve_placement(plan=plan(), node_views=static_node_views(plan(), '比较两个公开方案'),
                      models=models_of(configuration()).values(), privacy=privacy, record=record)
    assert record['status'] == 'selected' and record['eligible_models'] == {}
    assert restricted_eligible_models({'cost': ['cloud-strong', 'local-work']}, record) == {
        'cost': ['cloud-strong', 'local-work']}


def test_sensitive_node_without_local_candidate_blocks_instead_of_leaking():
    privacy = configuration()['privacy']
    cloud_only = configuration(local_deployment=None, privacy=None)
    models = compile_configuration(cloud_only).manifest.models
    record = new_record(privacy, models)
    resolve_placement(plan=plan(), node_views=static_node_views(plan(), SENSITIVE_TASK),
                      models=models, privacy=privacy, record=record)
    assert record['status'] == 'no-local-candidate'
    assert [row['detail'] for row in record['blocked']] == ['no-local-candidate'] * 3
    assert record['eligible_models'] == {}


def test_capability_intersection_starvation_is_visible():
    privacy = configuration()['privacy']
    record = new_record(privacy, models_of(configuration()).values())
    resolve_placement(plan=plan(), node_views=static_node_views(plan(), SENSITIVE_TASK),
                      models=models_of(configuration()).values(), privacy=privacy, record=record)
    narrowed = restricted_eligible_models({'cost': ['cloud-strong'], 'risk': ['cloud-strong', 'local-work']}, record)
    assert narrowed == {'cost': [], 'risk': ['local-work'], 'answer': ['local-work']}


def test_local_pool_must_contain_an_execution_candidate():
    """只有本地评审时，敏感节点仍不可派发；不得把评审当执行者。"""
    privacy = configuration()['privacy']
    compiled = models_of(configuration())
    models = [compiled['judge'], compiled['cloud-strong']]
    record = new_record(privacy, models)
    resolve_placement(plan=plan(), node_views=static_node_views(plan(), SENSITIVE_TASK),
                      models=models, privacy=privacy, record=record)
    assert record['local_model_ids'] == ['judge'] and record['local_execution_model_ids'] == []
    assert record['status'] == 'no-local-candidate'
    assert [row['detail'] for row in record['blocked']] == ['no-local-execution-candidate'] * 3


def test_dynamic_split_grading_keeps_runtime_verdicts():
    privacy = configuration()['privacy']
    record = new_record(privacy, models_of(configuration()).values())
    record['runtime_grades']['cost'] = {'grade': 'S1', 'reasons': ['runtime'], 'source': 'runtime-view', 'bytes': 10}
    narrowed = grade_nodes(record, nodes=[n for n in plan().nodes if n.node_id == 'cost'],
                           node_views=static_node_views(plan(), '比较两个公开方案'), privacy=privacy)
    # 运行期结论优先：静态视图的公开判定不得把已经升级为敏感的节点降级回云端。
    assert narrowed == {'cost': ['local-work']} and 'cost' not in record['grades']
    assert record['runtime_grades']['cost']['reasons'] == ['runtime']


# 四、运行期守门与角色隔离。

def guard_for(config):
    compiled = compile_configuration(config)
    record = new_record(compiled.privacy, compiled.manifest.models)
    return PlacementGuard(record, compiled.manifest.models)


def messages(text):
    return [{'role': 'user', 'content': text}]


def small_local_model(model):
    from dataclasses import replace
    return replace(model, context_window=1024, max_output_tokens=1000)


def test_guard_replaces_cloud_assignment_and_records_the_event():
    guard = guard_for(configuration())
    candidates = models_of(configuration())
    assignments = {'cost': 'cloud-strong'}
    assert guard.admit('cost', messages(SENSITIVE_TASK), assignments, candidates) == 'local-work'
    assert assignments == {'cost': 'local-work'}
    assert guard.record['events'] == [{'node_id': 'cost', 'from_model': 'cloud-strong', 'to_model': 'local-work',
        'grade': 'S1', 'reasons': ['email'], 'action': 'replaced'}]
    assert guard.record['runtime_grades']['cost']['source'] == 'runtime-view'


def test_guard_allows_cloud_for_public_views_and_local_workers():
    guard = guard_for(configuration())
    candidates = models_of(configuration())
    assert guard.admit('cost', messages('比较两个公开方案'), {'cost': 'cloud-strong'}, candidates) == 'cloud-strong'
    assert guard.admit('cost', messages(SENSITIVE_TASK), {'cost': 'local-work'}, candidates) == 'local-work'
    assert guard.record['events'] == []


def test_guard_blocks_when_no_local_candidate_can_take_the_view():
    guard = guard_for(configuration())
    candidates = models_of(configuration())
    tightened = {**candidates, 'local-work': small_local_model(candidates['local-work'])}
    with pytest.raises(PrivacyRouteViolation, match='no-local-candidate'):
        guard.admit('cost', messages(SENSITIVE_TASK), {'cost': 'cloud-strong'}, tightened)
    assert guard.record['violations'][0]['action'] == 'blocked'


def test_tool_result_is_rechecked_before_cloud_followup():
    compiled = compile_configuration(security_configuration())
    guard = PlacementGuard(new_record(compiled.privacy, compiled.manifest.models),
                           compiled.manifest.models)
    followup = [{'role': 'user', 'content': '查询公开天气'},
                {'role': 'tool', 'content': '联系人 wang@example.com'}]
    with pytest.raises(PrivacyRouteViolation, match='sensitive-tool-result'):
        guard.require('weather', 'cloud-strong', followup, stage='sensitive-tool-result')
    row = guard.record['violations'][0]
    assert row['detail'] == 'sensitive-tool-result' and row['reasons'] == ['email']


def test_tool_audit_contains_hashes_without_sensitive_payloads():
    records = [{'node': 'weather', 'status': 'completed',
                'call': {'id': 'c1', 'function': {'name': 'lookup',
                         'arguments': '{"email":"wang@example.com"}'}},
                'result': {'content': [{'type': 'text', 'text': 'wang@example.com'}]}}]
    audit = safe_tool_audit(records, privacy=compile_configuration(security_configuration()).privacy)
    encoded = json.dumps(audit, ensure_ascii=False)
    assert 'wang@example.com' not in encoded and 'arguments' not in encoded and 'content' not in encoded
    assert audit[0]['tool_name'] == 'lookup' and audit[0]['result_grade']['grade'] == 'S1'


def test_role_and_judge_isolation():
    models = models_of(configuration(judge_local=False))
    record = new_record(configuration(judge_local=False)['privacy'], models.values())
    planner = role_isolation(view=SENSITIVE_TASK, privacy=record['privacy'], model=models['cloud-strong'],
                             role='planner')
    assert planner == {'grade': 'S1', 'reasons': ['email'], 'source': 'role-view',
                       'bytes': len(SENSITIVE_TASK.encode()), 'role': 'planner', 'model_id': 'cloud-strong',
                       'deployment': 'cloud', 'satisfied': False}
    local = role_isolation(view=SENSITIVE_TASK, privacy=record['privacy'], model=models['local-work'],
                           role='split-planner')
    assert local['satisfied'] is True and local['deployment'] == 'simulated-local'
    record['grades']['cost'] = {'grade': 'S1', 'reasons': ['email'], 'source': 'static-view', 'bytes': 1}
    assert judge_isolation(record, models['judge']) == {'required': True, 'nodes': ['cost'],
        'judge_model_id': 'judge', 'judge_deployment': 'cloud', 'satisfied': False}
    record['grades']['cost'] = {'grade': 'S3', 'reasons': [], 'source': 'static-view', 'bytes': 1}
    assert judge_isolation(record, models['judge'])['satisfied'] is True


# 五、端到端：关闭路径不变，启用路径收窄，敏感外流在调用前被拦住。

def test_disabled_path_records_no_placement_and_routes_as_before(tmp_path):
    result = live({'task': SENSITIVE_TASK, 'template': 'single'}, configuration(privacy=None), tmp_path, Client())
    assert result['status'] == 'completed', result['issues']
    assert set(result['models'].values()) == {'CLOUD_STRONG'}
    assert 'privacy_placement' not in record_of(result)


def test_sensitive_task_never_reaches_a_cloud_planner(tmp_path):
    client = Client()
    result = live({'task': SENSITIVE_TASK, 'template': 'auto', 'planningMode': 'full',
                   'plannerModelId': 'cloud-strong'}, configuration(), tmp_path, client)
    assert result['status'] == 'privacy-route-blocked' and client.calls == []
    assert result['issues'] == ['planner: planner-not-local']
    placement = record_of(result)['privacy_placement']
    assert placement['role_checks'][0]['role'] == 'planner'
    assert placement['blocked'][0]['detail'] == 'planner-not-local'


def test_sensitive_run_places_every_node_and_the_judge_locally(tmp_path):
    client = Client()
    result = live({'task': SENSITIVE_TASK, 'template': 'auto', 'planningMode': 'full',
                   'plannerModelId': 'local-work'}, configuration(), tmp_path, client)
    assert result['status'] == 'completed', result['issues']
    assert set(result['models'].values()) == {'LOCAL_WORK'}
    assert {call[0].model_id for call in client.calls} == {'local-work', 'judge'}
    record = record_of(result)
    assert record['privacy_placement']['grades']['cost']['grade'] == 'S1'
    assert record['privacy_placement']['judge_isolation']['satisfied'] is True
    assert {row['deployment'] for row in record['nodes']} == {'simulated-local'}
    assert all('request_messages' not in call for call in record['calls'])


def test_cloud_judge_is_blocked_before_the_review_call(tmp_path):
    client = Client()
    result = live({'task': SENSITIVE_TASK, 'template': 'single'},
                  configuration(judge_local=False), tmp_path, client)
    assert result['status'] == 'privacy-route-blocked'
    assert {call[0].model_id for call in client.calls} == {'local-work'}
    assert result['issues'] == ['final-judge: privacy-judge-not-local']


def test_preflight_preview_reports_placement_without_calls(tmp_path):
    result = run_agent({'task': SENSITIVE_TASK, 'template': 'single'}, provider_config=configuration(),
                       mode='preflight', runs_dir=tmp_path)
    assert result['status'] == 'preview'
    placement = record_of(result)['privacy_placement']
    assert placement['status'] == 'selected' and placement['local_model_ids'] == ['judge', 'local-work']


def test_v3_preflight_routes_sensitive_direct_answer_to_a_real_trust_domain(tmp_path):
    result = run_agent({'task': SENSITIVE_TASK, 'template': 'single'},
                       provider_config=security_configuration(), mode='preflight', runs_dir=tmp_path)
    placement = record_of(result)['privacy_placement']
    assert result['status'] == 'preview'
    assert placement['policy_version'] == 'security-placement-v2'
    assert placement['eligible_models']['answer'] == ['local-work']


def test_preflight_reports_judge_isolation_before_any_paid_call(tmp_path):
    """预检即给出评审能否隔离的结论：云端评审的敏感任务在付费前就可见到阻断信号。"""
    (tmp_path/'blocked').mkdir()
    (tmp_path/'ok').mkdir()
    blocked = run_agent({'task': SENSITIVE_TASK, 'template': 'single'},
                        provider_config=configuration(judge_local=False),
                        mode='preflight', runs_dir=tmp_path/'blocked')
    assert blocked['status'] == 'preview'
    isolation = record_of(blocked)['privacy_placement']['judge_isolation']
    assert isolation == {'required': True, 'nodes': ['answer'], 'judge_model_id': 'judge',
                         'judge_deployment': 'cloud', 'satisfied': False}
    assert blocked['issues'] == ['final-judge: privacy-judge-not-local']
    ok = run_agent({'task': SENSITIVE_TASK, 'template': 'single'}, provider_config=configuration(),
                   mode='preflight', runs_dir=tmp_path/'ok')
    assert record_of(ok)['privacy_placement']['judge_isolation']['satisfied'] is True
