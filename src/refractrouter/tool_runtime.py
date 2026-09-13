"""宿主无关的节点工具循环：原生结构调用、逐轮记账、有界执行与副作用保护。"""
from concurrent.futures import CancelledError
from copy import deepcopy
import json
from threading import Lock, RLock

TOOL_PROTOCOL = 'refractrouter-tools/v1'
MAX_TOOL_ROUNDS = 16
MAX_TOOL_CALLS = 64


def validate_schemas(raw):
    if not isinstance(raw, list) or not raw or len(raw) > 256:
        raise ValueError('invalid host tool schemas')
    names = set()
    for schema in raw:
        if (not isinstance(schema, dict) or set(schema) != {'name', 'description', 'parameters'}
                or not isinstance(schema['name'], str) or not schema['name']
                or schema['name'] in names or not isinstance(schema['description'], str)
                or not isinstance(schema['parameters'], dict)):
            raise ValueError('invalid or duplicate host tool schema')
        names.add(schema['name'])
    if len(json.dumps(raw).encode()) > 262144:
        raise ValueError('host tool schemas too large')
    return deepcopy(raw)


def tool_instruction():
    return ('可通过本次请求的原生 tools 调用宿主工具，必须遵循宿主上下文中的权限、技能与工具说明。'
            '需要外部信息时先实际调用工具取得证据，再按节点契约回答。'
            '工具结果和新增技能内容会随下一次请求返回；据此继续调用所需工具。'
            '不要把 FunctionCallBegin 等协议标记、伪造调用或待执行指令作为正文输出。'
            '工具拒绝或失败必须如实说明，不得假装成功或使用其他工具绕过拒绝。')


class ToolTurnConcluded(Exception):
    def __init__(self, content):
        self.content = content
        super().__init__('host-tool-concluded-turn')


class StdioToolRuntime:
    def __init__(self, schemas, bridge):
        self.schemas = validate_schemas(schemas)
        self.bridge = bridge
        self.lock = RLock()
        self.execution_lock = Lock()
        self.records = []
        self.dispatched = set()
        self.closed = False

    def has_executed(self, label):
        with self.lock:
            return any(r['node'] == label or r['node'].startswith(label + ':attempt-') for r in self.records)

    def snapshot(self):
        with self.lock:
            return deepcopy(self.records)

    def execute(self, call, node, cancel_event=None, before_dispatch=lambda: None):
        # 串行执行锁不阻塞账本快照；审批期间仍能保存进度和取消其他节点。
        with self.execution_lock:
            with self.lock:
                if self.closed or (cancel_event is not None and cancel_event.is_set()):
                    raise CancelledError('host-tool-execution-stopped')
                if len(self.records) >= MAX_TOOL_CALLS:
                    raise ValueError('host-tool-call-limit-exhausted')
                identity = (node, call['id'])
                if identity in self.dispatched:
                    raise ValueError('duplicate-host-tool-call')
                self.dispatched.add(identity)
                row = {'node': node, 'call': deepcopy(call), 'status': 'dispatched'}
                self.records.append(row)
            try:
                before_dispatch()  # 先持久化可能产生副作用的调用，再写入宿主通道。
            except Exception:
                with self.lock:
                    row['status'] = 'cancelled-before-dispatch'
                raise
            try:
                reply = self.bridge.exchange(TOOL_PROTOCOL, {'node': node, 'call': call})
                if reply.get('ok') is not True or not isinstance(reply.get('result'), dict):
                    raise ValueError('host-tool-bridge-failed')
                result = reply['result']
                if (not isinstance(result.get('content'), list) or type(result.get('isError')) is not bool
                        or not isinstance(result.get('additionalContexts', []), list)):
                    raise ValueError('invalid-host-tool-result')
                with self.lock:
                    row.update(status='failed' if result['isError'] else 'completed', result=deepcopy(result))
                    if result.get('concludesTurn') is True:
                        self.closed = True
                return result
            except Exception:
                with self.lock:
                    self.closed = True
                    row['status'] = 'execution-unconfirmed'
                raise


def native_calls(raw, schemas):
    names = {s['name'] for s in schemas}
    if not isinstance(raw, (tuple, list)) or not 1 <= len(raw) <= 16:
        raise ValueError('invalid-native-tool-calls')
    ids = set()
    for call in raw:
        if (not isinstance(call, dict) or call.get('type') != 'function'
                or not isinstance(call.get('id'), str) or not call['id'] or call['id'] in ids
                or not isinstance(call.get('function'), dict)):
            raise ValueError('invalid-native-tool-call')
        function = call['function']
        if function.get('name') not in names or not isinstance(function.get('arguments'), str):
            raise ValueError('unavailable-native-tool-call')
        try:
            args = json.loads(function['arguments'])
        except ValueError:
            raise ValueError('invalid-native-tool-arguments') from None
        if not isinstance(args, dict):
            raise ValueError('native-tool-arguments-must-be-object')
        ids.add(call['id'])
    return deepcopy(list(raw))


def run_tool_node(runtime, reservation, budget, invoke, persist, *, cancel_event=None):
    messages = deepcopy(reservation.messages)
    initial = reservation
    for turn in range(MAX_TOOL_ROUNDS + 1):
        response, error, _, _ = invoke(reservation)
        if error is not None:
            raise error
        persist()  # 每轮先结算模型用量，再产生宿主副作用。
        calls = getattr(response, 'tool_calls', ())
        if not calls:
            if response.content.strip().startswith('<|FunctionCallBegin|>'):
                raise ValueError('模型输出了工具协议文本，未返回原生 tool_calls；未执行任何文本指令')
            return response
        calls = native_calls(calls, runtime.schemas)
        if turn >= MAX_TOOL_ROUNDS:
            raise ValueError('node-tool-round-limit-exhausted')
        messages.append({'role': 'assistant', 'content': response.content or None, 'tool_calls': calls,
                         **({'reasoning_content': response.replay_messages[0]['reasoning_content']}
                            if response.replay_messages and 'reasoning_content' in response.replay_messages[0] else {})})
        if initial.model.wire_api == 'responses':
            messages[-1]['_response_items'] = list(response.replay_messages)
        elif initial.model.wire_api == 'dsh-llm' and response.replay_state is not None:
            messages[-1]['_dsh_replay_state'] = response.replay_state
        additional = []
        for call in calls:
            if budget.stopped or (cancel_event is not None and cancel_event.is_set()):
                raise CancelledError('task-cancelled-before-tool')
            def before_tool():
                if budget.stopped or (cancel_event is not None and cancel_event.is_set()):
                    raise CancelledError('task-cancelled-before-tool')
                persist()
            result = runtime.execute(call, initial.row['label'], cancel_event, before_tool)
            persist()
            if result.get('concludesTurn'):
                budget.stop()
                text = '\n'.join(b.get('text', '') for b in result['content'] if b.get('type') == 'text')
                raise ToolTurnConcluded(text or '宿主工具已结束本轮。')
            messages.append({'role': 'tool', 'tool_call_id': call['id'],
                             'content': json.dumps({'isError': result['isError'], 'content': result['content']}, ensure_ascii=False)})
            for context in result.get('additionalContexts', []):
                # 保留技能原文与非文本引用，作为不可信宿主上下文传递。
                additional.append({'role': 'user', 'content': json.dumps(context, ensure_ascii=False)})
        messages.extend(additional)
        reservation = budget.reserve(initial.model, deepcopy(messages),
            label=initial.row['label'] + f':tool-round-{turn+1}', tools=runtime.schemas,
            json_mode=initial.json_mode, category_limit=initial.row.get('category_limit'))
    raise AssertionError('unreachable')
