"""三组恢复实验的确定性验收；不发起网络或付费调用。"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
import json
from threading import Event
import time
from unittest.mock import patch

import pytest

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.node_routing import load_profile
from refractrouter.recovery_study import ARMS, digest, preflight, run_study, run_trial, summarize
from refractrouter.task_budget import TaskCallBudget
from tests.test_node_recovery import BrokenNode
from tests.test_task_decomposition import example
from tests.test_text_tasks import Client, MANIFEST, PROFILE


def protocol():
    return {'schema_version': 'recovery-study-v1', 'implementation_sha256': implementation_fingerprint(),
        'manifest_sha256': digest(asdict(MANIFEST)), 'profile_sha256': digest(PROFILE),
        'failure_policy': 'settled-output-only-stop-on-infrastructure',
        'model_order': ['cheap', 'mid', 'strong'], 'max_switches': 2, 'repeats': 1, 'order_seed': 38,
        'judge_input_cap': 65536, 'execution_policy': {'maxConcurrency': 1},
        'constraints': {'qualityMin': 80, 'costMax': 10, 'latencyMaxMs': 300000},
        'tasks': [{'task_id': 'heldout', 'task': '根据材料比较两个方案。', 'plan': example()}]}


def trial(client, arm, *, raw=None, budget=None, **kwargs):
    raw = raw or protocol()
    budget = budget or TaskCallBudget(client, 100, 100, capture_payload=True)
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        return run_trial(raw['tasks'][0], arm, raw, MANIFEST, load_profile(PROFILE, MANIFEST), budget, **kwargs)


@pytest.mark.parametrize('kind', ['structure', 'truncated'])
def test_three_arms_preserve_siblings_or_rerun_whole_dag(kind):
    # 在汇总节点失败，确保两条上游分支均已完成，三组有相同失败位置。
    results = {}
    for arm in ARMS:
        client = BrokenNode(nid='answer', kind='truncated') if kind == 'truncated' else BrokenNode(nid='risk')
        result = results[arm] = trial(client, arm)
        assert all(c['status'] == 'billed' for c in result['calls'])
        assert result['cost'] == pytest.approx(sum(c['charged'] for c in result['calls']))
        assert len({c['label'] for c in result['calls']}) == len(result['calls'])
        if arm == ARMS[0]:
            assert result['status'] == 'failed' and len(result['attempts']) == 1
            continue
        assert result['status'] == 'completed', result
        assert client.seen[0][0] == 'cheap' and client.seen[1][0] == 'mid'
        counts = Counter(json.loads(m[-1]['content']).get('node_id') for _, m in client.calls)
        assert counts['cost'] == (1 if arm == ARMS[1] else 2)
        if arm == ARMS[1]:
            assert client.seen[0][1] == client.seen[1][1]
            assert len(set(result['attempts'][0]['assignments'].values())) == 2
        else:
            assert len(result['attempts']) == 2
            for attempt in result['attempts']:
                assert len(set(attempt['assignments'].values())) == 1
    assert results[ARMS[2]]['cost'] > results[ARMS[1]]['cost']


@pytest.mark.parametrize('arm', ARMS)
@pytest.mark.parametrize('kind', ['unknown', 'infrastructure'])
def test_unsafe_failures_never_resume(arm, kind):
    client = BrokenNode(kind=kind)
    result = trial(client, arm)
    assert result['fatal'] and len(client.seen) == 1
    assert len(result['attempts']) == 1
    assert result['calls'][0]['status'] == 'unknown-usage'
    assert result['calls'][0]['charged'] == result['calls'][0]['reserved']


@pytest.mark.parametrize('arm', ARMS[1:])
def test_exhaustion_never_revisits_model(arm):
    client = BrokenNode(failures=20)
    result = trial(client, arm)
    assert result['status'] == 'failed' and not result['fatal']
    assert [m for m, _ in client.seen] == ['cheap', 'mid', 'strong']


def test_global_call_limit_does_not_reset_on_whole_rerun():
    client = BrokenNode(nid='risk')
    budget = TaskCallBudget(client, 100, 100, max_calls=2, capture_payload=True)
    result = trial(client, ARMS[2], budget=budget)
    assert result['fatal'] and len(budget.records) == 2
    assert len(client.seen) == 1


@pytest.mark.parametrize('arm', ARMS[1:])
def test_cancellation_never_switches(arm):
    cancel = Event()
    class Cancel(BrokenNode):
        def complete(self, *args, **kwargs):
            response = super().complete(*args, **kwargs)
            cancel.set()
            return response
    client = Cancel()
    result = trial(client, arm, cancel_event=cancel)
    assert len(client.seen) == 1 and len(result['attempts']) == 1
    assert result['status'] != 'completed'


def test_whole_rerun_drains_inflight_and_honors_provider_interval():
    running = Event()
    class Concurrent(BrokenNode):
        def complete(self, model, messages, *, json_mode=False):
            nid = json.loads(messages[-1]['content']).get('node_id')
            if nid == 'cost' and model.model_id == 'cheap':
                assert running.wait(2)
            if nid == 'risk' and model.model_id == 'cheap':
                running.set()
                time.sleep(.03)
            return super().complete(model, messages, json_mode=json_mode)
    client = Concurrent()
    raw = protocol()
    provider = MANIFEST.candidates[0].provider
    raw['execution_policy'] = {'maxConcurrency': 2, 'providerMinIntervalMs': {provider: 10}}
    result = trial(client, ARMS[2], raw=raw)
    assert result['status'] == 'completed', result
    first, second = result['attempts']
    assert max(r['end_ms'] for r in first['nodes']) <= min(r['start_ms'] for r in second['nodes'])
    assert all(a['execution']['peak_running_nodes'] <= 2 for a in result['attempts'])
    times = sorted(c['dispatch_monotonic'] for c in result['calls'] if c['category'] == 'production')
    assert all(b - a >= .009 for a, b in zip(times, times[1:]))
    assert all(c['status'] == 'billed' for c in result['calls'])


@pytest.mark.parametrize('blocker', ['quality', 'capacity', 'cost', 'deadline'])
def test_whole_rerun_rechecks_admission(blocker):
    raw = protocol()
    client = BrokenNode()
    profiles = deepcopy(PROFILE)
    manifest = MANIFEST
    if blocker == 'quality':
        for p in profiles['candidates']:
            if p['model_id'] != 'cheap':
                p['quality'] = 79
    elif blocker == 'capacity':
        manifest = replace(MANIFEST, models=tuple(replace(m, context_window=100) if m.model_id == 'mid' else m for m in MANIFEST.models))
    elif blocker == 'cost':
        raw['constraints']['costMax'] = .035
    else:
        raw['constraints']['latencyMaxMs'] = 1
    budget = TaskCallBudget(client, 100, 100, capture_payload=True)
    result = run_trial(raw['tasks'][0], ARMS[2], raw, manifest, load_profile(profiles, manifest), budget)
    assert result['status'] != 'completed' and len(client.seen) <= 1


def test_preflight_envelope_and_freeze():
    raw = protocol()
    preview = preflight(raw, MANIFEST, PROFILE)
    assert preview['maximum_calls'] == 3 + 9 + 9 + 3
    assert len(preview['runs']) == 3 and preview['real_model_calls'] == 0
    raw['implementation_sha256'] = {}
    with pytest.raises(ValueError, match='implementation changed'):
        preflight(raw, MANIFEST, PROFILE)


def test_study_archives_inputs_outputs_and_partial_denominators(tmp_path):
    result = run_study(protocol(), MANIFEST, PROFILE, tmp_path / 'run', client=BrokenNode(kind='unknown'))
    assert result['status'] == 'stopped'
    assert sum(r['status'] == 'not-run' for r in result['runs']) == 2
    assert sum(g['planned'] for g in result['summary']['arms'].values()) == 3
    assert result['calls'][0]['request_messages']
    assert (tmp_path / 'run' / 'artifact-index.json').is_file()
    stored = json.loads((tmp_path / 'run' / 'result.json').read_text())
    assert len(next(r for r in stored['runs'] if r['status'] != 'not-run')['attempts']) == 1


def test_missing_evaluations_never_become_zero_scores():
    rows = [dict(task_id='one', repeat=1, arm=arm, status='failed', cost=3, evaluation=None) for arm in ARMS]
    report = summarize(rows, simulated=False)
    assert all(c['mean'] is None and c['excluded_pairs'] == 1 for c in report['comparisons'])
    assert all(g['total_cost'] == 3 and g['delivery_rate'] == 0 for g in report['arms'].values())


def test_deadline_after_billed_failure_never_gets_a_fresh_deadline():
    class Slow(BrokenNode):
        def complete(self, *args, **kwargs):
            time.sleep(.03)
            return super().complete(*args, **kwargs)
    raw = protocol()
    raw['constraints']['latencyMaxMs'] = 20
    profiles = deepcopy(PROFILE)
    for p in profiles['candidates']:
        p['latency_ms'] = 1
    client = Slow()
    result = run_trial(raw['tasks'][0], ARMS[2], raw, MANIFEST, load_profile(profiles, MANIFEST),
        TaskCallBudget(client, 100, 100))
    assert len(client.seen) == 1 and len(result['attempts']) == 1
    assert result['status'] != 'completed'


@pytest.mark.parametrize('arm', ARMS[1:])
def test_final_quality_failure_is_not_a_recovery_trigger(arm):
    class LowScore(Client):
        def complete(self, model, messages, *, json_mode=False):
            value = super().complete(model, messages, json_mode=json_mode)
            if model.role == 'judge':
                judged = json.loads(value.content)
                judged['score'] = 40
                return replace(value, content=json.dumps(judged))
            return value
    result = trial(LowScore(), arm)
    assert result['status'] == 'quality-failed' and result['recovery_triggers'] == 0
    assert len(result['attempts']) == 1


def test_response_archive_failure_is_fatal():
    client = BrokenNode()
    budget = TaskCallBudget(client, 100, 100, capture_payload=True)
    def fail(row, response):
        raise OSError('无法写入证据')
    budget.on_response = fail
    result = trial(client, ARMS[2], budget=budget)
    assert result['fatal'] and len(result['attempts']) == 1
    assert result['calls'][0]['status'] == 'unknown-usage'


def test_whole_rerun_shares_actual_production_budget():
    client = BrokenNode(nid='answer', kind='truncated')
    first = trial(client, ARMS[0])
    spent = sum(c['charged'] for c in first['calls'])
    # 允许最初 cheap 图的全部预留，却不足以承担 mid 的单次保守预留。
    client = BrokenNode(nid='answer', kind='truncated')
    budget = TaskCallBudget(client, max(.04, max(c['reserved'] for c in first['calls']) + spent), 100, capture_payload=True)
    result = trial(client, ARMS[2], budget=budget)
    assert result['status'] != 'completed'
    assert all(c['model_id'] == 'cheap' for c in result['calls'])
    assert budget.snapshot()[0]['production'] == pytest.approx(spent)


def test_settled_judge_failure_continues_independent_samples(tmp_path):
    class BadJudge(Client):
        max_retries = 0
        def complete(self, model, messages, *, json_mode=False):
            value = super().complete(model, messages, json_mode=json_mode)
            return replace(value, content='无法解析') if model.role == 'judge' else value
    result = run_study(protocol(), MANIFEST, PROFILE, tmp_path / 'run', client=BadJudge())
    assert result['status'] == 'completed'
    assert all(r['status'] == 'failed' and not r['fatal'] for r in result['runs'])
    assert len(result['calls']) == 12
    assert all(r['recovery_triggers'] == 0 for r in result['runs'])


def test_persistence_value_error_cannot_impersonate_a_judge_failure():
    from refractrouter.recovery_study import EvidenceFailure
    client = Client()
    budget = TaskCallBudget(client, 100, 100)
    def fail():
        raise ValueError('invalid judge response')
    with pytest.raises(EvidenceFailure):
        trial(client, ARMS[2], budget=budget, persist=fail)
    assert budget.stopped and not client.calls
