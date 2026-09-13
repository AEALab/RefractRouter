"""不限总时间必须贯通调度、请求期限与取消；不发起真实调用。"""
import json
import time
from pathlib import Path
from threading import Event
from unittest.mock import patch

from refractrouter.agent import run_agent, build_request
from refractrouter.agent_cli import example_configuration
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.task_budget import TaskCallBudget
from tests.test_text_tasks import Client, REQUEST, MANIFEST, PROFILE
from refractrouter.task_runtime import run_task
from dataclasses import replace
from tests.test_openai_compatible import real_model, success_response, SequenceTransport


def test_unlimited_application_completes_beyond_configured_limit(tmp_path):
    class Slow(Client):
        def complete(self,*args,**kwargs):
            time.sleep(.01)
            return super().complete(*args,**kwargs)
    config=example_configuration('openai-compatible')
    result=run_agent({'task':'离线测试','limits':{'unlimitedTime':True}},provider_config=config,
        mode='live',execute_paid_run=True,runs_dir=tmp_path,timeout_ms=1,client=Slow())
    assert result['status']=='completed',result['issues']
    saved=json.loads((Path(result['run_dir'])/'result.json').read_text())
    assert saved['routing']['latency_max_ms'] is None
    assert saved['wall_time_ms']>1
    json.dumps(saved,allow_nan=False)
    limited=run_agent({'task':'离线测试','limits':{'unlimitedTime':False}},provider_config=config,
        mode='live',execute_paid_run=True,runs_dir=tmp_path,timeout_ms=1,client=Slow())
    assert limited['status']!='completed'


def test_unlimited_still_honors_cancellation_and_budget():
    event=Event();event.set()
    result=run_task({**REQUEST,'unlimitedTime':True},MANIFEST,{**PROFILE,'kind':'empirical'},client=Client(),production_limit=100,evaluation_limit=100,cancel_event=event)
    assert result['status']=='cancelled'
    _,req,_,limits=build_request({'task':'mock','limits':{'unlimitedTime':True}},mode='live',production_budget=1,timeout_ms=1)
    assert req['costMax']==1 and limits['relaxBudget'] is False


def test_unlimited_request_passes_none_to_transport():
    transport=SequenceTransport([success_response()])
    client=OpenAICompatibleClient(transport=transport,environment={'TEST_API_KEY':'mock'},max_retries=0)
    budget=TaskCallBudget(client,100,100)
    budget.complete(replace(real_model(),context_window=32768),[],label='node',timeout_seconds=float('inf'))
    assert transport.calls[0]['timeout'] is None
