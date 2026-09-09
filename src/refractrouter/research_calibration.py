"""只从事前校准矩阵冻结整任务 A/B，不读取留出成绩。"""
from dataclasses import asdict
import statistics

from .model_selection import Candidate, Constraints, Weights, select_model
from .research_protocol import digest


def freeze_direct_models(tasks, rows, manifest, constraints, *, held_out_ids):
    ids = {t['task_id'] for t in tasks}
    if not tasks or len(ids) != len(tasks) or ids & set(held_out_ids):
        raise ValueError('invalid or overlapping calibration tasks')
    if any(t['split'] not in ('development', 'calibration') for t in tasks):
        raise ValueError('test tasks cannot calibrate selection')
    groups = {}
    for task in tasks:
        groups.setdefault(task['cell'], []).append(task['task_id'])
    mids = {m.model_id for m in manifest.candidates}
    matrix = {}
    for row in rows:
        if row['task_id'] not in ids or row['mode'] != 'direct':
            raise ValueError('unexpected calibration observation')
        assignment = set(row['assignments'].values())
        if len(assignment) != 1 or not assignment <= mids:
            raise ValueError('calibration must be a frozen single call model')
        key = row['task_id'], next(iter(assignment))
        if key in matrix:
            raise ValueError('duplicate calibration observation')
        matrix[key] = row
    if set(matrix) != {(tid, mid) for tid in ids for mid in mids}:
        raise ValueError('incomplete calibration matrix')
    result = {}
    for cell, tids in groups.items():
        candidates = []
        for mid in sorted(mids):
            sample = [matrix[tid, mid] for tid in tids]
            complete = len(tids) >= 3 and all(r['delivered'] and r['score'] is not None
                and r['deployment_cost'] is not None and r['cost_known'] for r in sample)
            candidates.append(Candidate(mid,
                statistics.mean(r['score'] for r in sample) if complete else None,
                statistics.mean(r['deployment_cost'] for r in sample) if complete else None,
                max(r['wall_time_ms'] for r in sample) if complete else None,
                len(tids), exclusions=() if complete else ('insufficient-or-failed-calibration',)))
        bound = Constraints(constraints['qualityMin'], constraints['costMax'], constraints['latencyMaxMs'])
        result[cell] = {method: select_model(candidates, method=method, constraints=bound,
            weights=Weights(**constraints['weights']) if method == 'B' else None) for method in ('A', 'B')}
    return {'schema_version': 'research-direct-calibration-v1', 'selections': result,
        'task_ids': sorted(ids), 'held_out_ids': sorted(held_out_ids), 'observations_sha256': digest(rows),
        'manifest_sha256': digest(asdict(manifest)), 'constraints': dict(constraints),
        'latency_summary': '校准样本的最大真实墙钟时间，借用选择器 latency_p95 字段，不声称估计了总体 p95。'}
