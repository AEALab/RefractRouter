"""零调用复核本阶段费用、盲评分数与冻结 Python 选模结果。"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path

from refractrouter.blind_review import digest, import_reviews
from refractrouter.cost_selection import select_cost_effective
from refractrouter.k3_experiment import load_task

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def verify_index(directory):
    index = read(directory / 'evidence-index.json')['artifacts']
    for name, expected in index.items():
        path = (directory / name).resolve()
        assert path.is_relative_to(directory.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    return len(index)


def main():
    output = HERE / 'output'
    summary = read(output / 'summary.json')
    artifact_count = verify_index(output)
    source = ROOT / 'reports/v0.5-k3-resume-admission-2/output'
    source_count = verify_index(source)
    state = read(source / 'private/state.json')
    plan = read(output / 'preflight.json')['plan']
    rows = [json.loads(line) for line in (output / 'responses.ndjson').read_text().splitlines()]
    events = [json.loads(line) for line in (output / 'model-progress.ndjson').read_text().splitlines()]
    starts = [e for e in events if e['event'] == 'request-start']
    finishes = [e for e in events if e['event'] == 'request-finish']
    assert len(starts) == summary['actual_model_calls'] <= 21
    assert len(rows) <= len(starts)
    assert len({e['request_id'] for e in starts}) == len(starts)
    assert [r['sample_id'] for r in rows] == [r['sample_id'] for r in plan['requests'][:len(rows)]]
    model = plan['model']
    costs, unknown = [], []
    for row in rows:
        assert row['attempts'] == 1
        if row['cost'] is None:
            unknown.append(row['sample_id'])
            continue
        cached = min(row['cached_input_tokens'], row['input_tokens'])
        cost = ((row['input_tokens'] - cached) * model['input_cost_per_1k']
                + cached * model['cached_input_cost_per_1k']
                + row['output_tokens'] * model['output_cost_per_1k']) / 1000
        assert math.isclose(row['cost'], cost, abs_tol=1e-8)
        usage = row['raw_usage']
        assert usage['prompt_tokens'] == row['input_tokens']
        assert usage['completion_tokens'] == row['output_tokens']
        assert 0 <= row['reasoning_tokens'] <= row['output_tokens']
        costs.append(cost)
    total = round(sum(costs), 8)
    assert total == summary['known_cost'] <= 210
    assert summary['total_cost'] == (None if unknown else total)
    partial = read(output / 'partial-reviews.json')
    public = state['node_packet']
    forbidden = [state['baseline_model']['api_model'], *(m['api_model'] for m in state['models'])]
    for row in partial['reviews']:
        single = {**public, 'samples': [s for s in public['samples'] if s['sample_id'] == row['sample_id']]}
        import_reviews(single, {**partial, 'packet_sha256': digest(single), 'reviews': [row]},
                       forbidden_models=forbidden)
    audit = {'actual_model_calls': len(starts), 'finished_requests': len(finishes),
             'valid_reviews': len(partial['reviews']), 'planned_reviews': 21,
             'known_cost': total, 'total_cost': None if unknown else total, 'billing_unit': 'AFP',
             'unknown_usage_samples': unknown, 'output_index_files_verified': artifact_count,
             'source_index_files_verified': source_count, 'max_attempts': 1,
             'production_calls': 0, 'selection': None, 'review_status': summary['status'],
             '说明': '缓存属于输入子集，推理属于输出子集；均不重复相加。局部分数不代表组合后的质量。'}
    if starts and finishes:
        audit['review_wall_clock_seconds'] = (
            datetime.fromisoformat(finishes[-1]['recorded_at'])
            - datetime.fromisoformat(starts[0]['recorded_at'])).total_seconds()
    if summary['status'] == 'review-ready':
        assert len(rows) == len(finishes) == 21 and not unknown
        assert all(r['finish_reason'] == 'stop' and not r['validation_error'] for r in rows)
        submitted = read(output / 'reviews.json')['nodes']
        judged = import_reviews(public, submitted, forbidden_models=forbidden)
        assert judged == summary['scores']
        # 检查使用的选模模块仍等于原生产快照；不调用 compose 或任何适配器。
        config = read(source / 'preflight.json')['config']
        import refractrouter.cost_selection as selection_module
        assert digest(Path(selection_module.__file__).read_text()) == config['code']['src/refractrouter/cost_selection.py']
        matrix = deepcopy(state['rows'])
        mapped = {state['node_mapping']['sample_records'][sid]: review for sid, review in judged.items()}
        for cell in matrix:
            review = mapped[f"{cell['node_id']}:{cell['model_id']}"]
            cell['evaluation'] = {**cell['evaluation'], 'error': None, 'method': 'independent-node-judge',
                'final_score': min(review['final_score'], cell['evaluation']['checks']['score_cap']),
                'review': review}
        decision = select_cost_effective(matrix, task=load_task(state['task']),
            model_ids=[m['model_id'] for m in state['models']],
            quality_floor=config['quality_floor'], max_quality_gap=config['max_quality_gap'])
        audit['selection'] = decision
        audit['node_scores'] = [{
            'node_id': c['node_id'], 'model_id': c['model_id'], 'score': c['evaluation']['final_score'],
            'probe_cost': c['node_result']['cost'],
            'selected': decision['assignments'].get(c['node_id']) == c['model_id']} for c in matrix]
    destination = HERE / 'audit.json'
    if destination.exists():
        assert read(destination) == audit, '复算与已有审计不一致；禁止覆盖'
    else:
        destination.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: v for k, v in audit.items() if k not in {'selection', 'node_scores'}}, ensure_ascii=False))
    if audit['selection'] is not None:
        print(json.dumps(audit['selection'], ensure_ascii=False))


if __name__ == '__main__':
    main()
