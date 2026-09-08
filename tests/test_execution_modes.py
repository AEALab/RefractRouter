from dataclasses import replace
import hashlib
import json
from unittest.mock import patch

import pytest

from experiments.run_execution_modes import main, select_complete_best
from refractrouter.adapters import OpenAICompatibleAdapter
from refractrouter.benchmark import BenchmarkObservation
from refractrouter.execution_modes import one_shot_task, run_one_shot
from refractrouter.judge import IndependentJudge
from refractrouter.model_registry import ModelRegistry
from refractrouter.openai_compatible import OpenAICompatibleClient
from tests.test_evidence_state import fixture
from tests.test_node_quality import JudgeClient
from tests.test_openai_compatible import SequenceTransport, real_model, success_response


def test_one_shot_is_one_real_request_with_complete_sources_and_same_final_judge():
    task, registry, _, dag, _ = fixture()
    transport = SequenceTransport([success_response(dag.final_output)])
    adapter = OpenAICompatibleAdapter(OpenAICompatibleClient(
        transport=transport, environment={'TEST_API_KEY': 'fixture'}, max_retries=0))
    result = run_one_shot(task, 'cheap', adapter, ModelRegistry([real_model()]))
    assert len(transport.calls) == len(result.node_results) == 1
    assert not result.failure_types and result.final_output == dag.final_output
    request = transport.calls[0]['payload']
    assert 'response_format' not in request
    prompt = request['messages'][1]['content']
    for source in task.source_documents:
        assert source.content in prompt and source.content_hash in prompt
    judge = IndependentJudge(JudgeClient(), replace(registry.strongest(), role='judge'))
    assert judge.evaluate(one_shot_task(task), result).final_score == judge.evaluate(task, dag).final_score


def test_preflight_is_zero_call_and_rejects_overwrite(tmp_path):
    with patch('experiments.run_execution_modes.OpenAICompatibleClient') as client:
        assert main(['--output-dir', str(tmp_path)]) == 0
    client.assert_not_called()
    preflight = json.loads((tmp_path/'preflight.json').read_text())
    assert preflight['model_calls'] == 0
    assert preflight['call_plan']['production_model_calls'] == 52
    assert preflight['call_plan']['judge_model_calls'] == 28
    assert preflight['call_plan']['total_model_calls'] == 80
    assert preflight['cost_estimates']['total_upper_estimate'] == 655.76
    assert preflight['inputs']['tasks']['A']['execution_mode'] == 'one-shot'
    with pytest.raises(SystemExit):
        main(['--output-dir', str(tmp_path)])


def test_three_repeat_simulation_has_complete_matrix_pairs_and_unique_accounting(tmp_path):
    with patch('experiments.run_execution_modes.OpenAICompatibleClient') as client:
        assert main(['--mode', 'offline', '--repeats', '3', '--output-dir', str(tmp_path)]) == 0
    client.assert_not_called()
    summary = json.loads((tmp_path/'benchmark-summary.json').read_text())
    assert summary['status'] == 'complete' and summary['simulation']
    assert not summary['empirical_evidence'] and summary['costs']['actual_paid_cost'] == 0
    assert summary['node_matrix'] == {'expected_cells': 63, 'recorded_cells': 63}
    assert all(gate['decision'] == 'Simulation-only' for gate in summary['go_gates'].values())
    calls = json.loads((tmp_path/'simulation-calls.json').read_text())
    assert calls == {'production': 156, 'evaluation': 84, 'actual_network_calls': 0, 'actual_paid_cost': 0}
    for repeat in range(1, 4):
        decision = json.loads((tmp_path/f'selection-report_001-{repeat}.json').read_text())
        assert decision['route_executable']
        # All fixture scores tie; price chooses Flash at all nodes. Do not force a mixture.
        assert set(decision['assignments'].values()) == {'cheap'}
    rows = [json.loads(p.read_text()) for p in tmp_path.glob('runs/*/*/*.json')]
    unique = [r for r in rows if not r['strategy'].endswith('-oracle')]
    assert len(unique) == 21 and len(rows) == 27
    probes = [json.loads(line) for line in (tmp_path/'node-evaluations.ndjson').read_text().splitlines()]
    assert summary['costs']['production'] == pytest.approx(
        sum(r['result']['total_cost'] for r in unique) + sum(r['node_result']['cost'] for r in probes))
    assert summary['costs']['evaluation'] == pytest.approx(
        sum(r['judge']['cost'] for r in unique) + sum(r['evaluation']['cost'] for r in probes))
    index = json.loads((tmp_path/'evidence-index.json').read_text())
    for path, digest in index['artifacts'].items():
        assert hashlib.sha256((tmp_path/path).read_bytes()).hexdigest() == digest


def test_family_baseline_is_unavailable_if_any_candidate_failed():
    task, registry, _, result, _ = fixture()
    judge = IndependentJudge(JudgeClient(), replace(registry.strongest(), role='judge')).evaluate(task, result)
    good = BenchmarkObservation(task.task_id, 1, 'dag:good', result, judge)
    bad = replace(good, strategy='dag:bad', judge=None, judge_error='timeout')
    assert select_complete_best([good, bad]) is None
    assert select_complete_best([good]) == good
    assert select_complete_best([]) is None


@pytest.mark.parametrize('kind', ['malformed', 'truncated', 'non-finite'])
def test_failed_final_judge_is_billed_and_preserved_before_next_budget_check(kind):
    from experiments.run_real_v0_1 import CostLedger, _evaluate_with_budget
    from refractrouter.openai_compatible import model_response_cost
    task, registry, _, result, _ = fixture()
    client = JudgeClient()
    valid = client.complete(None, [{}, {'content': json.dumps({
        'sources': [{'source_id': 'source_001'}], 'expected_claims': task.expected_claims})}])
    if kind == 'malformed':
        response = replace(valid, content='{')
    elif kind == 'truncated':
        response = replace(valid, finish_reason='length')
    else:
        payload = json.loads(valid.content)
        payload['scores']['analysis_depth'] = float('nan')
        response = replace(valid, content=json.dumps(payload))
    client.complete = lambda *args, **kwargs: response
    model = replace(registry.strongest(), role='judge')
    ledger = CostLedger('USD', 100, 100, 4000, 8000, 8192)
    saved = []
    judge = IndependentJudge(client, model)
    evaluation, error = _evaluate_with_budget(judge, task, result, ledger, saved.append)
    assert evaluation is None and error in {'invalid-final-judge-response', 'final-judge-output-truncated'}
    assert ledger.evaluation_spent == model_response_cost(model, response)
    assert saved[0]['response_content'] == response.content and saved[0]['request_id'] == response.request_id
    ledger.evaluation_limit = ledger.evaluation_spent
    assert _evaluate_with_budget(judge, task, result, ledger)[1] == 'evaluation-budget-exhausted'


@pytest.mark.parametrize('extra', [
    ['--execute-paid-run'],
    ['--execute-paid-run', '--max-production-cost', '1', '--max-evaluation-cost', '1'],
    ['--execute-paid-run', '--max-production-cost', '300', '--max-evaluation-cost', '500'],
    ['--mode', 'offline', '--execute-paid-run'],
    ['--max-retries', '1'], ['--repeats', '4'],
    ['--selection-policy', 'all-candidates-required-v1'],
])
def test_invalid_paid_requests_never_construct_network_client(tmp_path, monkeypatch, extra):
    monkeypatch.delenv('REFRACTROUTER_EXECUTION_MODES_HOST', raising=False)
    monkeypatch.setenv('CODEX_ARK_API_KEY', 'fixture-only')
    with patch('experiments.run_execution_modes.OpenAICompatibleClient') as client:
        with pytest.raises(SystemExit):
            main(['--output-dir', str(tmp_path), *extra])
    client.assert_not_called()
