"""DSH/CLI entry for bounded text tasks. Defaults to zero-call preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
from threading import Event
from pathlib import Path

from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.task_runtime import run_task, validate_request


def dump(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request-file', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--max-production-cost', type=float)
    parser.add_argument('--max-evaluation-cost', type=float)
    parser.add_argument('--max-retries', type=int, default=0)
    parser.add_argument('--invoked-by', default='cli', choices=['cli', 'dsh-plugin'])
    args = parser.parse_args()
    # A fresh output/evidence pair protects prior tasks and historical benchmark artifacts.
    if args.evidence.resolve().is_relative_to(args.output_dir.resolve()):
        parser.error('evidence must be outside output-dir')
    if args.evidence.exists() or args.output_dir.exists():
        parser.error('output-dir and evidence must both be fresh')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence = {'status': 'fail', 'mode': 'preflight', 'invoked_by': args.invoked_by,
                'issues': [], 'artifacts': {}}
    try:
        if args.max_retries != 0:
            raise ValueError('text tasks require zero retries')
        request = validate_request(json.loads(args.request_file.read_text()))
        live = request['mode'] in {'plan', 'run'}
        if live != args.execute_paid_run:
            raise ValueError('plan/run require --execute-paid-run; preflight/demo forbid it')
        if not live and (args.max_production_cost is not None or args.max_evaluation_cost is not None):
            raise ValueError('paid limits are only valid in plan/run modes')
        for key, limit in [('maxProductionCost', args.max_production_cost), ('maxEvaluationCost', args.max_evaluation_cost)]:
            if key in request and request[key] != limit:
                raise ValueError('request and invocation budget limits differ')
        manifest = load_model_manifest(args.manifest)
        profile = json.loads(args.profile.read_text())
        for name, value in [('request.json', request), ('profile.json', profile),
                            ('manifest.json', json.loads(args.manifest.read_text()))]:
            dump(args.output_dir / name, value)
        result_path = args.output_dir / 'task-result.json'
        cancelled = Event()
        previous_handlers = {sig: signal.signal(sig, lambda *_: cancelled.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            result = run_task(request, manifest, profile,
                client=OpenAICompatibleClient(max_retries=0) if live else None,
                production_limit=args.max_production_cost, evaluation_limit=args.max_evaluation_cost,
                checkpoint=lambda value: dump(result_path, value), cancel_event=cancelled)
        finally:
            for sig, handler in previous_handlers.items():
                signal.signal(sig, handler)
        if result['plan']:
            dump(args.output_dir / 'plan.json', result['plan'])
        if result['plan_analysis']:
            dump(args.output_dir / 'plan-analysis.json', result['plan_analysis'])
        if result['routing']:
            dump(args.output_dir / 'routing.json', result['routing'])
        if result['final_output']:
            (args.output_dir / 'answer.md').write_text(result['final_output'])
        assignments = result.get('assignments', result['routing']['assignments'] if result['routing'] else {})
        evidence.update(status='pass' if result['status'] in {'preview', 'planned', 'simulated', 'completed'} else 'fail',
            mode='paid' if live else 'preflight', issues=result['issues'],
            task={
                'executionMode': (result['plan_analysis'] or {}).get('execution_mode', 'bounded-parallel' if request.get('maxConcurrency', 1) > 1 else 'serial'),
                'maxConcurrency': request.get('maxConcurrency', 1),
                'peakActiveNodes': result.get('execution', {}).get('peak_running_nodes'),
                'predictedLatencyMs': ((result.get('routing') or {}).get('prediction') or {}).get('scheduled_latency_ms'),
                'status': result['status'], 'mode': request['mode'], 'planOrigin': result['plan_origin'],
                'nodes': [{'nodeId': n['node_id'], 'nodeType': n['node_type'], 'parents': n['parents'],
                           'modelId': assignments.get(n['node_id'], '')} for n in (result['plan'] or {}).get('nodes', [])],
                'qualityScore': result['evaluation']['score'] if result['evaluation'] else None,
                'evaluationPassed': result['evaluation']['passed'] if result['evaluation'] else None,
                'generationStatus': result['generation_status'], 'formatValidation': result['format_validation'],
                'outputPreview': result['final_output'][:12000], 'resultPath': str(result_path.resolve()),
                'productionCost': sum(c['charged'] for c in result['calls'] if c['category'] == 'production' and c['status'] == 'billed'),
                'evaluationCost': sum(c['charged'] for c in result['calls'] if c['category'] == 'evaluation' and c['status'] == 'billed'),
                'unconfirmedCost': sum(c['charged'] for c in result['calls'] if c['status'] in {'reserved', 'unknown-usage'}),
                'costIsSimulated': request['mode'] == 'demo', 'wallTimeMs': result['wall_time_ms'],
            })
        if evidence['status'] == 'fail' and not evidence['issues']:
            evidence['issues'] = [result['status']]
        evidence['preflight'] = {'billing_unit': manifest.billing_unit}
    except Exception as exc:
        evidence['issues'] = [str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__]
    evidence['artifacts'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(args.output_dir.iterdir()) if p.is_file() and p.resolve() != args.evidence.resolve()}
    dump(args.evidence, evidence)
    print(json.dumps({'status': evidence['status'], 'evidence': str(args.evidence), 'issues': evidence['issues']}))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
