"""Compare one-shot, single-model DAG and node-composed DAG under a frozen v0.4 protocol."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
import os
from pathlib import Path

if __package__:
    from .run_real_v0_1 import (BudgetedAdapter, CostLedger, NodeQualityRecorder,
                              _evaluate_with_budget, build_task_strategy_bundle, estimate_costs)
else:
    from run_real_v0_1 import (BudgetedAdapter, CostLedger, NodeQualityRecorder,
                             _evaluate_with_budget, build_task_strategy_bundle, estimate_costs)
from refractrouter.adapters import FakeModelAdapter, OpenAICompatibleAdapter
from refractrouter.benchmark import (
    BenchmarkObservation, aggregate_observations, failure_taxonomy, oracle_gate,
)
from refractrouter.comparisons import paired_comparisons
from refractrouter.execution_reports import (
    baseline_markdown, comparisons_markdown, failure_taxonomy_markdown, node_matrix_markdown,
)
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.evidence_state import evidence_artifact, with_evidence_state
from refractrouter.execution_modes import one_shot_task, run_one_shot, execution_mode_call_plan, execution_mode_pairs
from refractrouter.judge import IndependentJudge, DIMENSION_LIMITS
from refractrouter.manifest import load_model_manifest
from refractrouter.node_availability import REJECTION_SELECTION_POLICY, matrix_availability
from refractrouter.node_contracts import prompt_contract_snapshot
from refractrouter.node_judge import IndependentNodeJudge, NODE_LIMITS
from refractrouter.openai_compatible import ChatResponse, OpenAICompatibleClient
from refractrouter.schemas import TaskResult

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


class FixtureAdapter(FakeModelAdapter):
    """Synthetic complete outputs, never an empirical claim about model capability."""
    calls = 0

    def invoke(self, task, node, prompt, context, model):
        self.calls += 1
        return super().invoke(task, node, prompt, context, replace(model, capability=1.0))


class FixtureJudgeClient:
    calls = 0

    def complete(self, model, messages, **kwargs):
        self.calls += 1
        payload = json.loads(messages[1]['content'])
        if 'candidate_output' in payload:
            data = dict(scores=NODE_LIMITS, rationale='Synthetic fixture, not a semantic judgment.',
                        source_assessments=[dict(source_id=s, supported=True, explanation='Fixture assumption.')
                                            for s in payload['assessed_source_ids']])
        else:
            data = dict(scores=DIMENSION_LIMITS, rationale='Synthetic fixture, not a semantic judgment.',
                        claim_support=[dict(claim=c, source_ids=[payload['sources'][0]['source_id']],
                                            supported=True, explanation='Fixture assumption.')
                                       for c in payload['expected_claims']])
        return ChatResponse(json.dumps(data), 100, 100, 0, 0, 1, 1, 'stop', f'fixture-judge-{self.calls}')


def select_complete_best(observations):
    if not observations or any(row.judge is None or row.judge_error or row.result.failure_types
           or any(n.status != 'ok' for n in row.result.node_results) for row in observations):
        return None
    return min(observations, key=lambda row: (-row.judge.final_score, row.result.total_cost, row.strategy))


def run(task, manifest, adapter, client, ledger, output, repeats, *, simulation):
    registry = manifest.candidate_registry()
    models = [m.model_id for m in registry.list()]
    node_judge = IndependentNodeJudge(client, manifest.judge, contract_version='v0.4')
    recorder = NodeQualityRecorder(node_judge, ledger, output, manifest.candidates, REJECTION_SELECTION_POLICY)
    final_judge = IndependentJudge(client, manifest.judge)
    observations, availability = [], []

    def checkpoint(result, repeat, name, judge=None, error='awaiting-evaluation'):
        row = BenchmarkObservation(task.task_id, repeat, name, replace(result, strategy=name), judge, error)
        write(output / 'runs' / task.task_id / f'repeat-{repeat}' / f'{name}.json', asdict(row))
        return row

    def evaluate(eval_task, result, repeat, name):
        checkpoint(result, repeat, name)
        judge, error = _evaluate_with_budget(final_judge, eval_task, result, ledger,
            error_recorder=lambda failure: write(
                output / 'final-judge-failures' / f'repeat-{repeat}' / f'{name}.json', failure))
        row = checkpoint(result, repeat, name, judge, error)
        observations.append(row)
        return row

    for repeat in range(1, repeats + 1):
        singles_a = [evaluate(one_shot_task(task), run_one_shot(task, model, adapter, registry),
                              repeat, f'one-shot:{model}') for model in models]
        bundle = build_task_strategy_bundle(
            task, registry, adapter, include_learned=False, include_rule=False,
            selection_policy=REJECTION_SELECTION_POLICY,
            single_recorder=lambda model, result: checkpoint(result, repeat, f'dag:{model}'),
            node_evaluator=lambda task, node, result, context: recorder.record(
                task, node, result, context, repeat=repeat, stage='probe'))
        write(output / f'selection-{task.task_id}-{repeat}.json', bundle.selection_decision)
        singles_b = [evaluate(task, result, repeat, f'dag:{model}')
                     for model, result in bundle.single_results.items()]
        mixed = evaluate(task, bundle.results['node-oracle'], repeat, 'node-mixed')
        for name, rows in (('one-shot-oracle', singles_a), ('dag-oracle', singles_b)):
            best = select_complete_best(rows)
            if best is None:
                unavailable = TaskResult(task.task_id, name, {}, (), '', 0, 0, 0,
                                         manifest.billing_unit, ('incomplete-single-model-evaluations',))
                row = checkpoint(unavailable, repeat, name, error='incomplete-single-model-evaluations')
            else:
                row = checkpoint(best.result, repeat, name, best.judge, best.judge_error)
            observations.append(row)
        rows = [r for r in recorder.rows if r['repeat'] == repeat]
        state = matrix_availability(rows, node_ids=[n.node_id for n in task.nodes], model_ids=models)
        availability.append(dict(task_id=task.task_id, repeat=repeat, **state))
        # Each route's extraction output remains authoritative, independently of all descendants.
        for name, result in [(f'dag:{m}', r) for m, r in bundle.single_results.items()] + [('node-mixed', mixed.result)]:
            context = {node.node_id: node.output for node in result.node_results}
            try:
                artifact = evidence_artifact(task, context).snapshot()
                record = dict(available=True, artifact=artifact)
            except ValueError as exc:
                record = dict(available=False, error=str(exc))
            write(output / 'evidence-state' / f'repeat-{repeat}' / f'{name}.json', record)

    recorder.write_matrix()
    (output / 'node-quality-matrix.md').write_text(node_matrix_markdown(recorder.rows))
    blocks = [(task.task_id, repeat) for repeat in range(1, repeats + 1)]
    summary = aggregate_observations(observations, expected_blocks=blocks)
    comparison = paired_comparisons(observations, expected_blocks=blocks,
        comparison_pairs=execution_mode_pairs(models), interpretation=(
            '仅为模拟，不构成模型质量或节费的实测证据。' if simulation else '') +
        'A 为完整来源包的一次调用；B 为单模型七节点；C 为按独立节点评分选出的路线，允许全程使用同一模型。'
        '同模型 B/A 比较拆解效果，C/B 比较选模效果。组内最佳基线要求所有候选成功且完成评审；'
        '它是事后选择，不是可部署路由器。所有差值使用相同任务／轮次配对，探针与评审费用另计。')
    complete = all(v['cohort']['complete'] for v in summary.values()) and all(
        s['records_complete'] and s['evaluations_available'] for s in availability)
    gates = {}
    for baseline in ('dag-oracle', 'one-shot-oracle'):
        gate = oracle_gate({'node-oracle': summary['node-mixed'], 'task-oracle': summary[baseline]})
        if simulation:
            gate['decision'] = 'Simulation-only'
        elif repeats < 3 or not complete:
            gate['decision'] = 'Insufficient-evidence'
        gates[baseline] = gate
    failed = failure_taxonomy(observations)
    result = dict(schema_version='execution-modes-v0.4', status='complete' if complete else 'incomplete',
        simulation=simulation, empirical_evidence=not simulation, repeats=repeats,
        candidate_models=models, strategies=summary, comparisons=comparison['summaries'], go_gates=gates,
        node_matrix=dict(expected_cells=len(task.nodes)*len(models)*repeats, recorded_cells=len(recorder.rows)),
        node_availability=availability, failure_taxonomy=failed,
        costs=dict(billing_unit=manifest.billing_unit, simulated=simulation,
            production=round(ledger.production_spent, 8), evaluation=round(ledger.evaluation_spent, 8),
            node_evaluation=round(sum(r['evaluation']['cost'] for r in recorder.rows), 8),
            actual_paid_cost=0 if simulation else None,
            accounting='包括所有唯一 A/B/C 路线与探针；最终评审只计费一次，事后最佳基线复用不重复计费。'))
    write(output / 'benchmark-summary.json', result)
    write(output / 'strategy-comparisons.json', comparison)
    (output / 'strategy-comparisons.md').write_text(comparisons_markdown(comparison))
    (output / 'baseline-table.md').write_text(('仅为模拟，不是实测证据。\n\n' if simulation else '') + baseline_markdown(summary))
    (output / 'failure-taxonomy.md').write_text(failure_taxonomy_markdown(failed))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT/'data/benchmarks/v0.1.json')
    parser.add_argument('--manifest', type=Path, default=ROOT/'data/model-manifests/volcengine-agent-plan.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--phase', choices=['execution-modes'], default='execution-modes')
    parser.add_argument('--task-id', default='report_001')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--selection-policy', choices=[REJECTION_SELECTION_POLICY], default=REJECTION_SELECTION_POLICY)
    parser.add_argument('--max-retries', type=int, default=0)
    parser.add_argument('--mode', choices=['preflight', 'offline'], default='preflight')
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--max-production-cost', type=float)
    parser.add_argument('--max-evaluation-cost', type=float)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 3 or args.max_retries != 0:
        parser.error('execution-modes requires 1-3 repeats and zero retries')
    if args.execute_paid_run and args.mode == 'offline':
        parser.error('offline and paid execution are mutually exclusive')
    manifest = load_model_manifest(args.manifest)
    if any(m.provider != 'ark-plan' or m.base_url != 'https://ark.cn-beijing.volces.com/api/plan/v3'
           or m.wire_api != 'chat-completions' for m in manifest.models) or manifest.billing_unit != 'AFP':
        parser.error('execution-modes requires the frozen Agent Plan Chat Completions manifest')
    dataset = load_benchmark_dataset(args.dataset, ROOT/'data/tasks', ROOT/'data/source_packs')
    matches = [task for task in dataset.all_tasks if task.task_id == args.task_id]
    if len(matches) != 1:
        parser.error('task-id must identify one frozen dataset task')
    headings = {'Executive Summary': '执行摘要', 'Background': '背景', 'Selection Criteria': '选型标准',
                'Platform Comparison': '平台比较', 'Risks': '风险', 'Conclusion': '结论', 'References': '参考资料'}
    task = with_evidence_state(replace(matches[0],
        required_sections=tuple(headings.get(s, s) for s in matches[0].required_sections),
        output_constraints=(*matches[0].output_constraints,
            '最终报告的标题、正文、说明及来源介绍必须使用简体中文；模型名、来源标识及哈希保持原样。')))
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Use a fresh output directory; no evidence is overwritten')
    cap = max(m.max_output_tokens or 0 for m in manifest.models)
    plan = execution_mode_call_plan(task, len(manifest.candidates), args.repeats)
    estimates = estimate_costs(plan, manifest, 4000, cap)
    frozen_tasks = {'A': asdict(one_shot_task(task)), 'B_C': asdict(task)}
    sources = sorted(p for base in (ROOT/'src', ROOT/'experiments', ROOT/'validation/dsh')
                     for p in base.rglob('*') if p.is_file() and p.suffix in {'.py', '.ts', '.json', '.md', '.yml'}
                     and not set(p.parts) & {'node_modules', 'dist', '.test-dist', '__pycache__'})
    preflight = dict(schema_version='execution-modes-v0.4', phase=args.phase, repeats=args.repeats,
        task_id=task.task_id, output_language='zh-CN', mode='paid' if args.execute_paid_run else args.mode,
        model_calls=0 if not args.execute_paid_run else None,
        provider='ark-plan', wire_api='chat-completions', billing_unit='AFP',
        base_url=manifest.candidates[0].base_url, credential_env=manifest.candidates[0].api_key_env,
        credential_available=bool(os.environ.get(manifest.candidates[0].api_key_env or '')),
        candidate_models=[m.api_model for m in manifest.candidates], judge_model=manifest.judge.api_model,
        selection_policy=args.selection_policy, output_contract=prompt_contract_snapshot('v0.4'),
        node_rubric_sha256=sha(ROOT/'data/judges/node-v0.4.md'),
        inputs={'dataset_sha256':sha(args.dataset),'manifest_sha256':sha(args.manifest),
                'tasks':frozen_tasks,'code':{str(p.relative_to(ROOT)):sha(p) for p in sources}},
        execution_policy={'max_retries':0,'temperature':0,'timeout_seconds':120,
                          'models':[asdict(m) for m in manifest.models]},
        call_plan=plan, cost_estimates=estimates,
        estimate_assumptions=dict(production_input_tokens=4000, judge_input_tokens=8000,
                                  output_tokens=cap, cached_discount=False,
                                  outer_dsh_not_included=True, not_an_exact_input_bound=True))
    output.mkdir(parents=True, exist_ok=True)
    write(output/'preflight.json', preflight)
    if args.mode == 'preflight' and not args.execute_paid_run:
        print(json.dumps({'status':'preflight','call_plan':plan,'cost_estimates':estimates}))
        return 0
    if args.execute_paid_run:
        for label, limit in [('production',args.max_production_cost),('evaluation',args.max_evaluation_cost)]:
            if limit is None or not math.isfinite(limit) or limit < estimates[f'{label}_upper_estimate']:
                parser.error(f'{label} budget must cover the preflight estimate')
        if not os.environ.get(manifest.candidates[0].api_key_env or ''):
            parser.error('paid run requires the configured credential')
        # Require the native DSH boundary, in addition to both budget limits and credentials.
        if os.environ.get('REFRACTROUTER_EXECUTION_MODES_HOST') != 'dsh-plugin':
            parser.error('paid execution-modes runs require the native DSH plugin boundary')
        client = OpenAICompatibleClient(max_retries=0, environment={**os.environ,
            'REFRACTROUTER_MODEL_PROGRESS':str(output/'model-progress.ndjson')})
        delegate = OpenAICompatibleAdapter(client)
    else:
        client = FixtureJudgeClient()
        delegate = FixtureAdapter(manifest.candidate_registry())
    ledger = CostLedger('AFP', args.max_production_cost if args.execute_paid_run else 1e9,
                        args.max_evaluation_cost if args.execute_paid_run else 1e9, 4000, 8000, cap)
    result = run(task, manifest, BudgetedAdapter(delegate, ledger), client, ledger,
                 output, args.repeats, simulation=not args.execute_paid_run)
    if not args.execute_paid_run:
        write(output/'simulation-calls.json', {'production':delegate.calls,'evaluation':client.calls,
                                             'actual_network_calls':0,'actual_paid_cost':0})
    write(output/'evidence-index.json', {'schema_version':'execution-modes-v0.4','artifacts':{
        str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*'))
        if p.is_file() and p.name != 'evidence-index.json'}})
    print(json.dumps({'status':result['status'],'simulation':result['simulation'],'costs':result['costs']}))
    return 0 if result['status']=='complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
