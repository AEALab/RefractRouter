"""标准模型请求的形状与全执行候选准入；不派发模型或改变路由。"""
import json

from .task_budget import request_input_bound

REQUEST_FEATURES = ("jsonObject", "jsonSchema", "strictTools", "toolChoice", "parallelToolCalls", "promptCacheKey")
REQUEST_OPTIONS = {'temperature', 'top_p', 'stop', 'tool_choice', 'parallel_tool_calls',
                   'response_format', 'prompt_cache_key', 'seed', 'frequency_penalty', 'presence_penalty'}


def execution_models(config, strategy):
    roles = config['roles']
    if strategy == 'static':
        ids = [roles.get('efficient')]
        if config['parameters']['staticMode'] == 'random':
            ids.append(roles.get('capable'))
    elif strategy == 'task':
        ids = [*config['task']['pool'], config['task']['fallback']]
    elif strategy == 'composite':
        route = config['composite']
        ids = ([*route['task']['pool'], route['takeover']] if route['mode'] == 'configured'
               else [roles.get('efficient'), roles.get('capable')])
    elif strategy == 'escalation':
        ids = [config['escalation']['initial'], config['escalation']['takeover']]
    elif strategy == 'advisor':
        ids = [config['advisor'].get('executor', roles.get('efficient'))]
    else:
        ids = [roles.get('efficient'), roles.get('capable')]
    return [config['models'][key] for key in dict.fromkeys(ids) if key in config['models']]


def request_features(options, schemas):
    if not isinstance(options, dict) or set(options) - REQUEST_OPTIONS:
        raise ValueError('执行请求参数包含未验收字段')
    try:
        json.dumps({'options': options, 'schemas': schemas}, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError('请求参数须为有限原生JSON') from exc
    required = set()
    for key, low, high in (('temperature', 0, 2), ('top_p', 0, 1),
                           ('frequency_penalty', -2, 2), ('presence_penalty', -2, 2)):
        if key in options and (type(options[key]) not in (int, float) or not low <= options[key] <= high):
            raise ValueError(key + ' 参数无效')
    if 'seed' in options and (type(options['seed']) is not int or not -(2**63) <= options['seed'] < 2**63):
        raise ValueError('seed 参数无效')
    if 'stop' in options:
        stops = [options['stop']] if isinstance(options['stop'], str) else options['stop']
        if not isinstance(stops, list) or not 1 <= len(stops) <= 4 or any(not isinstance(s, str) or not s for s in stops):
            raise ValueError('stop 只支持非空字符串或至多四项字符串')
    if any(not isinstance(schema, dict) or not isinstance(schema.get('name'), str) or not schema['name'] for schema in schemas):
        raise ValueError('工具定义缺少名称')
    names = {schema['name'] for schema in schemas}
    for schema in schemas:
        if 'strict' in schema and type(schema['strict']) is not bool:
            raise ValueError('工具 strict 必须是布尔值')
        if schema.get('strict') is True:
            required.add('strictTools')
    if 'parallel_tool_calls' in options:
        if type(options['parallel_tool_calls']) is not bool:
            raise ValueError('parallel_tool_calls 必须是布尔值')
        required.add('parallelToolCalls')
    if 'tool_choice' in options:
        choice = options['tool_choice']
        if isinstance(choice, dict):
            function = choice.get('function')
            if (set(choice) != {'type', 'function'} or choice['type'] != 'function'
                    or not isinstance(function, dict) or set(function) != {'name'} or not isinstance(function['name'], str)
                    or function['name'] not in names):
                raise ValueError('tool_choice 必须引用当前工具')
        elif not isinstance(choice, str) or choice not in ('auto', 'none', 'required'):
            raise ValueError('tool_choice 参数无效')
        if not names and choice != 'none':
            raise ValueError('tool_choice 需要工具定义')
        required.add('toolChoice')
    if 'prompt_cache_key' in options:
        required.add('promptCacheKey')
    if 'response_format' in options:
        fmt = options['response_format']
        if not isinstance(fmt, dict) or fmt.get('type') not in ('text', 'json_object', 'json_schema'):
            raise ValueError('response_format 仅支持文本或既有JSON格式')
        if fmt['type'] == 'json_schema':
            schema = fmt.get('json_schema')
            if (set(fmt) != {'type', 'json_schema'} or not isinstance(schema, dict)
                    or set(schema) - {'name', 'description', 'schema', 'strict'}
                    or not isinstance(schema.get('name'), str) or not schema['name']
                    or not isinstance(schema.get('schema'), dict)
                    or ('strict' in schema and type(schema['strict']) is not bool)):
                raise ValueError('json_schema 合同无效')
            required.add('jsonSchema')
        elif set(fmt) != {'type'}:
            raise ValueError('response_format 包含未知字段')
        elif fmt['type'] == 'json_object':
            required.add('jsonObject')
    return required


def admit_all(config, strategy, messages, schemas, options, cap, admit):
    required = request_features(options, schemas)
    models = execution_models(config, strategy)
    if not models:
        raise ValueError('当前策略没有执行候选')
    bound = request_input_bound(messages, schemas, options)
    history_uses_tools = any(isinstance(block, dict) and block.get('type') in ('tool-call', 'tool-result')
        for message in messages for block in (message.get('content') if isinstance(message.get('content'), list) else []))
    for model in models:
        features = (model.capabilities or {}).get('requestFeatures', {})
        if (schemas or history_uses_tools) and (model.capabilities or {}).get('toolCalling') != 'verified':
            raise ValueError(f'候选 {model.model_id} 的 function 能力未验收')
        for feature in sorted(required):
            if features.get(feature) != 'verified':
                raise ValueError(f'候选 {model.model_id} 的 {feature} 能力未验收')
        output = model.max_output_tokens if cap is None else cap
        if output > model.max_output_tokens or bound + output > model.context_window:
            raise ValueError(f'候选 {model.model_id} 的请求容量不足')
        admit({'config': config}, model_id=model.model_id, role=None, messages=messages, tools=schemas, execution_options=options)
    return {'schemaVersion': 'all-executor-protocol-admission-v1', 'candidateCount': len(models),
            'requiredFeatures': sorted(required), 'scope': 'configured-capability-evidence', 'modelCalls': 0}
