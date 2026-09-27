"""Responses 文本/function 协议适配；不管理 Agent 工具、压缩或委派。"""
from copy import deepcopy
import hashlib
from uuid import uuid4


def namespaced_name(namespace, name):
    if not all(isinstance(v,str) and v and not any(ord(c)<32 for c in v) for v in (namespace,name)):
        raise ValueError('工具命名空间或名称无效')
    return 'rrns_' + hashlib.sha256((namespace+'\0'+name).encode()).hexdigest()[:48]


def lower_tools(request):
    """仅转换名称；保留全部 schema 和命名空间描述，不代替宿主执行。"""
    lowered, aliases, owners = [], {}, set()
    for tool in request.get('tools',[]):
        if not isinstance(tool,dict): raise ValueError('无效工具定义')
        if tool.get('type')=='namespace':
            if set(tool)-{'type','name','description','tools'} or not isinstance(tool.get('tools'),list):
                raise ValueError('不支持的工具命名空间结构')
            for child in tool['tools']:
                if not isinstance(child,dict) or child.get('type')!='function':
                    raise ValueError('命名空间目前仅支持 function 工具')
                name=namespaced_name(tool.get('name'),child.get('name'))
                if name in owners: raise ValueError('工具名称冲突')
                owners.add(name);aliases[name]={'namespace':tool['name'],'name':child['name']}
                description='\n'.join(v for v in (tool.get('description'),child.get('description')) if v)
                lowered.append({**child,'name':name,**({'description':description} if description else {})})
        else:
            name=tool.get('name')
            if name in owners: raise ValueError('工具名称冲突')
            owners.add(name);lowered.append(deepcopy(tool))
    return lowered,aliases


def to_chat(request):
    allowed = {'model', 'input', 'instructions', 'tools', 'stream', 'store', 'max_output_tokens',
               'temperature', 'top_p', 'parallel_tool_calls', 'tool_choice', 'metadata',
               'reasoning', 'include', 'prompt_cache_key', 'client_metadata'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise ValueError('当前 Responses 接口仅接通全文文本与 function；增量 ID、私有推理和托管工具尚未验收')
    if request.get('store', False) is not False:
        raise ValueError('当前 Responses 接口要求 store=false，并由客户端保存完整历史')
    reasoning=request.get('reasoning') or {}
    if not isinstance(reasoning,dict) or set(reasoning)-{'summary'} or reasoning.get('summary') not in (None,'auto'):
        raise ValueError('虚拟路由的实际推理等级由角色配置冻结；当前仅支持自动摘要提示')
    if request.get('include') not in (None,[],['reasoning.encrypted_content']):
        raise ValueError('不支持的 Responses include')
    if request.get('client_metadata') is not None and not isinstance(request['client_metadata'],dict):
        raise ValueError('client_metadata 必须是对象')
    raw = request.get('input')
    if isinstance(raw, str):
        raw = [{'role': 'user', 'content': raw}]
    if not isinstance(raw, list) or not raw:
        raise ValueError('Responses input 必须是文本或非空列表')
    messages = []
    if request.get('instructions') is not None:
        if not isinstance(request['instructions'], str):
            raise ValueError('instructions 必须是字符串')
        messages.append({'role': 'system', 'content': request['instructions']})
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('无效 Responses input item')
        kind = item.get('type', 'message')
        if kind == 'function_call':
            if set(item) - {'type', 'id', 'call_id', 'name', 'namespace', 'arguments', 'status'}:
                raise ValueError('未知 function_call 字段')
            function = {'id': item.get('call_id'), 'type': 'function',
                        'function': {'name': namespaced_name(item['namespace'],item.get('name')) if item.get('namespace') else item.get('name'), 'arguments': item.get('arguments')}}
            if messages and messages[-1]['role'] == 'assistant':
                messages[-1].setdefault('tool_calls', []).append(function)
            else:
                messages.append({'role': 'assistant', 'content': None, 'tool_calls': [function]})
        elif kind == 'function_call_output':
            if set(item) - {'type', 'id', 'call_id', 'output'} or not isinstance(item.get('output'), str):
                raise ValueError('当前 function_call_output 只支持字符串 output')
            messages.append({'role': 'tool', 'tool_call_id': item.get('call_id'), 'content': item['output']})
        elif kind == 'message':
            if set(item) - {'type', 'id', 'role', 'content', 'status'}:
                raise ValueError('未知 Responses message 字段')
            content = item.get('content')
            if isinstance(content, list):
                parts = []
                for block in content:
                    if (not isinstance(block, dict) or block.get('type') not in ('input_text', 'output_text')
                            or not isinstance(block.get('text'), str) or set(block) - {'type', 'text', 'annotations'}
                            or block.get('annotations')):
                        raise ValueError('未接通的 Responses 内容块或注释')
                    parts.append(block['text'])
                content = '\n'.join(parts)
            messages.append({'role': item.get('role'), 'content': content})
        else:
            raise ValueError('不支持的 Responses 输入类型：' + str(kind))
    tools = []
    for tool in lower_tools(request)[0]:
        if not isinstance(tool, dict) or tool.get('type') != 'function':
            raise ValueError('只支持外部 Agent 执行的 function 工具')
        tools.append({'type': 'function', 'function': {k: deepcopy(v) for k,v in tool.items() if k != 'type'}})
    result = {'model': request.get('model'), 'messages': messages, 'tools': tools,
              'stream': request.get('stream', False)}
    for key in ('temperature', 'top_p', 'parallel_tool_calls', 'metadata', 'prompt_cache_key'):
        if key in request:
            result[key] = deepcopy(request[key])
    if request.get('client_metadata'):
        result['metadata']={**result.get('metadata',{}),'client_metadata':deepcopy(request['client_metadata'])}
    if 'max_output_tokens' in request:
        result['max_tokens'] = request['max_output_tokens']
    if 'tool_choice' in request:
        choice = request['tool_choice']
        if isinstance(choice, dict):
            if set(choice)-{'type','name','namespace'} or choice.get('type') != 'function' or not choice.get('name'):
                raise ValueError('无效 Responses tool_choice')
            choice = {'type': 'function', 'function': {'name': namespaced_name(choice['namespace'],choice['name']) if choice.get('namespace') else choice['name']}}
        result['tool_choice'] = choice
    return result


def from_chat(chat, aliases=None):
    choice = chat['choices'][0]
    message, output = choice['message'], []
    if message.get('content'):
        output.append({'type': 'message', 'id': 'msg_' + uuid4().hex, 'role': 'assistant', 'status': 'completed',
            'content': [{'type': 'output_text', 'text': message['content'], 'annotations': []}]})
    for call in message.get('tool_calls', []):
        output.append({'type': 'function_call', 'id': 'fc_' + uuid4().hex, 'call_id': call['id'],
            'name': call['function']['name'], 'arguments': call['function']['arguments'], 'status': 'completed'})
    for item in output:
        if item['type']=='function_call' and item['name'] in (aliases or {}):
            item.update(aliases[item['name']])
    incomplete = choice['finish_reason'] == 'length'
    return {'id': 'resp_' + uuid4().hex, 'object': 'response', 'created_at': chat['created'],
        'model': chat['model'], 'status': 'incomplete' if incomplete else 'completed', 'output': output,
        'error': None, 'incomplete_details': {'reason': 'max_output_tokens'} if incomplete else None,
        'usage': {'input_tokens': chat['usage']['prompt_tokens'], 'output_tokens': chat['usage']['completion_tokens'],
                  'total_tokens': chat['usage']['total_tokens']}}


def stream_events(response):
    """仅已结算且被策略接受的回复进入事件流；不伪造首次 token 测量。"""
    sequence = 0
    def event(kind, **value):
        nonlocal sequence
        result = {'type': kind, 'sequence_number': sequence, **value}
        sequence += 1
        return result
    initial = {**response, 'status': 'in_progress', 'output': [], 'usage': None}
    yield event('response.created', response=initial)
    yield event('response.in_progress', response=initial)
    for index, item in enumerate(response['output']):
        stub = {**item, 'status': 'in_progress'}
        if item['type'] == 'message':
            stub['content'] = []
        else:
            stub['arguments'] = ''
        yield event('response.output_item.added', output_index=index, item=stub)
        if item['type'] == 'message':
            for n, part in enumerate(item['content']):
                context = {'item_id': item['id'], 'output_index': index, 'content_index': n}
                yield event('response.content_part.added', **context, part={**part, 'text': ''})
                yield event('response.output_text.delta', **context, delta=part['text'])
                yield event('response.output_text.done', **context, text=part['text'])
                yield event('response.content_part.done', **context, part=part)
        else:
            yield event('response.function_call_arguments.delta', item_id=item['id'], output_index=index,
                        delta=item['arguments'])
            yield event('response.function_call_arguments.done', item_id=item['id'], output_index=index,
                        arguments=item['arguments'])
        yield event('response.output_item.done', output_index=index, item=item)
    yield event('response.incomplete' if response['status'] == 'incomplete' else 'response.completed', response=response)
