"""标准模型接口的增量传输；文本实时交付，工具完成事件在结算后交付。"""
from dataclasses import replace
import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from uuid import uuid4

from .openai_compatible import OpenAICompatibleClient, TransportResponse

MAX_STREAM_BYTES = 8 * 1024 * 1024


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def stream_chat(url, headers, payload, timeout, on_text):
    """一次 HTTP 派发；没有自动重试，使用最终 usage 结算。"""
    started = time.perf_counter()
    request = Request(url, data=encoded({**payload, 'stream': True,
        'stream_options': {'include_usage': True}}), headers=headers, method='POST')
    text, reasoning, calls, usage, finish, first = [], [], {}, None, None, None
    response_id, total, done, event = None, 0, False, []
    try:
        response = urlopen(request, timeout=timeout)
    except HTTPError as exc:
        exc.close()
        raise RuntimeError(f'上游模型 HTTP {exc.code}；未自动重试') from None
    with response:
        if 'text/event-stream' not in response.headers.get('Content-Type', ''):
            raise ValueError('上游未返回 SSE；不自动重新请求')
        while True:
            if time.perf_counter() - started >= timeout:
                raise TimeoutError('上游流超过调用期限')
            response.fp.raw._sock.settimeout(max(.001, timeout - (time.perf_counter() - started)))
            line = response.readline(MAX_STREAM_BYTES + 1)
            total += len(line)
            if total > MAX_STREAM_BYTES:
                raise ValueError('上游流超过 8 MiB 上限')
            if not line:
                break
            if line.strip():
                if line.startswith(b'data:'):
                    event.append(line[5:].strip())
                continue
            if not event:
                continue
            raw = b'\n'.join(event); event = []
            if raw == b'[DONE]':
                done = True
                break
            data = json.loads(raw)
            if not isinstance(data, dict) or data.get('error'):
                raise ValueError('上游流返回错误或无效事件')
            response_id = response_id or data.get('id')
            if data.get('usage') is not None:
                if usage is not None and usage != data['usage']:
                    raise ValueError('上游流用量回执互相矛盾')
                usage = data['usage']
            choices = data.get('choices', [])
            if not isinstance(choices, list) or len(choices) > 1:
                raise ValueError('流式接口仅支持一个候选')
            for choice in choices:
                if choice.get('index', 0) != 0:
                    raise ValueError('无效流式候选编号')
                delta = choice.get('delta') or {}
                if set(delta) - {'role', 'content', 'reasoning_content', 'tool_calls', 'refusal'} or delta.get('refusal'):
                    raise ValueError('未验收的流式内容类型')
                if finish is not None and any(delta.get(k) for k in ('content','reasoning_content','tool_calls')):
                    raise ValueError('结束标识之后仍收到模型输出')
                for key, pieces in (('content', text), ('reasoning_content', reasoning)):
                    value = delta.get(key)
                    if value is not None:
                        if not isinstance(value, str):
                            raise ValueError('流式文本类型不合法')
                        pieces.append(value)
                        if key == 'content' and value:
                            if first is None: first = round((time.perf_counter() - started) * 1000)
                            on_text(value)
                for item in delta.get('tool_calls') or []:
                    index = item.get('index')
                    if type(index) is not int or index < 0 or index >= 256:
                        raise ValueError('无效工具流编号')
                    call = calls.setdefault(index, {'id':'', 'type':'function',
                        'function':{'name':'', 'arguments':''}})
                    if item.get('type', 'function') != 'function':
                        raise ValueError('当前只支持 function 工具')
                    if item.get('id'):
                        if call['id'] and call['id'] != item['id']:
                            raise ValueError('同一工具流身份改变')
                        call['id'] = item['id']
                    for key in ('name', 'arguments'):
                        value = (item.get('function') or {}).get(key)
                        if value is not None:
                            if not isinstance(value, str): raise ValueError('工具流参数不是字符串')
                            call['function'][key] += value
                reason = choice.get('finish_reason')
                if reason is not None:
                    if finish is not None and reason != finish: raise ValueError('矛盾的结束原因')
                    finish = reason
        if not done or finish is None:
            raise ValueError('上游流中断或缺少完成标识；保留未知用量预留')
        if any(not c['id'] or not c['function']['name'] for c in calls.values()):
            raise ValueError('未完成的工具调用')
        message = {'role':'assistant', 'content': ''.join(text),
            **({'reasoning_content': ''.join(reasoning)} if reasoning else {}),
            **({'tool_calls': [calls[i] for i in sorted(calls)]} if calls else {})}
        body = {'id':response_id, 'choices':[{'message':message,'finish_reason':finish}], 'usage':usage}
        parsed = OpenAICompatibleClient._parse_response(
            TransportResponse(response.status, dict(response.headers), encoded(body)), 1, started)
        return replace(parsed, ttft_ms=first)


class WireStream:
    """两种下游 SSE 格式共享交付时序；不输出成功结束事件直到核心完成结算。"""
    def __init__(self, send, *, responses=False, include_usage=False, aliases=None):
        self.send, self.responses, self.include_usage = send, responses, include_usage
        self.aliases = aliases or {}
        self.started, self.text_started, self.live_text = False, False, ''
        self.sequence, self.message_id = 0, 'msg_' + uuid4().hex
        self.response_id, self.base = 'resp_' + uuid4().hex, None

    def event(self, kind, **data):
        value = {'type':kind, 'sequence_number':self.sequence, **data}
        self.sequence += 1
        self.send(b'event: '+kind.encode()+b'\ndata: '+encoded(value)+b'\n\n')

    def chunk(self, delta, finish=None, usage=None):
        value = {**self.base,'object':'chat.completion.chunk',
            'choices':[] if usage is not None else [{'index':0,'delta':delta,'finish_reason':finish}]}
        if usage is not None: value['usage'] = usage
        self.send(b'data: '+encoded(value)+b'\n\n')

    def start(self, meta):
        if self.started: return
        self.started = True
        self.base = {k:meta[k] for k in ('id','created','model')}
        if self.responses:
            initial = {'id':self.response_id,'object':'response','created_at':meta['created'],
                'model':meta['model'],'status':'in_progress','output':[],'usage':None}
            self.event('response.created',response=initial)
            self.event('response.in_progress',response=initial)
        else: self.chunk({'role':'assistant'})

    def text(self, meta, text):
        self.start(meta)
        if self.responses:
            if not self.text_started:
                self.event('response.output_item.added',output_index=0,item={'type':'message',
                    'id':self.message_id,'role':'assistant','status':'in_progress','content':[]})
                self.event('response.content_part.added',item_id=self.message_id,output_index=0,
                    content_index=0,part={'type':'output_text','text':'','annotations':[]})
            self.event('response.output_text.delta',item_id=self.message_id,output_index=0,
                content_index=0,delta=text)
        else: self.chunk({'content':text})
        self.text_started = True
        self.live_text += text

    def finish(self, result):
        from .gateway_responses import from_chat
        self.start(result)
        choice = result['choices'][0]; message = choice['message']
        text = message.get('content') or ''
        if self.text_started and text != self.live_text:
            raise ValueError('已释放的文本不能被替换')
        if text and not self.text_started: self.text(result, text)
        if not self.responses:
            if message.get('tool_calls'):
                self.chunk({'tool_calls':[{'index':i,**call} for i,call in enumerate(message['tool_calls'])]})
            self.chunk({}, choice['finish_reason'])
            if self.include_usage: self.chunk({},usage=result['usage'])
            self.send(b'data: [DONE]\n\n')
            return
        final = from_chat(result, self.aliases);final['id'] = self.response_id
        offset = 0
        if self.text_started:
            item = final['output'][0];item['id'] = self.message_id
            ctx = {'item_id':self.message_id,'output_index':0,'content_index':0}
            self.event('response.output_text.done',**ctx,text=text)
            self.event('response.content_part.done',**ctx,part=item['content'][0])
            self.event('response.output_item.done',output_index=0,item=item)
            offset = 1
        for index,item in enumerate(final['output'][offset:],start=offset):
            self.event('response.output_item.added',output_index=index,item={**item,'status':'in_progress','arguments':''})
            self.event('response.function_call_arguments.delta',item_id=item['id'],output_index=index,delta=item['arguments'])
            self.event('response.function_call_arguments.done',item_id=item['id'],output_index=index,arguments=item['arguments'])
            self.event('response.output_item.done',output_index=index,item=item)
        self.event('response.incomplete' if final['status']=='incomplete' else 'response.completed',response=final)

    def fail(self):
        if self.responses:
            self.event('error',code='router_stream_failed',message='流式调用未完成；请核对账本，未自动重试',param=None)
        else:
            self.send(b'data: '+encoded({'error':{'type':'router_stream_failed',
                'message':'流式调用未完成；请核对账本，未自动重试'}})+b'\n\n')
