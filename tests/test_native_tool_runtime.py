"""模拟原生工具与模型；不联网、不查询真实天气、不产生付费调用。"""
from copy import deepcopy
from dataclasses import replace
import io
import json
from threading import Event

import pytest

from refractrouter.openai_compatible import ChatResponse, DshStdioBridge, OpenAICompatibleClient, TransportResponse
from refractrouter.task_budget import TaskCallBudget, InvalidModelOutput
from refractrouter.tool_runtime import StdioToolRuntime, TOOL_PROTOCOL, run_tool_node, ToolTurnConcluded
from refractrouter.task_runtime import run_task
from tests.test_openai_compatible import real_model as base_model, SequenceTransport

def real_model():
    return replace(base_model(), context_window=32768)
from tests.test_text_tasks import MANIFEST, PROFILE, REQUEST, branched_plan

SCHEMAS = [{'name': 'skill', 'description': '加载技能', 'parameters': {'type': 'object'}},
           {'name': 'weather', 'description': '查询天气', 'parameters': {'type': 'object'}}]

def call(name='skill', id='c1', args='{"name":"weather"}'):
    return {'id': id, 'type': 'function', 'function': {'name': name, 'arguments': args}}

def reply(text='', calls=(), finish=None):
    return ChatResponse(text, 100, 30, 0, 0, 1, 1, finish or ('tool_calls' if calls else 'stop'), 'mock', tool_calls=calls)

class Host:
    def __init__(self, result=None):
        self.calls = []
        self.result = result
    def exchange(self, protocol, payload):
        assert protocol == TOOL_PROTOCOL
        self.calls.append(deepcopy(payload))
        return {'ok': True, 'result': self.result or {
            'isError': False, 'content': [{'type': 'text', 'text': '模拟天气：晴'}],
            'additionalContexts': [{'role': 'user', 'content': [{'type': 'text', 'text': '技能说明：使用 weather 工具查询'}]}]}}

class Client:
    max_retries = 0
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
    def complete(self, model, messages, **kw):
        self.requests.append((deepcopy(messages), kw))
        return self.responses.pop(0)


def loop(responses, *, host=None, limit=10, cancel=None):
    client = Client(responses)
    runtime = StdioToolRuntime(SCHEMAS, host or Host())
    budget = TaskCallBudget(client, limit, limit, capture_payload=True)
    reservation = budget.reserve(real_model(), [{'role': 'user', 'content': '模拟天气查询'}],
                                 label='fetch', tools=runtime.schemas, category_limit=limit)
    def invoke(r):
        return budget.invoke(r), None, 0, 1
    def run():
        return run_tool_node(runtime, reservation, budget, invoke, lambda: None, cancel_event=cancel)
    return run, runtime, client, budget


def test_skill_then_weather_then_answer_stays_in_node_and_bills_every_round():
    run, runtime, client, budget = loop([reply(calls=[call()]), reply(calls=[call('weather', 'c2')]), reply('杭州天气（模拟）：晴')])
    assert run().content == '杭州天气（模拟）：晴'
    assert [c['call']['function']['name'] for c in runtime.bridge.calls] == ['skill', 'weather']
    assert len(budget.records) == 3
    assert all(c['status'] == 'billed' for c in budget.records)
    assert sum(c['charged'] for c in budget.records) == pytest.approx(budget.charged['production'])
    assert '技能说明' in json.dumps(client.requests[1][0], ensure_ascii=False)
    assert any(m.get('tool_call_id') == 'c2' for m in client.requests[2][0])
    assert runtime.has_executed('fetch')

@pytest.mark.parametrize('bad', [call('hidden'), call(args='bad json'), call(args='[]')])
def test_invalid_calls_are_billed_but_never_dispatched(bad):
    run, runtime, _, budget = loop([reply(calls=[bad])])
    with pytest.raises(ValueError): run()
    assert runtime.bridge.calls == []
    assert budget.records[0]['status'] == 'billed'


def test_truncated_tool_call_is_never_executed():
    run, runtime, _, budget = loop([reply(calls=[call()], finish='length')])
    with pytest.raises(InvalidModelOutput): run()
    assert runtime.bridge.calls == []
    assert budget.records[0]['status'] == 'billed'


def test_literal_protocol_is_not_executed_or_delivered():
    run, runtime, _, _ = loop([reply('<|FunctionCallBegin|>[{}]<|FunctionCallEnd|>')])
    with pytest.raises(ValueError, match='协议文本'): run()
    assert runtime.bridge.calls == []


def test_duplicate_call_does_not_repeat_effect():
    run, runtime, _, budget = loop([reply(calls=[call()]), reply(calls=[call()])])
    with pytest.raises(ValueError, match='duplicate'): run()
    assert len(runtime.bridge.calls) == 1
    assert len(budget.records) == 2


def test_configured_task_tool_limit_stops_before_second_dispatch():
    host = Host()
    runtime = StdioToolRuntime(SCHEMAS, host, max_calls=1)
    runtime.execute(call(), 'fetch')
    with pytest.raises(ValueError, match='host-tool-call-limit-exhausted'):
        runtime.execute(call(id='c2'), 'fetch')
    assert len(host.calls) == 1
    assert len(runtime.snapshot()) == 1


def test_unlimited_tool_choice_removes_router_total_cap_without_bypassing_host():
    host = Host()
    runtime = StdioToolRuntime(SCHEMAS, host, max_calls='unlimited')
    for index in range(65):
        runtime.execute(call(id=f'c{index}'), 'fetch')
    assert len(host.calls) == 65
    assert len(runtime.snapshot()) == 65


def test_unlimited_tool_choice_allows_more_than_legacy_node_round_cap():
    responses = [reply(calls=[call(id=f'c{index}')]) for index in range(17)] + [reply('完成')]
    run, runtime, client, _ = loop(responses, limit=1000)
    runtime.max_calls = 'unlimited'
    assert run().content == '完成'
    assert len(runtime.bridge.calls) == 17
    assert len(client.requests) == 18


def test_denial_returned_to_same_model_without_fabricated_success():
    host = Host({'isError': True, 'content': [{'type': 'text', 'text': '权限拒绝'}]})
    run, runtime, client, _ = loop([reply(calls=[call()]), reply('工具被拒绝，无法查询。')], host=host)
    assert '拒绝' in run().content
    assert '权限拒绝' in json.dumps(client.requests[1][0], ensure_ascii=False)
    assert runtime.records[0]['status'] == 'failed'


def test_cancel_after_model_settlement_prevents_tool_dispatch():
    cancelled = Event(); cancelled.set()
    run, runtime, _, budget = loop([reply(calls=[call()])], cancel=cancelled)
    from concurrent.futures import CancelledError
    with pytest.raises(CancelledError): run()
    assert not runtime.bridge.calls


def test_concluding_tool_stops_followups():
    host = Host({'isError': False, 'content': [{'type': 'text', 'text': '已完成宿主操作'}], 'concludesTurn': True})
    run, _, client, budget = loop([reply(calls=[call()])], host=host)
    with pytest.raises(ToolTurnConcluded): run()
    assert budget.stopped and len(client.requests) == 1


def test_schema_size_counts_toward_reservation():
    budget = TaskCallBudget(Client([]), 100, 100)
    with pytest.raises(ValueError, match='context bound'):
        budget.reserve(replace(real_model(), context_window=4200), [{'role': 'user', 'content': 'x'}],
                       label='node', tools=[{'name':'tool','description':'x'*3000,'parameters':{}}])


def test_chat_wire_sends_tools_and_accepts_null_content_with_usage():
    body = {'choices': [{'message': {'content': None, 'tool_calls': [call()]}, 'finish_reason': 'tool_calls'}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 30}}
    transport = SequenceTransport([TransportResponse(200, {}, json.dumps(body).encode())])
    client = OpenAICompatibleClient(transport=transport, environment={'TEST_API_KEY': 'mock'}, max_retries=0)
    response = client.complete(real_model(), [{'role': 'user', 'content': 'mock'}], tools=SCHEMAS, json_mode=True)
    assert response.content == '' and response.tool_calls == (call(),)
    sent = transport.calls[0]['payload']
    assert sent['tools'][0]['function'] == SCHEMAS[0]
    assert 'response_format' not in sent


def test_stdio_model_and_tool_requests_share_ids_and_pair_responses():
    wire = io.StringIO('\n'.join(json.dumps({'protocol': protocol, 'type':'response', 'id':str(i), 'ok':True})
                               for i, protocol in enumerate([TOOL_PROTOCOL, 'refractrouter-dsh-llm/v1'], 1))+'\n')
    out = io.StringIO(); bridge = DshStdioBridge(wire, out)
    bridge.exchange(TOOL_PROTOCOL, {'call':call()})
    bridge.complete(real_model(), [], json_mode=False, timeout_seconds=5, tools=SCHEMAS)
    sent = [json.loads(s) for s in out.getvalue().splitlines()]
    assert [r['id'] for r in sent] == ['1','2']
    assert sent[1]['tools'] == SCHEMAS


def test_full_dag_tool_node_unlocks_downstream_and_judge_has_no_tools():
    class DagClient:
        max_retries = 0
        def __init__(self): self.requests = []
        def complete(self, model, messages, **kwargs):
            self.requests.append((model, deepcopy(messages), kwargs))
            if model.role == 'judge':
                criteria = json.loads(messages[-1]['content'])['criteria']
                return reply(json.dumps({'score':92,'passed':True,'rationale':'模拟通过',
                    'criteria':[{'criterion':c,'passed':True,'rationale':'模拟证据'} for c in criteria]}))
            payload = json.loads(messages[1]['content'])
            if payload['node_id'] == 'cost' and len(messages) == 2: return reply(calls=[call()])
            return reply('模拟节点结果')
    client = DagClient(); runtime = StdioToolRuntime(SCHEMAS, Host())
    result = run_task({**REQUEST, 'plan':branched_plan()}, MANIFEST, {**PROFILE,'kind':'empirical'},
        client=client, production_limit=100, evaluation_limit=100, tool_runtime=runtime)
    assert result['status'] == 'completed', result['issues']
    assert [n['node_id'] for n in result['nodes']] == ['cost','risk','answer']
    assert len(result['tool_calls']) == 1
    assert all(c['status']=='billed' for c in result['calls'])
    assert not client.requests[-1][2].get('tools')
    answer = next(messages for model,messages,kw in client.requests if model.role!='judge' and json.loads(messages[1]['content'])['node_id']=='answer')
    assert json.loads(answer[1]['content'])['upstream'] == {'cost':'模拟节点结果','risk':'模拟节点结果'}


def test_responses_native_tool_loop_replays_reasoning_and_function_items():
    from refractrouter.application_config import compile_configuration
    from tests.test_responses_api import configuration, envelope
    model = compile_configuration(configuration()).manifest.candidates[0]
    first = envelope()
    first['output'] = [{'type':'reasoning','id':'r1','summary':[], 'encrypted_content':'mock-encrypted'},
                       {'type':'function_call','id':'fc1','call_id':'c1','name':'skill','arguments':'{"name":"weather"}'}]
    final = envelope('模拟查询结果')
    class Transport:
        def __init__(self): self.requests=[];self.responses=[first,final]
        def post(self,url,headers,body,timeout_seconds):
            self.requests.append(json.loads(body))
            return TransportResponse(200,{},json.dumps(self.responses.pop(0)).encode())
    transport=Transport()
    client=OpenAICompatibleClient(transport=transport,environment={'OPENAI_API_KEY':'mock'},max_retries=0)
    runtime=StdioToolRuntime(SCHEMAS,Host());budget=TaskCallBudget(client,100,100)
    reserved=budget.reserve(model,[{'role':'user','content':'模拟查询'}],label='fetch',tools=SCHEMAS)
    response=run_tool_node(runtime,reserved,budget,lambda r:(budget.invoke(r),None,0,1),lambda:None)
    assert response.content=='模拟查询结果'
    assert transport.requests[0]['tools'][0]['type']=='function'
    second=transport.requests[1]['input']
    assert any(i.get('encrypted_content')=='mock-encrypted' for i in second)
    assert any(i.get('type')=='function_call_output' and i['call_id']=='c1' for i in second)
    assert not any('_response_items' in i for i in second)


def test_tool_round_limit_and_budget_prevent_unbounded_model_calls(monkeypatch):
    import refractrouter.tool_runtime as module
    monkeypatch.setattr(module,'MAX_TOOL_ROUNDS',1)
    run,runtime,client,budget=loop([reply(calls=[call()]),reply(calls=[call('weather','c2')])])
    with pytest.raises(ValueError,match='round-limit'): run()
    assert len(client.requests)==2 and len(runtime.bridge.calls)==1
    assert all(r['status']=='billed' for r in budget.records)
    run,runtime,client,budget=loop([reply(calls=[call()]),reply('unused')])
    budget.limits['production']=budget.records[0]['reserved']
    # 工具返回大量新证据，下一轮必须重新预留；不能把整个循环只结算最后一轮。
    runtime.bridge.result={'isError':False,'content':[{'type':'text','text':'x'*10000}]}
    with pytest.raises(ValueError,match='budget-exhausted'):run()
    assert len(client.requests)==1 and len(runtime.bridge.calls)==1


def test_missing_tool_call_usage_never_executes_host():
    run,runtime,_,budget=loop([replace(reply(calls=[call()]),usage_available=False)])
    with pytest.raises(ValueError,match='unconfirmed model usage'):run()
    assert budget.records[0]['status']=='unknown-usage' and not runtime.bridge.calls


def test_pending_host_tool_does_not_block_checkpoint_and_pre_dispatch_is_persisted():
    from concurrent.futures import ThreadPoolExecutor
    entered=Event();release=Event()
    class BlockingHost(Host):
        def exchange(self,protocol,payload):
            entered.set()
            assert release.wait(2)
            return super().exchange(protocol,payload)
    runtime=StdioToolRuntime(SCHEMAS,BlockingHost());snapshots=[]
    with ThreadPoolExecutor() as pool:
        future=pool.submit(runtime.execute,call(),'fetch',None,lambda:snapshots.append(runtime.snapshot()))
        assert entered.wait(1)
        try:
            snapshot=pool.submit(runtime.snapshot).result(timeout=1)
            assert snapshot[0]['status']=='dispatched'
            assert snapshots[0][0]['status']=='dispatched'
        finally:
            release.set()
        assert future.result()['isError'] is False


def test_node_with_tool_effect_is_not_split_or_replayed_after_bad_final_output(monkeypatch):
    from tests.test_task_decomposition import example
    import refractrouter.task_runtime as module
    class Dynamic:
        def eligible(self,*args,**kwargs):
            raise AssertionError('不得重跑已经产生工具副作用的节点')
    monkeypatch.setattr(module,'DynamicDecomposition',lambda **kwargs:Dynamic())
    runtime=StdioToolRuntime(SCHEMAS,Host())
    client=Client([reply(calls=[call()]),reply('不是契约所要求的 JSON')])
    result=run_task({**REQUEST,'plan':example(),'maxDynamicSplits':1},MANIFEST,{**PROFILE,'kind':'empirical'},
        client=client,production_limit=100,evaluation_limit=100,tool_runtime=runtime)
    assert result['status']=='failed'
    assert len(client.requests)==2 and len(runtime.bridge.calls)==1
    assert len(result['nodes'])==1
    assert result['execution']['not_started']==['risk','answer']


def test_execution_capacity_survives_tool_round_and_preserves_thinking_and_budget():
    from refractrouter.application_config import execution_capacity_model
    from refractrouter.responses_api import output_token_limit
    original = replace(real_model(), base_url='https://ark.cn-beijing.volces.com/api/plan/v3',
                       api_model='deepseek-v4-flash', context_window=1024000,
                       request_options={'thinking': {'type': 'enabled'}}, max_output_tokens=8192)
    model = execution_capacity_model(original)
    assert output_token_limit(original) == 8192
    assert output_token_limit(model) == 384000
    client = Client([reply(calls=[call()]), reply('有依据的模拟天气')])
    runtime = StdioToolRuntime(SCHEMAS, Host())
    budget = TaskCallBudget(client, 10000, 10000)
    initial = budget.reserve(model, [{'role':'user','content':'天气'}],label='weather',tools=SCHEMAS)
    seen = []
    def invoke(reservation):
        seen.append(reservation.model)
        return budget.invoke(reservation), None, 0, 1
    assert run_tool_node(runtime, initial, budget, invoke, lambda:None).content
    assert [output_token_limit(m) for m in seen] == [384000,384000]
    assert all(m.request_options == original.request_options for m in seen)
    with pytest.raises(ValueError, match='budget'):
        TaskCallBudget(client, 0.00001, 1).reserve(model,initial.messages,label='too-small',tools=SCHEMAS)


def test_execution_capacity_leaves_room_for_actual_input_and_schema():
    from refractrouter.application_config import execution_capacity_model
    from refractrouter.task_budget import request_input_bound
    model = execution_capacity_model(replace(real_model(),max_output_tokens=32000,context_window=32000))
    messages = [{'role':'user','content':'测试输入'}]
    reservation = TaskCallBudget(Client([]),10000,10000).reserve(model,messages,label='node',tools=SCHEMAS)
    assert reservation.model.max_output_tokens == 32000-request_input_bound(messages,SCHEMAS)


def test_execution_capacity_reaches_chat_wire_without_legacy_clamp():
    from refractrouter.application_config import execution_capacity_model
    model = execution_capacity_model(replace(real_model(),max_output_tokens=32000,context_window=128000))
    body = {'choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],
            'usage':{'prompt_tokens':100,'completion_tokens':9000,'completion_tokens_details':{'reasoning_tokens':8999}}}
    transport=SequenceTransport([TransportResponse(200,{},json.dumps(body).encode())])
    client=OpenAICompatibleClient(transport=transport,environment={'TEST_API_KEY':'mock'},max_retries=0)
    response=TaskCallBudget(client,10000,10000).complete(model,[{'role':'user','content':'模拟'}],label='node')
    assert response.content=='ok'
    assert transport.calls[0]['payload'][model.token_limit_parameter]==32000
