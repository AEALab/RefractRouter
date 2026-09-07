from copy import deepcopy
from dataclasses import replace
import json
from unittest.mock import patch

import pytest

from experiments.run_blind_calibration import main
from experiments.run_k3_baseline import main as main_k3, read_bundle
from refractrouter.calibration_runner import calibration_plan, run_calibration
from refractrouter.k3_experiment import fixture_reviews
from refractrouter.openai_compatible import ChatResponse, ModelInvocationError


@pytest.fixture
def setup(tmp_path):
    source = tmp_path/'source'
    main_k3(['--output-dir', str(source)])
    state = read_bundle(source)
    bundle = state['calibration']
    forbidden = ['kimi-k3', 'deepseek-v4-flash', 'minimax-m3', 'deepseek-v4-pro']
    plan = calibration_plan(bundle, forbidden)
    reviews = fixture_reviews(bundle['public'])
    for row in reviews['reviews']:
        if bundle['private']['sample_records'][row['sample_id']] == 'missing-comparison':
            row['task_checks']['substantive_comparison'] = False
    responses = [ChatResponse(json.dumps(row, ensure_ascii=False), 100, 100, 20, 60, 10, 1, 'stop', 'mock')
                 for row in reviews['reviews']]
    class Client:
        calls = 0
        def complete(self, model, messages, *, json_mode):
            self.calls += 1
            assert model.api_model == 'glm-5.3'
            assert model.request_options == {'thinking': {'type': 'enabled'}}
            result = responses[self.calls-1]
            if isinstance(result, Exception):
                raise result
            return result
    output = tmp_path/'output'
    output.mkdir()
    return source, bundle, forbidden, plan, responses, Client(), output


def test_preflight_is_blind_and_has_no_client_or_production_calls(setup, tmp_path):
    source, bundle, forbidden, plan, *_ = setup
    assert len(plan['requests']) == 2 and plan['max_retries'] == 0
    prompt = json.dumps(plan['requests'], ensure_ascii=False)
    assert all(m not in prompt for m in forbidden)
    assert 'missing-comparison' not in prompt and 'positive_case_min' not in prompt
    assert plan['model']['json_mode_strategy'] == 'prompt-only'
    with patch('experiments.run_blind_calibration.OpenAICompatibleClient') as client:
        assert main(['--input-dir', str(source), '--output-dir', str(tmp_path/'preflight')]) == 0
    client.assert_not_called()
    assert json.loads((tmp_path/'preflight/summary.json').read_text())['actual_model_calls'] == 0


def test_two_mock_reviews_import_without_starting_production(setup):
    _, bundle, forbidden, plan, _, client, output = setup
    result = run_calibration(bundle, plan, client, output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert result['status'] == 'calibration-passed' and client.calls == 2
    assert result['production_calls'] == 0
    assert result['known_cost'] == pytest.approx(.18)
    assert result['submitted_reviews']['calibration']['reviewer'] == {'kind': 'model', 'id': 'glm-5.3'}
    assert len((output/'responses.ndjson').read_text().splitlines()) == 2


@pytest.mark.parametrize('failure', ['json', 'length', 'quote', 'unknown-usage', 'timeout', 'wrong-id'])
def test_failure_preserves_telemetry_and_stops_remaining_calls(setup, failure):
    _, bundle, forbidden, plan, responses, client, output = setup
    first = responses[0]
    if failure == 'json': responses[0] = replace(first, content='broken')
    elif failure == 'length': responses[0] = replace(first, finish_reason='length')
    elif failure == 'unknown-usage': responses[0] = replace(first, input_tokens=0, output_tokens=0)
    elif failure == 'timeout': responses[0] = ModelInvocationError('timeout', 'test', 1, 100)
    else:
        row = json.loads(first.content)
        row['sample_id' if failure == 'wrong-id' else 'evidence_quote'] = '不存在的值'
        responses[0] = replace(first, content=json.dumps(row))
    result = run_calibration(bundle, plan, client, output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert result['status'] == 'blocked' and client.calls == 1
    assert result['submitted_reviews'] is None
    raw = json.loads((output/'responses.ndjson').read_text())
    if failure in {'unknown-usage', 'timeout'}:
        assert result['total_cost'] is None and raw['cost'] is None
    else:
        assert result['known_cost'] > 0 and raw['content'] == responses[0].content


def test_budget_and_modified_plan_are_rejected_before_any_call(setup):
    _, bundle, forbidden, plan, _, client, output = setup
    for limit in [0, float('nan'), True]:
        with pytest.raises(ValueError):
            run_calibration(bundle, plan, client, output, limit=limit, forbidden_models=forbidden)
    changed = deepcopy(plan)
    changed['requests'][0]['messages'][0]['content'] = '泄漏预期答案'
    with pytest.raises(ValueError):
        run_calibration(bundle, changed, client, output, limit=1000, forbidden_models=forbidden)
    assert client.calls == 0


def test_live_cli_requires_matching_frozen_preflight(setup, tmp_path):
    source, _, _, _, _, client, _ = setup
    preflight = tmp_path/'preflight'
    main(['--input-dir', str(source), '--output-dir', str(preflight)])
    args = ['--input-dir', str(source), '--execute-paid-run', '--max-review-cost', '1000']
    with patch('experiments.run_blind_calibration.OpenAICompatibleClient', return_value=client) as factory:
        with pytest.raises(SystemExit):main([*args, '--output-dir', str(tmp_path/'blocked')])
        factory.assert_not_called()
        assert main([*args, '--output-dir', str(tmp_path/'live-mocked'),
                     '--approved-preflight', str(preflight/'preflight.json')]) == 0
    assert client.calls == 2


def test_high_score_on_negative_control_does_not_pass_calibration(setup):
    _, bundle, forbidden, plan, responses, client, output = setup
    for i, response in enumerate(responses):
        row = json.loads(response.content)
        row['task_checks'] = dict.fromkeys(row['task_checks'], True)
        responses[i] = replace(response, content=json.dumps(row))
    result = run_calibration(bundle, plan, client, output, limit=plan['reserved_cost'], forbidden_models=forbidden)
    assert result['status'] == 'blocked' and not result['calibration']['passed']
