"""只读复算真实调用原始证据；不调用模型，不修改输出目录。"""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def audit():
    out = ROOT / 'output'
    index = json.loads((out / 'artifact-index.json').read_text())
    actual_files = {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p.name != 'artifact-index.json'}
    assert actual_files == set(index), '证据索引与文件集合不一致'
    for name, expected in index.items():
        path = (out / name).resolve()
        assert path.is_relative_to(out.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    result = json.loads((out / 'session.json').read_text())
    assert result['simulated'] is False
    models = {m['model_id']: m for m in result['manifest']['models']}
    labels = [c['label'] for c in result['calls']]
    assert len(labels) == len(set(labels)) <= result['preflight']['maximum_calls']
    recomputed = {'production': 0.0, 'evaluation': 0.0}
    known = True
    for call in result['calls']:
        if call['status'] == 'cancelled-before-dispatch':
            assert call['charged'] == 0
            continue
        if call['status'] != 'billed':
            known = False
            continue
        archived = json.loads((out / 'calls' / (hashlib.sha256(call['label'].encode()).hexdigest()+'.json')).read_text())
        assert archived['label'] == call['label']
        assert archived['usage_available'] and archived['attempts'] == 1
        for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens', 'finish_reason', 'request_id'):
            assert call[key] == archived[key], (call['label'], key)
        assert hashlib.sha256(archived['content'].encode()).hexdigest() == call['output_sha256']
        assert hashlib.sha256(json.dumps(call['request_messages'], ensure_ascii=False).encode()).hexdigest() == call['input_sha256']
        model = models[call['model_id']]
        amount = round(((call['input_tokens']-call['cached_input_tokens'])*model['input_cost_per_1k']
            + call['cached_input_tokens']*model['cached_input_cost_per_1k']
            + call['output_tokens']*model['output_cost_per_1k'])/1000, 8)
        assert abs(amount-call['charged']) < 1e-7
        assert amount <= call['reserved'] + 1e-7
        recomputed[call['category']] += amount
    buckets = [r for key in ('runs', 'plan_setups', 'probe_runs') for r in result.get(key, [])]
    assert Counter(label for row in buckets for label in row['call_labels']) == Counter(labels)
    if known:
        for category, amount in recomputed.items():
            assert abs(amount-result['charged'][category]) < 1e-7
        assert abs(sum(recomputed.values())-sum(r['deployment_cost'] for r in buckets)) < 1e-7
    rows = []
    for planned in result['planned_runs']:
        match = [r for r in result['runs'] if (r['task_id'], r['mode']) == (planned['task_id'], planned['mode'])]
        assert len(match) <= 1
        row = match[0] if match else {}
        rows.append({**planned, **{key: row.get(key) for key in ('status', 'score', 'judge_passed',
            'delivered', 'deployment_cost', 'wall_time_ms', 'error_type', 'error')}})
    return {'artifact_hashes_verified': len(index), 'calls': len(labels),
        'call_statuses': dict(Counter(c['status'] for c in result['calls'])),
        'all_usage_known': known, 'known_actual_afp': recomputed,
        'total_actual_afp': sum(recomputed.values()) if known else None,
        'planned_runs': len(rows), 'delivered_runs': sum(r.get('delivered') is True for r in rows),
        'rows': rows, 'plan_setups': [{k: r.get(k) for k in ('cache_id', 'status', 'deployment_cost', 'error')}
                                    for r in result['plan_setups']],
        'human_review': False, 'scope': '真实执行先导批次，不是完整 A/B 收益或人工复核。'}


if __name__ == '__main__':
    result = audit()
    target = ROOT / 'audit.json'
    if target.exists():
        raise SystemExit('保留原审计结果；如需重跑请使用新的输出文件')
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
