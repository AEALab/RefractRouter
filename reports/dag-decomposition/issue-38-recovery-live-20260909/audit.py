"""离线核对本轮原始证据、用量、账本、上游与调度；不调用模型。"""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from refractrouter.openai_compatible import ChatResponse, model_response_cost
from refractrouter.recovery_study import digest
from refractrouter.schemas import ModelSpec

root = Path('reports/dag-decomposition/issue-38-recovery-live-20260909')
out = root / 'run'
result = json.loads((out / 'result.json').read_text())
assert result['status'] in ('completed', 'stopped')
index = json.loads((out / 'artifact-index.json').read_text())
for name, value in index.items():
    assert hashlib.sha256((out / name).read_bytes()).hexdigest() == value, name
protocol = json.loads((out / 'protocol.json').read_text())
manifest = json.loads((out / 'manifest.json').read_text())
profile = json.loads((out / 'profile.json').read_text())
preview = json.loads((out / 'preflight.json').read_text())
assert digest(protocol) == preview['protocol_sha256']
assert digest(manifest) == protocol['manifest_sha256']
assert digest(profile) == protocol['profile_sha256']
assert preview['protocol_sha256'] == 'd84b9573b8e57ddba34cc44f1175c96e49d0d0ad1afeee9b98efb1ed98a3038c'
models = {m['model_id']: ModelSpec(**m) for m in manifest['models']}
calls = result['calls']
assert len(calls) <= preview['maximum_calls']
assert len({c['label'] for c in calls}) == len(calls)
assert Counter(c['label'] for r in result['runs'] for c in r.get('calls', [])) == Counter(c['label'] for c in calls)
usage_checked = 0
for call in calls:
    assert hashlib.sha256(json.dumps(call['request_messages'], ensure_ascii=False).encode()).hexdigest() == call['input_sha256']
    if call['status'] != 'billed':
        continue
    response = json.loads((out / ('response-' + hashlib.sha256(call['label'].encode()).hexdigest() + '.json')).read_text())
    assert response['attempts'] == 1
    assert hashlib.sha256(response['content'].encode()).hexdigest() == call['output_sha256']
    assert response['content'] == call['response_output']
    for key in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens'):
        assert response[key] == call[key]
    actual = model_response_cost(models[call['model_id']], ChatResponse(**response))
    assert math.isclose(actual, call['charged'], abs_tol=1e-8)
    usage_checked += 1
for category in ('production', 'evaluation'):
    cost = sum(c['charged'] for c in calls if c['category'] == category)
    assert math.isclose(cost, result['charged'][category], abs_tol=1e-8)
    assert cost <= preview['budget'][category]
edges = 0
for row in result['runs']:
    if row['status'] == 'not-run':
        continue
    assert math.isclose(row['cost'], sum(c['charged'] for c in row['calls']), abs_tol=1e-8)
    if row['arm'] == 'local-node-switch':
        by_node = {}
        for c in row['calls']:
            if c['category'] == 'production':
                nid = json.loads(c['request_messages'][-1]['content'])['node_id']
                by_node.setdefault(nid, []).append(c)
        for attempts in by_node.values():
            assert len({c['input_sha256'] for c in attempts}) == 1
        if row['recovery_triggers']:
            assert len(by_node['cost']) == len(by_node['answer']) == 1
    initial = row['attempts'][0]
    assert initial.get('initial_assignments', initial['assignments']) == {n['node_id']: 'mid' for n in next(t for t in protocol['tasks'] if t['task_id'] == row['task_id'])['plan']['nodes']}
    for attempt in row['attempts']:
        if row['arm'] != 'local-node-switch':
            assert len(set(attempt['assignments'].values())) == 1
        successful = {n['node_id']: n for n in attempt['nodes'] if n['status'] == 'ok'}
        events = sorted((t, change) for n in attempt.get('node_attempts', attempt['nodes'])
            if 'start_ms' in n and n['status'] != 'cancelled-before-dispatch'
            for t, change in ((n['start_ms'], 1), (n['end_ms'], -1)))
        active = 0
        for _, change in events:
            active += change
            assert 0 <= active <= 2
        for node in attempt.get('node_attempts', attempt['nodes']):
            matching = [c for c in row['calls'] if c['category'] == 'production' and
                json.loads(c['request_messages'][-1]['content'])['node_id'] == node['node_id'] and
                c['model_id'] == node['model_id']]
            assert len(matching) == 1
            payload = json.loads(matching[0]['request_messages'][-1]['content'])
            for parent, value in payload['upstream'].items():
                fields = payload['contract']['inputs'][parent]['fields']
                expected = {k: json.loads(successful[parent]['output'])[k] for k in fields}
                assert value == expected
                assert successful[parent]['end_ms'] <= node['start_ms']
                edges += 1
    assert sum(c['charged'] for c in row['calls'] if c['category'] == 'production') <= protocol['constraints']['costMax']
    if row['status'] == 'completed':
        assert row['evaluation']['passed'] and row['evaluation']['score'] >= 80
        assert row['wall_time_ms'] <= protocol['constraints']['latencyMaxMs']
starts = sorted(c['dispatch_monotonic'] for c in calls if c['category'] == 'production')
assert all(b-a >= .099 for a,b in zip(starts, starts[1:]))
audit = {'protocol_sha256': preview['protocol_sha256'], 'status': result['status'],
    'artifact_hashes_verified': len(index), 'calls': len(calls), 'billed_usage_verified': usage_checked,
    'call_states': dict(Counter(c['status'] for c in calls)), 'upstream_edges_verified': edges,
    'model_calls': dict(Counter(c['model_id'] for c in calls)), 'charged': result['charged'],
    'run_states': dict(Counter(r['status'] for r in result['runs'])), 'checks_passed': True,
    'material_arithmetic': {'storage': {'a': 18000+2100*12, 'b': 6000+3400*12},
        'translation': {'a': 9000+600*(70+20), 'b': 600*(95+20),
                        'break_even_thousand_characters': 9000/(95-70)},
        'support': {'a': 15000+40*45*12, 'b': 3000+40*80*12}},
    'arithmetic_scope': '仅复算冻结材料，不改写模型评审分数或冒充全面人工验收。'}
(root / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(audit, ensure_ascii=False, indent=2))
print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
