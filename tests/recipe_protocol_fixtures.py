"""协议差异测试的模拟传输；生产解析器、路由与账本均使用真实实现。"""
from collections import deque
from copy import deepcopy
import http.client
import io
import json

from refractrouter.model_gateway import HttpModelCaller, ModelGateway
from refractrouter.openai_compatible import TransportResponse
from tests.test_planning_routing import configuration


TEXT = '中文🦀🚀👩🏽\u200d💻e\u0301；示例 </think> <｜DSML｜invoke name="read">'
PRIVATE = "内部思考🧠，仅供同源工具续接"
USAGE = {"prompt_tokens": 80, "completion_tokens": 24, "total_tokens": 104,
         "prompt_tokens_details": {"cached_tokens": 20},
         "completion_tokens_details": {"reasoning_tokens": 8}}
TOOLS = [{"type": "function", "name": "read", "description": "读取宿主内容",
          "strict": True, "parameters": {"type": "object", "properties": {
              "path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}]


def function_call(call_id="call_a", name="read", arguments=None):
    return {"id": call_id, "type": "function", "function": {"name": name,
        "arguments": arguments if arguments is not None else '{"path":"中文🦀.txt"}'}}


def completion(text=TEXT, calls=(), reasoning=PRIVATE, usage=USAGE, finish=None):
    return {"id": "upstream_fixture", "object": "chat.completion", "model": "fixture-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text,
                **({"reasoning_content": reasoning} if reasoning else {}),
                **({"tool_calls": list(calls)} if calls else {})},
                "finish_reason": finish or ("tool_calls" if calls else "stop")}],
            "usage": deepcopy(usage)}


def delta_event(delta=None, finish=None, usage=None, response_id="upstream_fixture"):
    return {"id": response_id, "object": "chat.completion.chunk", "model": "fixture-model",
        "choices": [] if usage is not None else [{"index": 0, "delta": delta or {},
                                                   "finish_reason": finish}],
        **({"usage": deepcopy(usage)} if usage is not None else {})}


def sse_bytes(events, *, done=True, crlf=False, multiline=False, ascii_json=False):
    lines = []
    for event in events:
        value = json.dumps(event, ensure_ascii=ascii_json, separators=(",", ":"))
        if multiline:
            # 仅在 JSON token 间换行；SSE 的多条 data 行按换行拼接。
            cut = value.index(",") + 1
            lines.append("data: " + value[:cut] + "\ndata: " + value[cut:] + "\n\n")
        else:
            lines.append("data: " + value + "\n\n")
    if done:
        lines.append("data: [DONE]\n\n")
    text = ": keepalive\n\n" + "".join(lines)
    return (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")


def stream_events(raw, *, pieces=None):
    message = raw["choices"][0]["message"]
    events = [delta_event({"role": "assistant"})]
    if message.get("reasoning_content"):
        events.extend(delta_event({"reasoning_content": c}) for c in message["reasoning_content"])
    events.extend(delta_event({"content": c}) for c in
                  (pieces if pieces is not None else [message.get("content") or ""]))
    for index, call in enumerate(message.get("tool_calls", [])):
        events.append(delta_event({"tool_calls": [{"index": index, "id": call["id"],
            "type": "function", "function": {"name": call["function"]["name"], "arguments": ""}}]}))
        events.extend(delta_event({"tool_calls": [{"index": index, "function": {"arguments": c}}]})
                      for c in call["function"]["arguments"])
    events.append(delta_event(finish=raw["choices"][0]["finish_reason"]))
    if raw.get("usage") is not None:
        events.append(delta_event(usage=raw["usage"]))
    return events


class FragmentedReader(io.RawIOBase):
    """模拟任意网络字节切分，包括 UTF-8 字符与 SSE 行内部。"""
    def __init__(self, data, sizes):
        super().__init__()
        self.remaining = memoryview(data)
        self.sizes = deque(sizes)
        self._sock = self

    def readable(self):
        return True

    def settimeout(self, _timeout):
        pass

    def readinto(self, target):
        size = min(len(target), len(self.remaining), self.sizes.popleft() if self.sizes else 8192)
        target[:size] = self.remaining[:size]
        self.remaining = self.remaining[size:]
        return size


class ScriptedSocket:
    def __init__(self, body, sizes, content_type):
        self.data = ("HTTP/1.1 200 OK\r\nContent-Type: " + content_type +
                     "\r\nConnection: close\r\n\r\n").encode() + body
        self.sizes = sizes

    def makefile(self, *_args):
        return io.BufferedReader(FragmentedReader(self.data, self.sizes))


class MemoryUpstream:
    """同时提供完整 JSON 与 SSE，记录实际发送的 Chat Completions 请求。"""
    def __init__(self, monkeypatch, replies, *, body=None, sizes=(1,) * 20000,
                 content_type="text/event-stream"):
        self.replies, self.requests = deque(deepcopy(replies)), []
        self.body, self.sizes, self.content_type = body, sizes, content_type
        monkeypatch.setattr("refractrouter.gateway_streaming.urlopen", self.urlopen)

    def post(self, url, _headers, body, _timeout):
        self.requests.append({"url": url, "payload": json.loads(body)})
        return TransportResponse(200, {"Content-Type": "application/json"},
                                 json.dumps(self.replies.popleft(), ensure_ascii=False).encode())

    def urlopen(self, request, *, timeout):
        self.requests.append({"url": request.full_url, "payload": json.loads(request.data)})
        body = self.body
        if body is None:
            body = sse_bytes(stream_events(self.replies.popleft()))
        response = http.client.HTTPResponse(ScriptedSocket(body, self.sizes, self.content_type))
        response.begin()
        return response

    def gateway(self, path):
        cfg = configuration("static")
        # 明确模拟价格单位，避免历史 USD 配置的 CNY 换算干扰用量断言。
        cfg.update(schemaVersion="refractagent-planning-v3", billingUnit="CNY",
                   maxProductionCostByUnit={"CNY": 10})
        for model in cfg["models"]:
            model["provider"] = "memory"
            model["billingUnit"] = "CNY"
        providers = {"memory": {"baseURL": "http://fixture.invalid/v1"}}
        return ModelGateway({"planningRouting": cfg, "providers": providers}, path,
                            caller=HttpModelCaller(providers, transport=self))


def responses_request(**overrides):
    return {"model": "refract/static", "input": [{"role": "user", "content": "读取内容后回答"}],
            "tools": deepcopy(TOOLS), "store": False, **overrides}


def decode_sse(packets):
    """测试端按 SSE 帧读取 JSON；不重用生产解析器作为判定依据。"""
    values = []
    for frame in b"".join(packets).decode().split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:"))
        if data:
            values.append(data if data == "[DONE]" else json.loads(data))
    return values
