"""Responses API 的文本协议转换；路由与预算继续由任务核心负责。"""
from __future__ import annotations


def output_token_limit(model):
    """Responses 为推理与正文共用较大额度；历史协议保持 8192 上限。"""
    if getattr(model, 'unrestricted_planning_output', False) or getattr(model, 'unrestricted_execution_output', False):
        return model.max_output_tokens or 4096
    return min(model.max_output_tokens or 4096, 128000 if model.wire_api == 'responses' else 8192)


def available_output_limit(model, input_bound):
    limit = output_token_limit(model)
    if getattr(model, 'unrestricted_execution_output', False):
        return max(0, min(limit, model.context_window - input_bound))
    return limit


def request_payload(model, messages, *, json_mode):
    options = dict(model.request_options)
    allowed = {'reasoning', 'text', 'temperature', 'top_p'}
    if set(options) - allowed:
        raise ValueError('unsupported Responses request options')
    text_options = dict(options.pop('text', {}))
    if set(text_options) - {'verbosity'}:
        raise ValueError('Responses text options cannot override output format')
    if json_mode and model.json_mode_strategy != 'prompt-only':
        text_options['format'] = {'type': 'json_object'}
    inputs = []
    for message in messages:
        if message.get('_response_items'):
            inputs.extend(message['_response_items'])
        elif message['role'] == 'tool':
            inputs.append({'type': 'function_call_output', 'call_id': message['tool_call_id'], 'output': message['content']})
        elif message.get('tool_calls'):
            if message.get('content'):
                inputs.append({'role': 'assistant', 'content': message['content']})
            inputs.extend({'type': 'function_call', 'call_id': c['id'], **c['function']} for c in message['tool_calls'])
        else:
            inputs.append(dict(message))
    return {'model': model.api_model, 'input': inputs,
            'max_output_tokens': output_token_limit(model), 'store': False,
            **options, **({'text': text_options} if text_options else {})}


def decode_response(data, *, tools=False):
    """提取 assistant 正文；拒绝、截断和失败仍保留用量以便先结算。"""
    if not isinstance(data, dict) or data.get('status') not in {
            'completed', 'incomplete', 'failed', 'cancelled', 'queued', 'in_progress'}:
        raise ValueError('invalid Responses status')
    if not isinstance(data.get('output'), list):
        raise ValueError('invalid Responses output')
    parts, refused, unsupported = [], False, False
    calls = []
    for item in data['output']:
        if not isinstance(item, dict):
            raise ValueError('invalid Responses output item')
        if item.get('type') == 'reasoning':
            continue
        if tools and item.get('type') == 'function_call':
            calls.append({'id': item.get('call_id'), 'type': 'function',
                          'function': {'name': item.get('name'), 'arguments': item.get('arguments')}})
            continue
        if item.get('type') != 'message':
            unsupported = True
            continue
        if item.get('role') != 'assistant' or not isinstance(item.get('content'), list):
            raise ValueError('invalid Responses assistant message')
        if item.get('status') not in {None, 'completed'}:
            unsupported = True
        for block in item['content']:
            if not isinstance(block, dict):
                raise ValueError('invalid Responses content block')
            if block.get('type') == 'output_text' and isinstance(block.get('text'), str):
                parts.append(block['text'])
            elif block.get('type') == 'refusal':
                refused = True
            else:
                unsupported = True
    status = data['status']
    finish = 'stop' if status == 'completed' else status
    if status == 'incomplete':
        detail = data.get('incomplete_details')
        reason = detail.get('reason') if isinstance(detail, dict) else None
        finish = {'max_output_tokens': 'length', 'content_filter': 'content_filter'}.get(reason, 'incomplete')
    if status == 'completed' and data.get('error') is not None:
        finish = 'failed'
    if finish == 'stop':
        finish = 'content_filter' if refused else 'unsupported-output' if unsupported else finish
    if finish == 'stop' and calls:
        finish = 'tool_calls'
    raw_usage = data.get('usage')
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    inputs = usage.get('input_tokens')
    outputs = usage.get('output_tokens')
    input_details = usage.get('input_tokens_details', {})
    output_details = usage.get('output_tokens_details', {})
    cached = input_details.get('cached_tokens', 0) if isinstance(input_details, dict) else None
    reasoning = output_details.get('reasoning_tokens', 0) if isinstance(output_details, dict) else None
    counts = (inputs, outputs, cached, reasoning)
    available = all(type(v) is int and v >= 0 for v in counts)
    available = available and cached <= inputs and reasoning <= outputs
    return {'content': ''.join(parts), 'finish_reason': finish, 'raw_usage': raw_usage,
            **({'tool_calls': tuple(calls), 'replay_messages': tuple(data['output'])} if tools else {}),
            'usage_available': available,
            **{key: value if type(value) is int else 0 for key, value in zip(
                ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens'), counts)}}
