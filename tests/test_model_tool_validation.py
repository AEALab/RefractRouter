"""标准入口不允许模型猜对答案替代当前任务的可信工具回执。"""
import json
import pytest

from tests.test_model_gateway import Caller, reply, gateway, request, follow, call
from tests.test_planning_routing import advisor_gate_configuration
from refractrouter.host_evidence import EVIDENCE_VERSION
from refractrouter.model_tool_validation import request_requirements, verify


def tool_request(strategy='static'):
    return {**request(strategy, [{'role': 'user', 'content': '请使用 read 工具读取文件，再根据真实结果回答。'}]),
            'metadata': {'refract_tool_evidence_policy': 'confirmed'}}


def add_fact(gw, cid, status='completed'):
    return gw.record_host_evidence({'version': EVIDENCE_VERSION, 'callId': cid,
        'status': status, 'kind': 'observe', 'fingerprint': 'host-verified'})


@pytest.mark.parametrize('strategy', ['static', 'stage', 'advisor'])
def test_correct_guess_stops_before_judge_and_preserves_cost(tmp_path, strategy):
    caller = Caller(reply('我已读取文件，答案是 7'), reply(json.dumps({'verdict': 'APPROVE'})))
    gw = gateway(tmp_path, caller, advisor_gate_configuration() if strategy == 'advisor' else None)
    with pytest.raises(ValueError, match='required-host-tool-not-observed'):
        gw.complete(tool_request(strategy))
    run = next(iter(gw.runtime.runs.values()))
    assert len(caller.actions) == 1
    assert run['status'] == 'tool-requirement-failed'
    assert run['budget'].records[0]['status'] == 'billed'
    assert run['budget'].records[0]['disposition'] == 'discarded'
    assert run['state']['toolValidation']['passed'] is False
    gw.close()


@pytest.mark.parametrize('status, released', [('completed', True), ('failed', True),
    ('denied', False), ('infrastructure', False), ('unclassified-error', False)])
def test_current_host_fact_distinguishes_exit_failure_denial_and_infrastructure(tmp_path, status, released):
    caller = Caller(reply(calls=[call()]), reply('真实宿主结果已如实报告'))
    gw = gateway(tmp_path, caller)
    req = tool_request()
    first = gw.complete(req)
    add_fact(gw, 'call-1', status)
    if released:
        result = gw.complete(follow(req, first))
        assert result['choices'][0]['message']['content'] == '真实宿主结果已如实报告'
    else:
        with pytest.raises(ValueError, match='工具要求未验收'):
            gw.complete(follow(req, first))
    run = next(iter(gw.runtime.runs.values()))
    assert run['state']['toolValidation']['records'][0]['status'] == status
    assert run['state']['toolValidation']['semanticQualityVerified'] is False
    assert len(caller.actions) == 2  # 验收不执行工具，不增加 Judge 或重试。
    gw.close()


def test_plain_tool_text_cannot_invent_confirmed_exit(tmp_path):
    caller = Caller(reply(calls=[call()]), reply('success exit code 0'))
    gw = gateway(tmp_path, caller)
    req = tool_request()
    first = gw.complete(req)
    with pytest.raises(ValueError, match='host-tool-status-unconfirmed'):
        gw.complete(follow(req, first))
    gw.close()


def test_base_url_receipt_stays_compatible_without_claiming_exit_success(tmp_path):
    caller = Caller(reply(calls=[call()]), reply('宿主提供的内容'))
    gw = gateway(tmp_path, caller)
    req = tool_request(); req.pop('metadata')
    first = gw.complete(req)
    assert gw.complete(follow(req, first))['choices'][0]['message']['content'] == '宿主提供的内容'
    validation = next(iter(gw.runtime.runs.values()))['state']['toolValidation']
    assert validation['passed'] is True and validation['outcomeConfirmed'] is False
    assert validation['records'][0]['status'] == 'unclassified'
    assert validation['semanticQualityVerified'] is False
    gw.close()


def test_old_history_cannot_satisfy_new_task(tmp_path):
    caller = Caller(reply(calls=[call()]), reply('旧任务'), reply('猜出的新答案'))
    gw = gateway(tmp_path, caller)
    req = tool_request(); first = gw.complete(req); add_fact(gw, 'call-1')
    old = follow(req, first); result = gw.complete(old)
    new = {**req, 'messages': old['messages'] + [result['choices'][0]['message'],
        {'role': 'user', 'content': '请使用 read 工具读取文件，再根据真实结果回答。'}]}
    with pytest.raises(ValueError, match='required-host-tool-not-observed'):
        gw.complete(new)
    assert len(gw.runtime.runs) == 2
    gw.close()


def test_missing_receipt_buffers_output_before_any_user_text(tmp_path):
    class StreamingCaller(Caller):
        def stream(self, action, options, deliver):
            deliver('猜出的答案不应闪现')
            return self(action, options)
    gw = gateway(tmp_path, StreamingCaller(reply('7')))
    delivered = []
    with pytest.raises(ValueError, match='工具要求未验收'):
        gw.complete(tool_request(), on_text=lambda *v: delivered.append(v))
    assert delivered == []
    gw.close()


def test_negation_system_messages_and_codex_command_alias():
    assert request_requirements([{'role': 'system', 'content': '请使用 Bash'},
        {'role': 'user', 'content': '不要调用工具，只回答 7'}], [])['required'] is False
    result = verify({'required': True, 'tools': ['bash']}, [
        {'callId': 'current', 'tool': 'exec_command', 'status': 'completed'}])
    assert result['passed'] is True
