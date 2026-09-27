"""真实本地 HTTP 流，确定性验收释放时序、审核和失败记账。"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.request import Request, urlopen

import pytest

from refractrouter.model_gateway import ModelGateway, create_server
from tests.test_planning_routing import configuration, escalation_configuration


def upstream(*, unknown=False, disconnect=False):
    observed, released, finish_allowed = [], Event(), Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append(request)
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
            def chunk(delta=None, finish=None, usage=None):
                value={'id':'upstream','choices':[] if usage is not None else [{'index':0,'delta':delta or {},'finish_reason':finish}]}
                if usage is not None: value['usage']=usage
                self.wfile.write(b'data: '+json.dumps(value).encode()+b'\n\n');self.wfile.flush()
            chunk({'content':'第一段'});released.set()
            assert finish_allowed.wait(5)
            if disconnect: return
            chunk({'content':'第二段'})
            chunk({},'stop')
            if not unknown: chunk(usage={'prompt_tokens':20,'completion_tokens':10})
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    Thread(target=server.serve_forever,daemon=True).start()
    return server,observed,released,finish_allowed


def real_gateway(tmp_path, upstream):
    config=configuration('static')
    for model in config['models']: model['provider']='fixture'
    return ModelGateway({'planningRouting':config,'providers':{'fixture':{
        'baseURL':f'http://127.0.0.1:{upstream.server_port}/v1'}}},tmp_path)


@pytest.mark.parametrize('responses',[False,True])
@pytest.mark.parametrize('failure',[None,'unknown','disconnect'])
def test_first_text_arrives_before_upstream_finish_and_errors_have_no_success(tmp_path,responses,failure):
    up,seen,released,finish=upstream(unknown=failure=='unknown',disconnect=failure=='disconnect')
    gw=real_gateway(tmp_path,up);server=create_server(gw,port=0)
    Thread(target=server.serve_forever,daemon=True).start()
    body={'model':'refract/static','stream':True,**({'input':'你好','store':False} if responses else
        {'messages':[{'role':'user','content':'你好'}],'stream_options':{'include_usage':True}})}
    path='responses' if responses else 'chat/completions'
    try:
        with urlopen(Request(f'http://127.0.0.1:{server.server_port}/v1/{path}',data=json.dumps(body).encode(),
                headers={'Content-Type':'application/json'}),timeout=5) as response:
            collected=b''
            while '第一段'.encode() not in collected:
                collected+=response.readline()
            assert released.is_set() and not finish.is_set()
            assert seen[0]['stream'] is True
            finish.set();collected+=response.read()
        run=next(iter(gw.runtime.runs.values()))
        row=run['budget'].records[0]
        assert row['deliveryMode']=='live-text' and row['userFirstTextMs'] >= 0
        if failure:
            assert b'router_stream_failed' in collected
            assert b'response.completed' not in collected and b'[DONE]' not in collected
            assert row['charged'] > 0
        else:
            assert '第一段'.encode() in collected and '第二段'.encode() in collected
            assert (b'response.completed' if responses else b'[DONE]') in collected
            assert row['status']=='billed' and row['releasedTextBytes']==len('第一段第二段'.encode())
        assert len(seen)==1
    finally:
        finish.set();server.shutdown();server.server_close();up.shutdown();up.server_close();gw.close()


def test_reviewed_candidate_is_not_streamed_but_takeover_is(tmp_path):
    from tests.test_model_gateway import Caller, reply, request, gateway
    judge=json.dumps({'verdict':'DEFECT','confidence':.99,'evidenceIds':[],'reason':'缺陷'})
    class StreamingCaller(Caller):
        def stream(self,action,options,on_text):
            assert action['purpose']=='takeover'
            on_text('接管')
            return super().__call__(action,options)
    caller=StreamingCaller(reply('秘密坏回复'),reply(judge),reply('接管'))
    gw=gateway(tmp_path,caller,escalation_configuration());seen=[]
    result=gw.complete(request('escalation'),on_text=lambda meta,text:seen.append(text))
    assert seen==['接管'] and result['choices'][0]['message']['content']=='接管'
    assert [a['purpose'] for a in caller.actions]==['execute','escalation','takeover']
    gw.close()


def test_equivalent_history_keeps_task_and_private_replay(tmp_path):
    from copy import deepcopy
    from tests.test_model_gateway import gateway, Caller, reply, call, request, follow
    gw=gateway(tmp_path,Caller(reply('',calls=[call()]),reply()))
    req=request();first=gw.complete(req);next_request=follow(req,first)
    assistant=next_request['messages'][-2]
    assistant['content']=''
    assistant['tool_calls'][0]['function']['arguments']='{ "path" : "demo" }'
    next_request['messages'][-2]=dict(reversed(list(assistant.items())))
    gw.complete(next_request)
    assert len(gw.runtime.runs)==1
    gw.close()


def test_namespace_conversion_preserves_schema_choice_and_return_identity():
    from refractrouter.gateway_responses import to_chat,from_chat,lower_tools
    from tests.test_model_gateway import call
    tools=[{'type':'namespace','name':'local','description':'宿主工具', 'tools':[
        {'type':'function','name':'read','description':'读取','strict':True,
         'parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}]}]
    request={'model':'refract/static','input':'读取','tools':tools,'tool_choice':{'type':'function','namespace':'local','name':'read'},
        'reasoning':{'summary':'auto'},'include':['reasoning.encrypted_content'], 'prompt_cache_key':'cache-key'}
    chat=to_chat(request);aliases=lower_tools(request)[1];name=chat['tools'][0]['function']['name']
    assert chat['tools'][0]['function']['parameters']==tools[0]['tools'][0]['parameters']
    assert chat['tool_choice']['function']['name']==name and chat['prompt_cache_key']=='cache-key'
    tool=call();tool['function']['name']=name
    result={'model':'refract/static','created':0,'choices':[{'message':{'tool_calls':[tool]},'finish_reason':'tool_calls'}],
        'usage':{'prompt_tokens':1,'completion_tokens':2,'total_tokens':3}}
    output=from_chat(result,aliases)['output'][0]
    assert output['namespace']=='local' and output['name']=='read'
    replay=to_chat({**request,'input':[{'role':'user','content':'读取'},output,{'type':'function_call_output','call_id':tool['id'],'output':'内容'}]})
    assert replay['messages'][-2]['tool_calls'][0]['function']['name']==name
    with pytest.raises(ValueError,match='function'):
        to_chat({**request,'tools':[{'type':'web_search'}]})
    with pytest.raises(ValueError,match='推理等级'):
        to_chat({**request,'reasoning':{'effort':'high'}})


def test_cancel_after_text_settles_dispatched_stream_without_replacement(tmp_path):
    from tests.test_model_gateway import Caller,reply,request,gateway
    from refractrouter.gateway_streaming import WireStream
    cancelled=[False]
    class StreamingCaller(Caller):
        def stream(self,action,options,on_text):
            on_text('第一段');on_text('第二段')
            return super().__call__(action,options)
    gw=gateway(tmp_path,StreamingCaller(reply('第一段第二段')));seen=[]
    def deliver(meta,text):
        seen.append(text);cancelled[0]=True
    with pytest.raises(RuntimeError,match='停止'):
        gw.complete(request(),on_text=deliver,cancelled=lambda:cancelled[0])
    run=next(iter(gw.runtime.runs.values()))
    assert seen==['第一段'] and run['status']=='cancelled'
    assert run['budget'].records[0]['status']=='billed'
    gw.close()


@pytest.mark.parametrize('arguments',['{"path":"wrong","path":"demo"}', '{"path":"different"}', '{"path":"demo","extra":1}'])
def test_history_does_not_normalize_ambiguous_or_changed_arguments(tmp_path,arguments):
    from tests.test_model_gateway import gateway,Caller,reply,call,request,follow
    caller=Caller(reply('',calls=[call()]),reply())
    gw=gateway(tmp_path,caller);req=request();first=gw.complete(req);followup=follow(req,first)
    followup['messages'][-2]['tool_calls'][0]['function']['arguments']=arguments
    with pytest.raises(ValueError,match='历史已改变'):
        gw.complete(followup)
    assert len(caller.actions)==1
    gw.close()
