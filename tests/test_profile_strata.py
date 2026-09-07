"""分层匹配、校准/测试隔离和完整候选矩阵的离线验证。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from refractrouter.node_routing import load_profile, route_nodes
from refractrouter.profile_calibration import build_stratified_profile
from refractrouter.task_plan import validate_plan
from tests.test_task_decomposition import example
from tests.test_text_tasks import MANIFEST, PROFILE, Client, live


def corpus():
    observations, contexts = [], []
    for repeat in range(1, 4):
        context = {'task_id': 'calibration-1', 'repeat': repeat, 'node_id': 'answer'}
        contexts.append(context)
        for model in MANIFEST.candidates:
            input_text, output = '固定原始任务与相同上游', model.model_id + ' 的模拟答案'
            ih = hashlib.sha256(input_text.encode()).hexdigest()
            oh = hashlib.sha256(output.encode()).hexdigest()
            observations.append({**context, 'model_id': model.model_id, 'input': input_text, 'output': output,
                'input_sha256': ih, 'output_sha256': oh, 'status': 'completed', 'finish_reason': 'stop',
                'features': {'node_type': 'generation', 'difficulty': 'medium', 'risk': 'high', 'input_budget_tokens': 16000},
                'output_contract': {'format': 'text', 'fields': {'text': '完整答案'}},
                'evaluation': {'method': 'independent-text-node-v1', 'status': 'completed',
                               'input_sha256': ih, 'output_sha256': oh, 'score': 90, 'passed': True},
                'usage': {'input_tokens': 100, 'output_tokens': 80, 'cached_input_tokens': 0, 'reasoning_tokens': 0},
                'latency_ms': 10})
    return {'schema_version': 'node-observations-v1', 'kind': 'synthetic',
            'expected_contexts': contexts, 'observations': observations}


def build(raw):
    return build_stratified_profile(raw, MANIFEST, calibration_task_ids=['calibration-1'], test_task_ids=['test-1'])


def test_stratified_calibration_preserves_synthetic_label_and_matches_features():
    profile = build(corpus())
    assert profile['kind'] == 'synthetic' and profile['schema_version'] == 'node-routing-profile-v2'
    assert len(profile['candidates']) == 3
    assert all(p['samples'] == 3 for p in profile['candidates'])
    profiles = load_profile(profile, MANIFEST)
    plan = validate_plan(example('single-answer'))
    assert route_nodes(plan, profiles, method='A', quality_min=80, cost_max=100, latency_max_ms=100)['status'] == 'selected'
    raw = example('single-answer')
    raw['nodes'][0]['contract']['capability']['risk'] = 'low'
    assert route_nodes(validate_plan(raw), profiles, method='A', quality_min=80, cost_max=100, latency_max_ms=100)['status'] == 'no-feasible-route'
    raw['nodes'][0]['contract']['capability']['risk'] = 'high'
    raw['nodes'][0]['contract']['capability']['input_budget_tokens'] = 65536
    assert route_nodes(validate_plan(raw), profiles, method='A', quality_min=80, cost_max=100, latency_max_ms=100)['status'] == 'no-feasible-route'


@pytest.mark.parametrize('mutation', [
    lambda c: c['observations'].pop(),
    lambda c: c['observations'][0].update(task_id='test-1'),
    lambda c: c['observations'][0].update(input='改动上游但不更新哈希'),
    lambda c: c['observations'][0]['evaluation'].update(score=None),
    lambda c: c['observations'][0]['evaluation'].update(method='whole-task-score'),
    lambda c: c['observations'][0].update(status='unavailable'),
    lambda c: c['observations'][0].update(finish_reason='length'),
    lambda c: c['observations'][0]['usage'].update(input_tokens=True),
])
def test_unavailable_unaligned_or_held_out_observations_are_rejected(mutation):
    raw = corpus()
    mutation(raw)
    with pytest.raises(ValueError):
        build(raw)


def test_different_but_correctly_hashed_upstream_is_not_an_aligned_matrix():
    raw = corpus()
    row = raw['observations'][0]
    row['input'] = '来自另一个上游模型的产物'
    row['input_sha256'] = hashlib.sha256(row['input'].encode()).hexdigest()
    row['evaluation']['input_sha256'] = row['input_sha256']
    with pytest.raises(ValueError, match='different upstream'):
        build(raw)


def test_profile_overlapping_intervals_are_rejected():
    raw = build(corpus())
    extra = deepcopy(raw['candidates'][0])
    extra.update(input_min_tokens=16000, input_max_tokens=65536)
    raw['candidates'].append(extra)
    with pytest.raises(ValueError, match='overlapping'):
        load_profile(raw, MANIFEST)


def test_different_models_handoff_under_stratified_selection():
    raw = example()
    raw['nodes'][1]['contract']['capability']['risk'] = 'high'
    rows = []
    for kind, risk, selected in [('synthesis', 'medium', 'cheap'), ('synthesis', 'high', 'strong'), ('generation', 'high', 'mid')]:
        for model in MANIFEST.candidates:
            rows.append({'node_type': kind, 'model_id': model.model_id, 'difficulty': 'medium', 'risk': risk,
                'input_min_tokens': 8193, 'input_max_tokens': 32769, 'quality': 90 if model.model_id == selected else 50,
                'cost': 1, 'latency_ms': 1, 'samples': 3})
    profile = {**PROFILE, 'schema_version': 'node-routing-profile-v2', 'kind': 'empirical', 'candidates': rows}
    from refractrouter.task_runtime import run_task
    from tests.test_text_tasks import REQUEST
    client = Client()
    result = run_task({**REQUEST, 'plan': raw, 'maxConcurrency': 2}, MANIFEST, profile,
                      client=client, production_limit=100, evaluation_limit=100)
    assert result['status'] == 'completed'
    assert result['routing']['assignments'] == {'cost': 'cheap', 'risk': 'strong', 'answer': 'mid'}
    answer_payload = next(json.loads(messages[-1]['content']) for _, messages in client.calls
                          if json.loads(messages[-1]['content']).get('node_id') == 'answer')
    assert set(answer_payload['upstream']) == {'cost', 'risk'}
    assert all(n['contract_status'] == 'structure-valid' for n in result['nodes'])


def test_known_semantic_failure_excludes_entire_model_stratum():
    raw = corpus()
    failed_model = raw['observations'][0]['model_id']
    raw['observations'][0]['evaluation']['passed'] = False
    profile = build(raw)
    assert failed_model not in {row['model_id'] for row in profile['candidates']}
    assert profile['exclusions'][0]['reason'] == 'semantic-criterion-failure'
