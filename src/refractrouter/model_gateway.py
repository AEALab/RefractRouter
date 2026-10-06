"""独立模型路由 HTTP 接口：只调用模型，工具与 Agent 生命周期由客户端拥有。"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version
import json
import os
import select
import signal
import socket
from pathlib import Path
from threading import RLock
import time
from urllib.parse import urlsplit
from uuid import uuid4

from .host_evidence import EVIDENCE_VERSION, validate_evidence
from . import gateway_responses
from .gateway_streaming import stream_chat, WireStream
from .openai_compatible import OpenAICompatibleClient, UrllibTransport
from .planning_config import compile_config, preview
from .planning_runtime import PlanningRuntime

ROUTES = ("static", "stage", "task", "composite", "escalation", "advisor")
MAX_BODY = 8 * 1024 * 1024
GATEWAY_CONFIG_VERSION = "refractrouter-gateway-config-v1"
GATEWAY_PROTOCOL_VERSION = "refractrouter-model-gateway-v1"
EXECUTION_OPTIONS = {"temperature", "top_p", "stop", "tool_choice", "parallel_tool_calls",
                     "response_format", "prompt_cache_key", "seed", "frequency_penalty", "presence_penalty"}


def package_version():
    try:
        return version("refractrouter")
    except PackageNotFoundError:
        return "development"


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True).encode()).hexdigest()


def chat_messages(raw):
    """公开文本/function 消息转成核心内容块；不注入 system prompt 或工具。"""
    if not isinstance(raw, list) or not raw:
        raise ValueError("messages 必须是非空列表")
    result = []
    for row in raw:
        if not isinstance(row, dict) or set(row) - {"role", "content", "name", "tool_calls", "tool_call_id"}:
            raise ValueError("当前接口仅支持标准文本与 function 消息；不支持私有 replay 字段")
        role = row.get("role")
        if role not in ("system", "developer", "user", "assistant", "tool"):
            raise ValueError("未知消息角色")
        content = row.get("content")
        if isinstance(content, str):
            blocks = [{"type": "text", "text": content}]
        elif content is None and role == "assistant":
            blocks = []
        elif isinstance(content, list) and all(isinstance(b, dict) and set(b) == {"type", "text"}
                and b["type"] == "text" and isinstance(b["text"], str) for b in content):
            blocks = deepcopy(content)
        else:
            raise ValueError("当前独立接口仅验收文本与 function 工具；媒体内容尚未接通")
        if role == "tool":
            if not isinstance(row.get("tool_call_id"), str) or not row["tool_call_id"]:
                raise ValueError("工具结果缺少 tool_call_id")
            blocks = [{"type": "tool-result", "toolCallId": row["tool_call_id"], "content": blocks}]
        calls = row.get("tool_calls", [])
        if not isinstance(calls, list) or (calls and role != "assistant"):
            raise ValueError("tool_calls 只能来自 assistant")
        for call in calls:
            if not isinstance(call, dict) or set(call) != {"id", "type", "function"} or call["type"] != "function":
                raise ValueError("无效 function 调用")
            fn = call["function"]
            if not isinstance(fn, dict) or set(fn) != {"name", "arguments"} or not all(
                    isinstance(v, str) and v for v in (call["id"], fn["name"], fn["arguments"])):
                raise ValueError("无效 function 参数")
            blocks.append({"type": "tool-call", "id": call["id"], **fn})
        result.append({"role": "user" if role == "tool" else "system" if role == "developer" else role,
                       "content": blocks, "wireRole": role,
                       **({"wireName": row["name"]} if "name" in row else {})})
    return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('JSON 对象含重复键')
        result[key] = value
    return result


def canonical_message(message):
    value = deepcopy(message)
    value['content'] = [b for b in value['content'] if not (b['type']=='text' and b['text']=='')]
    for block in value['content']:
        if block['type']=='tool-call':
            try:
                parsed=json.loads(block['arguments'], object_pairs_hook=unique_object)
                block['arguments']=json.dumps(parsed,ensure_ascii=False,sort_keys=True,allow_nan=False)
            except (TypeError,ValueError): pass
    return value


def history_digest(messages):
    return digest([canonical_message(m) for m in chat_messages(messages)])


def wire_messages(messages):
    result = []
    for row in messages:
        if isinstance(row["content"], str):
            result.append({"role": row["role"], "content": row["content"]})
            continue
        blocks = row["content"]
        tool_results = [b for b in blocks if b["type"] == "tool-result"]
        if tool_results:
            if len(tool_results) != len(blocks):
                raise ValueError("工具结果不能与其他内容块混排")
            for b in tool_results:
                result.append({"role": "tool", "tool_call_id": b["toolCallId"],
                               "content": "\n".join(c["text"] for c in b["content"])})
            continue
        if any(b["type"] not in ("text", "tool-call") for b in blocks):
            raise ValueError("未验收的模型内容块")
        text = "\n".join(b["text"] for b in blocks if b["type"] == "text")
        calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"],
                  "arguments": b["arguments"]}} for b in blocks if b["type"] == "tool-call"]
        # 私有推理仅来自本服务记录的真实来源，且核心准入没有在换模时移除 replay。
        replay = (row.get("source", {}).get("replayState") or {}).get("response") or {}
        result.append({"role": row.get("wireRole", row["role"]), "content": text or (None if calls else ""),
                       **({"name": row["wireName"]} if "wireName" in row else {}),
                       **({"reasoning_content": replay["reasoning_content"]} if replay.get("reasoning_content") else {}),
                       **({"tool_calls": calls} if calls else {})})
    return result


def tool_schemas(raw):
    if not isinstance(raw, list) or len(raw) > 256:
        raise ValueError("无效工具列表")
    result, names = [], set()
    for entry in raw:
        if not isinstance(entry, dict) or set(entry) != {"type", "function"} or entry["type"] != "function":
            raise ValueError("只支持客户端拥有的 function 工具，不执行托管工具")
        fn = entry["function"]
        if not isinstance(fn, dict) or set(fn) - {"name", "description", "parameters", "strict"}:
            raise ValueError("未知 function schema 字段")
        if not isinstance(fn.get("name"), str) or not fn["name"] or fn["name"] in names:
            raise ValueError("无效或重复工具名称")
        if not isinstance(fn.get("parameters"), dict):
            raise ValueError("工具需要 parameters schema")
        names.add(fn["name"])
        result.append(deepcopy(fn))
    return result


def ordinary_evidence(messages):
    """纯 API 文本结果没有可信退出码；保持无法分类，不猜测失败或成功。"""
    calls, result = {}, []
    for row in messages:
        for block in row["content"]:
            if block["type"] == "tool-call":
                calls[block["id"]] = block
            elif block["type"] == "tool-result":
                cid = block["toolCallId"]
                call = calls.get(cid, {})
                result.append({"id": cid, "callId": cid, "tool": call.get("name", "unknown"),
                    "status": "unclassified", "kind": "unknown",
                    "fingerprint": digest([call.get("name"), call.get("arguments")])})
    return validate_evidence(result)


def bound_tool_evidence(messages, supplied, known=None):
    """只接受与当前已完成工具调用配对的宿主事实。"""
    ordinary = ordinary_evidence(messages)
    known = known or {}
    if supplied is None:
        supplied = {'version': EVIDENCE_VERSION, 'events': []}
    if (not isinstance(supplied, dict) or set(supplied) != {'version', 'events'}
            or supplied['version'] != EVIDENCE_VERSION):
        raise ValueError('工具证据协议版本或结构无效')
    facts = validate_evidence(supplied['events'])
    expected = {event['callId']: event for event in ordinary}
    for call_id, fact in known.items():
        original = expected.get(call_id)
        if original is not None and (fact['id'] != call_id or fact['tool'] != original['tool']):
            raise ValueError('已保存的工具事实与当前历史不匹配')
    overrides = {}
    for fact in facts:
        if set(fact) != {'id', 'callId', 'tool', 'kind', 'status', 'fingerprint'}:
            raise ValueError('宿主工具证据包含未知字段')
        original = expected.get(fact['callId'])
        if (original is None or fact['id'] != fact['callId']
                or fact['tool'] != original['tool'] or fact['callId'] in overrides):
            raise ValueError('宿主工具证据与当前历史的调用或结果不匹配')
        if fact['callId'] in known and known[fact['callId']] != fact:
            raise ValueError('同一工具调用的宿主事实发生矛盾变化')
        overrides[fact['callId']] = fact
    return [overrides.get(event['callId'], known.get(event['callId'], event))
            for event in ordinary]


def merge_host_evidence(messages, supplied, inbox):
    """合并客户端随请求提供的证据与独立工具钩子提交的事实。"""
    calls = {event['callId'] for event in ordinary_evidence(messages)}
    pending = [fact for call_id, fact in inbox.items() if call_id in calls]
    if not pending:
        return supplied
    if supplied is None:
        return {'version': EVIDENCE_VERSION, 'events': pending}
    if (not isinstance(supplied, dict) or set(supplied) != {'version', 'events'}
            or supplied.get('version') != EVIDENCE_VERSION
            or not isinstance(supplied['events'], list)):
        raise ValueError('工具证据协议版本或结构无效')
    events = list(supplied.get('events', []))
    by_call = {event.get('callId'): event for event in events if isinstance(event, dict)}
    for fact in pending:
        previous = by_call.get(fact['callId'])
        if previous is not None and previous != fact:
            raise ValueError('客户端与工具钩子的事实矛盾')
        if previous is None:
            events.append(fact)
    return {'version': EVIDENCE_VERSION, 'events': events}


class HttpModelCaller:
    """一次派发、零重试；与 DSH 服务和 Agent 工具执行完全独立。"""
    def __init__(self, providers, transport=None):
        self.providers = deepcopy(providers)
        self.transport = transport or UrllibTransport()
        self.parser = OpenAICompatibleClient(max_retries=0)

    def _request(self, action, options):
        target = action["model"]
        provider = self.providers[target["provider"]]
        token = os.environ.get(provider.get("apiKeyEnv", ""), "")
        if provider.get("apiKeyEnv") and not token:
            raise ValueError("上游模型凭证未配置")
        payload = {"model": target["model"], "messages": wire_messages(action["messages"]),
            provider.get("tokenLimitParameter", "max_tokens"): target["maxTokens"], "stream": False}
        payload.update(provider.get("requestOptions", {}))
        if action["purpose"] in ("execute", "takeover"):
            payload.update(options)
        if target.get("reasoning_effort"):
            payload["reasoning_effort"] = target["reasoning_effort"]
        if action["tools"]:
            payload["tools"] = [{"type": "function", "function": tool} for tool in action["tools"]]
        timeout = provider.get("timeoutSeconds", 120)
        if action.get("remainingMs") is not None:
            timeout = min(timeout, action["remainingMs"] / 1000)
        if action.get("timeoutMs") is not None:
            timeout = min(timeout, action["timeoutMs"] / 1000)
        if timeout <= 0:
            raise ValueError("任务期限已耗尽")
        return (provider["baseURL"].rstrip('/') + '/chat/completions',
            {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})},
            payload, timeout)

    def stream(self, action, options, on_text):
        return stream_chat(*self._request(action, options), on_text)

    def __call__(self, action, options):
        url, headers, payload, timeout = self._request(action, options)
        started = time.perf_counter()
        response = self.transport.post(url, headers, encode(payload), timeout)
        if not 200 <= response.status < 300:
            raise RuntimeError(f"上游模型 HTTP {response.status}；未自动重试")
        if len(response.body) > MAX_BODY:
            raise ValueError("上游回复超过 8 MiB 缓冲上限")
        return self.parser._parse_response(response, 1, started)


class ModelGateway:
    def __init__(self, config, runs_dir, caller=None):
        self.config = deepcopy(config)
        self.planning = self.config["planningRouting"]
        compiled = compile_config(self.planning)
        self.runtime = PlanningRuntime(runs_dir)
        self.caller = caller or HttpModelCaller(config["providers"])
        self.lock = RLock()
        self.path = Path(runs_dir) / 'gateway-continuations.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"tools": {}}
        if caller is None:
            self._check_providers(compiled)

    def service_info(self):
        models = self.models()["data"]
        return {
            "status": "ready",
            "service": GATEWAY_PROTOCOL_VERSION,
            "version": package_version(),
            "configDigest": digest(self.config),
            "strategies": [row["id"] for row in models],
            "modelCalls": 0,
            "toolExecution": False,
        }

    def _check_providers(self, compiled):
        for model in compiled["models"].values():
            p = self.config.get("providers", {}).get(model.provider)
            if not isinstance(p, dict) or set(p) - {"baseURL", "apiKeyEnv", "timeoutSeconds", "tokenLimitParameter", "requestOptions"}:
                raise ValueError("独立网关缺少 provider 或包含未知字段")
            url = urlsplit(p.get("baseURL", ""))
            if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError("provider baseURL 无效")
            if p.get("apiKeyEnv") and not os.environ.get(p["apiKeyEnv"]):
                raise ValueError("上游模型凭证未配置")
            if model.billing_mode == 'subscription':
                expected = (model.reference_pricing or {}).get('executionEndpoint', '')
                if expected.rstrip('/') != p['baseURL'].rstrip('/'):
                    raise ValueError("订阅参考价格与实际调用端点不一致")
            if model.billing_unit == 'AFP' and url.path.rstrip('/') != '/api/plan/v3':
                raise ValueError("AFP 路线必须使用已冻结的 /api/plan/v3 接口")
            if p.get("tokenLimitParameter", "max_tokens") not in ('max_tokens', 'max_completion_tokens'):
                raise ValueError("未知输出上限参数")
            if set(p.get("requestOptions", {})) - {"thinking", "reasoning_effort", "temperature", "top_p"}:
                raise ValueError("provider 参数不能覆盖消息、工具、模型或输出上限")
            if type(p.get("timeoutSeconds", 120)) not in (int, float) or not 0 < p.get("timeoutSeconds", 120) <= 600:
                raise ValueError("provider 超时必须在 0—600 秒之间")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def capabilities(self, strategy):
        """保守公开执行路线的交集；判别模型不影响主模型参数声明。"""
        c = compile_config(self.planning)
        if strategy == 'static':
            ids = [c['roles'].get('efficient')]
            if c['parameters']['staticMode'] == 'random':
                ids.append(c['roles'].get('capable'))
        elif strategy == 'task':
            ids = [*c['task']['pool'], c['task']['fallback']]
        elif strategy == 'composite':
            composite = c['composite']
            ids = ([*composite['task']['pool'], composite['takeover']]
                   if composite['mode'] == 'configured'
                   else [c['roles'].get('efficient'), c['roles'].get('capable')])
        elif strategy == 'escalation':
            ids = [c['escalation']['initial'], c['escalation']['takeover']]
        elif strategy == 'advisor':
            ids = [c['advisor'].get('executor', c['roles'].get('efficient'))]
        else:
            ids = [c['roles'].get('efficient'), c['roles'].get('capable')]
        models = [c['models'][key] for key in dict.fromkeys(ids) if key in c['models']]
        efforts = {m.request_options.get('reasoning_effort', self.config.get('providers', {})
            .get(m.provider, {}).get('requestOptions', {}).get('reasoning_effort')) for m in models}
        common = next(iter(efforts)) if len(efforts) == 1 else None
        return {'schemaVersion': 'refract-model-capabilities/1',
            'inputModalities': ['text'], 'outputModalities': ['text'], 'toolTypes': ['function'],
            'historyMode': 'full', 'reasoningPolicy': 'frozen-role-assertion',
            'acceptedReasoningEfforts': [common] if common else [],
            'contextWindow': min((m.context_window for m in models), default=0),
            'maxOutputTokens': min((m.max_output_tokens for m in models), default=0),
            'streaming': True, 'toolExecution': 'client'}

    def models(self):
        available = {row['id'] for row in preview(self.planning)['strategies'] if row['available']}
        return {"object": "list", "data": [{"id": "refract/" + strategy, "object": "model",
            "created": 0, "owned_by": "refractrouter", "refract": self.capabilities(strategy)} for strategy in ROUTES if strategy in available]}

    def _identity(self, request, scope):
        metadata = request.get('metadata') or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata 必须是对象")
        explicit = [metadata.get('refract_session'), metadata.get('refract_task')]
        if any(v is not None for v in explicit):
            if not all(isinstance(v, str) and 0 < len(v) <= 256 for v in explicit):
                raise ValueError("显式身份必须同时提供 refract_session 与 refract_task")
            return {"session": scope + ':' + explicit[0], "agent": "api", "turn": explicit[1]}
        messages = request['messages']
        # 标准 function 工具续接可用已交付的 call ID 对应任务；新 user 消息建立新任务。
        tail = []
        for row in reversed(messages):
            if row['role'] != 'tool':
                break
            tail.append(row['tool_call_id'])
        if tail:
            known = [self.state['tools'].get(scope + ':' + cid) for cid in tail]
            if any(known):
                if not all(known) or len({digest(v['identity']) for v in known}) != 1:
                    raise ValueError("工具结果来自不同任务或无法核对的调用")
                entry = known[0]
                # 检查已接受的历史，防止同一个 call ID 被另一段会话冒用。
                prefix = messages[:-len(tail)]
                if history_digest(prefix) != entry['prefix']:
                    raise ValueError("工具续接历史已改变；请提供显式任务身份并核对上下文")
                return entry['identity']
        return {"session": scope + ':' + uuid4().hex, "agent": "api", "turn": 1}

    def record_host_evidence(self, submitted, *, scope='default'):
        """保存已交付工具调用的宿主事实；工具仍由客户端执行。"""
        if (not isinstance(submitted, dict) or set(submitted) !=
                {'version', 'callId', 'status', 'kind', 'fingerprint'}
                or submitted['version'] != EVIDENCE_VERSION):
            raise ValueError('宿主工具事实协议版本或结构无效')
        call_id = submitted['callId']
        if not isinstance(call_id, str) or not call_id or len(call_id) > 256:
            raise ValueError('宿主工具事实缺少调用 ID')
        key = scope + ':' + call_id
        with self.lock:
            issued = self.state['tools'].get(key)
            if not issued or not issued.get('tool'):
                raise ValueError('工具调用 ID 未由当前 Router 交付')
            fact = {"id": call_id, "callId": call_id, "tool": issued['tool'],
                    "kind": submitted['kind'], "status": submitted['status'],
                    "fingerprint": submitted['fingerprint']}
            validate_evidence([fact])
            inbox = self.state.setdefault('hostEvidenceInbox', {})
            previous = inbox.get(key)
            if previous is not None and previous != fact:
                raise ValueError('同一工具调用的宿主事实发生矛盾变化')
            if previous is None:
                inbox[key] = fact
                try:
                    self.save()
                except Exception:
                    del inbox[key]
                    raise
        return {'accepted': True, 'callId': call_id}

    def complete(self, request, *, scope='default', cancelled=lambda: False, on_text=None):
        started = time.monotonic()
        allowed = {'model', 'messages', 'tools', 'stream', 'stream_options', 'max_tokens', 'max_completion_tokens',
                   'metadata', 'n', 'reasoning_effort', *EXECUTION_OPTIONS}
        if not isinstance(request, dict) or set(request) - allowed:
            raise ValueError("请求包含当前网关未接通的参数")
        strategy = str(request.get('model', '')).removeprefix('refract/')
        if strategy not in ROUTES or request.get('n', 1) != 1:
            raise ValueError("请选择 refract/static、stage、task、composite、escalation 或 advisor；只支持 n=1")
        if 'reasoning_effort' in request:
            effort = request['reasoning_effort']
            # Hermes 等客户端用 none 表示不提出档位要求；真实模型仍按冻结角色配置执行。
            if (not isinstance(effort, str) or
                    (effort != 'none' and effort not in self.capabilities(strategy)['acceptedReasoningEfforts'])):
                raise ValueError('reasoning_effort 与冻结执行角色不一致；请省略该参数或使用模型目录声明的值')
        if not isinstance(request.get('stream', False), bool):
            raise ValueError("stream 必须是布尔值")
        if request.get('stream_options') not in (None, {}, {'include_usage': True}, {'include_usage': False}):
            raise ValueError("未知 stream_options")
        if 'prompt_cache_key' in request and (not isinstance(request['prompt_cache_key'],str) or len(request['prompt_cache_key'])>512):
            raise ValueError('prompt_cache_key 必须是不超过 512 字符的字符串')
        cap = request.get('max_completion_tokens', request.get('max_tokens'))
        if cap is not None and (type(cap) is not int or cap < 1):
            raise ValueError("输出上限必须是正整数")
        if 'max_completion_tokens' in request and 'max_tokens' in request:
            raise ValueError("不能同时指定两个输出上限")
        messages = chat_messages(request.get('messages'))
        schemas = tool_schemas(request.get('tools', []))
        options = {key: deepcopy(request[key]) for key in EXECUTION_OPTIONS if key in request}
        with self.lock:
            identity = self._identity(request, scope)
            for message in messages:
                calls = [b for b in message["content"] if b["type"] == "tool-call"]
                entries = [self.state["tools"].get(scope + ':' + b["id"]) for b in calls]
                if any(e and e.get("source") and e.get("assistantDigest") != digest(canonical_message(message)) for e in entries):
                    raise ValueError("工具调用的原始模型回复已改变，不能附加私有 replay")
                sources = [e.get("source") for e in entries if e and e.get("source")]
                if sources and len(sources) == len(calls) and all(s == sources[0] for s in sources):
                    message["source"] = deepcopy(sources[0])
            begun = self.runtime.handle({'op': 'begin', 'identity': identity, 'config': self.planning, 'strategy': strategy})
            run_id = begun['runId']
            if begun['strategy'] != strategy:
                raise ValueError('当前任务的路由策略已冻结；新任务才能切换策略')
            all_facts = self.state.setdefault('toolEvidence', {})
            scope_facts = all_facts.get(run_id, {})
            inbox = {cid: fact for key, fact in self.state.get('hostEvidenceInbox', {}).items()
                     if key.startswith(scope + ':') for cid in [key[len(scope) + 1:]]}
            submitted = merge_host_evidence(messages,
                (request.get('metadata') or {}).get('refract_tool_evidence'), inbox)
            evidence = bound_tool_evidence(messages, submitted, scope_facts)
            new_facts = dict(scope_facts)
            for fact in evidence:
                if fact['status'] != 'unclassified' and fact['callId'] not in scope_facts:
                    new_facts[fact['callId']] = fact
            if new_facts != scope_facts:
                all_facts[run_id] = new_facts
                try:
                    self.save()
                except Exception:
                    if run_id in all_facts:
                        if scope_facts:
                            all_facts[run_id] = scope_facts
                        else:
                            del all_facts[run_id]
                    raise
            action = self.runtime.handle({'op': 'step', 'runId': run_id, 'messages': messages,
                'tools': schemas, 'toolEvidence': evidence,
                **({'maxTokens': cap} if cap is not None else {})})
        responses, targets, total_in, total_out = {}, {}, 0, 0
        meta = {'id':'chatcmpl-' + uuid4().hex, 'created':int(time.time()), 'model':request['model']}
        try:
            while action['action'] in ('call', 'wait'):
                if cancelled():
                    raise ConnectionError("客户端已取消")
                if action['action'] == 'wait':
                    time.sleep(.02)
                    action = self.runtime.handle({'op': 'local-judge-poll', 'runId': run_id, 'jobId': action['jobId']})
                    continue
                if on_text is not None and not action['buffered'] and hasattr(self.caller, 'stream'):
                    def deliver(text):
                        if cancelled(): return
                        run = self.runtime.runs[run_id]
                        row = run['flow']['pending'][1].row
                        if 'userFirstTextMs' not in row:
                            row['userFirstTextMs'] = round((time.monotonic() - started) * 1000)
                            row['deliveryMode'] = 'live-text'
                            self.runtime.persist(run)
                        row['releasedTextBytes'] = row.get('releasedTextBytes', 0) + len(text.encode())
                        on_text(meta, text)
                    response = self.caller.stream(action, options, deliver)
                else:
                    response = self.caller(action, options)
                responses[action['callId']] = response
                targets[action['callId']] = deepcopy(action['model'])
                total_in += response.input_tokens
                total_out += response.output_tokens
                # 先结算已派发调用，取消不释放已花费或未知用量。
                if cancelled():
                    self.runtime.handle({'op': 'cancel', 'runId': run_id})
                action = self.runtime.handle({'op': 'complete', 'runId': run_id, 'callId': action['callId'],
                    'response': {'content': response.content, 'inputTokens': response.input_tokens,
                        'outputTokens': response.output_tokens, 'cachedInputTokens': response.cached_input_tokens,
                        'reasoningTokens': response.reasoning_tokens, 'usageAvailable': response.usage_available,
                        'finishReason': response.finish_reason, 'toolCalls': list(response.tool_calls),
                        'latencyMs': response.latency_ms, 'requestId': response.request_id, 'ttftMs': response.ttft_ms}})
            if action['action'] != 'release':
                raise RuntimeError("模型调用已停止")
            selected = responses[action['callId']]
            message = {'role': 'assistant', 'content': selected.content or (None if selected.tool_calls else '')}
            if selected.tool_calls:
                message['tool_calls'] = list(selected.tool_calls)
            result = {**meta, 'object': 'chat.completion', 'choices': [{'index': 0, 'message': message,
                    'finish_reason': selected.finish_reason}],
                'usage': {'prompt_tokens': total_in, 'completion_tokens': total_out,
                          'total_tokens': total_in + total_out}}
            with self.lock:
                prefix = history_digest(request['messages'] + [message])
                for call in selected.tool_calls:
                    key = scope + ':' + call['id']
                    if key in self.state['tools']:
                        raise ValueError("提供方重复使用工具调用 ID；停止续接")
                    target = targets[action['callId']]
                    private = (selected.replay_messages[0].get('reasoning_content')
                               if selected.replay_messages else None)
                    source = {'kind': 'model', 'provider': target['provider'], 'model': target['model']}
                    if private:
                        source['replayState'] = {'response': {'reasoning_content': private}}
                    self.state['tools'][key] = {'identity': identity, 'prefix': prefix, 'source': source,
                                                 'tool': call['function']['name'],
                                                 'assistantDigest': digest(canonical_message(chat_messages([message])[0]))}
                self.save()
                if not selected.tool_calls and not (request.get('metadata') or {}).get('refract_task'):
                    self.runtime.handle({'op': 'end', 'runId': run_id})
            return result
        except Exception:
            self.runtime.handle({'op': 'cancel', 'runId': run_id})
            raise

    def close(self):
        self.runtime.local_service.close()


def chat_stream(result, include_usage=False):
    base = {key: result[key] for key in ('id', 'created', 'model')}
    base['object'] = 'chat.completion.chunk'
    choice = result['choices'][0]
    yield {**base, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]}
    message = choice['message']
    delta = {key: value for key, value in message.items() if key != 'role' and value is not None}
    if 'tool_calls' in delta:
        delta['tool_calls'] = [{'index': index, **call} for index, call in enumerate(delta['tool_calls'])]
    yield {**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]}
    yield {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': choice['finish_reason']}]}
    if include_usage:
        yield {**base, 'choices': [], 'usage': result['usage']}


def create_server(gateway, host='127.0.0.1', port=8088, token=None):
    if host not in ('127.0.0.1', 'localhost', '::1') and not token:
        raise ValueError("对外监听必须配置 authTokenEnv")

    class Handler(BaseHTTPRequestHandler):
        server_version = "RefractRouter"
        sys_version = ""

        def log_message(self, *args):
            pass  # 不记录凭证或用户请求正文。

        def authorized(self):
            return not token or hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

        def send_json(self, status, body):
            data = encode(body)
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-RefractRouter-Protocol', GATEWAY_PROTOCOL_VERSION)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/healthz':
                self.send_json(200, {'status': 'ok', 'service': GATEWAY_PROTOCOL_VERSION})
            elif not self.authorized():
                self.send_json(401, {'error': {'message': '认证失败', 'type': 'authentication_error'}})
            elif path == '/v1/models':
                self.send_json(200, gateway.models())
            elif path == '/readyz':
                self.send_json(200, gateway.service_info())
            elif path == '/health':
                self.send_json(200, {'status': 'ok', 'service': GATEWAY_PROTOCOL_VERSION})
            else:
                self.send_json(404, {'error': {'message': '未知接口'}})

        def do_POST(self):
            if not self.authorized():
                self.send_json(401, {'error': {'message': '认证失败', 'type': 'authentication_error'}})
                return
            if self.path not in ('/v1/chat/completions', '/v1/responses', '/v1/tool-evidence'):
                self.send_json(404, {'error': {'message': '未知接口'}})
                return
            media_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if media_type != 'application/json':
                self.send_json(415, {'error': {'message': '请求必须使用 application/json',
                    'type': 'invalid_request_error'}})
                return
            wire, sent, lost = None, False, False
            def send(data):
                nonlocal sent, lost
                if lost: return
                try:
                    if not sent:
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Cache-Control', 'no-cache')
                        self.send_header('X-RefractRouter-Protocol', GATEWAY_PROTOCOL_VERSION)
                        self.end_headers()
                        sent = True
                    self.wfile.write(data)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    lost = True
            def disconnected():
                if lost: return True
                if not select.select([self.connection], [], [], 0)[0]: return False
                try: return self.connection.recv(1, socket.MSG_PEEK) == b''
                except OSError: return True
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                    raise ValueError('请求大小超限或缺少 Content-Length')
                self.connection.settimeout(30)
                request = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('数值非法')))
                if self.path == '/v1/tool-evidence':
                    self.send_json(200, gateway.record_host_evidence(request))
                    return
                responses = self.path == '/v1/responses'
                aliases = gateway_responses.lower_tools(request)[1] if responses else {}
                if responses: request = gateway_responses.to_chat(request)
                if request.get('stream'):
                    wire = WireStream(send, responses=responses, aliases=aliases,
                        include_usage=(request.get('stream_options') or {}).get('include_usage', False))
                result = gateway.complete(request, cancelled=disconnected, on_text=wire.text if wire else None)
                if wire:
                    wire.finish(result)
                else:
                    self.send_json(200, gateway_responses.from_chat(result, aliases) if responses else result)
            except Exception as exc:
                if sent:
                    if wire and not lost: wire.fail()
                elif not disconnected():
                    self.send_json(400 if isinstance(exc, ValueError) else 502, {'error': {
                        'message': str(exc) if isinstance(exc, ValueError) else '受管模型调用失败；未自动重试，请核对本地账本',
                        'type': 'invalid_request_error' if isinstance(exc, ValueError) else 'upstream_error'}})

    return ThreadingHTTPServer((host, port), Handler)


def load_gateway_config(path):
    raw = json.loads(path.read_text())
    allowed = {'schemaVersion', 'authTokenEnv', 'providers', 'planningRouting'}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError('网关配置不是对象或包含未知字段')
    if raw.get('schemaVersion', GATEWAY_CONFIG_VERSION) != GATEWAY_CONFIG_VERSION:
        raise ValueError('不支持的网关配置版本')
    if 'authTokenEnv' in raw and (not isinstance(raw['authTokenEnv'], str) or not raw['authTokenEnv']):
        raise ValueError('authTokenEnv 必须是非空环境变量名称')
    if not isinstance(raw.get('providers'), dict) or not isinstance(raw.get('planningRouting'), dict):
        raise ValueError('网关配置必须包含 providers 与 planningRouting')
    return raw


def main():
    parser = argparse.ArgumentParser(description='独立 RefractRouter 模型接口；Agent 工具由客户端执行')
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--runs-dir', required=True, type=Path)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8088)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--load-stage-judge', action='store_true',
                        help='明确加载已下载的 Stage 本地 Judge；不下载权重')
    args = parser.parse_args()
    config = load_gateway_config(args.config)
    token_env = config.get('authTokenEnv')
    token = os.environ.get(token_env) if token_env else None
    if token_env and not token:
        raise ValueError('服务认证凭证未配置')
    gateway = ModelGateway(config, args.runs_dir)
    if args.preflight:
        print(json.dumps({**gateway.service_info(), 'models': gateway.models()}, ensure_ascii=False))
        gateway.close()
        return 0
    if args.load_stage_judge:
        local_config = deepcopy(gateway.planning)
        local_config['defaultStrategy'] = 'stage'
        try:
            gateway.runtime.handle({'op': 'local-judge', 'config': local_config, 'action': 'load'})
        except Exception:
            gateway.close()
            raise
    server = create_server(gateway, args.host, args.port, token)
    def stop_service(_signum, _frame):
        raise KeyboardInterrupt
    previous = {}
    for name in ('SIGINT', 'SIGTERM'):
        member = getattr(signal, name, None)
        if member is not None:
            previous[member] = signal.signal(member, stop_service)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for member, handler in previous.items():
            signal.signal(member, handler)
        server.server_close()
        gateway.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
