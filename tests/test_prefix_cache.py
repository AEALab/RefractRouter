"""前缀字节、可观测缓存及实发一致性；全部使用模拟响应。"""
from copy import deepcopy
from dataclasses import replace
import json
import os
import time

import pytest

from refractrouter.agent import plan_template
from refractrouter.cache_usage import cache_usage
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse, model_response_cost
from refractrouter.task_budget import request_input_bound
from refractrouter.task_execution import node_messages
from refractrouter.task_inputs import prepare_inputs
from refractrouter.task_plan import validate_plan
from tests.test_openai_compatible import real_model
from tests.test_selective_context import ContextClient, run, MATERIALS


def test_stable_prefix_keeps_task_before_node_differences_without_changing_content():
    plan = validate_plan(plan_template('single', ['保留证据']))
    node = plan.nodes[0]
    contract = plan.contracts[node.node_id]
    task = '共享的原始材料，不添加填充。'
    old = node_messages(task, node, contract, {})
    stable = node_messages(task, node, contract, {}, prefix_policy='stable-v1')
    other = node_messages(task, replace(node, node_id='other', prompt_template='另一职责'),
                          contract, {}, prefix_policy='stable-v1')
    assert old[0] == stable[0] == other[0]
    assert json.loads(old[1]['content']) == json.loads(stable[1]['content'])
    assert old[1]['content'].startswith('{"node_id":')
    assert stable[1]['content'].startswith('{"task":')
    assert task in os.path.commonprefix([stable[1]['content'], other[1]['content']])
    reverse = {k: contract[k] for k in reversed(contract)}
    assert stable == node_messages(task, node, reverse, {}, prefix_policy='stable-v1')


def test_global_materials_and_criteria_precede_local_even_if_input_order_differs():
    request = {'task': '核对', 'prefixPolicy': 'stable-v1', 'acceptanceCriteria': ['保留限制'],
        'materials': [MATERIALS[1], MATERIALS[0], MATERIALS[2], MATERIALS[3]]}
    original = deepcopy(request)
    _, task, _ = prepare_inputs(request, for_node=True)
    assert task.index('保留限制') < task.index('保留免责条款') < task.index('费用原始记录')
    _, judge, _ = prepare_inputs(request)
    _, legacy, _ = prepare_inputs({**request, 'prefixPolicy': 'legacy'})
    assert judge == legacy
    assert request == original
    for source in request['materials']:
        assert source['text'] in task


@pytest.mark.parametrize('policy', ['legacy', 'stable-v1'])
def test_selective_forecasts_equal_dispatch_and_parallel_scheduler_unchanged(tmp_path, policy):
    summary, raw = run(tmp_path, ContextClient(), prefixPolicy=policy, maxConcurrency=2)
    assert summary['status'] == 'completed', summary['issues']
    assert summary['prefix_policy'] == policy
    assert len(raw['calls']) == 5
    assert raw['execution']['policy']['max_concurrency'] == 2
    for nid in ('cost_node', 'risk_node'):
        call = next(c for c in raw['calls'] if c['label'] == nid)
        assert request_input_bound(call['request_messages']) == raw['plan_admission'][nid]['input_estimate']['base_input_bound']
        assert call['ttft_ms'] is None and call['cache_usage_available'] is False


def test_final_judge_receives_identical_input_across_layouts(tmp_path):
    results = [run(tmp_path / policy, ContextClient(), prefixPolicy=policy)[1]
               for policy in ('legacy', 'stable-v1')]
    judges = [next(c['request_messages'] for c in raw['calls'] if c['label'] == 'final-judge') for raw in results]
    assert judges[0] == judges[1]


@pytest.mark.parametrize('usage, expected, source', [
    ({}, 0, None),
    ({'prompt_tokens_details': {'cached_tokens': 0}}, 0, 'prompt_tokens_details.cached_tokens'),
    ({'prompt_tokens_details': {'cached_tokens': 12}}, 12, 'prompt_tokens_details.cached_tokens'),
    ({'input_tokens_details': {'cached_tokens': 13}}, 13, 'input_tokens_details.cached_tokens'),
    ({'prompt_cache_hit_tokens': 14}, 14, 'prompt_cache_hit_tokens'),
])
def test_cache_missing_zero_and_reported_positive_are_distinct(usage, expected, source):
    raw = {'choices': [{'message': {'content': '已核对'}, 'finish_reason': 'stop'}],
           'usage': {'prompt_tokens': 100, 'completion_tokens': 20, **usage}}
    response = OpenAICompatibleClient._parse_response(
        TransportResponse(200, {}, json.dumps(raw).encode()), 1, time.perf_counter())
    assert response.usage_available
    assert response.cached_input_tokens == expected and response.cache_usage_source == source
    assert response.ttft_ms is None
    model = real_model()
    undiscounted = replace(model, cached_input_cost_per_1k=model.input_cost_per_1k)
    assert model_response_cost(undiscounted, response) == model_response_cost(undiscounted, replace(response, cached_input_tokens=0))


@pytest.mark.parametrize('value', [-1, 101, True, '5', None, {}, []])
def test_invalid_cache_usage_is_not_silently_billed(value):
    assert cache_usage({'prompt_cache_hit_tokens': value}, 100)[2] is False


def test_conflicting_cache_aliases_are_unknown_usage():
    assert cache_usage({'prompt_tokens_details': {'cached_tokens': 12},
                        'prompt_cache_hit_tokens': 13}, 100)[2] is False


def test_unknown_policy_fails_before_any_call(tmp_path):
    client = ContextClient()
    with pytest.raises(ValueError, match='prefixPolicy'):
        run(tmp_path, client, prefixPolicy='bad')
    assert not client.calls


def test_full_frozen_diagnostic_envelope_with_mock_provider(tmp_path):
    from experiments.validate_prefix_cache import execute, freeze
    from refractrouter.openai_compatible import ChatResponse
    class DiagnosticClient:
        def complete(self, model, messages, **kwargs):
            payload = json.loads(messages[-1]['content'])
            if 'answer' in payload and 'criteria' in payload:
                content = json.dumps({'passed': True, 'score': 90, 'rationale': '模拟',
                    'criteria': [{'criterion': c, 'passed': True, 'rationale': '模拟'} for c in payload['criteria']]})
            elif payload['contract']['output']['format'] == 'json':
                content = json.dumps({k: '模拟证据与限制' for k in payload['contract']['output']['fields']})
            else:
                content = '模拟答案'
            return ChatResponse(content, 100, 100, 0, 0, 10, 1, 'stop', None)
        def for_task_call(self, timeout):
            return self
    frozen = freeze()
    assert freeze()['sha256'] == frozen['sha256']
    from refractrouter.agent import atomic_json
    atomic_json(tmp_path / 'frozen.json', frozen)
    execute(frozen, tmp_path, DiagnosticClient())
    status = json.loads((tmp_path / 'run-status.json').read_text())
    assert status['actual_calls'] == frozen['protocol']['maximum_calls'] == 44
    results = json.loads((tmp_path / 'applications.json').read_text())
    assert len(results) == 4 and all(r['status'] == 'completed' for r in results)
    probes = json.loads((tmp_path / 'probe-ledger.json').read_text())
    assert len(probes['calls']) == 32 and all(c['status'] == 'billed' for c in probes['calls'])
    assert all(c['cache_usage_available'] is False for c in probes['calls'])
    from experiments.analyze_prefix_cache import analyze
    report = analyze(tmp_path, tmp_path / 'analysis')
    assert report['ledger_calls'] == report['actual_calls'] == 44
    assert report['cache_unknown_calls'] == 44
    assert report['observed_cached_tokens'] == 0 and report['human_quality_verified'] is False
    assert all(r['cached_tokens'] is None for r in report['probes'])


def test_batch_unknown_usage_drains_siblings_and_preserves_ledger(tmp_path):
    from experiments.validate_prefix_cache import execute, freeze
    from refractrouter.openai_compatible import ChatResponse
    class MissingUsage:
        def complete(self, *args, **kwargs):
            return ChatResponse('不可确认用量', 0, 0, 0, 0, 10, 1, 'stop', None, usage_available=False)
        def for_task_call(self, timeout):
            return self
    with pytest.raises(ValueError, match='usage'):
        execute(freeze(), tmp_path, MissingUsage())
    ledger = json.loads((tmp_path / 'probe-ledger.json').read_text())
    assert len(ledger['calls']) == 2
    assert all(c['status'] == 'unknown-usage' and c['charged'] > 0 for c in ledger['calls'])
    assert (tmp_path / 'artifact-index.json').exists()
