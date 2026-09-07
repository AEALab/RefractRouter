"""Recompute reviewed summaries offline without rewriting original run evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from refractrouter.benchmark import (
    BenchmarkObservation, aggregate_observations, baseline_markdown,
    oracle_gate, oracle_gap_markdown, pareto_front_markdown,
)
from refractrouter.comparisons import comparisons_markdown, paired_comparisons
from refractrouter.judge import JudgeEvaluation
from refractrouter.node_availability import matrix_availability
from refractrouter.schemas import NodeResult, TaskResult


def observation(record, *, repeat=None, strategy=None):
    result = dict(record['result'])
    result['node_results'] = tuple(NodeResult(**node) for node in result['node_results'])
    result['failure_types'] = tuple(result['failure_types'])
    task_result = TaskResult(**result)
    return BenchmarkObservation(
        task_result.task_id, repeat if repeat is not None else record['repeat'],
        strategy or record['strategy'], task_result,
        JudgeEvaluation(**record['judge']) if record['judge'] else None,
        record['judge_error'],
    )


def review(root: Path, output_dir: Path):
    root, output_dir = root.resolve(), output_dir.resolve()
    if output_dir == root or output_dir.is_relative_to(root):
        raise ValueError("Review output must be separate from frozen evidence")
    if output_dir.exists():
        raise ValueError("Review requires a fresh output directory")
    outputs = {}
    def read(name):
        return json.loads((root / name).read_text())

    def write(name, value):
        outputs[name] = json.dumps(value, ensure_ascii=False, indent=2) + '\n'

    index = read('evidence-index.json')['artifacts']
    if not {'preflight.json', 'node-quality-matrix.json', 'benchmark-summary.json'} <= index.keys():
        raise ValueError('Required inputs must be indexed')
    for name, expected in index.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Artifact escapes evidence directory: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Evidence hash mismatch: {name}")
    matrix = read('node-quality-matrix.json')['rows']
    groups = defaultdict(list)
    for row in matrix:
        assert hashlib.sha256(row['node_result']['output'].encode()).hexdigest() == row['output_sha256']
        upstream = json.dumps(row['upstream'], sort_keys=True, ensure_ascii=False).encode()
        assert hashlib.sha256(upstream).hexdigest() == row['upstream_sha256']
        groups[(row['task_id'], row['repeat'], row['node_id'])].append(row)
    for rows in groups.values():
        assert len(rows) == len({r['model_id'] for r in rows}) == 3
        assert len({r['upstream_sha256'] for r in rows}) == 1

    for folder in ('runs', 'single-models'):
        actual = {str(path.relative_to(root)) for path in (root / folder).rglob('*.json')}
        indexed = {name for name in index if name.startswith(folder + '/') and name.endswith('.json')}
        if actual != indexed:
            raise ValueError(f"{folder} files do not match frozen evidence index")
    observations = [observation(json.loads(path.read_text()))
                    for path in sorted((root / 'runs').rglob('*.json'))]
    singles = [observation(json.loads(path.read_text()),
                           repeat=int(path.parent.name.removeprefix('repeat-')),
                           strategy=path.stem)
               for path in sorted((root / 'single-models').rglob('*.json'))]
    preflight = read('preflight.json')
    expected_blocks = [(task, repeat) for task in preflight['test_task_ids']
                       for repeat in range(1, preflight['repeats'] + 1)]
    summary = aggregate_observations(observations, expected_blocks=expected_blocks)
    gate = oracle_gate(summary)
    original = read('benchmark-summary.json')
    for key in ('routing_change_observed', 'repeated', 'matrix_complete'):
        gate[key] = original['oracle_gate'][key]
    if not all(gate[key] for key in ('routing_change_observed', 'repeated', 'matrix_complete')):
        gate['decision'] = 'Insufficient-evidence'
    comparisons = paired_comparisons(observations, expected_blocks=expected_blocks)
    # Expected node/model identities come from indexed full single-model runs, not today's manifest.
    models = sorted({item.strategy for item in singles})
    if len(models) != len(preflight['candidate_models']):
        raise ValueError('Single-model candidate count differs from frozen preflight')
    availability = []
    for task, repeat in expected_blocks:
        matching = [item for item in singles if item.task_id == task and item.repeat == repeat]
        if len(matching) != len(models):
            raise ValueError('Missing single-model block')
        node_sets = [set(item.result.model_assignments) for item in matching]
        if not node_sets[0] or any(nodes != node_sets[0] for nodes in node_sets):
            raise ValueError('Inconsistent single-model node identities')
        rows = [row for row in matrix if row['task_id'] == task and row['repeat'] == repeat
                and row['stage'] == 'probe']
        state = matrix_availability(rows, node_ids=sorted(node_sets[0]), model_ids=models)
        route = next((item for item in observations if item.task_id == task and item.repeat == repeat
                      and item.strategy == 'node-oracle'), None)
        availability.append(dict(task_id=task, repeat=repeat, **state,
                                 route_executed=bool(route and route.result.model_assignments),
                                 route_judged=bool(route and route.judge and not route.judge_error)))
    write('reviewed-node-availability.json', {
        'selection_policy': preflight['node_quality']['selection_policy'],
        'selection_changed': False, 'blocks': availability,
    })
    write('reviewed-summary.json', {
        'schema_version': 'aligned-cohort-review-v1',
        'source': 'Immutable run and judge records; successful independently judged cohort for all metrics',
        'source_hashes': index, 'model_calls': 0,
        'status': original['status'], 'strategies': summary,
        'single_models': aggregate_observations(singles, expected_blocks=expected_blocks), 'oracle_gate': gate,
        'costs': original['costs'], 'failure_taxonomy': original['failure_taxonomy'],
    })
    write('reviewed-strategy-comparisons.json', comparisons)
    for name, content in (
        ('reviewed-baseline-table.md', baseline_markdown(summary)),
        ('reviewed-single-models.md', baseline_markdown(aggregate_observations(singles, expected_blocks=expected_blocks))),
        ('reviewed-pareto-front.md', pareto_front_markdown(summary)),
        ('reviewed-oracle-gap.md', oracle_gap_markdown(gate)),
        ('reviewed-strategy-comparisons.md', comparisons_markdown(comparisons)),
    ):
        outputs[name] = content

    events = [json.loads(line) for line in (root / 'model-progress.ndjson').read_text().splitlines()]
    started = [e for e in events if e['event'] == 'request-start']
    finished = [e for e in events if e['event'] == 'request-finish']
    assert len(started) == len(finished)
    assert Counter(e['request_id'] for e in started) == Counter(e['request_id'] for e in finished)
    write('reviewed-audit.json', {
        'original_artifact_hashes_verified': len(index),
        'matrix_cells': len(matrix), 'eligible_cells': sum(r['eligible'] for r in matrix),
        'selected_cells': sum(r['selected'] for r in matrix),
        'upstream_and_output_hashes_verified': True, 'same_upstream_for_three_candidates': True,
        'strategy_artifacts': len(observations), 'single_model_artifacts': len(singles),
        'requests_started': len(started), 'requests_finished': len(finished),
        'requests_ok': sum(e['ok'] for e in finished),
        'finish_reasons': dict(Counter(e['finish_reason'] for e in finished)),
        'attempt_counts': dict(Counter(e['attempts'] for e in finished)),
        'models': dict(Counter(e['model'] for e in finished)),
        'endpoints': sorted({e['endpoint'] for e in started}),
    })

    output_dir.mkdir(parents=True)
    for name, content in outputs.items():
        (output_dir / name).write_text(content, encoding="utf-8")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    review(args.directory, args.output_dir)
