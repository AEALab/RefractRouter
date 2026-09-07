"""Build a transferable (not task-guaranteed) profile from the frozen v0.3 matrix."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean

from refractrouter.task_plan import NODE_TYPES


def build_profile(root: Path):
    index = json.loads((root / 'evidence-index.json').read_text())['artifacts']
    path = root / 'node-quality-matrix.json'
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if index['node-quality-matrix.json'] != digest:
        raise ValueError('node matrix evidence hash mismatch')
    rows = json.loads(path.read_text())['rows']
    groups = defaultdict(list)
    for row in rows:
        if row['node_type'] in NODE_TYPES:
            groups[(row['node_type'], row['model_id'])].append(row)
    candidates, exclusions = [], []
    for (kind, model), values in sorted(groups.items()):
        expected = 6 if kind == 'planning' else 3
        blocks = {(v['node_id'], v['repeat']) for v in values}
        valid = len(values) == expected and len(blocks) == expected and all(
            v['node_result']['status'] == 'ok' and not v['node_result']['failure_type']
            and isinstance(v.get('evaluation'), dict) and v['evaluation'].get('eligible') is not False
            and v.get('eligible') is not False and not v.get('error')
            and not v['evaluation'].get('checks', {}).get('issues')
            for v in values)
        if not valid:
            exclusions.append({'node_type': kind, 'model_id': model, 'reason': 'incomplete-or-invalid-cohort'})
            continue
        candidates.append({'node_type': kind, 'model_id': model, 'samples': len(values),
            'quality': mean(v['evaluation']['final_score'] for v in values),
            'cost': mean(v['node_result']['cost'] for v in values),
            # Conservative observed maximum; this is not a population p95 or an SLA.
            'latency_ms': max(v['node_result']['latency_ms'] for v in values)})
    return {'schema_version': 'node-routing-profile-v1', 'kind': 'empirical', 'billing_unit': 'AFP',
            'scope': 'Transfer estimates from report_001 fixed-source report generation, three repeats; not calibrated for arbitrary tasks.',
            'provenance': 'reports/v0.3-contract-recovery/repeated-agent-plan/node-quality-matrix.json',
            'source_sha256': digest, 'latency_statistic': 'observed maximum',
            'model_bindings': {r['model_id']: r['api_model'] for r in rows},
            'candidates': candidates, 'exclusions': exclusions}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile = build_profile(args.archive)
    with args.output.open('x') as stream:
        json.dump(profile, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
