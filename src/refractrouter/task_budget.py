"""并发调用的原子预留、派发、结算与取消账本。"""
from __future__ import annotations

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import dataclass, asdict, replace
import hashlib
import json
import math
from threading import RLock
import time

from .responses_api import output_token_limit, available_output_limit
from .node_routing import number
from .openai_compatible import ModelInvocationError, model_response_cost


def request_input_bound(messages, tools=None):
    """模型请求与节点准入共用相同的保守序列化计数。"""
    payload = {"messages": messages, "tools": tools} if tools else messages
    return len(json.dumps(payload, ensure_ascii=False).encode()) + 256


class InvalidModelOutput(ValueError):
    """用量已结算，但模型返回空内容或非正常结束的输出。"""


@dataclass
class Reservation:
    model: object
    messages: list
    row: dict
    json_mode: bool
    tools: object = None


class TaskCallBudget:
    def __init__(self, client, production: float, evaluation: float, *, max_calls=None, capture_payload=False,
                 max_total_output_tokens=None, adaptive_output_reservation=False):
        self.client = client
        self.limits = {'production': float('inf') if production is None else number(production, 'production budget', positive=True),
                       'evaluation': number(evaluation, 'evaluation budget', positive=True)}
        self.charged = {'production': 0.0, 'evaluation': 0.0}
        self.records = []
        self.lock = RLock()
        self.stopped = False
        self.max_calls = max_calls
        self.capture_payload = capture_payload
        self.max_total_output_tokens = max_total_output_tokens
        self.adaptive_output_reservation = adaptive_output_reservation
        self.planning_elapsed = 0.0
        self.on_reserve = None
        self.on_response = None

    def deadline(self, deadline):
        return deadline + self.planning_elapsed

    def remaining(self, category='production'):
        with self.lock:
            return max(0, self.limits[category] - self.charged[category])

    def snapshot(self):
        with self.lock:
            return dict(self.charged), deepcopy(self.records)

    def reserve(self, model, messages, *, category='production', label, json_mode=False, category_limit=None, tools=None):
        if category_limit is not None:
            category_limit = number(category_limit, 'category limit')
        encoded = json.dumps({"messages": messages, "tools": tools} if tools else messages, ensure_ascii=False).encode()
        input_bound = request_input_bound(messages, tools)
        output_bound = available_output_limit(model, input_bound)
        if output_bound <= 0:
            raise ValueError('request leaves no model output capacity')
        if getattr(model, 'unrestricted_execution_output', False):
            model = replace(model, max_output_tokens=output_bound)
        if input_bound + output_bound > model.context_window:
            raise ValueError('request exceeds conservative context bound')
        with self.lock:
            if self.stopped:
                raise CancelledError('task execution stopped')
            if self.max_calls is not None and len(self.records) >= self.max_calls:
                raise ValueError('study-call-limit-exhausted')
            ceiling = min(self.limits[category], category_limit if category_limit is not None else float('inf'))
            input_reserve = input_bound / 1000 * model.input_cost_per_1k
            remaining = ceiling - self.charged[category] - input_reserve
            if remaining < 0:
                raise ValueError(f'{category}-budget-exhausted before {label}')
            if self.adaptive_output_reservation and model.output_cost_per_1k > 0:
                affordable = math.floor((remaining + 1e-12) * 1000 / model.output_cost_per_1k)
                output_bound = min(output_bound, affordable)
            if output_bound <= 0:
                raise ValueError(f'{category}-budget-exhausted before {label}')
            if self.adaptive_output_reservation:
                model = replace(model, max_output_tokens=output_bound)
            reserve = input_reserve + output_bound / 1000 * model.output_cost_per_1k
            reserved_output = sum(row.get('reserved_output_tokens', 0) for row in self.records)
            if (self.max_total_output_tokens is not None
                    and reserved_output + output_bound > self.max_total_output_tokens):
                raise ValueError(f'task-output-budget-exhausted before {label}')
            if self.charged[category] + reserve > ceiling + 1e-12:
                raise ValueError(f'{category}-budget-exhausted before {label}')
            self.charged[category] += reserve
            row = {'label': label, 'model_id': model.model_id, 'category': category,
                   'reserved': reserve, 'charged': reserve, 'status': 'reserved',
                   'reserved_output_tokens': output_bound,
                   'input_sha256': hashlib.sha256(encoded).hexdigest()}
            if category_limit is not None:
                row['category_limit'] = category_limit
            if self.capture_payload:
                row['request_messages'] = deepcopy(messages)
                if tools:
                    row['request_tools'] = deepcopy(tools)
            self.records.append(row)
        reservation = Reservation(model, messages, row, json_mode, tools)
        if self.on_reserve is not None:
            try:
                self.on_reserve(reservation)
            except Exception:
                self.stop()
                raise
        return reservation

    def stop(self):
        """仅释放尚未派发的预留；已派发请求继续保留并结算。"""
        with self.lock:
            self.stopped = True
            for row in self.records:
                if row['status'] == 'reserved':
                    self.charged[row['category']] -= row['charged']
                    row.update(charged=0, status='cancelled-before-dispatch')
            for category in self.charged:
                self.charged[category] = sum(r['charged'] for r in self.records if r['category'] == category)

    def dispatch(self, reservation, *, timeout_seconds=None, cancel_event=None):
        row, model = reservation.row, reservation.model
        with self.lock:
            if cancel_event is not None and cancel_event.is_set():
                self.stop()
            if self.stopped or row['status'] != 'reserved':
                self.stop()
                raise CancelledError('task execution stopped')
            if timeout_seconds is not None and timeout_seconds <= 0:
                self.stop()
                raise ValueError('task-deadline-exhausted')
            row.update(status='unknown-usage', dispatch_monotonic=time.monotonic())

    def invoke(self, reservation, *, timeout_seconds=None, cancel_event=None, unlimited=False):
        row, model = reservation.row, reservation.model
        self.dispatch(reservation, timeout_seconds=timeout_seconds, cancel_event=cancel_event)
        call_client = self.client
        if (unlimited or timeout_seconds is not None) and hasattr(call_client, 'for_task_call'):
            call_client = call_client.for_task_call(None if unlimited or timeout_seconds == float("inf") else timeout_seconds)
        planning_started = time.monotonic()
        try:
            response = call_client.complete(model, reservation.messages, json_mode=reservation.json_mode,
                **({"tools": reservation.tools} if reservation.tools else {}))
        except ModelInvocationError as exc:
            with self.lock:
                row['failure'] = exc.public_details()
            raise
        finally:
            if unlimited:
                self.planning_elapsed += time.monotonic() - planning_started
        return self.settle(reservation, response)

    def settle(self, reservation, response):
        """结算宿主实际执行的调用；与内置 complete 共用费用和输出验收。"""
        row, model = reservation.row, reservation.model
        with self.lock:
            if row['status'] != 'unknown-usage':
                raise ValueError('call receipt already settled or not dispatched')
        if self.on_response is not None:
            self.on_response(row, response)
        if self.capture_payload:
            with self.lock:
                row['response_output'] = response.content
                row['response'] = asdict(response)
        counts = (response.input_tokens, response.output_tokens, response.cached_input_tokens, response.reasoning_tokens)
        if not response.usage_available or ((response.content.strip() or getattr(response, "tool_calls", ())) and (response.input_tokens == 0 or response.output_tokens == 0)):
            raise ValueError('missing or unconfirmed model usage; reservation retained')
        if any(type(x) is not int or x < 0 for x in counts) or response.cached_input_tokens > response.input_tokens:
            raise ValueError('invalid model usage; reservation retained')
        actual = number(model_response_cost(model, response), 'model cost')
        with self.lock:
            self.charged[row['category']] += actual - row['charged']
            row.update(charged=actual, status='billed', input_tokens=response.input_tokens,
                       output_tokens=response.output_tokens, cached_input_tokens=response.cached_input_tokens,
                       cache_usage_source=response.cache_usage_source,
                       cache_usage_available=response.cache_usage_source is not None, ttft_ms=response.ttft_ms,
                       reasoning_tokens=response.reasoning_tokens, latency_ms=response.latency_ms,
                       request_id=response.request_id, finish_reason=response.finish_reason,
                       output_sha256=hashlib.sha256((json.dumps({'content': response.content, 'tool_calls': response.tool_calls},
                           ensure_ascii=False) if getattr(response, 'tool_calls', ()) else response.content).encode()).hexdigest())
            if (actual > row['reserved'] + 1e-8
                    or self.charged[row['category']] > min(self.limits[row['category']], row.get('category_limit', float('inf')))):
                self.stop()
                raise ValueError('provider usage exceeded conservative budget reserve; execution stopped')
        if not getattr(response, 'tool_calls', ()) and response.content.strip().startswith('<|FunctionCallBegin|>'):
            raise ValueError('模型返回工具协议文本而非原生 tool_calls；未执行文本指令')
        if reservation.tools and getattr(response, 'tool_calls', ()) and response.finish_reason in {'tool_calls', 'stop'}:
            return response
        if getattr(response, 'tool_calls', ()) or response.finish_reason != 'stop' or not response.content.strip():
            finish = response.finish_reason if response.finish_reason in {
                'stop', 'length', 'content_filter', 'tool_calls', 'function_call'} else 'other'
            raise InvalidModelOutput(f"invalid or truncated output for {row['label']} "
                f"(finish_reason={finish}, output_tokens={response.output_tokens}, "
                f"reasoning_tokens={response.reasoning_tokens}, output_cap={output_token_limit(model)})")
        return response

    def complete(self, model, messages, *, category='production', label, json_mode=False, timeout_seconds=None, category_limit=None, unlimited=False):
        return self.invoke(self.reserve(model, messages, category=category, label=label, json_mode=json_mode, category_limit=category_limit),
                           timeout_seconds=timeout_seconds, **({"unlimited": True} if unlimited else {}))
