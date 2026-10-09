"""费用预测与安全预留分离；节点证据必须独立、对齐并绑定执行参数。"""
from copy import deepcopy
import hashlib
import json

import pytest

from refractrouter.application_config import compile_configuration, execution_capacity_model
from refractrouter.configured_routing import configured_profile
from refractrouter.node_quality import import_node_quality
from refractrouter.node_routing import load_profile, route_nodes
from refractrouter.openai_compatible import output_token_limit
from refractrouter.routing_actions import action_binding
from refractrouter.task_budget import TaskCallBudget
from refractrouter.task_plan import validate_plan
from refractrouter.task_runtime import run_task, _shared_judge_forecast
from tests.test_live_execution import config, CompactClient
from tests.test_task_decomposition import example


def configuration():
    raw = config()
    raw.update(schemaVersion='refractagent-providers-v6', billingUnit='CNY',
               cashLimits={'production': 100, 'evaluation': 100})
    for model in raw['models']:
        model['pricing']['unit'] = 'CNY'
        model.update(contextWindow=1048576, maxOutputTokens=393216)
    raw['providers'][1]['deployment'] = 'trusted-cloud'
    raw['providers'][1]['trustPolicy'] = 'team'
    raw['trustPolicies'] = [{'id': 'team', 'residency': 'CN',
                            'auditLogging': True, 'allowsSensitiveData': True}]
    # 两条模拟现金路线，保留不同价格和独立的质量先验。
    raw['models'][1]['pricing'].update(inputPer1k=.003, outputPer1k=.004)
    raw['models'][2]['pricing'].update(inputPer1k=.003, outputPer1k=.004)
    return compile_configuration(raw)


def test_v6_runtime_uses_planned_output_without_reducing_safe_reservation():
    c = configuration()
    plan = validate_plan(example('single-answer'))
    original = configured_profile(c, c.manifest, plan.to_dict())
    result = run_task({'task': '核对材料后回答', 'mode': 'run', 'method': 'A',
        'qualityMin': 80, 'costMax': 100, 'latencyMaxMs': 300000, 'plan': plan.to_dict()},
        c.manifest, original, client=CompactClient(), production_limit=100,
        evaluation_limit=100, configured_application=True, configuration=c)
    assert result['status'] == 'completed', result['issues']
    model = c.manifest.candidates[0]
    basis = result['routing_profile']['forecast_basis']['answer'][model.model_id]
    assert basis['output_tokens'] == plan.contracts['answer']['capability']['expected_output_tokens']
    assert basis['output_tokens'] < model.max_output_tokens
    assert basis['input_tokens'] < basis['conservative_input_bound']
    assert basis['quality_source'] == 'global-prior-no-matching-node-evidence'
    call = next(r for r in result['calls'] if r['label'].startswith('answer'))
    assert call['reserved'] > result['routing']['prediction']['cost']
    assert call['status'] == 'billed'


def test_judge_expected_usage_does_not_change_capacity_protection():
    c = configuration()
    judge = c.manifest.judge
    workers = {m.model_id: m for m in c.manifest.candidates}
    safe = _shared_judge_forecast(judge, '原始任务', ['核对来源'], workers)
    expected = _shared_judge_forecast(judge, '原始任务', ['核对来源'], workers,
                                      expected_answer_tokens=1000)
    assert 0 < expected < safe / 10
    budget = TaskCallBudget(CompactClient(), 100, 100)
    reservation = budget.reserve(judge, [{'role': 'user', 'content': '审核请求'}],
                                 label='judge', category='evaluation')
    assert reservation.row['reserved'] >= output_token_limit(judge) / 1000 * judge.output_cost_per_1k
    assert reservation.row['reserved'] > expected


def bundle(c):
    workers = c.manifest.candidates
    contexts, observations = [], []
    for task_id, kind, risk in [('extract', 'extraction', 'low'), ('verify', 'verification', 'high')]:
        for repeat in range(1, 4):
            context = {'task_id': task_id, 'repeat': repeat, 'node_id': task_id}
            contexts.append(context)
            for i, model in enumerate(workers):
                prompt, output = f'相同的独立节点输入 {task_id}/{repeat}', f'{model.model_id} 的模拟产物'
                ih, oh = hashlib.sha256(prompt.encode()).hexdigest(), hashlib.sha256(output.encode()).hexdigest()
                # 确定性夹具验证差异化选模，不作为真实产品质量证据。
                score = (95 if i == 0 else 85) if kind == 'extraction' else (70 if i == 0 else 94)
                observations.append({**context, 'model_id': model.model_id, 'input': prompt, 'output': output,
                    'input_sha256': ih, 'output_sha256': oh, 'status': 'completed', 'finish_reason': 'stop',
                    'features': {'node_type': kind, 'difficulty': 'medium', 'risk': risk, 'input_budget_tokens': 16000},
                    'output_contract': {'format': 'text', 'fields': {'text': '节点产物'}},
                    'evaluation': {'method': 'independent-text-node-v1', 'status': 'completed',
                        'input_sha256': ih, 'output_sha256': oh, 'score': score, 'passed': True},
                    'usage': {'input_tokens': 100, 'output_tokens': 80, 'cached_input_tokens': 0, 'reasoning_tokens': 0},
                    'latency_ms': 10})
    return {'schema_version': 'node-quality-bundle-v1', 'kind': 'empirical',
        'action_bindings': {m.model_id: action_binding(m) for m in workers},
        'calibration_task_ids': ['extract', 'verify'], 'held_out_task_ids': ['held-out'],
        'observations': {'schema_version': 'node-observations-v1', 'kind': 'empirical',
                         'expected_contexts': contexts, 'observations': observations}}


def import_fixture(tmp_path, c, raw):
    path = tmp_path / 'fixture-not-real-evidence.json'
    path.write_text(json.dumps(raw, ensure_ascii=False))
    return import_node_quality(path, c)


def test_independent_node_matrix_changes_assignments_and_explains_uncovered_nodes(tmp_path):
    c = configuration()
    overrides, summary = import_fixture(tmp_path, c, bundle(c))
    raw = deepcopy(c.snapshot)
    for model in raw['models']:
        if model['id'] in overrides:
            model['routing']['profiles'] = overrides[model['id']]
    c = compile_configuration(raw)
    plan = example()
    plan['nodes'][0]['node_type'] = 'extraction'
    plan['nodes'][0]['contract']['capability']['risk'] = 'low'
    plan['nodes'][1]['node_type'] = 'verification'
    plan['nodes'][1]['contract']['capability']['risk'] = 'high'
    p = validate_plan(plan)
    profile = configured_profile(c, c.manifest, plan,
        input_forecasts={n.node_id: 16000 for n in p.nodes},
        cost_input_forecasts={n.node_id: 4000 for n in p.nodes})
    selected = route_nodes(p, load_profile(profile, c.manifest), method='A',
                          quality_min=80, cost_max=100, latency_max_ms=300000)
    assert selected['assignments']['cost'] == c.manifest.candidates[0].model_id
    assert selected['assignments']['risk'] == c.manifest.candidates[1].model_id
    evidence = profile['forecast_basis']['risk'][c.manifest.candidates[1].model_id]
    assert evidence['quality_source'] == 'independent-node-evaluation'
    assert evidence['quality_evidence']['samples'] == 3
    assert profile['forecast_basis']['answer'][c.manifest.candidates[0].model_id]['quality_source'] == 'global-prior-no-matching-node-evidence'
    assert summary['whole_task_scores_used'] is False


@pytest.mark.parametrize('mutation,reason', [
    (lambda b: b.update(kind='synthetic'), '真实节点'),
    (lambda b: b['observations']['observations'].pop(), 'incomplete matrix'),
    (lambda b: b['observations']['observations'][0]['evaluation'].update(method='whole-task-score'), 'independent node'),
    (lambda b: b['action_bindings'].update({'external-worker': '0' * 64}), '不匹配'),
    (lambda b: b.update(held_out_task_ids=['extract']), 'disjoint'),
])
def test_untrusted_or_unaligned_quality_cannot_silently_replace_priors(tmp_path, mutation, reason):
    c = configuration()
    raw = bundle(c)
    mutation(raw)
    with pytest.raises(ValueError, match=reason):
        import_fixture(tmp_path, c, raw)


def test_observed_semantic_failure_excludes_stratum_without_optimistic_fallback(tmp_path):
    c = configuration()
    raw = bundle(c)
    raw['observations']['observations'][0]['evaluation']['passed'] = False
    profiles, summary = import_fixture(tmp_path, c, raw)
    entry = next(row for row in profiles[c.manifest.candidates[0].model_id] if row['nodeType'] == 'extraction')
    assert entry['quality'] == 0
    assert entry['evidence']['excludedReason'] == 'semantic-criterion-failure'
    assert summary['excluded_strata']


def test_oracle_evaluation_requires_frozen_criteria_and_consistent_receipt(tmp_path):
    c = configuration()
    raw = bundle(c)
    for row in raw['observations']['observations']:
        row['evaluation'].update(method='independent-node-oracle-v1', score=100,
            oracle={'criteria_sha256': 'a' * 64, 'checks': [{'id': 'required-fact', 'passed': True}]})
    profiles, _ = import_fixture(tmp_path, c, raw)
    assert all(p['quality'] == 100 for rows in profiles.values() for p in rows)
    raw['observations']['observations'][0]['evaluation']['score'] = 95
    with pytest.raises(ValueError, match='oracle receipt'):
        import_fixture(tmp_path, c, raw)


def test_held_out_failure_vetoes_calibrated_stratum_without_fitting_test_scores(tmp_path):
    c = configuration()
    raw = bundle(c)
    raw['held_out_task_ids'] = ['held-out-extract', 'held-out-verify']
    validation = deepcopy(raw['observations'])
    validation['expected_contexts'] = [dict(task_id='held-out-' + r['task_id'], repeat=1, node_id=r['node_id'])
        for r in validation['expected_contexts'] if r['repeat'] == 1]
    validation['observations'] = [dict(r, task_id='held-out-' + r['task_id'])
        for r in validation['observations'] if r['repeat'] == 1]
    validation['observations'][0]['evaluation']['passed'] = False
    raw['held_out_observations'] = validation
    profiles, summary = import_fixture(tmp_path, c, raw)
    first = next(p for p in profiles[c.manifest.candidates[0].model_id] if p['nodeType'] == 'extraction')
    assert first['quality'] == 0
    assert first['evidence']['excludedReason'] == 'held-out-semantic-criterion-failure'
    assert first['evidence']['samples'] == 3 and first['evidence']['heldOutSamples'] == 1
    assert summary['strata'] == 3
    assert summary['held_out_policy'] == 'known-failure-veto-only-no-score-or-usage-fitting'
    # 其余分层的分数完全来自原校准样本，没有混入保留集。
    assert next(p for p in profiles[c.manifest.candidates[1].model_id]
                if p['nodeType'] == 'verification')['quality'] == 94
    raw['held_out_observations']['observations'].pop()
    with pytest.raises(ValueError, match='incomplete matrix'):
        import_fixture(tmp_path, c, raw)


def test_changed_input_band_cannot_erase_known_failure(tmp_path):
    c = configuration()
    raw = bundle(c)
    raw['observations']['observations'][0]['evaluation']['passed'] = False
    profiles, _ = import_fixture(tmp_path, c, raw)
    cfg = deepcopy(c.snapshot)
    for m in cfg['models']:
        if m['id'] in profiles:
            m['routing']['profiles'] = profiles[m['id']]
    c = compile_configuration(cfg)
    plan = example()
    plan['nodes'][0]['node_type'] = 'extraction'
    plan['nodes'][0]['contract']['capability']['risk'] = 'low'
    plan['nodes'][0]['contract']['capability']['input_budget_tokens'] = 131072
    p = configured_profile(c, c.manifest, plan)
    basis = p['forecast_basis']['cost'][c.manifest.candidates[0].model_id]
    assert basis['quality_prior'] == 0
    assert basis['quality_source'] == 'known-node-failure-outside-observed-input-range'
    assert basis['quality_evidence']['excludedReason'] == 'semantic-criterion-failure'


def test_independent_output_envelope_binding_rejects_other_execution_capacity(tmp_path):
    c = configuration()
    raw = bundle(c)
    raw['execution_action_bindings'] = {m.model_id: action_binding(execution_capacity_model(m))
                                      for m in c.manifest.candidates}
    import_fixture(tmp_path, c, raw)
    raw['execution_action_bindings'][c.manifest.candidates[0].model_id] = 'f' * 64
    with pytest.raises(ValueError, match='实际执行输出容量'):
        import_fixture(tmp_path, c, raw)
