import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from experiments.replay_node_contracts import ARCHIVE, load_cases, main
from experiments.run_real_v0_1 import CostLedger, NodeQualityRecorder
from refractrouter.adapters import FakeModelAdapter, OpenAICompatibleAdapter
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.graph_executor import GraphExecutor
from refractrouter.manifest import load_model_manifest
from refractrouter.node_contracts import output_schema
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.scoring import node_contract_checks
from tests.test_node_quality import JudgeClient, fixture
from tests.test_openai_compatible import SequenceTransport, real_model, success_response
from refractrouter.node_judge import IndependentNodeJudge

ROOT = Path(__file__).resolve().parents[1]


def task():
    return load_benchmark_dataset(ROOT / 'data/benchmarks/v0.1.json', ROOT / 'data/tasks',
                                  ROOT / 'data/source_packs').all_tasks[0]


@pytest.mark.parametrize('case', load_cases(), ids=lambda c: c['case_id'])
def test_saved_contract_failures_are_rejected_without_rewriting_output(case):
    current = task()
    node = next(n for n in current.nodes if n.node_id == case['node_id'])
    transport = SequenceTransport([success_response(case['original_output'])])
    adapter = OpenAICompatibleAdapter(OpenAICompatibleClient(
        transport=transport, environment={'TEST_API_KEY': 'test'}, max_retries=0))
    result = adapter.invoke(current, node, node.prompt_template, case['upstream'], real_model())
    assert result.status == 'failed'
    assert result.failure_type in {'invalid-json', 'invalid-evidence'}
    assert result.output == case['original_output']
    assert result.cost > 0 and result.output_tokens == 25
    assert len(transport.calls) == 1
    assert node_contract_checks(current, node, result.output, case['upstream'])['score_cap'] == 0


def test_valid_evidence_survives_and_missing_fields_stop_handoff():
    current, registry, run, context = fixture()
    node = current.nodes[4]
    output = json.loads(context[node.node_id])
    assert OpenAICompatibleAdapter._output_failure(current, node, json.dumps(output), context) is None
    for field in ('title', 'claim', 'source_id', 'content_hash'):
        broken = json.loads(json.dumps(output))
        del broken['evidence'][0][field]
        assert OpenAICompatibleAdapter._output_failure(current, node, json.dumps(broken), context) == 'invalid-evidence'
    output['evidence'][0]['claim'] = '   '
    assert OpenAICompatibleAdapter._output_failure(current, node, json.dumps(output), context) == 'invalid-evidence'


def test_generation_request_scopes_html_to_final_artifact_and_preserves_claim_contract():
    current = task()
    node = current.nodes[4]
    prompt = OpenAICompatibleAdapter._user_prompt(current, node, node.prompt_template)
    task_payload = json.loads(prompt.split('TASK\n')[1].split('\n\nNODE REQUEST')[0])
    assert 'output_constraints' not in task_payload
    assert 'standalone HTML' in task_payload['final_artifact_requirements']['constraints']
    schema = output_schema('generation')
    assert set(schema['properties']['evidence']['items']['required']) == {'source_id', 'title', 'content_hash', 'claim'}
    assert prompt.endswith('Do not return HTML, Markdown fences, or the schema itself.')


def test_m3_prompt_only_strategy_omits_unverified_response_format():
    manifest = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    assert manifest.candidate_registry().get('mid').json_mode_strategy == 'prompt-only'
    for strategy, expected in [('prompt-only', False), ('json-object-hint', True)]:
        transport = SequenceTransport([success_response()])
        client = OpenAICompatibleClient(transport=transport, environment={'TEST_API_KEY': 'test'})
        client.complete(replace(real_model(), json_mode_strategy=strategy),
                        [{'role': 'user', 'content': 'Return JSON.'}], json_mode=True)
        assert ('response_format' in transport.calls[0]['payload']) == expected


def test_unavailable_execution_is_not_a_known_zero_quality_candidate(tmp_path):
    current, registry, run, context = fixture()
    client = JudgeClient()
    judge = IndependentNodeJudge(client, replace(registry.strongest(), role='judge'))
    recorder = NodeQualityRecorder(judge, CostLedger('USD', 100, 100, 4000, 8000, 8192), tmp_path)
    for failure, expected_state, expected_score in [('timeout', 'unavailable', None),
                                                   ('invalid-json', 'contract-rejected', 0.0)]:
        result = replace(run.node_results[0], status='failed', failure_type=failure, output='')
        row = recorder.record(current, current.nodes[0], result, context, repeat=1, stage='probe')
        assert row['evaluation_state'] == expected_state
        assert row['evaluation']['final_score'] == expected_score
        assert not row['eligible']
    assert not client.payloads


def test_replay_preflight_has_seven_calls_and_no_client(tmp_path):
    with patch('experiments.replay_node_contracts.OpenAICompatibleClient') as client:
        assert main(['--output-dir', str(tmp_path)]) == 0
    client.assert_not_called()
    preflight = json.loads((tmp_path / 'preflight.json').read_text())
    assert preflight['call_plan']['total_model_calls'] == 7
    assert preflight['call_plan']['judge_model_calls'] == 0
    assert preflight['cost_estimates']['production_upper_estimate'] > 0
    with pytest.raises(ValueError, match='fresh'):
        main(['--output-dir', str(tmp_path)])


def test_replay_stops_after_first_contract_failure_and_preserves_billed_result(tmp_path):
    class SavedFailureAdapter:
        calls = 0
        def invoke(self, task, node, prompt, context, model):
            self.calls += 1
            from refractrouter.schemas import NodeResult
            return NodeResult(node.node_id, node.node_type, model.model_id, '<html>bad</html>',
                              20, 10, .25, 10, billing_unit='AFP', status='failed', failure_type='invalid-json')
    adapter = SavedFailureAdapter()
    with patch.object(OpenAICompatibleAdapter, 'invoke', side_effect=adapter.invoke):
        assert main(['--output-dir', str(tmp_path), '--execute-paid-run',
                     '--max-production-cost', '1000', '--max-evaluation-cost', '0']) == 0
    assert adapter.calls == 1
    summary = json.loads((tmp_path / 'benchmark-summary.json').read_text())
    assert summary['status'] == 'incomplete' and summary['production_afp'] == .25
    assert summary['completed_calls'] == 1 and summary['planned_calls'] == 7
    assert '<html>bad</html>' in (tmp_path / 'replay-results.ndjson').read_text()


def test_replay_all_seven_contracts_with_fake_adapter(tmp_path):
    registry = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json').candidate_registry()
    class FullAdapter(FakeModelAdapter):
        calls = 0
        def invoke(self, task, node, prompt, context, model):
            self.calls += 1
            return super().invoke(task, node, prompt, context, replace(model, capability=1))
    adapter = FullAdapter(registry)
    with patch.object(OpenAICompatibleAdapter, 'invoke', side_effect=adapter.invoke):
        assert main(['--output-dir', str(tmp_path), '--execute-paid-run',
                     '--max-production-cost', '1000', '--max-evaluation-cost', '0']) == 0
    assert adapter.calls == 7
    summary = json.loads((tmp_path / 'benchmark-summary.json').read_text())
    assert summary['status'] == 'complete' and 'unassessed' in summary['interpretation']


def test_replay_rejects_insufficient_budget_before_invoking_client(tmp_path):
    with patch('experiments.replay_node_contracts.OpenAICompatibleClient') as client:
        with pytest.raises(ValueError, match='budget'):
            main(['--output-dir', str(tmp_path), '--execute-paid-run',
                  '--max-production-cost', '0.01', '--max-evaluation-cost', '0'])
    client.assert_not_called()


def test_production_bound_counts_fixed_sweeps_and_worst_case_composed_routes():
    from experiments.run_real_v0_1 import call_plan, estimate_costs
    manifest = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    plan = call_plan([], [task()], 3, 3, False)
    assert plan['fixed_calls_per_candidate'] == 42
    assert plan['production_model_calls'] == 168
    costs = estimate_costs(plan, manifest, 4000, 8192)
    prices = [(4000*m.input_cost_per_1k + 8192*m.output_cost_per_1k)/1000 for m in manifest.candidates]
    assert costs['production_upper_estimate'] == round(42*sum(prices) + 42*max(prices), 2)
    assert costs['production_upper_estimate'] == 716.89
    assert costs['total_upper_estimate'] == 1979.87
    # Price ordering must weight input/output token counts, not add their unit rates.
    models = tuple(replace(m, input_cost_per_1k=2, output_cost_per_1k=0) if m.model_id == 'cheap'
                   else replace(m, input_cost_per_1k=0, output_cost_per_1k=1) if m.model_id == 'mid'
                   else m for m in manifest.models)
    bound = estimate_costs({'production_model_calls': 1, 'judge_model_calls': 0}, replace(manifest, models=models), 1, 10000)
    assert bound['production_upper_estimate'] == 10
