"""SSE 与完整 JSON 的差异验收；只使用已有 Chat/Responses 格式与内存 HTTP。"""
from contextlib import closing
from copy import deepcopy
import json
import socket
import time

import pytest

from refractrouter.gateway_responses import from_chat, to_chat
from refractrouter.gateway_streaming import WireStream, stream_chat
from refractrouter.openai_compatible import OpenAICompatibleClient, TransportResponse
from tests.recipe_protocol_fixtures import (
    MemoryUpstream, PRIVATE, TEXT, USAGE, completion, decode_sse, delta_event,
    function_call, responses_request, sse_bytes, stream_events,
)


@pytest.fixture(autouse=True)
def no_socket_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("本组禁止真实 socket 或 DNS")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


def parse_memory(monkeypatch, events, **options):
    body_options = {k: options.pop(k) for k in list(options)
                    if k in {"done", "crlf", "multiline", "ascii_json"}}
    upstream = MemoryUpstream(monkeypatch, [], body=sse_bytes(events, **body_options), **options)
    text = []
    response = stream_chat("http://fixture.invalid/v1/chat/completions", {}, {}, 5, text.append)
    assert len(upstream.requests) == 1
    return response, text


@pytest.mark.parametrize("sizes", [(1,) * 20000, (1, 2, 3, 5, 8) * 1000, (65536,)],
                         ids=["every-byte", "mixed-bytes", "one-read"])
@pytest.mark.parametrize("crlf", [False, True], ids=["lf", "crlf"])
@pytest.mark.parametrize("multiline", [False, True], ids=["one-data-line", "multi-data-line"])
@pytest.mark.parametrize("ascii_json", [False, True], ids=["utf8", "escaped-unicode"])
def test_utf8_tool_reasoning_and_usage_match_nonstream(
        monkeypatch, sizes, crlf, multiline, ascii_json):
    calls = [function_call(arguments=json.dumps({"path": "中文🦀.txt", "nested": ["🚀", {"quoted": 'a"b\\c'}]},
                                                ensure_ascii=False))]
    raw = completion(TEXT, calls)
    expected = OpenAICompatibleClient._parse_response(TransportResponse(200, {},
        json.dumps(raw, ensure_ascii=False).encode()), 1, time.perf_counter())
    actual, delivered = parse_memory(monkeypatch, stream_events(raw, pieces=list(TEXT)),
        sizes=sizes, crlf=crlf, multiline=multiline, ascii_json=ascii_json)
    for field in ("content", "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens",
                  "tool_calls", "finish_reason", "request_id", "raw_usage", "replay_messages"):
        assert getattr(actual, field) == getattr(expected, field), field
    assert "".join(delivered) == TEXT and PRIVATE not in "".join(delivered)
    assert actual.usage_available and actual.ttft_ms is not None


def test_interleaved_tool_argument_chunks_keep_call_identity(monkeypatch):
    args = ['{"path":"中文🦀.txt"}', '{"path":"第二份🚀.txt"}']
    events = [delta_event({"tool_calls": [{"index": i, "id": "call_" + str(i),
        "type": "function", "function": {"name": "re", "arguments": ""}} for i in (0, 1)]})]
    events.append(delta_event({"tool_calls": [{"index": i, "function": {"name": "ad"}} for i in (1, 0)]}))
    for n in range(max(map(len, args))):
        for i in (1, 0):
            if n < len(args[i]):
                events.append(delta_event({"tool_calls": [{"index": i, "function": {"arguments": args[i][n]}}]}))
    events.extend([delta_event(finish="tool_calls"), delta_event(usage=USAGE)])
    response, delivered = parse_memory(monkeypatch, events)
    assert response.tool_calls == tuple(function_call("call_" + str(i), arguments=args[i]) for i in (0, 1))
    assert delivered == []


@pytest.mark.parametrize("responses", [False, True], ids=["chat", "responses"])
def test_tools_and_success_are_released_only_after_settlement(tmp_path, monkeypatch, responses):
    upstream = MemoryUpstream(monkeypatch, [completion(TEXT, [function_call()])])
    packets = []
    wire = WireStream(packets.append, responses=responses, include_usage=True)
    with closing(upstream.gateway(tmp_path)) as gw:
        result = gw.complete(to_chat(responses_request()), on_text=wire.text)
        before = decode_sse(packets)
        assert before and PRIVATE not in json.dumps(before, ensure_ascii=False)
        assert not any(v == "[DONE]" or (isinstance(v, dict) and (
            v.get("type") == "response.completed" or "function_call" in v.get("type", "")
            or any(c.get("delta", {}).get("tool_calls") for c in v.get("choices", [])))) for v in before)
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["status"] == "billed"
        wire.finish(result)
        after = decode_sse(packets)
        if responses:
            assert after[-1]["type"] == "response.completed" and "[DONE]" not in after
            assert [v["sequence_number"] for v in after] == list(range(len(after)))
            final = after[-1]["response"]
            assert final["output"][1]["call_id"] == "call_a"
            assert final["output"][1]["arguments"] == function_call()["function"]["arguments"]
            deltas = [v for v in after if v["type"] == "response.output_text.delta"]
            done = next(v for v in after if v["type"] == "response.output_text.done")
            assert "".join(v["delta"] for v in deltas) == done["text"] == TEXT
            assert {v["item_id"] for v in deltas} == {final["output"][0]["id"]}
        else:
            assert after[-1] == "[DONE]"
            assert after[-2]["usage"] == result["usage"]
            assert sum(bool(v.get("choices") and v["choices"][0]["delta"].get("tool_calls"))
                       for v in after[:-1]) == 1


@pytest.mark.parametrize("finish", ["length", "content_filter", "error", "unknown-finish"])
@pytest.mark.parametrize("responses", [False, True], ids=["chat", "responses"])
def test_unsuccessful_finish_is_billed_without_success_event(tmp_path, monkeypatch, finish, responses):
    upstream = MemoryUpstream(monkeypatch, [completion(finish=finish)])
    packets = []
    wire = WireStream(packets.append, responses=responses, include_usage=True)
    with closing(upstream.gateway(tmp_path)) as gw:
        with pytest.raises(ValueError):
            gw.complete(to_chat(responses_request()), on_text=wire.text)
        wire.fail()
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["status"] == "billed" and row["charged"] > 0
    decoded = decode_sse(packets)
    assert "[DONE]" not in decoded and not any(v.get("type") == "response.completed" for v in decoded)
    assert b"router_stream_failed" in b"".join(packets) and len(upstream.requests) == 1


def malformed_streams():
    final = [delta_event(finish="stop"), delta_event(usage=USAGE)]
    return [
        pytest.param([delta_event({"content": "片段"})], True, id="missing-finish"),
        pytest.param([delta_event({"content": "片段"}), *final], False, id="missing-done"),
        pytest.param([*final, delta_event({"content": "结束后新增"})], True, id="output-after-finish"),
        pytest.param([*final, delta_event(finish="length")], True, id="conflicting-finish"),
        pytest.param([*final, delta_event(usage={**USAGE, "completion_tokens": 25})], True, id="conflicting-usage"),
        pytest.param([delta_event({"tool_calls": [{"index": 0, "id": "a", "function": {"name": "read"}},
                            {"index": 0, "id": "b"}]}), *final], True, id="changed-tool-id"),
        pytest.param([delta_event({"tool_calls": [{"index": -1}]}), *final], True, id="negative-tool-index"),
        pytest.param([delta_event({"tool_calls": [{"index": 0, "function": {"arguments": "{}"}}]}), *final],
                     True, id="missing-tool-identity"),
    ]


@pytest.mark.parametrize("events,done", malformed_streams())
def test_malformed_stream_preserves_reservation_and_never_retries(tmp_path, monkeypatch, events, done):
    upstream = MemoryUpstream(monkeypatch, [], body=sse_bytes(events, done=done))
    packets = []
    wire = WireStream(packets.append, responses=True)
    with closing(upstream.gateway(tmp_path)) as gw:
        with pytest.raises(ValueError):
            gw.complete(to_chat(responses_request()), on_text=wire.text)
        wire.fail()
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"] > 0
    assert len(upstream.requests) == 1
    assert not any(v.get("type") == "response.completed" for v in decode_sse(packets))


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 80},
    {"prompt_tokens": True, "completion_tokens": 24},
    {"prompt_tokens": 80, "completion_tokens": 0},
    {**USAGE, "prompt_tokens_details": {"cached_tokens": 81}}])
@pytest.mark.parametrize("stream", [False, True])
def test_missing_or_invalid_usage_is_never_reported_as_free_success(tmp_path, monkeypatch, usage, stream):
    upstream = MemoryUpstream(monkeypatch, [completion(usage=usage)])
    with closing(upstream.gateway(tmp_path)) as gw:
        with pytest.raises(ValueError, match="usage"):
            gw.complete(to_chat(responses_request()), on_text=(lambda *_: None) if stream else None)
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"] > 0
    assert len(upstream.requests) == 1


def test_duplicate_identical_usage_is_only_billed_once(tmp_path, monkeypatch):
    events = stream_events(completion())
    events.append(deepcopy(events[-1]))
    upstream = MemoryUpstream(monkeypatch, [], body=sse_bytes(events))
    with closing(upstream.gateway(tmp_path)) as gw:
        result = gw.complete(to_chat(responses_request()), on_text=lambda *_: None)
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert result["usage"]["completion_tokens"] == 24
        assert row["charged"] == pytest.approx(.000128)


def test_response_identity_change_is_rejected(tmp_path, monkeypatch):
    events = [delta_event({"content": "第一份"}),
              delta_event({"content": "第二份"}, response_id="other_response"),
              delta_event(finish="stop"), delta_event(usage=USAGE)]
    upstream = MemoryUpstream(monkeypatch, [], body=sse_bytes(events))
    with closing(upstream.gateway(tmp_path)) as gw:
        with pytest.raises(ValueError):
            gw.complete(to_chat(responses_request()), on_text=lambda *_: None)
        row = next(iter(gw.runtime.runs.values()))["budget"].records[0]
        assert row["status"] == "unknown-usage" and row["charged"] == row["reserved"]
    assert len(upstream.requests) == 1


@pytest.mark.parametrize("with_tool", [False, True])
@pytest.mark.xfail(strict=True, reason="RCP-004：incomplete 外层仍配有 completed 输出项；仅转换器可达")
def test_incomplete_converter_does_not_mark_unfinished_items_completed(with_tool):
    raw = completion("未完成", [function_call(arguments='{"path":')] if with_tool else (), finish="length")
    raw["created"] = 0
    response = from_chat(raw)
    assert response["status"] == "incomplete"
    assert all(item["status"] != "completed" for item in response["output"])
