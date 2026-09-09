"""独立评审使用确定性客户端，禁止真实模型调用。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.review_k3_outputs import main
from experiments.run_k3_baseline import read_bundle
from refractrouter.blind_review import digest, import_reviews
from refractrouter.k3_experiment import fixture_reviews
from refractrouter.k3_review_runner import review_plan, run_reviews, validate_review_input
from refractrouter.openai_compatible import ChatResponse, ModelInvocationError

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reports/v0.5-k3-resume-admission-2/output'
CALIBRATION = ROOT / 'reports/v0.5-glm-calibration/paid-admission-1/reviews.json'


@pytest.fixture
def case(tmp_path):
    state = read_bundle(SOURCE)
    calibration = json.loads(CALIBRATION.read_text())['calibration']
    public, key, forbidden = validate_review_input(state, calibration)
    plan = review_plan(public, forbidden)
    rows = fixture_reviews(public)['reviews']
    responses = [ChatResponse(json.dumps(r, ensure_ascii=False), 100, 100, 20, 60, 10, 1, 'stop', 'mock') for r in rows]
    class Client:
        calls = 0
        def complete(self, model, messages, *, json_mode):
            self.calls += 1
            assert model.api_model == 'glm-5.3' and json_mode
            material = json.loads(messages[1]['content'])['material']
            assert len(material['samples']) == 1
            assert set(material) == set(public)
            result = responses[self.calls - 1]
            if isinstance(result, Exception): raise result
            return result
    output = tmp_path / 'output'
    output.mkdir()
    return public, forbidden, plan, responses, Client(), output


def test_existing_material_preflight_never_constructs_client(tmp_path):
    with patch('experiments.review_k3_outputs.OpenAICompatibleClient') as client:
        assert main(['--input-dir', str(SOURCE), '--calibration-reviews', str(CALIBRATION),
                     '--output-dir', str(tmp_path / 'preflight')]) == 0
    client.assert_not_called()
    plan = json.loads((tmp_path / 'preflight/preflight.json').read_text())['plan']
    assert plan['max_calls'] == 21 and plan['production_calls'] == plan['max_retries'] == 0
    assert 'private' not in plan['requests'][0]['messages'][1]['content']


def test_all_scores_are_importable_and_costed(case):
    public, forbidden, plan, _, client, output = case
    result = run_reviews(public, plan, client, output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert result['status'] == 'review-ready' and client.calls == 21
    assert len(import_reviews(public, result['partial_reviews'], forbidden_models=forbidden)) == 21
    assert result['total_cost'] == pytest.approx(1.89)
    assert len((output / 'responses.ndjson').read_text().splitlines()) == 21


@pytest.mark.parametrize('failure', ['json', 'length', 'quote', 'unknown', 'timeout', 'wrong-id'])
def test_first_error_retains_partial_evidence_and_stops(case, failure):
    public, forbidden, plan, responses, client, output = case
    first = responses[1]
    if failure == 'json': responses[1] = replace(first, content='bad')
    elif failure == 'length': responses[1] = replace(first, finish_reason='length')
    elif failure == 'unknown': responses[1] = replace(first, input_tokens=0, output_tokens=0)
    elif failure == 'timeout': responses[1] = ModelInvocationError('timeout', '测试', 1, 100)
    else:
        row = json.loads(first.content)
        row['sample_id' if failure == 'wrong-id' else 'evidence_quote'] = '不存在'
        responses[1] = replace(first, content=json.dumps(row))
    result = run_reviews(public, plan, client, output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert result['status'] == 'blocked' and client.calls == 2
    assert result['scores'] is None and len(result['partial_reviews']['reviews']) == 1
    assert len((output / 'responses.ndjson').read_text().splitlines()) == 2
    assert (result['total_cost'] is None) == (failure in {'unknown', 'timeout'})


def test_plan_mutation_and_invalid_budget_cannot_call_models(case):
    public, forbidden, plan, _, client, output = case
    changed = deepcopy(plan)
    changed['requests'][0]['messages'][0]['content'] = 'changed'
    for limit in (True, 0, float('inf'), float('nan')):
        with pytest.raises(ValueError):
            run_reviews(public, plan, client, output, limit=limit, forbidden_models=forbidden)
    with pytest.raises(ValueError):
        run_reviews(public, changed, client, output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert client.calls == 0


def test_changed_calibration_or_simulation_cannot_be_used():
    state = read_bundle(SOURCE)
    calibration = json.loads(CALIBRATION.read_text())['calibration']
    state['simulation'] = True
    with pytest.raises(ValueError): validate_review_input(state, calibration)
    state['simulation'] = False
    calibration['reviewer']['id'] = 'other-model'
    with pytest.raises(ValueError): validate_review_input(state, calibration)


def test_approved_cli_saves_import_bundle(case, tmp_path):
    *_, client, _ = case
    args = ['--input-dir', str(SOURCE), '--calibration-reviews', str(CALIBRATION)]
    main([*args, '--output-dir', str(tmp_path / 'preflight')])
    with patch('experiments.review_k3_outputs.OpenAICompatibleClient', return_value=client) as factory:
        with pytest.raises(SystemExit):
            main([*args, '--output-dir', str(tmp_path / 'blocked'), '--execute-paid-run', '--max-review-cost', '10000'])
        factory.assert_not_called()
        assert main([*args, '--output-dir', str(tmp_path / 'live'), '--execute-paid-run',
                     '--max-review-cost', '10000', '--approved-preflight', str(tmp_path / 'preflight/preflight.json')]) == 0
    saved = json.loads((tmp_path / 'live/reviews.json').read_text())
    assert set(saved) == {'calibration', 'nodes'}
    assert saved['nodes']['packet_sha256'] == digest(read_bundle(SOURCE)['node_packet'])


def test_final_review_reuses_identity_and_keeps_task_completion_cap(case):
    _, forbidden, _, _, _, output = case
    state = read_bundle(SOURCE)
    calibration = json.loads(CALIBRATION.read_text())['calibration']
    state['stage'] = 'final-review-ready'
    state['final_packet'] = {**state['calibration']['public'], 'kind': 'final'}
    public, key, forbidden = validate_review_input(state, calibration)
    assert key == 'final'
    plan = review_plan(public, forbidden)
    assert plan['max_calls'] == 2
    rows = fixture_reviews(public)['reviews']
    for row in rows:
        row['task_checks']['substantive_comparison'] = False
    class Client:
        def complete(self, model, messages, *, json_mode):
            return ChatResponse(json.dumps(rows.pop(0)), 100, 100, 0, 0, 1, 1, 'stop', 'mock')
    result = run_reviews(public, plan, Client(), output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert result['status'] == 'review-ready'
    assert all(row['final_score'] <= 50 for row in result['scores'].values())
