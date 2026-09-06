"""Bounded contract-only replay of frozen issue #25 failures; preflight by default."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import asdict
from pathlib import Path

from refractrouter.adapters import OpenAICompatibleAdapter
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.graph_executor import GraphExecutor
from refractrouter.manifest import load_model_manifest
from refractrouter.node_contracts import prompt_contract_snapshot
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.scoring import node_contract_checks

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "reports/v0.2-node-quality/repeated-agent-plan"
AGENT_PLAN_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_cases(archive=ARCHIVE):
    index = json.loads((archive / 'evidence-index.json').read_text())['artifacts']
    for filename, expected in index.items():
        if hashlib.sha256((archive / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Original artifact hash mismatch: {filename}")
    cases = []
    matrix = json.loads((archive / 'node-quality-matrix.json').read_text())['rows']
    for cell in matrix:
        if cell['node_id'] != 'write_report' or cell['eligible']:
            continue
        if _hash(cell['upstream']) != cell['upstream_sha256']:
            raise ValueError('Original upstream hash mismatch')
        cases.append(dict(case_id=f"probe-{cell['repeat']}-{cell['model_id']}",
                          task_id=cell['task_id'], model_id=cell['model_id'],
                          node_id=cell['node_id'], upstream=cell['upstream'],
                          original_output=cell['node_result']['output']))
    paths = sorted((archive / 'single-models').rglob('mid.json'))
    paths += [archive / 'runs/report_001/repeat-1/node-oracle.json']
    for path in paths:
        record = json.loads(path.read_text())['result']
        results = {node['node_id']: node for node in record['node_results']}
        result = results['write_report']
        if result['status'] != 'failed':
            raise ValueError(f'Expected saved failure: {path}')
        if results['synthesize_analysis']['status'] != 'ok':
            raise ValueError(f'Invalid saved parent: {path}')
        cases.append(dict(case_id=f"{path.parent.name}-{path.stem}", task_id=record['task_id'],
                          model_id=result['model_id'], node_id='write_report',
                          upstream={'synthesize_analysis': results['synthesize_analysis']['output']},
                          original_output=result['output']))
    if len(cases) != 7 or len({c['case_id'] for c in cases}) != 7:
        raise ValueError('Issue #25 replay requires exactly seven distinct frozen cases')
    for case in cases:
        case['upstream_sha256'] = _hash(case['upstream'])
        case['original_output_sha256'] = hashlib.sha256(case['original_output'].encode()).hexdigest()
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'data/benchmarks/v0.1.json')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--phase', choices=['contract-replay'], default='contract-replay')
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=1)
    parser.add_argument('--max-retries', type=int, choices=[0], default=0)
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--max-production-cost', type=float)
    parser.add_argument('--max-evaluation-cost', type=float)
    args = parser.parse_args(argv)
    out = args.output_dir
    if out.exists() and any(out.iterdir()):
        raise ValueError('Replay requires a fresh output directory')
    manifest = load_model_manifest(args.manifest)
    if any(m.provider != 'ark-plan' or m.base_url != AGENT_PLAN_URL or
           m.billing_unit != 'AFP' or m.wire_api != 'chat-completions' for m in manifest.models):
        raise ValueError('Contract replay requires the Agent Plan manifest')
    dataset = load_benchmark_dataset(args.dataset, ROOT / 'data/tasks', ROOT / 'data/source_packs')
    tasks = {task.task_id: task for task in dataset.all_tasks}
    registry = manifest.candidate_registry()
    cases = load_cases()
    for case in cases:
        task = tasks[case['task_id']]
        node = next(n for n in task.nodes if n.node_id == case['node_id'])
        if set(case['upstream']) != set(node.parents):
            raise ValueError('Replay context must contain exactly the direct parents')
        prompt = GraphExecutor(task, None, registry)._build_prompt(node, case['upstream'])
        messages = [dict(role='system', content=OpenAICompatibleAdapter._system_prompt(node)),
                    dict(role='user', content=OpenAICompatibleAdapter._user_prompt(task, node, prompt))]
        model = registry.get(case['model_id'])
        # Conservative byte-based input allowance, including request framing reserve.
        inputs = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
        case['messages_sha256'] = _hash(messages)
        case['estimated_input_tokens'] = inputs
        case['reserved_afp'] = round((inputs * model.input_cost_per_1k +
                                     8192 * model.output_cost_per_1k) / 1000, 8)
    estimate = round(sum(c['reserved_afp'] for c in cases) * args.repeats, 8)
    preflight = dict(
        schema_version='v0.2', phase='contract-replay', repeats=args.repeats,
        scope='Seven saved write_report failures; contract validity only, no semantic or Go claim',
        billing_unit='AFP', provider='ark-plan', wire_api='chat-completions', base_url=AGENT_PLAN_URL,
        credential_env=manifest.candidates[0].api_key_env,
        credential_available=bool(os.environ.get(manifest.candidates[0].api_key_env)),
        node_output_contract=prompt_contract_snapshot(), cases_sha256=_hash(cases),
        call_plan=dict(training_model_calls=0, production_model_calls=len(cases)*args.repeats,
                       judge_model_calls=0, total_model_calls=len(cases)*args.repeats),
        cost_estimates=dict(billing_unit='AFP', production_upper_estimate=estimate,
                            evaluation_upper_estimate=0, total_upper_estimate=estimate),
        json_mode_by_model={m.api_model: m.json_mode_strategy for m in manifest.models},
        execution_policy=dict(max_retries=0, timeout_seconds=120, temperature=0,
                              max_output_tokens=8192, stop_after_contract_failure=True),
    )
    out.mkdir(parents=True, exist_ok=True)
    (out / 'preflight.json').write_text(json.dumps(preflight, ensure_ascii=False, indent=2)+'\n')
    (out / 'replay-cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2)+'\n')
    if not args.execute_paid_run:
        print(json.dumps(preflight, ensure_ascii=False))
        return 0
    if (args.max_production_cost is None or not math.isfinite(args.max_production_cost)
            or not args.max_production_cost >= estimate):
        raise ValueError(f'Production budget must cover replay estimate {estimate} AFP')
    if (args.max_evaluation_cost is None or not math.isfinite(args.max_evaluation_cost)
            or not args.max_evaluation_cost >= 0):
        raise ValueError('Replay requires an explicit nonnegative evaluation limit')
    adapter = OpenAICompatibleAdapter(OpenAICompatibleClient(
        max_retries=0, timeout_seconds=120,
        environment={**os.environ, 'REFRACTROUTER_MODEL_PROGRESS': str(out / 'model-progress.ndjson')}))
    rows, spent, stop = [], 0.0, False
    for repeat in range(1, args.repeats + 1):
        for case in cases:
            if spent + case['reserved_afp'] > args.max_production_cost:
                stop = True
                break
            task = tasks[case['task_id']]
            node = next(n for n in task.nodes if n.node_id == case['node_id'])
            result = GraphExecutor(task, adapter, registry).probe_node(
                node.node_id, case['model_id'], case['upstream'])
            spent += result.cost
            checks = node_contract_checks(task, node, result.output, case['upstream'])
            row = dict(case_id=case['case_id'], repeat=repeat, result=asdict(result), checks=checks,
                       upstream_sha256=case['upstream_sha256'], messages_sha256=case['messages_sha256'],
                       output_sha256=hashlib.sha256(result.output.encode()).hexdigest())
            rows.append(row)
            with (out / 'replay-results.ndjson').open('a') as stream:
                stream.write(json.dumps(row, ensure_ascii=False)+'\n')
            if result.status != 'ok' or checks['score_cap'] != 100:
                stop = True
                break
        if stop:
            break
    summary = dict(status='incomplete' if stop else 'complete', phase='contract-replay',
                   planned_calls=preflight['call_plan']['total_model_calls'], completed_calls=len(rows),
                   production_afp=round(spent, 8), evaluation_afp=0, stopped_early=stop,
                   interpretation='Contract-only replay. Semantic quality and oracle Go remain unassessed.')
    (out / 'benchmark-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
    (out / 'evidence-index.json').write_text(json.dumps({'artifacts': artifacts}, indent=2)+'\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
