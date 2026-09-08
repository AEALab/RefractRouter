"""使用同步事件而非真实模型验证并发、派发间隔和费用语义。"""
from concurrent.futures import ThreadPoolExecutor, CancelledError
from copy import deepcopy
from dataclasses import replace
import json
from threading import Barrier, Event, Lock
import time

import pytest

from refractrouter.model_selection import Weights
from refractrouter.node_routing import NodeProfile, route_nodes
from refractrouter.task_budget import TaskCallBudget
from refractrouter.task_plan import validate_plan
from refractrouter.task_runtime import run_task, validate_request
from refractrouter.task_scheduling import ExecutionPolicy, estimate_schedule
from tests.test_task_decomposition import example
from tests.test_text_tasks import Client, MANIFEST, PROFILE, REQUEST, live


class OverlapClient(Client):
    def __init__(self):
        super().__init__()
        self.barrier = Barrier(2)

    def complete(self, model, messages, *, json_mode=False):
        if json.loads(messages[-1]['content']).get('node_id') in {'cost', 'risk'}:
            self.barrier.wait(timeout=2)
        return super().complete(model, messages, json_mode=json_mode)


def test_independent_nodes_overlap_and_join_waits_for_both():
    result = live(OverlapClient(), plan=example(), maxConcurrency=2)
    assert result['status'] == 'completed', result['issues']
    rows = {n['node_id']: n for n in result['nodes']}
    assert max(rows[n]['start_ms'] for n in ('cost', 'risk')) < min(rows[n]['end_ms'] for n in ('cost', 'risk'))
    assert rows['answer']['start_ms'] >= max(rows[n]['end_ms'] for n in ('cost', 'risk'))
    assert result['execution']['peak_active_nodes'] == 2
    prediction = result['routing']['prediction']
    assert prediction['scheduled_latency_ms'] < prediction['serial_latency_ms']
    assert result['plan_analysis']['execution_mode'] == 'bounded-parallel'
    assert all(n['queue_ms'] >= 0 for n in result['nodes'])


class MeteredClient(Client):
    def __init__(self):
        super().__init__()
        self.lock, self.active, self.peak, self.starts = Lock(), 0, 0, []

    def complete(self, model, messages, *, json_mode=False):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            if model.role != 'judge':
                self.starts.append(time.monotonic())
        time.sleep(.01)
        try:
            return super().complete(model, messages, json_mode=json_mode)
        finally:
            with self.lock:
                self.active -= 1


def test_provider_limit_and_request_spacing_are_enforced():
    provider = MANIFEST.candidates[0].provider
    client = MeteredClient()
    result = live(client, plan=example(), maxConcurrency=2, providerConcurrency={provider: 1})
    assert result['status'] == 'completed' and client.peak == 1
    client = MeteredClient()
    result = live(client, plan=example(), maxConcurrency=2, providerMinIntervalMs={provider: 50})
    assert result['status'] == 'completed'
    assert all(b-a >= .045 for a, b in zip(client.starts, client.starts[1:]))
    assert result['routing']['prediction']['schedule']['nodes']['risk']['start_ms'] >= 50


def pipeline():
    return validate_plan({'nodes': [
        {'node_id': nid, 'node_type': 'generation', 'parents': parents, 'prompt_template': nid}
        for nid, parents in [('fast', []), ('slow', []), ('child', ['fast']), ('answer', ['child', 'slow'])]],
        'final_node_id': 'answer', 'acceptance_criteria': ['完整回答']})


def test_dispatch_has_no_artificial_wave_barrier():
    child_started = Event()
    class PipelineClient(Client):
        def complete(self, model, messages, *, json_mode=False):
            nid = json.loads(messages[-1]['content']).get('node_id')
            if nid == 'slow':
                assert child_started.wait(2), '不应等待整层所有节点后才释放 child'
            if nid == 'child':
                child_started.set()
            return super().complete(model, messages, json_mode=json_mode)
    result = live(PipelineClient(), plan=pipeline().to_dict(), maxConcurrency=2)
    assert result['status'] == 'completed'
    rows = {n['node_id']: n for n in result['nodes']}
    assert rows['child']['start_ms'] < rows['slow']['end_ms']
    estimated = estimate_schedule(pipeline(), {'fast': 1, 'slow': 10, 'child': 1, 'answer': 1},
                                  {n.node_id: 'provider' for n in pipeline().nodes}, ExecutionPolicy(2))
    assert estimated['makespan_ms'] == 11
    assert estimated['nodes']['child']['start_ms'] == 1


def test_atomic_reservations_prevent_two_concurrent_admissions_over_budget():
    entered, release, rejected = Event(), Event(), Event()
    class Blocked(Client):
        def complete(self, model, messages, *, json_mode=False):
            entered.set()
            assert release.wait(2)
            return super().complete(model, messages, json_mode=json_mode)
    model = MANIFEST.candidates[0]
    messages = [{'role': 'user', 'content': '{}'}]
    probe = TaskCallBudget(Client(), 100, 100).reserve(model, messages, label='probe').row['reserved']
    client = Blocked()
    budget = TaskCallBudget(client, probe * 1.5, 100)
    barrier = Barrier(2)
    def attempt(label):
        barrier.wait(2)
        try:
            return budget.complete(model, messages, label=label)
        except ValueError:
            rejected.set()
            return None
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(attempt, label) for label in ('a', 'b')]
        try:
            assert entered.wait(1) and rejected.wait(1)
        finally:
            release.set()
        results = [f.result() for f in futures]
    assert sum(r is not None for r in results) == 1
    assert len(client.calls) == len(budget.records) == 1
    assert budget.charged['production'] <= budget.limits['production']


@pytest.mark.parametrize('trigger', ['cancel', 'failure', 'deadline'])
def test_stop_dispatch_drains_inflight_calls_and_retains_cost(trigger):
    both_started, release, stopped, cancel = Event(), Event(), Event(), Event()
    barrier = Barrier(2)
    class Controlled(Client):
        def complete(self, model, messages, *, json_mode=False):
            nid = json.loads(messages[-1]['content']).get('node_id')
            if nid in {'cost', 'risk'}:
                barrier.wait(2)
                both_started.set()
                if trigger == 'failure' and nid == 'cost':
                    raise RuntimeError('不得泄漏的 Provider 诊断')
                assert release.wait(2)
            return super().complete(model, messages, json_mode=json_mode)
    snapshots = []
    def checkpoint(result):
        snapshots.append(deepcopy(result))
        if result.get('execution', {}).get('dispatch_stopped'):
            stopped.set()
    profile = deepcopy(PROFILE)
    profile['kind'] = 'empirical'
    for row in profile['candidates']:
        row['latency_ms'] = 1
    request = {**REQUEST, 'plan': example(), 'maxConcurrency': 2,
               'latencyMaxMs': 150 if trigger == 'deadline' else 300000}
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(run_task, request, MANIFEST, profile, client=Controlled(),
            production_limit=100, evaluation_limit=100, cancel_event=cancel, checkpoint=checkpoint)
        try:
            assert both_started.wait(1)
            if trigger == 'cancel':
                cancel.set()
            assert stopped.wait(1)
        finally:
            release.set()
        result = future.result(timeout=2)
    assert result['status'] == ('cancelled' if trigger == 'cancel' else 'failed')
    assert result['execution']['not_started'] == ['answer']
    assert result['evaluation'] is None and not result['final_output']
    assert len(result['calls']) == 2
    assert result['charged']['production'] > 0
    assert '不得泄漏' not in str(result['issues'])
    statuses = {row['status'] for row in result['calls']}
    assert statuses == ({'unknown-usage', 'billed'} if trigger == 'failure' else {'billed'})
    assert any(row['status'] == 'reserved' for snapshot in snapshots for row in snapshot['calls'])


def test_cancelled_reservation_is_released_only_before_dispatch():
    client = Client()
    budget = TaskCallBudget(client, 100, 100)
    reservation = budget.reserve(MANIFEST.candidates[0], [{'role': 'user', 'content': '{}'}], label='pending')
    budget.stop()
    with pytest.raises(CancelledError):
        budget.invoke(reservation)
    assert not client.calls and budget.charged['production'] == 0
    assert budget.records[0]['status'] == 'cancelled-before-dispatch'


def test_weighted_latency_does_not_pay_to_accelerate_a_noncritical_branch():
    plan = validate_plan({'nodes': [
        {'node_id': 'long', 'node_type': 'planning', 'parents': [], 'prompt_template': '长分支'},
        {'node_id': 'short', 'node_type': 'synthesis', 'parents': [], 'prompt_template': '短分支'},
        {'node_id': 'answer', 'node_type': 'generation', 'parents': ['long', 'short'], 'prompt_template': '汇总'}],
        'final_node_id': 'answer', 'acceptance_criteria': ['完整回答']})
    profiles = (NodeProfile('long_model', 'planning', 90, 1, 10, 3),
                NodeProfile('cheap', 'synthesis', 90, 1, 5, 3),
                NodeProfile('fast', 'synthesis', 90, 5, 1, 3),
                NodeProfile('writer', 'generation', 90, 1, 1, 3))
    result = route_nodes(plan, profiles, method='B', quality_min=80, cost_max=10,
        latency_max_ms=20, weights=Weights(0, 0, 1), execution_policy=ExecutionPolicy(2))
    assert result['assignments']['short'] == 'cheap'
    assert result['prediction']['scheduled_latency_ms'] == 11
    assert result['prediction']['cost'] == 3


@pytest.mark.parametrize('fields', [
    {'maxConcurrency': True}, {'maxConcurrency': 9}, {'maxConcurrency': 0},
    {'providerConcurrency': []}, {'providerConcurrency': {'openai': 0}},
    {'providerMinIntervalMs': {'openai': -1}}, {'providerMinIntervalMs': None},
])
def test_invalid_execution_policy_rejected(fields):
    with pytest.raises(ValueError):
        validate_request({**REQUEST, **fields})


def test_usage_above_reservation_stops_even_with_remaining_global_budget():
    class ExcessUsage(Client):
        def complete(self, model, messages, *, json_mode=False):
            return replace(super().complete(model, messages, json_mode=json_mode), output_tokens=100000)
    budget = TaskCallBudget(ExcessUsage(), 1000, 1000)
    with pytest.raises(ValueError, match='reserve'):
        budget.complete(MANIFEST.candidates[0], [{'role': 'user', 'content': '{}'}], label='unexpected-usage')
    charged, rows = budget.snapshot()
    assert budget.stopped and rows[0]['status'] == 'billed'
    assert rows[0]['reserved'] < charged['production'] < 1000
    with pytest.raises(CancelledError):
        budget.reserve(MANIFEST.candidates[0], [], label='blocked')


def test_concurrent_clients_have_isolated_timeouts_and_progress_ids(tmp_path):
    from refractrouter.openai_compatible import OpenAICompatibleClient
    from tests.test_openai_compatible import real_model, success_response
    class Transport:
        def __init__(self):
            self.barrier, self.timeouts = Barrier(2), []
        def post(self, url, headers, body, timeout_seconds):
            self.timeouts.append(timeout_seconds)
            self.barrier.wait(2)
            return success_response('模拟输出')
    transport = Transport()
    progress = tmp_path/'progress.ndjson'
    client = OpenAICompatibleClient(transport=transport, timeout_seconds=120, max_retries=0,
        environment={'TEST_API_KEY': '测试凭证', 'REFRACTROUTER_MODEL_PROGRESS': str(progress)})
    def invoke(timeout):
        return client.for_task_call(timeout).complete(real_model(), [{'role': 'user', 'content': '测试'}])
    with ThreadPoolExecutor(2) as pool:
        assert all(response.content == '模拟输出' for response in pool.map(invoke, [3, 7]))
    assert sorted(transport.timeouts) == [3, 7]
    assert client.timeout_seconds == 120 and client.progress_request_id == 0
    rows = [json.loads(line) for line in progress.read_text().splitlines()]
    starts = [r for r in rows if r['event'] == 'request-start']
    finishes = [r for r in rows if r['event'] == 'request-finish']
    assert len(starts) == len(finishes) == 2
    assert len({r['request_id'] for r in starts}) == 2
    assert {r['request_id'] for r in starts} == {r['request_id'] for r in finishes}
