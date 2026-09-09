"""修复回归的独立哈希、输入一致性与 AFP 复算。"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def audit():
    out = ROOT / 'output'
    index = json.loads((out / 'artifact-index.json').read_text())
    assert set(index) == {str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p.name != 'artifact-index.json'}
    for name, expected in index.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == expected
    r = json.loads((out / 'session.json').read_text())
    assert not r['simulated'] and len(r['calls']) == 6
    assert all(c['status'] == 'billed' for c in r['calls'])
    models = {m['model_id']: m for m in r['manifest']['models']}
    criteria = r['regression_protocol']['task']['criteria']
    totals = {'production': 0., 'evaluation': 0.}
    for call in r['calls']:
        response = json.loads((out / 'calls' / (hashlib.sha256(call['label'].encode()).hexdigest()+'.json')).read_text())
        assert response['usage_available'] and response['attempts'] == 1
        assert hashlib.sha256(response['content'].encode()).hexdigest() == call['output_sha256']
        assert hashlib.sha256(json.dumps(call['request_messages'], ensure_ascii=False).encode()).hexdigest() == call['input_sha256']
        for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens'):
            assert call[key] == response[key]
        if call['category'] == 'production':
            payload = json.loads(call['request_messages'][-1]['content'])
            assert all(c in payload['task'] for c in criteria)
        model = models[call['model_id']]
        amount = round(((call['input_tokens']-call['cached_input_tokens'])*model['input_cost_per_1k']
            + call['cached_input_tokens']*model['cached_input_cost_per_1k']
            + call['output_tokens']*model['output_cost_per_1k'])/1000, 8)
        assert abs(amount-call['charged']) < 1e-7
        totals[call['category']] += amount
    assert all(abs(totals[k]-r['charged'][k]) < 1e-7 for k in totals)
    assert abs(sum(totals.values())-sum(row['deployment_cost'] for row in r['runs'])) < 1e-7
    return {'calls': 6, 'artifact_hashes_verified': len(index), 'all_billed': True,
        'acceptance_criteria_present_in_every_generation_call': True, 'actual_afp': totals,
        'total_actual_afp': sum(totals.values()),
        'runs': [{k: row.get(k) for k in ('run_id', 'status', 'score', 'delivered', 'deployment_cost', 'wall_time_ms')}
                 for row in r['runs']], 'independent_holdout': False}


if __name__ == '__main__':
    result = audit()
    target = ROOT / 'audit.json'
    assert not target.exists(), '不覆盖已有审计结果'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False))
