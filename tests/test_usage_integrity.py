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
