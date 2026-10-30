"""缺失或异常零用量不能释放预留并伪装免费；必须保留原始计量证据。"""
from dataclasses import asdict, replace
import json
from pathlib import Path
import time

import pytest

from refractrouter.openai_compatible import ChatResponse, OpenAICompatibleClient, TransportResponse
from refractrouter.task_budget import TaskCallBudget
from tests.test_openai_compatible import real_model


@pytest.mark.parametrize('usage', [None, {}, {'prompt_tokens':12}, {'prompt_tokens':0,'completion_tokens':0}])
def test_unconfirmed_usage_retains_reservation_and_raw_response(usage):
    payload={'choices':[{'message':{'content':'{"result":"片段'},'finish_reason':''}]}
    if usage is not None:payload['usage']=usage
    response=OpenAICompatibleClient._parse_response(TransportResponse(200,{},json.dumps(payload).encode()),1,time.perf_counter())
    class Client:
        def complete(self,*args,**kwargs):return response
    budget=TaskCallBudget(Client(),100,100)
    archived=[]
    budget.on_response=lambda row,value:archived.append(asdict(value))
    with pytest.raises(ValueError,match='missing or unconfirmed model usage'):
        budget.complete(replace(real_model(),context_window=65536),[{'role':'user','content':'固定输入'}],label='probe')
    _,calls=budget.snapshot()
    assert calls[0]['status']=='unknown-usage' and calls[0]['charged']==calls[0]['reserved']>0
    assert archived[0]['raw_usage']==usage and archived[0]['content']==response.content
    assert response.usage_available is (usage=={'prompt_tokens':0,'completion_tokens':0})


def test_archived_partial_response_is_rejected_before_zero_cost_billing():
    root=Path(__file__).resolve().parents[1]/'reports/dag-decomposition/issue-32-independent-samples-20260908/study'
    import hashlib
    label='cash_holdout_v4--2--dag-single-b:cost'
    raw=json.loads((root/'calls'/(hashlib.sha256(label.encode()).hexdigest()+'-response.json')).read_text())
    response=ChatResponse(**{k:v for k,v in raw.items() if k!='label'})
    class Client:
        def complete(self,*args,**kwargs):return response
    budget=TaskCallBudget(Client(),100,100)
    with pytest.raises(ValueError,match='unconfirmed model usage'):
        budget.complete(replace(real_model(),context_window=65536),[{'role':'user','content':'固定输入'}],label=label)
    assert budget.snapshot()[1][0]['status']=='unknown-usage'


@pytest.mark.parametrize('reasoning', [True, False, '8', 8.5, -1, None, {}, [], 25])
def test_settlement_rejects_invalid_reasoning_even_for_confirmed_typed_receipt(reasoning):
    response=ChatResponse(content='受控回复',input_tokens=80,output_tokens=24,cached_input_tokens=20,
        reasoning_tokens=reasoning,latency_ms=1,attempts=1,finish_reason='stop',request_id='fixture',
        usage_available=True,raw_usage={'completion_tokens_details':{'reasoning_tokens':reasoning}})
    class Client:
        def complete(self,*args,**kwargs):return response
    budget=TaskCallBudget(Client(),100,100,capture_payload=True)
    with pytest.raises(ValueError,match='invalid model usage'):
        budget.complete(replace(real_model(),context_window=65536),
                        [{'role':'user','content':'固定输入'}],label='reasoning-boundary')
    _,calls=budget.snapshot()
    assert calls[0]['status']=='unknown-usage' and calls[0]['charged']==calls[0]['reserved']>0
    assert calls[0]['response']['raw_usage']==response.raw_usage


@pytest.mark.parametrize('extra', [
    {'input_tokens': 0}, {'output_tokens': 0}, {'total_tokens': 1}, {'total_tokens': True},
    {'output_tokens_details': {'reasoning_tokens': 9}},
])
def test_conflicting_usage_aliases_retain_reservation_and_raw_evidence(extra):
    raw = {'choices': [{'message': {'content': '中文回复'}, 'finish_reason': 'stop'}],
           'usage': {'prompt_tokens': 80, 'completion_tokens': 24, 'total_tokens': 104,
                     'completion_tokens_details': {'reasoning_tokens': 8}, **extra}}
    response = OpenAICompatibleClient._parse_response(
        TransportResponse(200, {}, json.dumps(raw).encode()), 1, time.perf_counter())
    assert response.usage_available is False and response.raw_usage == raw['usage']
    class Client:
        def complete(self, *args, **kwargs):
            return response
    budget = TaskCallBudget(Client(), 100, 100, capture_payload=True)
    with pytest.raises(ValueError, match='unconfirmed'):
        budget.complete(replace(real_model(), context_window=65536),
                        [{'role': 'user', 'content': '输入'}], label='alias-conflict')
    row = budget.snapshot()[1][0]
    assert row['status'] == 'unknown-usage' and row['charged'] == row['reserved'] > 0


def test_matching_usage_aliases_and_known_secondary_reasoning_are_kept():
    usage = {'prompt_tokens': 80, 'input_tokens': 80, 'completion_tokens': 24, 'output_tokens': 24,
             'total_tokens': 104, 'completion_tokens_details': {'other': 0},
             'output_tokens_details': {'reasoning_tokens': 8}}
    response = OpenAICompatibleClient._parse_response(TransportResponse(200, {}, json.dumps({
        'choices': [{'message': {'content': '回复'}, 'finish_reason': 'stop'}], 'usage': usage}).encode()),
        1, time.perf_counter())
    assert response.usage_available is True and response.reasoning_tokens == 8


@pytest.mark.parametrize('write_price', [.02, .01, .04, 0.])
def test_unknown_cache_write_only_blocks_when_it_changes_amount(write_price):
    from refractrouter.planning_config import PlanningModel
    response = ChatResponse('已知总用量', 100, 20, 0, 0, 1, 1, 'stop', 'fixture')
    class Client:
        def complete(self, *args, **kwargs):
            return response
    model = replace(PlanningModel(**asdict(real_model())), context_window=65536, billing_unit='CNY',
                    input_cost_per_1k=.02, cache_write_cost_per_1k=write_price)
    budget = TaskCallBudget(Client(), 100, 100)
    if write_price != model.input_cost_per_1k:
        with pytest.raises(ValueError, match='unconfirmed cache write usage'):
            budget.complete(model, [{'role': 'user', 'content': '输入'}], label='cache-write-price')
        assert budget.snapshot()[1][0]['status'] == 'unknown-usage'
    else:
        budget.complete(model, [{'role': 'user', 'content': '输入'}], label='cache-write-price')
        row = budget.snapshot()[1][0]
        assert row['status'] == 'billed' and row['cache_write_usage_available'] is False
        assert row['cache_write_tokens'] is None  # 金额可确定，不补造未知细分。


@pytest.mark.parametrize('hour', [10, 22])
@pytest.mark.parametrize('write_tokens', [None, 0, 100])
def test_missing_cache_write_uses_dispatch_time_materialized_price(hour, write_tokens):
    from refractrouter.application_config import ApplicationModelSpec
    model = ApplicationModelSpec(**{**asdict(real_model()), 'context_window': 65536,
        'api_model': 'deepseek-flash', 'billing_unit': 'CNY', 'input_cost_per_1k': .002,
        'cache_write_cost_per_1k': .002, 'price_policy': 'deepseek-official-cny-v1'})
    raw = None if write_tokens is None else {'cacheWriteTokens': write_tokens}
    response = ChatResponse('回复', 100, 20, 0, 0, 1, 1, 'stop', 'fixture', raw_usage=raw)
    budget = TaskCallBudget(None, 100, 100)
    reservation = budget.reserve(model, [{'role': 'user', 'content': '输入'}], label='dispatch-price')
    budget.dispatch(reservation)
    reservation.row['dispatch_at'] = f'2026-10-28T{hour}:00:00+08:00'
    if hour == 22 and write_tokens is None:
        with pytest.raises(ValueError, match='unconfirmed cache write usage'):
            budget.settle(reservation, response)
        assert reservation.row['status'] == 'unknown-usage'
    else:
        budget.settle(reservation, response)
        expected = .00036 if hour == 10 else .00018 + write_tokens * .000001
        assert reservation.row['charged'] == pytest.approx(expected)
        assert reservation.row['cache_write_usage_available'] is (write_tokens is not None)
