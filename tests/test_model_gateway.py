"""独立 API 的无网络模型验收：真实核心/账本，客户端自行执行工具。"""
from copy import deepcopy
from dataclasses import replace
import json
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from refractrouter.model_gateway import ModelGateway, HttpModelCaller, chat_messages, wire_messages, create_server, bound_tool_evidence, ordinary_evidence
from refractrouter.host_evidence import EVIDENCE_VERSION
from refractrouter.openai_compatible import ChatResponse, TransportResponse
from refractrouter.host_evidence import validate_evidence
from refractrouter.planning_policy import stage_decision
from refractrouter.planning_runtime import PlanningRuntime
from tests.test_planning_routing import (advisor_gate_configuration, configuration,
                                         composite_configuration, escalation_configuration,
                                         task_pool_configuration)


def reply(text='完成', calls=(), usage=True):
    return ChatResponse(text, 20, 10, 0, 0, 5, 1, 'tool_calls' if calls else 'stop',
                        'fixture', usage_available=usage, tool_calls=tuple(calls))


def call(cid='call-1'):
    return {'id': cid, 'type': 'function', 'function': {'name': 'read', 'arguments': '{"path":"demo"}'}}


TOOLS = [{'type': 'function', 'function': {'name': 'read', 'description': '读取',
         'parameters': {'type': 'object'}, 'strict': True}}]


class Caller:
    def __init__(self, *replies):
        self.replies, self.actions = list(replies), []
    def __call__(self, action, options):
        self.actions.append(deepcopy(action))
        response = self.replies.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def gateway(tmp_path, caller, config=None):
    return ModelGateway({'planningRouting': config or configuration('static')}, tmp_path, caller)


def request(strategy='static', messages=None):
    return {'model': 'refract/' + strategy, 'messages': messages or [{'role': 'user', 'content': '读 demo 后回答'}], 'tools': TOOLS}


def follow(req, result):
    return {**req, 'messages': req['messages'] + [result['choices'][0]['message'],
        {'role': 'tool', 'tool_call_id': result['choices'][0]['message']['tool_calls'][0]['id'], 'content': '文件内容'}]}


@pytest.mark.parametrize('strategy', ['static', 'stage'])
def test_plain_api_tool_continuation_never_executes_tools(tmp_path, monkeypatch, strategy):
    import refractrouter.tool_runtime as tools
    monkeypatch.setattr(tools, 'run_tool_node', lambda *a, **k: pytest.fail('路由器不执行工具'))
    caller = Caller(reply(calls=[call()]), reply('实际来自宿主的文件内容'))
    gw = gateway(tmp_path, caller)
    req = request(strategy)
    first = gw.complete(req)
    assert first['choices'][0]['message']['tool_calls'] == [call()]
    second = gw.complete(follow(req, first))
    assert second['choices'][0]['message']['content'] == '实际来自宿主的文件内容'
    assert len(gw.runtime.runs) == 1
    assert [a['model']['id'] for a in caller.actions] == ['small', 'small']
    assert wire_messages(caller.actions[1]['messages'])[-1]['role'] == 'tool'
    gw.close()


def test_task_single_candidate_and_followup_do_not_call_judge(tmp_path):
    cfg = task_pool_configuration()
    cfg['task']['pool'] = ['small']
    cfg['task']['fallback'] = 'small'
    caller = Caller(reply(calls=[call()]), reply())
    gw = gateway(tmp_path, caller, cfg)
    req = request('task');first = gw.complete(req);gw.complete(follow(req, first))
    assert [a['purpose'] for a in caller.actions] == ['execute', 'execute']
    gw.close()


def test_composite_standard_api_classifies_once_and_keeps_tool_continuation(tmp_path):
    decision = json.dumps({"answers": {"candidates": {
        "small": {"score": .95, "missingInformation": 0},
        "large": {"score": .2, "missingInformation": 0}}}})
    caller = Caller(reply(decision), reply(calls=[call()]), reply("完成"))
    gw = gateway(tmp_path, caller, composite_configuration())
    req = request("composite")
    first = gw.complete(req)
    final = gw.complete(follow(req, first))
    assert final["choices"][0]["message"]["content"] == "完成"
    assert [action["purpose"] for action in caller.actions] == ["task", "execute", "execute"]
    assert [action["model"]["id"] for action in caller.actions] == ["judge", "small", "small"]
    assert "refract/composite" in [row["id"] for row in gw.models()["data"]]
    gw.close()


def test_composite_trusted_failures_switch_hold_and_return_over_standard_api(tmp_path):
    decision = json.dumps({"answers": {"candidates": {
        "small": {"score": .95, "missingInformation": 0},
        "large": {"score": .2, "missingInformation": 0}}}})
    caller = Caller(reply(decision), reply(calls=[call("c1")]), reply(calls=[call("c2")]),
                    reply(calls=[call("c3")]), reply(calls=[call("c4")]), reply("完成"))
    gw = gateway(tmp_path, caller, composite_configuration())
    req = request("composite")
    result = gw.complete(req)
    statuses = [("c1", "failed", "same"), ("c2", "failed", "same"),
                ("c3", "completed", "ok-3"), ("c4", "completed", "ok-4")]
    for call_id, status, fingerprint in statuses:
        req = follow(req, result)
        req["metadata"] = {"refract_tool_evidence": {"version": EVIDENCE_VERSION, "events": [{
            "id": call_id, "callId": call_id, "tool": "read", "kind": "unknown",
            "status": status, "fingerprint": fingerprint}]}}
        result = gw.complete(req)
    assert result["choices"][0]["message"]["content"] == "完成"
    assert [action["model"]["id"] for action in caller.actions] == [
        "judge", "small", "small", "large", "large", "small"]
    run = next(iter(gw.runtime.runs.values()))
    reasons = [row["reason"] for row in run["decisions"]]
    assert "composite-repeated-failure" in reasons
    assert "composite-takeover-hold" in reasons
    assert reasons[-1] == "composite-return-base"
    gw.close()


def test_escalation_discards_tool_and_takeover_stays_fixed(tmp_path):
    verdict = json.dumps({'verdict': 'DEFECT', 'confidence': .95, 'evidenceIds': [], 'reason': '不满足任务'})
    caller = Caller(reply('坏候选', [call('discarded')]), reply(verdict),
                    reply('接管', [call('accepted')]), reply('完成'))
    gw = gateway(tmp_path, caller, escalation_configuration())
    req = request('escalation');first = gw.complete(req);gw.complete(follow(req, first))
    assert first['choices'][0]['message']['tool_calls'][0]['id'] == 'accepted'
    assert [a['purpose'] for a in caller.actions] == ['execute', 'escalation', 'takeover', 'execute']
    assert [a['model']['id'] for a in caller.actions] == ['small', 'judge', 'large', 'large']
    assert '坏候选' not in json.dumps(caller.actions[-1]['messages'], ensure_ascii=False)
    assert not any('discarded' in key for key in gw.state['tools'])
    run = next(iter(gw.runtime.runs.values()))
    assert run['budget'].records[0]['disposition'] == 'discarded'
    assert len(run['budget'].records) == 4
    gw.close()


def test_advisor_gateway_releases_only_reviewed_final_candidate(tmp_path):
    caller = Caller(reply('可交付答复'), reply(json.dumps({'verdict': 'APPROVE'})))
    gw = gateway(tmp_path, caller, advisor_gate_configuration())
    result = gw.complete(request('advisor'))
    assert result['choices'][0]['message']['content'] == '可交付答复'
    assert [action['purpose'] for action in caller.actions] == ['execute', 'advisor']
    assert gw.models()['data'][-1]['id'] == 'refract/advisor'
    gw.close()


def test_advisor_gateway_redo_tool_continuation_requires_second_review(tmp_path):
    caller = Caller(
        reply('含错误的候选'),
        reply(json.dumps({'verdict': 'REDO', 'feedback': '先读取文件并按证据修正'})),
        reply(calls=[call('redo-tool')]),
        reply('根据文件修正后的答复'),
        reply(json.dumps({'verdict': 'APPROVE'})),
    )
    gw = gateway(tmp_path, caller, advisor_gate_configuration())
    req = request('advisor')
    first = gw.complete(req)
    assert first['choices'][0]['message']['tool_calls'][0]['id'] == 'redo-tool'
    final = gw.complete(follow(req, first))
    assert final['choices'][0]['message']['content'] == '根据文件修正后的答复'
    assert [action['purpose'] for action in caller.actions] == [
        'execute', 'advisor', 'redo', 'execute', 'advisor']
    assert '含错误的候选' not in json.dumps(caller.actions[3]['messages'], ensure_ascii=False)
    assert '先读取文件并按证据修正' in json.dumps(caller.actions[3]['messages'], ensure_ascii=False)
    run = next(iter(gw.runtime.runs.values()))
    assert run['state']['advisorPhase'] == 'approved'
    assert run['budget'].records[0]['disposition'] == 'discarded'
    gw.close()


def test_unknown_usage_retains_reservation_no_judge(tmp_path):
    caller = Caller(reply(usage=False))
    gw = gateway(tmp_path, caller, escalation_configuration())
    with pytest.raises(Exception, match='usage'):
        gw.complete(request('escalation'))
    run = next(iter(gw.runtime.runs.values()))
    assert len(caller.actions) == 1
    assert run['budget'].records[0]['status'] == 'unknown-usage'
    assert run['budget'].records[0]['charged'] > 0
    gw.close()


def test_restart_never_reissues_accepted_tool_continuation(tmp_path):
    first_gw = gateway(tmp_path, Caller(reply(calls=[call()])))
    req = request();first = first_gw.complete(req);first_gw.close()
    caller = Caller(reply());second_gw = gateway(tmp_path, caller)
    with pytest.raises(ValueError, match='不得自动重新派发'):
        second_gw.complete(follow(req, first))
    assert not caller.actions
    second_gw.close()


def test_identical_prompts_isolated_and_explicit_guidance_stays_in_task(tmp_path):
    caller = Caller(reply(), reply(), reply(), reply())
    gw = gateway(tmp_path, caller)
    gw.complete(request());gw.complete(request())
    assert len(gw.runtime.runs) == 2
    req = {**request(), 'metadata': {'refract_session': 'a', 'refract_task': '1'}}
    gw.complete(req);gw.complete({**req, 'messages': [{'role': 'user', 'content': '补充说明'}]})
    assert len(gw.runtime.runs) == 3
    assert len(list(gw.runtime.runs.values())[-1]['budget'].records) == 2
    gw.close()


def test_changed_tool_history_cannot_reuse_budget(tmp_path):
    caller = Caller(reply(calls=[call()]))
    gw = gateway(tmp_path, caller);req = request();first = gw.complete(req)
    next_req = follow(req, first);next_req['messages'][0] = {'role': 'user', 'content': '另一个任务'}
    with pytest.raises(ValueError, match='历史已改变'):
        gw.complete(next_req)
    assert len(caller.actions) == 1
    gw.close()


def test_http_auth_sse_and_tools(tmp_path):
    gw = gateway(tmp_path, Caller(reply(calls=[call()])))
    server = create_server(gw, port=0, token='fixture-only')
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    root = f'http://127.0.0.1:{server.server_port}'
    try:
        with pytest.raises(HTTPError) as exc:
            urlopen(root + '/v1/models')
        assert exc.value.code == 401
        body = {**request(), 'stream': True, 'stream_options': {'include_usage': True}}
        res = urlopen(Request(root + '/v1/chat/completions', data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer fixture-only', 'Content-Type': 'application/json'}))
        data = res.read().decode()
        assert data.endswith('data: [DONE]\n\n')
        assert '"tool_calls"' in data and '"index": 0' in data and '"total_tokens": 30' in data
    finally:
        server.shutdown();server.server_close();gw.close()


def test_transport_preserves_client_tools_system_and_parameters(tmp_path):
    class Transport:
        def post(self, url, headers, body, timeout):
            self.sent = json.loads(body)
            return TransportResponse(200, {}, json.dumps({'choices': [{'message': {'content': '完成'},
                'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 2, 'completion_tokens': 3}}).encode())
    transport = Transport()
    caller = HttpModelCaller({'fake': {'baseURL': 'http://localhost/v1'}}, transport)
    gw = gateway(tmp_path, caller)
    req = request(messages=[{'role': 'developer', 'content': '客户端规则'}, {'role': 'user', 'content': '问题'}])
    req['tool_choice'] = 'auto'
    req['temperature'] = .3
    gw.complete(req)
    assert transport.sent['messages'] == req['messages']
    assert transport.sent['tools'] == TOOLS
    assert transport.sent['tool_choice'] == 'auto'
    assert transport.sent['temperature'] == .3
    gw.close()


def test_native_evidence_deduplicated_and_conflicting_result_rejected():
    e = {'id': '1', 'callId': '1', 'tool': 'bash', 'kind': 'unknown', 'status': 'failed', 'fingerprint': 'x'}
    assert len(validate_evidence([e,e])) == 1
    with pytest.raises(ValueError, match='矛盾'):
        validate_evidence([e, {**e, 'status': 'completed'}])
    decision = stage_decision([e,e], {}, {'window': 3, 'threshold': .5, 'holdTurns': 2}, 'efficient')
    assert decision['role'] == 'efficient'


def test_stage_old_failures_cannot_escalate_new_research():
    events = [{'id': str(i), 'callId': str(i), 'tool': 'x', 'kind': 'unknown', 'status': 'failed', 'fingerprint': str(i)} for i in range(2)]
    events.append({'id': '2', 'callId': '2', 'tool': 'read', 'kind': 'observe', 'status': 'completed', 'fingerprint': '2'})
    decision = stage_decision(events, {'consumedEvidenceIds': ['0','1']}, {'window': 3, 'threshold': .1, 'holdTurns': 2}, 'efficient')
    assert decision['role'] == 'efficient'


def test_stage_gateway_accepts_only_paired_host_facts_and_recovers(tmp_path):
    ids = ['a', 'b', 'c', 'd']
    caller = Caller(*(reply(calls=[call(cid)]) for cid in ids), reply())
    gw = gateway(tmp_path, caller, configuration('stage'))
    req = request('stage')
    evidence = []
    for index, cid in enumerate(ids):
        result = gw.complete(req)
        req = follow(req, result)
        event = ordinary_evidence(chat_messages(req['messages']))[-1]
        evidence.append({**event, 'status': 'failed' if index < 2 else 'completed'})
        req['metadata'] = {'refract_tool_evidence': {'version': EVIDENCE_VERSION,
            'events': list(evidence)}}
    gw.complete(req)
    assert [action['model']['id'] for action in caller.actions] == [
        'small', 'small', 'large', 'large', 'small']
    run = next(iter(gw.runtime.runs.values()))
    assert [row['reason'] for row in run['decisions'] if row.get('ruleVersion') == 'stage-v4'][2:5] == [
        'repeated-failure', 'capable-hold', 'ambiguous']
    gw.close()


def test_host_facts_cannot_claim_other_calls_or_change_after_commit(tmp_path):
    caller = Caller(reply(calls=[call('a')]), reply(calls=[call('b')]))
    gw = gateway(tmp_path, caller, configuration('stage'))
    req = request('stage'); req = follow(req, gw.complete(req))
    event = ordinary_evidence(chat_messages(req['messages']))[0]
    fact = {**event, 'status': 'failed'}
    package = {'version': EVIDENCE_VERSION, 'events': [fact]}
    for invalid in ({**fact, 'callId': 'different'}, {**fact, 'tool': 'other'},
                    {**fact, 'id': 'other'}, {**fact, 'extra': 'unknown'}):
        with pytest.raises(ValueError):
            gw.complete({**req, 'metadata': {'refract_tool_evidence':
                {**package, 'events': [invalid]}}})
    assert len(caller.actions) == 1
    req['metadata'] = {'refract_tool_evidence': package}
    req = follow(req, gw.complete(req))
    changed = {**fact, 'status': 'completed'}
    with pytest.raises(ValueError, match='矛盾'):
        gw.complete({**req, 'metadata': {'refract_tool_evidence':
            {**package, 'events': [changed]}}})
    assert len(caller.actions) == 2
    gw.close()


def test_stage_evidence_write_failure_never_dispatches_or_leaves_memory_fact(tmp_path, monkeypatch):
    caller = Caller(reply(calls=[call('a')]))
    gw = gateway(tmp_path, caller, configuration('stage'))
    req = follow(request('stage'), gw.complete(request('stage')))
    event = ordinary_evidence(chat_messages(req['messages']))[0]
    req['metadata'] = {'refract_tool_evidence': {'version': EVIDENCE_VERSION,
        'events': [{**event, 'status': 'failed'}]}}
    monkeypatch.setattr(gw, 'save', lambda: (_ for _ in ()).throw(OSError('写入失败')))
    with pytest.raises(OSError, match='写入失败'):
        gw.complete(req)
    assert len(caller.actions) == 1
    assert not any(gw.state.get('toolEvidence', {}).values())
    gw.close()


def test_static_random_only_selected_candidate_consumes_budget(tmp_path):
    cfg = configuration('static')
    cfg['parameters'] = {'staticMode': 'random', 'efficientWeight': 1, 'capableWeight': 0}
    cfg['models'][1]['outputPer1k'] = 100000
    cfg['maxCalls'] = 1
    caller = Caller(reply());gw = gateway(tmp_path, caller,cfg)
    gw.complete(request())
    assert caller.actions[0]['model']['id'] == 'small'
    assert len(next(iter(gw.runtime.runs.values()))['budget'].records) == 1
    gw.close()


def test_invalid_request_rejected_before_spend(tmp_path):
    caller = Caller(reply());gw = gateway(tmp_path, caller)
    with pytest.raises(ValueError, match='冻结'):
        gw.complete({**request(), 'reasoning_effort': 'rr:stage'})
    with pytest.raises(ValueError, match='媒体'):
        gw.complete(request(messages=[{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://example.test/x'}}]}]))
    assert not caller.actions
    gw.close()


def test_responses_roundtrip_native_function_and_sse(tmp_path):
    from refractrouter.gateway_responses import to_chat, from_chat, stream_events
    caller = Caller(reply('开始读取', [call()]), reply('完成'))
    gw = gateway(tmp_path, caller)
    req = {'model': 'refract/static', 'input': [{'role': 'user', 'content': '读取'}], 'store': False,
           'tools': [{'type': 'function', **TOOLS[0]['function']}]}
    first = from_chat(gw.complete(to_chat(req)))
    events = list(stream_events(first))
    assert [e['sequence_number'] for e in events] == list(range(len(events)))
    assert events[-1]['type'] == 'response.completed'
    next_req = {**req, 'input': req['input'] + first['output'] +
                [{'type': 'function_call_output', 'call_id': 'call-1', 'output': '读取结果'}]}
    assert from_chat(gw.complete(to_chat(next_req)))['output'][0]['content'][0]['text'] == '完成'
    assert len(gw.runtime.runs) == 1
    gw.close()


def test_responses_http_serves_protocol_events(tmp_path):
    gw = gateway(tmp_path, Caller(reply()))
    server = create_server(gw, port=0);Thread(target=server.serve_forever, daemon=True).start()
    try:
        request = Request(f'http://127.0.0.1:{server.server_port}/v1/responses',
            data=json.dumps({'model': 'refract/static', 'input': '你好', 'stream': True, 'store': False}).encode(),
            headers={'Content-Type': 'application/json'})
        data = urlopen(request).read().decode()
        assert 'event: response.created\n' in data
        assert 'event: response.output_text.delta\n' in data
        assert 'event: response.completed\n' in data
    finally:
        server.shutdown();server.server_close();gw.close()


def test_cancel_after_executor_settles_and_does_not_dispatch_judge(tmp_path):
    cancelled = [False]
    class CancellingCaller(Caller):
        def __call__(self, action, options):
            result = super().__call__(action, options)
            cancelled[0] = True
            return result
    caller = CancellingCaller(reply())
    gw = gateway(tmp_path, caller, escalation_configuration())
    with pytest.raises(RuntimeError, match='停止'):
        gw.complete(request('escalation'), cancelled=lambda: cancelled[0])
    run = next(iter(gw.runtime.runs.values()))
    assert len(caller.actions) == 1
    assert run['budget'].records[0]['status'] == 'billed'
    gw.close()


def test_explicit_session_concurrent_call_cannot_overspend(tmp_path):
    from threading import Event
    entered, release = Event(), Event()
    class BlockingCaller(Caller):
        def __call__(self, action, options):
            entered.set();assert release.wait(3)
            return super().__call__(action,options)
    caller = BlockingCaller(reply())
    gw = gateway(tmp_path, caller)
    req = {**request(), 'metadata': {'refract_session':'one','refract_task':'one'}}
    errors = []
    def first():
        try: gw.complete(req)
        except Exception as e: errors.append(e)
    worker = Thread(target=first);worker.start();assert entered.wait(3)
    try:
        with pytest.raises(ValueError, match='未结算'):
            gw.complete(req)
    finally:
        release.set();worker.join();gw.close()
    assert not errors and len(caller.actions) == 1


def test_judge_timeout_and_requested_execution_cap_in_protected_path(tmp_path):
    cfg = escalation_configuration()
    cfg['escalation']['judgeTimeoutMs'] = 321
    caller = Caller(reply(), reply(json.dumps({'verdict':'PROCEED','confidence':.9,'evidenceIds':[],'reason':'符合'})))
    gw = gateway(tmp_path,caller,cfg)
    gw.complete({**request('escalation'), 'max_tokens': 100})
    assert caller.actions[0]['model']['maxTokens'] == 100
    assert caller.actions[1]['timeoutMs'] <= 321
    run = next(iter(gw.runtime.runs.values()))
    models = run['config']['models']
    expected = sum(gw.runtime._cost_bound(models[m], caller.actions[0]['messages'],
        caller.actions[0]['tools'],100) for m in ('small','large'))
    expected += gw.runtime._bounded_input_cost(models['judge'],8000,256)
    assert run['state']['protectedBudget']['CNY'] == pytest.approx(expected)
    gw.close()


def test_private_reasoning_preserved_only_for_accepted_same_model_history(tmp_path):
    private_reply = replace(reply('开始', [call()]), replay_messages=({'reasoning_content': '私有推理'},))
    caller = Caller(private_reply,reply())
    gw = gateway(tmp_path,caller)
    req = request();first = gw.complete(req)
    assert '私有推理' not in json.dumps(first,ensure_ascii=False)
    gw.complete(follow(req,first))
    sent = wire_messages(caller.actions[1]['messages'])
    assert sent[-2]['reasoning_content'] == '私有推理'
    gw.close()


def test_private_reasoning_removed_on_unverified_cross_model_history(tmp_path):
    cfg = configuration('static')
    caller = Caller(replace(reply('开始',[call()]),replay_messages=({'reasoning_content':'私有推理'},)),reply())
    gw = gateway(tmp_path,caller,cfg)
    req = request();first = gw.complete(req)
    gw.planning['roles']['efficient'] = 'large'
    continuation = follow(req, first)
    continuation['metadata'] = {'refract_session':'different','refract_task':'1'}
    gw.complete(continuation)
    assert caller.actions[-1]['model']['id'] == 'large'
    assert all('reasoning_content' not in m for m in wire_messages(caller.actions[-1]['messages']))
    gw.close()
