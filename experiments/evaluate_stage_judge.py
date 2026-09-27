"""固定 Stage 本地判别验收；不调用云端、不下载、不覆盖旧证据。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from refractrouter.planning_decision import LayaDecisionAdapter, LocalDecisionCapacityError
from refractrouter.stage_hybrid import decision_request, parse_answers, VERSION


def evaluate(suite, adapter):
    rows = []
    for case in suite['cases']:
        messages = [{'role': 'user', 'content': case['task']},
            {'role': 'assistant', 'content': [{'type': 'tool-call', 'id': case['id'], 'name': 'read', 'arguments': {}}]},
            {'role': 'user', 'content': [{'type': 'tool-result', 'toolCallId': case['id'],
                'content': [{'type': 'text', 'text': case['result']}]}]}]
        events = [{'id': case['id'], 'tool': 'read', 'status': 'unclassified'}]
        request = decision_request(messages, events, SimpleNamespace(capability_card=suite['efficient']),
            SimpleNamespace(capability_card=suite['capable']), 65536)
        start = time.perf_counter()
        try:
            result = adapter.decide_stage(request)
            parsed = parse_answers(result.payload['answers'],
                                   {'upgradeThreshold': .8, 'downgradeThreshold': .9})
            decision = parsed['verdict']
            details = {'answers': parsed['answers'], 'confidence': parsed['confidence'],
                       'latencyMs': result.latency_ms, 'usage': result.usage, 'actualModel': result.model}
        except LocalDecisionCapacityError as exc:
            decision = 'UNCERTAIN'
            details = {'capacityReason': str(exc), 'usage': {'forwards': 0}}
        rows.append({'id': case['id'], 'group': case['group'], 'language': case['language'],
                     'expected': case['expected'], 'outcome': decision, 'matched': decision == case['expected'],
                     'elapsedMs': (time.perf_counter()-start)*1000, 'inputDigest': request['inputDigest'], **details})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--model-path', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('验收输出已存在，拒绝覆盖')
    raw = args.cases.read_bytes()
    suite = json.loads(raw)
    expected_counts = {'explore': 4, 'strong': 4, 'down': 4, 'unknown': 4}
    if suite.get('schemaVersion') == 'stage-judge-suite-v1':
        expected_counts = {key: 6 for key in expected_counts}
    elif suite.get('schemaVersion') != 'stage-judge-suite-v2':
        raise ValueError('未知 Stage 判别题集')
    if ({key: sum(case.get('group') == key for case in suite['cases']) for key in expected_counts}
            != expected_counts or len(suite['cases']) != sum(expected_counts.values())):
        raise ValueError('Stage 判别题集分组或数量无效')
    started = time.perf_counter()
    adapter = LayaDecisionAdapter({'modelPath': str(args.model_path), 'sourceModel': suite['checkpoint'],
        'revision': suite['revision'], 'device': 'gpu', 'dtype': 'float16'})
    cold = (time.perf_counter()-started)*1000
    rows = evaluate(suite, adapter)
    normal = sum(r['outcome'] == 'EFFICIENT_OK' for r in rows if r['group'] == 'explore')
    unsafe = sum(r['outcome'] == 'EFFICIENT_OK' for r in rows if r['group'] == 'strong')
    unknown_efficient = sum(r['outcome'] == 'EFFICIENT_OK' for r in rows if r['group'] == 'unknown')
    matrix = {}
    for row in rows:
        matrix.setdefault(row['expected'], {}).setdefault(row['outcome'], 0)
        matrix[row['expected']][row['outcome']] += 1
    latencies = sorted(r['elapsedMs'] for r in rows if 'capacityReason' not in r)
    report = {'schemaVersion': 'stage-judge-result-v2', 'ruleVersion': VERSION,
        'recordedAt': datetime.now(timezone.utc).isoformat(), 'suiteSha256': hashlib.sha256(raw).hexdigest(),
        'checkpoint': suite['checkpoint'], 'revision': suite['revision'], 'coldLoadAndWarmupMs': cold,
        'warmP50Ms': latencies[len(latencies)//2] if latencies else None,
        'warmP95Ms': latencies[min(len(latencies)-1, int(len(latencies)*.95))] if latencies else None,
        'matched': sum(r['matched'] for r in rows), 'total': len(rows),
        'capacityFallbacks': sum('capacityReason' in r for r in rows),
        'normalAccepted': normal, 'unsafeEfficient': unsafe,
        'unknownSentEfficient': unknown_efficient,
        'dailyUseAccepted': (normal >= expected_counts['explore'] - 1
                             and unsafe == 0 and unknown_efficient == 0),
        'confusionMatrix': matrix, 'apiCalls': 0, 'apiCost': 0, 'cases': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
