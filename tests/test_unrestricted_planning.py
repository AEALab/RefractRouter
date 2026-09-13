"""无规划超时贯穿HTTP与执行时钟，规划容量不被节点上限截断。"""
import json
from unittest.mock import patch
import pytest
from refractrouter.agent import run_agent
from refractrouter.application_config import compile_configuration
from refractrouter.ark_plan import application_configuration
from refractrouter.compact_planning import planner_model
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse
from tests.test_fast_dynamic_dag import Client


def test_large_model_capacity_reaches_http_and_timeout_is_none():
    config=compile_configuration(application_configuration())
    planner,_=planner_model({m.model_id:m for m in config.manifest.candidates},configuration=config,unrestricted=True)
    class Transport:
        def post(self,url,headers,body,timeout_seconds):
            request=json.loads(body)
            assert request['max_completion_tokens']==128000
            assert 'thinking' not in request
            assert timeout_seconds is None
            return TransportResponse(200,{},json.dumps({'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],
                'usage':{'prompt_tokens':10,'completion_tokens':2}}).encode())
    original=OpenAICompatibleClient(transport=Transport(),environment={'CODEX_ARK_API_KEY':'test'},max_retries=0)
    original.for_task_call(None).complete(planner,[{'role':'user','content':'test'}])
    assert original.timeout_seconds==120


def test_hour_long_planning_does_not_consume_execution_deadline(tmp_path):
    now=[100.0]
    class SlowPlanner(Client):
        def complete(self,model,messages,**kwargs):
            if not self.calls:now[0]+=3600
            return super().complete(model,messages,**kwargs)
    with patch('time.monotonic',lambda:now[0]):
        result=run_agent({'task':'测试规划等待','template':'auto'},provider_config=application_configuration(),
            client=SlowPlanner(),mode='live',execute_paid_run=True,runs_dir=tmp_path,timeout_ms=60000)
    assert result['status']=='completed',result['issues']
    assert result['planner']['timeout_ms'] is None


@pytest.mark.parametrize('thinking',['enabled','disabled','inherit'])
def test_planner_thinking_setting_changes_only_planner(tmp_path,thinking):
    config=application_configuration();config['plannerThinking']=thinking
    client=Client()
    result=run_agent({'task':'测试规划配置','template':'auto'},provider_config=config,client=client,
        mode='live',execute_paid_run=True,runs_dir=tmp_path)
    assert result['status']=='completed',result['issues']
    assert client.calls[0][0].request_options.get('thinking')==({'type':thinking} if thinking!='inherit' else None)
    assert all('thinking' not in m.request_options for m,p,_ in client.calls[1:] if 'node_id' in p)
