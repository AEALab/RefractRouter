"""参考 recipe 的协议保真合同，仅验收现有 Responses/text/function 子集。"""
from contextlib import closing
from copy import deepcopy
import json
import socket

import pytest

from refractrouter.gateway_responses import from_chat, lower_tools, to_chat
from refractrouter.gateway_streaming import WireStream
from refractrouter.model_gateway import wire_messages
from tests.recipe_protocol_fixtures import (
    MemoryUpstream, PRIVATE, TEXT, USAGE, completion, decode_sse, function_call,
    responses_request,
)


@pytest.fixture(autouse=True)
def no_socket_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("本组仅使用内存响应，禁止真实 socket 或 DNS")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


@pytest.mark.parametrize("stream", [False, True], ids=["json", "sse"])
def test_responses_options_and_literal_text_preserve_chat_request(tmp_path, monkeypatch, stream):
    upstream = MemoryUpstream(monkeypatch, [completion()])
    request = responses_request(instructions="只使用宿主提供的内容", stream=stream,
        temperature=0, top_p=.9, max_output_tokens=300, parallel_tool_calls=False,
        tool_choice={"type": "function", "name": "read"},
        reasoning={"effort": "low", "summary": "auto"},
        include=["reasoning.encrypted_content"], prompt_cache_key="opaque-cache-key")
    saved = deepcopy(request)
    packets = []
    wire = WireStream(packets.append, responses=True)
    with closing(upstream.gateway(tmp_path)) as gw:
        result = gw.complete(to_chat(request), on_text=wire.text if stream else None)
        if stream:
            wire.finish(result)
        output = decode_sse(packets)[-1]["response"] if stream else from_chat(result)
        assert output["output"][0]["content"][0]["text"] == TEXT
        assert output["status"] == "completed"
        assert PRIVATE not in json.dumps(output, ensure_ascii=False)
    sent = upstream.requests[0]
    assert sent["url"] == "http://fixture.invalid/v1/chat/completions"
    payload = sent["payload"]
    assert payload["messages"] == [{"role": "system", "content": request["instructions"]},
                                    {"role": "user", "content": "读取内容后回答"}]
    assert payload["tools"] == [{"type": "function", "function": {
        k: v for k, v in request["tools"][0].items() if k != "type"}}]
    assert payload["tool_choice"] == {"type": "function", "function": {"name": "read"}}
    for key in ("temperature", "top_p", "parallel_tool_calls", "prompt_cache_key"):
        assert payload[key] == request[key]
    assert payload["max_tokens"] == 300 and payload["reasoning_effort"] == "low"
    assert payload["stream"] is stream
    assert not {"input", "instructions", "store", "include", "max_output_tokens"} & payload.keys()
    assert request == saved and len(upstream.requests) == 1


@pytest.mark.parametrize("stream", [False, True], ids=["json", "sse"])
@pytest.mark.parametrize("namespace", [False, True], ids=["plain", "namespace"])
@pytest.mark.parametrize("reverse_results", [False, True], ids=["same-order", "reverse-order"])
def test_parallel_tool_roundtrip_replays_private_reasoning_only_upstream(
        tmp_path, monkeypatch, stream, namespace, reverse_results):
    request = responses_request(stream=stream)
    if namespace:
        request["tools"] = [{"type": "namespace", "name": "local", "description": "本地工具",
                             "tools": request["tools"]}]
    aliases = lower_tools(request)[1]
    lowered = to_chat(request)["tools"][0]["function"]["name"]
    calls = [function_call("call_a", lowered), function_call("call_b", lowered, '{"path":"第二份🚀.txt"}')]
    upstream = MemoryUpstream(monkeypatch, [completion("开始读取🦀", calls), completion("完成✅")])
    with closing(upstream.gateway(tmp_path)) as gw:
        packets = []
        wire = WireStream(packets.append, responses=True, aliases=aliases)
        first = gw.complete(to_chat(request), on_text=wire.text if stream else None)
        if stream:
            wire.finish(first)
        response = decode_sse(packets)[-1]["response"] if stream else from_chat(first, aliases)
        call_items = [i for i in response["output"] if i["type"] == "function_call"]
        assert [i["call_id"] for i in call_items] == ["call_a", "call_b"]
        assert all(i["name"] == "read" for i in call_items)
        if namespace:
            assert all(i["namespace"] == "local" for i in call_items)
        outputs = [{"type": "function_call_output", "call_id": i["call_id"],
                    "output": "宿主结果 " + i["call_id"] + " 中文🦀"} for i in call_items]
        if reverse_results:
            outputs.reverse()
        follow = {**request, "input": request["input"] + response["output"] + outputs}
        follow_packets = []
        second_wire = WireStream(follow_packets.append, responses=True, aliases=aliases)
        result = gw.complete(to_chat(follow), on_text=second_wire.text if stream else None)
        if stream:
            second_wire.finish(result)
        final = decode_sse(follow_packets)[-1]["response"] if stream else from_chat(result, aliases)
        assert final["output"][0]["content"][0]["text"] == "完成✅"
        sent = upstream.requests[1]["payload"]["messages"]
        assistant = next(m for m in sent if m["role"] == "assistant")
        assert assistant["reasoning_content"] == PRIVATE and assistant["tool_calls"] == calls
        assert [m["tool_call_id"] for m in sent if m["role"] == "tool"] == [o["call_id"] for o in outputs]
        assert PRIVATE not in json.dumps([response, final, decode_sse(packets)], ensure_ascii=False)
        assert len(gw.runtime.runs) == 1
        rows = next(iter(gw.runtime.runs.values()))["budget"].records
        assert len(rows) == 2 and all(r["status"] == "billed" for r in rows)
        assert all(r["reasoning_tokens"] == 8 and r["cached_input_tokens"] == 20 for r in rows)
    assert len(upstream.requests) == 2


@pytest.mark.parametrize("change", ["model", "scope"])
def test_private_reasoning_is_not_attached_to_different_source(tmp_path, monkeypatch, change):
    upstream = MemoryUpstream(monkeypatch, [completion("读取", [function_call()]), completion("完成")])
    request = responses_request()
    with closing(upstream.gateway(tmp_path)) as gw:
        first = from_chat(gw.complete(to_chat(request)))
        follow = {**request, "input": request["input"] + first["output"] + [
            {"type": "function_call_output", "call_id": "call_a", "output": "内容"}]}
        if change == "model":
            gw.planning["roles"]["efficient"] = "large"
            follow["metadata"] = {"refract_session": "new", "refract_task": "new"}
        gw.complete(to_chat(follow), scope="other" if change == "scope" else "default")
    assert all("reasoning_content" not in m for m in upstream.requests[1]["payload"]["messages"])


@pytest.mark.parametrize("mutate", ["text", "arguments", "call_id", "injected_reasoning"])
def test_changed_tool_history_fails_without_second_dispatch(tmp_path, monkeypatch, mutate):
    upstream = MemoryUpstream(monkeypatch, [completion("原始正文", [function_call()])])
    request = responses_request()
    with closing(upstream.gateway(tmp_path)) as gw:
        first = from_chat(gw.complete(to_chat(request)))
        items = deepcopy(first["output"])
        if mutate == "text":
            items[0]["content"][0]["text"] = "被修改"
        elif mutate == "arguments":
            items[1]["arguments"] = '{"path":"被修改"}'
        elif mutate == "call_id":
            # 保留工具结果原 ID，使调用与结果的配对失败。
            items[1]["call_id"] = "different"
        else:
            items.append({"type": "reasoning", "encrypted_content": "untrusted"})
        follow = {**request, "input": request["input"] + items + [
            {"type": "function_call_output", "call_id": "call_a", "output": "内容"}]}
        with pytest.raises(ValueError):
            gw.complete(to_chat(follow))
    assert len(upstream.requests) == 1


@pytest.mark.parametrize("extra", [
    {"previous_response_id": "old"}, {"store": True},
    {"input": [{"type": "reasoning", "encrypted_content": "private"}]},
    {"input": [{"role": "user", "content": [{"type": "input_image", "image_url": "file:x"}]}]},
    {"tools": [{"type": "web_search"}]}, {"tools": [{"type": "custom", "name": "shell"}]},
    {"unknown_parameter": True},
])
def test_unsupported_protocol_stays_rejected_before_dispatch(tmp_path, monkeypatch, extra):
    upstream = MemoryUpstream(monkeypatch, [])
    with closing(upstream.gateway(tmp_path)) as gw:
        with pytest.raises(ValueError):
            gw.complete(to_chat(responses_request(**extra)))
    assert upstream.requests == []


@pytest.mark.parametrize("stream", [False, True])
def test_known_usage_is_counted_once_and_not_as_reasoning_plus_output(tmp_path, monkeypatch, stream):
    upstream = MemoryUpstream(monkeypatch, [completion()])
    with closing(upstream.gateway(tmp_path)) as gw:
        packets = []
        wire = WireStream(packets.append, responses=True)
        result = gw.complete(to_chat(responses_request()), on_text=wire.text if stream else None)
        if stream:
            wire.finish(result)
        response = decode_sse(packets)[-1]["response"] if stream else from_chat(result)
        assert response["usage"] == {"input_tokens": 80, "output_tokens": 24, "total_tokens": 104}
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["input_tokens"] == 80 and row["output_tokens"] == 24
        assert row["reasoning_tokens"] == 8 and row["cached_input_tokens"] == 20
        assert row["charged"] == pytest.approx(.000128)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("reasoning", [True, "8", 8.5, 25])
def test_invalid_reasoning_usage_must_retain_reservation(tmp_path, monkeypatch, stream, reasoning):
    raw = completion()
    raw["usage"]["completion_tokens_details"]["reasoning_tokens"] = reasoning
    upstream = MemoryUpstream(monkeypatch, [raw])
    with closing(upstream.gateway(tmp_path)) as gw:
        with pytest.raises(ValueError, match="usage"):
            gw.complete(to_chat(responses_request()), on_text=(lambda *_: None) if stream else None)
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"] > 0
    assert len(upstream.requests) == 1


@pytest.mark.parametrize("detail,expected", [
    ("input_tokens_details", {"cached_tokens": 20}),
    ("output_tokens_details", {"reasoning_tokens": 8}),
])
@pytest.mark.xfail(strict=True, reason="RCP-003：转换层仅返回总用量，尚未传递已知细分；兼容性缺项")
def test_converter_preserves_known_usage_breakdown(detail, expected):
    raw = completion()
    raw["created"] = 0
    response = from_chat(raw)
    assert response["usage"].get(detail) == expected


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.xfail(strict=True, reason="RCP-003：已知缓存计数的来源在核心结算交接时丢失")
def test_known_cache_observability_survives_core_settlement(tmp_path, monkeypatch, stream):
    upstream = MemoryUpstream(monkeypatch, [completion()])
    with closing(upstream.gateway(tmp_path)) as gw:
        gw.complete(to_chat(responses_request()), on_text=(lambda *_: None) if stream else None)
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["cached_input_tokens"] == 20
        assert row["cache_usage_available"] is True
        assert row["cache_usage_source"] == "prompt_tokens_details.cached_tokens"


def test_source_roundtrip_preserves_literal_control_spellings():
    request = responses_request(input=[{"role": "user", "content": [{"type": "input_text", "text": TEXT}]}])
    chat = to_chat(request)
    from refractrouter.model_gateway import chat_messages
    assert wire_messages(chat_messages(chat["messages"])) == [{"role": "user", "content": TEXT}]
