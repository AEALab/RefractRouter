from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from experiments.run_real_v0_1 import (
    CostLedger, NodeQualityRecorder, build_task_strategy_bundle, main,
)
from refractrouter.adapters import FakeModelAdapter, OpenAICompatibleAdapter
from refractrouter.graph_executor import GraphExecutor
from refractrouter.judge import DIMENSION_LIMITS
from refractrouter.manifest import load_model_manifest
from refractrouter.node_judge import IndependentNodeJudge, NODE_LIMITS, NodeJudgeError
from refractrouter.openai_compatible import ChatResponse
from refractrouter.scoring import node_contract_checks
from tests.helpers import make_registry, make_task

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    task, registry = make_task(), make_registry()
    result = GraphExecutor(task, FakeModelAdapter(registry), registry).execute(
        {n.node_id: 'strong-model' for n in task.nodes}, 'strong-all')
    return task, registry, result, {r.node_id: r.output for r in result.node_results}


def response(data, finish='stop'):
    return ChatResponse(json.dumps(data), 100, 50, 0, 0, 12, 1, finish, 'test-request')


def node_response(payload):
    return dict(scores=dict(NODE_LIMITS), rationale='具体内容与冻结来源一致。',
                source_assessments=[dict(source_id=s, supported=True, explanation='原文支持。')
                                    for s in payload['assessed_source_ids']])


class JudgeClient:
    def __init__(self):
        self.payloads = []

    def complete(self, model, messages, **kwargs):
        payload = json.loads(messages[1]['content'])
        self.payloads.append(payload)
        if 'candidate_output' in payload:
            data = node_response(payload)
        else:
            data = dict(scores=DIMENSION_LIMITS, rationale='Matches sources.', claim_support=[
                dict(claim=c, source_ids=[payload['sources'][0]['source_id']],
                     supported=True, explanation='Supported.') for c in payload['expected_claims']])
        return response(data)


def test_contracts_reject_spam_and_bad_identity_but_accept_chinese_analysis():
    task, _, run, context = fixture()
    node = task.nodes[3]
    output = json.loads(context[node.node_id])
    output['analysis'] = '应按约束选择方案，并记录证据覆盖范围与局限。'
    assert node_contract_checks(task, node, json.dumps(output), context)['score_cap'] == 100
    assert node_contract_checks(task, node, 'analysis tradeoff recommendation source_001 ' * 50)['score_cap'] == 0
    output['evidence'].append(output['evidence'][0])
    assert node_contract_checks(task, node, json.dumps(output))['score_cap'] == 0
    output['evidence'].pop()
    output['evidence'][0]['content_hash'] = 'invented'
    assert node_contract_checks(task, node, json.dumps(output))['score_cap'] == 0
    assert node_contract_checks(task, task.nodes[4], '{"sections": null}')['score_cap'] == 0
    rendered = context['render_html']
    for section in task.required_sections:
        rendered = rendered.replace(f'<h2>{section}</h2>', f'<p>{section}</p>')
    assert node_contract_checks(task, task.nodes[5], rendered)['score_cap'] == 0


def test_verification_scores_verdict_against_actual_input():
    task, _, _, context = fixture()
    node = task.nodes[-1]
    valid = json.dumps(dict(valid=True, issues=[], summary='验证通过。'))
    invalid = json.dumps(dict(valid=False, issues=['Missing citation'], summary='缺少引用。'))
    assert node_contract_checks(task, node, valid, context)['score_cap'] == 100
    # A mechanically valid report can still have semantic defects. The judge decides
    # whether this finding is accurate; this check supplies only a validity cap.
    assert node_contract_checks(task, node, invalid, context)['score_cap'] == 100
    broken = {'render_html': '<html>incomplete'}
    assert node_contract_checks(task, node, invalid, broken)['score_cap'] == 100
    assert node_contract_checks(task, node, valid, broken)['score_cap'] == 0
    assert OpenAICompatibleAdapter._output_failure(task, node, invalid, broken) is None
    assert OpenAICompatibleAdapter._output_failure(task, node, valid, broken) == 'incorrect-verification'


def test_distinct_claims_from_one_source_are_eligible_without_inflating_source_count():
    task, _, _, context = fixture()
    node = task.nodes[2]
    output = json.loads(context[node.node_id])
    first = output['evidence'][0]
    output['evidence'].append({**first, 'claim': 'Another distinct fact from the same source.'})
    checks = node_contract_checks(task, node, json.dumps(output))
    assert checks['score_cap'] == 100
    assert len(checks['checks']['unique_sources']) == 3
    # Identity checks admit distinct facts; semantic support is decided by the judge.
    output['evidence'].append({**first, 'claim': '  ' + first['claim'].upper() + '  '})
    assert node_contract_checks(task, node, json.dumps(output))['score_cap'] == 0


def test_node_judge_is_blind_and_grounding_requires_semantic_support():
    task, registry, run, context = fixture()
    client = JudgeClient()
    judge = IndependentNodeJudge(client, replace(registry.strongest(), model_id='judge', role='judge'))
    result = judge.evaluate(task, task.nodes[2], run.node_results[2], context)
    assert result['final_score'] == 100
    payload = client.payloads[0]
    assert not {'model_id', 'price', 'strategy', 'capability'} & payload.keys()
    assert set(payload['upstream']) == set(task.nodes[2].parents)
    assert 'strong-model' not in json.dumps(payload)
    data = node_response(payload)
    for source in data['source_assessments']:
        source['supported'] = False
    client.complete = lambda *a, **kw: response(data)
    assert judge.evaluate(task, task.nodes[2], run.node_results[2], context)['final_score'] == 70


@pytest.mark.parametrize('bad_score', [True, float('nan'), float('inf'), -1, 41])
def test_invalid_judge_scores_preserve_billed_telemetry(bad_score):
    task, registry, run, context = fixture()
    client = JudgeClient()
    data = dict(scores={**NODE_LIMITS, 'correctness': bad_score}, rationale='x', source_assessments=[])
    client.complete = lambda *a, **kw: response(data)
    judge = IndependentNodeJudge(client, replace(registry.strongest(), role='judge'))
    with pytest.raises(NodeJudgeError) as exc:
        judge.evaluate(task, task.nodes[0], run.node_results[0], context)
    assert exc.value.telemetry['cost'] > 0
    assert exc.value.failure_type == 'invalid-node-judge-response'


def test_recorder_budget_failure_and_truncation_never_select_cheap_fallback(tmp_path):
    task, registry, run, context = fixture()
    client = JudgeClient()
    judge = IndependentNodeJudge(client, replace(registry.strongest(), role='judge'))
    ledger = CostLedger('USD', 100, 0, 4000, 8000, 8192)
    recorder = NodeQualityRecorder(judge, ledger, tmp_path)
    row = recorder.record(task, task.nodes[0], run.node_results[0], context, repeat=1, stage='probe')
    assert row['evaluation']['error'] == 'evaluation-budget-exhausted'
    assert not row['eligible'] and not client.payloads
    ledger.evaluation_limit = 100
    client.complete = lambda *a, **kw: response({}, finish='length')
    row = recorder.record(task, task.nodes[0], run.node_results[0], context, repeat=1, stage='probe')
    assert row['evaluation']['error'] == 'node-judge-output-truncated'
    assert ledger.evaluation_spent == row['evaluation']['cost'] > 0
    bundle = build_task_strategy_bundle(task, registry, FakeModelAdapter(registry), include_learned=False,
        node_evaluator=lambda *a: {'evaluation': {'error': 'missing', 'final_score': None},
                                  'eligible': False, 'node_id': a[1].node_id, 'model_id': a[2].model_id})
    assert not bundle.matrix_complete
    assert bundle.results['node-oracle'].model_assignments == {}
    assert bundle.results['node-oracle'].failure_types == ('node-quality-incomplete',)


def test_node_selection_follows_semantic_scores_not_price_tier():
    task, registry, _, _ = fixture()
    preferred = {n.node_id: registry.list()[i % 3].model_id for i, n in enumerate(task.nodes)}
    def evaluate(task, node, result, context):
        return dict(node_id=node.node_id, model_id=result.model_id, eligible=True,
                    evaluation=dict(error=None, final_score=95 if result.model_id == preferred[node.node_id] else 50))
    bundle = build_task_strategy_bundle(task, registry, FakeModelAdapter(registry),
                                       include_learned=False, node_evaluator=evaluate)
    assert bundle.results['node-oracle'].model_assignments == preferred
    assert sum(row['selected'] for row in bundle.node_matrix) == 7


def test_three_repeat_run_persists_all_cells_singles_and_matched_comparisons(tmp_path):
    manifest_path = ROOT / 'data/model-manifests/volcengine-agent-plan.json'
    manifest = load_model_manifest(manifest_path)
    registry = manifest.candidate_registry()
    client = JudgeClient()
    class FullAdapter(FakeModelAdapter):
        calls = 0
        def invoke(self, task, node, prompt, context, model):
            self.calls += 1
            return super().invoke(task, node, prompt, context, replace(model, capability=1.0))
    adapter = FullAdapter(registry)
    with patch('experiments.run_real_v0_1.OpenAICompatibleClient', return_value=client), \
         patch('experiments.run_real_v0_1.OpenAICompatibleAdapter', return_value=adapter), \
         patch.dict('os.environ', {manifest.candidates[0].api_key_env: 'offline-test-only'}):
        assert main(['--phase', 'dry-run', '--repeats', '3', '--manifest', str(manifest_path),
                     '--output-dir', str(tmp_path), '--execute-paid-run', '--max-production-cost', '1200',
                     '--max-evaluation-cost', '1300', '--max-retries', '0']) == 0
    matrix = json.loads((tmp_path / 'node-quality-matrix.json').read_text())['rows']
    assert len(matrix) == 63
    assert adapter.calls == 168
    assert len(client.payloads) == 78
    assert sum(r['selected'] for r in matrix) == 21
    assert all(r['eligible'] for r in matrix)
    for repeat in range(1, 4):
        for node_id in {r['node_id'] for r in matrix}:
            cells = [r for r in matrix if r['repeat'] == repeat and r['node_id'] == node_id]
            assert len(cells) == 3
            assert len({r['upstream_sha256'] for r in cells}) == 1
            assert len({r['api_model'] for r in cells}) == 3
            for cell in cells:
                assert cell['output_sha256'] == hashlib.sha256(cell['node_result']['output'].encode()).hexdigest()
    assert len(list((tmp_path / 'single-models').rglob('*.json'))) == 9
    report = json.loads((tmp_path / 'strategy-comparisons.json').read_text())
    assert len(report['pairs']) == 12
    assert all(row['included'] for row in report['pairs'])
    assert all(s['pairs'] == 3 and s['task_count'] == 1 and s['repeats'] == [1, 2, 3]
               for s in report['summaries'].values())
    summary = json.loads((tmp_path / 'benchmark-summary.json').read_text())
    assert summary['status'] == 'complete'
    assert summary['node_matrix'] == dict(expected_cells=63, recorded_cells=63)
    # Equal semantic scores legitimately select the cheapest single model; never force a mixture.
    assert summary['oracle_gate']['decision'] == 'Insufficient-evidence'
    assert not summary['oracle_gate']['routing_change_observed']
    assert len((tmp_path / 'node-evaluations.ndjson').read_text().splitlines()) == 63
    index = json.loads((tmp_path / 'evidence-index.json').read_text())['artifacts']
    assert index['node-quality-matrix.json'] == hashlib.sha256((tmp_path / 'node-quality-matrix.json').read_bytes()).hexdigest()


def test_paired_statistics_exclude_failures_and_never_pair_across_repeats():
    from refractrouter.benchmark import BenchmarkObservation
    from refractrouter.comparisons import paired_comparisons
    _, _, run, _ = fixture()
    observations = []
    for repeat, delta in ((1, 2), (2, 8)):
        observations.append(BenchmarkObservation(run.task_id, repeat, 'task-oracle',
                            replace(run, task_score=100), judge=SimpleNamespace(final_score=80)))
        observations.append(BenchmarkObservation(run.task_id, repeat, 'node-oracle',
                            replace(run, task_score=100), judge=SimpleNamespace(final_score=80 + delta)))
    observations.append(BenchmarkObservation(run.task_id, 3, 'node-oracle',
                        replace(run, task_score=100), judge=SimpleNamespace(final_score=100)))
    stats = paired_comparisons(observations)['summaries']['node-oracle vs task-oracle']
    assert stats['pairs'] == 2 and stats['excluded_pairs'] == 1
    assert stats['quality_delta_mean'] == 5 and stats['quality_delta_stddev'] == 3
    assert stats['task_count'] == 1 and stats['identical_assignment_pairs'] == 2
    assert stats['per_task_quality_delta'][run.task_id]['repeats'] == 2
    with pytest.raises(ValueError, match='Duplicate'):
        paired_comparisons(observations + observations[:1])


def test_live_multifact_extraction_regression():
    from refractrouter.dataset import load_benchmark_dataset
    dataset = load_benchmark_dataset(ROOT / 'data/benchmarks/v0.1.json', ROOT / 'data/tasks', ROOT / 'data/source_packs')
    task = dataset.all_tasks[0]
    path = ROOT / 'reports/v0.2-node-quality/interrupted-duplicate-source-check/node-evaluations.ndjson'
    cell = next(r for r in map(json.loads, path.read_text().splitlines())
                if r['node_id'] == 'extract_evidence' and r['model_id'] == 'strong')
    assert cell['evaluation']['final_score'] == 0  # immutable original failure
    checks = node_contract_checks(task, task.nodes[2], cell['node_result']['output'], cell['upstream'])
    assert checks['score_cap'] == 100
    assert len(checks['checks']['unique_sources']) == 8


def test_single_models_checkpoint_before_node_judge_failure():
    task, registry, _, _ = fixture()
    saved = {}
    def fail_evaluation(*args):
        assert len(saved) == 3
        raise RuntimeError('interrupted node judge')
    with pytest.raises(RuntimeError, match='interrupted node judge'):
        build_task_strategy_bundle(task, registry, FakeModelAdapter(registry), include_learned=False,
                                   node_evaluator=fail_evaluation, single_recorder=saved.__setitem__)
    assert all(result.node_results for result in saved.values())


def test_unjudged_fallback_scores_never_become_quality_or_pareto_evidence():
    from refractrouter.benchmark import (BenchmarkObservation, aggregate_observations,
                                        baseline_markdown, pareto_front_markdown)
    _, _, run, _ = fixture()
    rows = [BenchmarkObservation(run.task_id, 1, 'task-oracle', replace(run, task_score=100),
                                 judge_error='incomplete-single-model-evaluations'),
            BenchmarkObservation(run.task_id, 1, 'valid', replace(run, task_score=100),
                                 judge=SimpleNamespace(final_score=88, cost=1, billing_unit='USD'))]
    summary = aggregate_observations(rows)
    assert summary['task-oracle']['quality_mean'] is None
    assert summary['valid']['quality_mean'] == 88
    assert '| `task-oracle` | N/A (unjudged)' in baseline_markdown(summary)
    row = next(line for line in pareto_front_markdown(summary).splitlines() if '`task-oracle`' in line)
    assert 'N/A' in row and row.endswith('| No |')
    from refractrouter.comparisons import paired_comparisons
    rows.append(replace(rows[1], strategy='node-oracle'))
    pair = next(p for p in paired_comparisons(rows)['pairs']
                if p['candidate'] == 'node-oracle' and p['baseline'] == 'task-oracle')
    assert pair['included'] is False
    assert pair['candidate_quality'] == 88
    assert pair['baseline_quality'] is None and pair['quality_delta'] is None
