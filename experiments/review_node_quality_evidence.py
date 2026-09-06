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


def review(root: Path):
    def read(name):
        return json.loads((root / name).read_text())

    def write(name, value):
        (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    index = read('evidence-index.json')['artifacts']
    for name, expected in index.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
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

    observations = [observation(json.loads(path.read_text()))
                    for path in sorted((root / 'runs').rglob('*.json'))]
    singles = [observation(json.loads(path.read_text()),
                           repeat=int(path.parent.name.removeprefix('repeat-')),
                           strategy=path.stem)
               for path in sorted((root / 'single-models').rglob('*.json'))]
    summary = aggregate_observations(observations)
    gate = oracle_gate(summary)
    original = read('benchmark-summary.json')
    for key in ('routing_change_observed', 'repeated', 'matrix_complete'):
        gate[key] = original['oracle_gate'][key]
    comparisons = paired_comparisons(observations)
    write('reviewed-summary.json', {
        'source': 'Immutable run and judge records; deterministic fallback excluded from quality',
        'status': original['status'], 'strategies': summary,
        'single_models': aggregate_observations(singles), 'oracle_gate': gate,
        'costs': original['costs'], 'failure_taxonomy': original['failure_taxonomy'],
    })
    write('reviewed-strategy-comparisons.json', comparisons)
    for name, content in (
        ('reviewed-baseline-table.md', baseline_markdown(summary)),
        ('reviewed-single-models.md', baseline_markdown(aggregate_observations(singles))),
        ('reviewed-pareto-front.md', pareto_front_markdown(summary)),
        ('reviewed-oracle-gap.md', oracle_gap_markdown(gate)),
        ('reviewed-strategy-comparisons.md', comparisons_markdown(comparisons)),
    ):
        (root / name).write_text(content)

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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    review(parser.parse_args().directory)
