"""Responses 协议、推理用量和任务结算；只使用离线响应。"""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from refractrouter.agent import run_agent
from refractrouter.agent_cli import example_configuration, main
from refractrouter.application_config import compile_configuration
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse, model_response_cost
from refractrouter.task_budget import TaskCallBudget, InvalidModelOutput


def configuration():
    config=example_configuration('openai-responses')
    for m in config['models']:
        m['model']='reasoning-answer' if m['role']=='candidate' else 'reasoning-judge'
    return config


def envelope(content='{"answer":"done"}', status='completed'):
    return {'id':'resp_fixture','status':status,'error':None,'incomplete_details':None,
        'output':[{'type':'reasoning','summary':[{'type':'summary_text','text':'not the answer'}]},
                  {'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':content}]}],
        'usage':{'input_tokens':100,'input_tokens_details':{'cached_tokens':40},
                 'output_tokens':9000,'output_tokens_details':{'reasoning_tokens':8000}}}


class Transport:
    def __init__(self, response=None):
        self.response=response
        self.calls=[]
    def post(self,url,headers,body,timeout_seconds):
        request=json.loads(body)
        self.calls.append((url,headers,request,timeout_seconds))
        if self.response is not None:
            reply=deepcopy(self.response)
        else:
            payload=json.loads(request['input'][-1]['content'])
            if request['model']=='reasoning-judge':
                content={'score':92,'passed':True,'rationale':'覆盖要求',
                    'criteria':[{'criterion':c,'passed':True,'rationale':'已覆盖'} for c in payload['criteria']]}
            else:
                content={key:'fixture answer' for key in payload['contract']['output']['fields']}
            reply=envelope(json.dumps(content))
        return TransportResponse(200,{'X-Request-ID':'http-fixture'},json.dumps(reply).encode())


def client(transport):
    return OpenAICompatibleClient(transport=transport,environment={'OPENAI_API_KEY':'test-responses-key'},max_retries=0)


def test_responses_wire_uses_native_fields_and_preserves_total_reasoning_usage():
    config=configuration();config['models'][0]['pricing']['cachedInputPer1k']=.0005
    config['models'][0]['requestOptions']['text']={'verbosity':'low'}
    model=compile_configuration(config).manifest.candidates[0]
    transport=Transport(envelope())
    response=client(transport).complete(model,[{'role':'system','content':'JSON only'},{'role':'user','content':'test'}],json_mode=True)
    url,headers,body,_=transport.calls[0]
    assert url=='https://api.openai.com/v1/responses'
    assert headers['Authorization']=='Bearer test-responses-key'
    assert body['reasoning']=={'effort':'medium'}
    assert body['text']=={'verbosity':'low','format':{'type':'json_object'}}
    assert body['max_output_tokens']==32768 and body['store'] is False
    assert not {'messages','temperature','top_p','max_completion_tokens','max_tokens','stream'} & body.keys()
    assert response.content=='{"answer":"done"}'
    assert response.request_id=='http-fixture' and response.finish_reason=='stop'
    assert response.usage_available and response.cached_input_tokens==40 and response.reasoning_tokens==8000
    assert response.output_tokens==9000
    assert model_response_cost(model,response)==.01808  # 推理包含在 9000 output 中，只计费一次。


def test_response_messages_are_concatenated_without_reasoning_or_tool_results():
    raw=envelope('first')
    raw['output'].append({'type':'message','role':'assistant','content':[{'type':'output_text','text':'second'}]})
    config=configuration();config['models'][0]['jsonMode']='prompt-only'
    model=compile_configuration(config).manifest.candidates[0]
    transport=Transport(raw)
    response=client(transport).complete(model,[{'role':'user','content':'test'}],json_mode=True)
    assert response.content=='firstsecond' and 'text' not in transport.calls[0][2]


def test_live_core_can_run_production_and_judge_with_reasoning_above_8192(tmp_path):
    transport=Transport()
    result=run_agent({'task':'简短比较两种方案','temperature':0},provider_config=configuration(),
        mode='live',execute_paid_run=True,runs_dir=tmp_path,client=client(transport),max_output_tokens=32768)
    assert result['status']=='completed',result['issues']
    assert len(transport.calls)==2 and all(c[0].endswith('/responses') for c in transport.calls)
    assert all('temperature' not in c[2] for c in transport.calls)
    assert result['usage']['output_tokens']==18000 and result['usage']['reasoning_tokens']==16000
    calls=json.loads(Path(result['result_path']).read_text())['calls']
    assert all(c['status']=='billed' and c['reserved']>.065 for c in calls)
    assert result['costs']['unconfirmed']==0
    assert not any('test-responses-key' in p.read_text() for p in Path(result['run_dir']).glob('*.json'))


@pytest.mark.parametrize(('status','reason','refusal','finish'),[
    ('incomplete','max_output_tokens',False,'length'),
    ('incomplete','content_filter',False,'content_filter'),
    ('completed',None,True,'content_filter'),
    ('failed',None,False,'failed'),
    ('cancelled',None,False,'cancelled'),
])
def test_non_successful_responses_are_billed_and_never_accepted(status,reason,refusal,finish):
    raw=envelope('',status)
    raw['incomplete_details']={'reason':reason} if reason else None
    if refusal:raw['output'][-1]['content']=[{'type':'refusal','refusal':'cannot answer'}]
    else:raw['output']=raw['output'][:1]  # 只有推理、没有正文的响应。
    model=compile_configuration(configuration()).manifest.candidates[0]
    transport=Transport(raw);budget=TaskCallBudget(client(transport),1,1)
    with pytest.raises(InvalidModelOutput):
        budget.complete(model,[{'role':'user','content':'test'}],label='answer',json_mode=True)
    assert budget.records[0]['status']=='billed' and budget.records[0]['finish_reason']==finish
    assert budget.records[0]['reasoning_tokens']==8000 and budget.charged['production']>0
    assert len(transport.calls)==1


@pytest.mark.parametrize('mutate',[
    lambda raw:raw.pop('usage'),
    lambda raw:raw['usage'].update(output_tokens=True),
    lambda raw:raw['usage'].update(input_tokens_details='invalid'),
    lambda raw:raw['usage']['input_tokens_details'].update(cached_tokens=101),
    lambda raw:raw['usage']['output_tokens_details'].update(reasoning_tokens=9001),
    lambda raw:raw['usage']['output_tokens_details'].update(reasoning_tokens=-1),
])
def test_unknown_or_inconsistent_usage_retains_the_reservation(mutate):
    raw=envelope();mutate(raw)
    model=compile_configuration(configuration()).manifest.candidates[0]
    transport=Transport(raw);budget=TaskCallBudget(client(transport),1,1)
    with pytest.raises(ValueError,match='usage'):
        budget.complete(model,[{'role':'user','content':'test'}],label='answer')
    assert budget.records[0]['status']=='unknown-usage'
    assert budget.records[0]['charged']==budget.records[0]['reserved']
    assert len(transport.calls)==1


def test_function_call_is_not_accepted_as_a_completed_text_node():
    raw=envelope();raw['output'].append({'type':'function_call','name':'fake-tool','arguments':'{}'})
    model=compile_configuration(configuration()).manifest.candidates[0]
    budget=TaskCallBudget(client(Transport(raw)),1,1)
    with pytest.raises(InvalidModelOutput):budget.complete(model,[{'role':'user','content':'test'}],label='answer')
    assert budget.records[0]['finish_reason']=='unsupported-output' and budget.records[0]['status']=='billed'


@pytest.mark.parametrize('options',[{'messages':[]},{'max_output_tokens':1},{'reasoning_effort':'high'},
    {'thinking':{'type':'enabled'}},{'reasoning':{'unknown':'x'}},{'text':{'format':{'type':'text'}}}])
def test_protocol_mismatches_and_envelope_overrides_fail_before_calls(options):
    config=configuration();config['models'][0]['requestOptions']=options
    with pytest.raises(ValueError):compile_configuration(config)


def test_chat_model_output_caps_and_native_reasoning_fields_stay_separate():
    config=example_configuration('openai-compatible');config['models'][0]['maxOutputTokens']=32768
    with pytest.raises(ValueError):compile_configuration(config)
    config=example_configuration('openai-compatible');config['models'][0]['requestOptions']={'reasoning':{'effort':'high'}}
    with pytest.raises(ValueError):compile_configuration(config)
    config=configuration();config['providers'][0]['maxTokensParameter']='max_tokens'
    with pytest.raises(ValueError):compile_configuration(config)


def test_responses_cli_template_and_dsh_output_envelope(tmp_path):
    source=tmp_path/'providers.json';target=tmp_path/'dsh.json'
    assert main(['config-example','--provider-type','openai-responses','--output',str(source)])==0
    assert main(['dsh-config','--provider-config',str(source),'--output',str(target),'--mode','live','--max-output-tokens','32768'])==0
    config=json.loads(target.read_text())[0]['config']
    assert config['maxOutputTokens']==32768
    assert config['providerConfig']['providers'][0]['credentialEnv']=='OPENAI_API_KEY'


def test_reasoning_envelope_is_reserved_before_any_model_call(tmp_path):
    config=configuration()
    for m in config['models']:m['contextWindow']=32769
    transport=Transport()
    result=run_agent({'task':'比较两种方案'},provider_config=config,mode='live',execute_paid_run=True,
        runs_dir=tmp_path,client=client(transport),max_output_tokens=32768)
    assert result['status']=='no-feasible-route' and not transport.calls
