"""并发调用的原子预留、派发、结算与取消账本。"""
from __future__ import annotations

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from threading import RLock
import time

from .node_routing import number
from .openai_compatible import model_response_cost


class InvalidModelOutput(ValueError):
    """用量已结算，但模型返回空内容或非正常结束的输出。"""


@dataclass
class Reservation:
    model: object
    messages: list
    row: dict
    json_mode: bool


class TaskCallBudget:
    def __init__(self, client, production: float, evaluation: float, *, max_calls=None, capture_payload=False):
        self.client = client
        self.limits = {'production': number(production, 'production budget', positive=True),
                       'evaluation': number(evaluation, 'evaluation budget', positive=True)}
        self.charged = {'production': 0.0, 'evaluation': 0.0}
        self.records = []
        self.lock = RLock()
        self.stopped = False
        self.max_calls = max_calls
        self.capture_payload = capture_payload
        self.on_reserve = None
        self.on_response = None

    def remaining(self, category='production'):
        with self.lock:
            return max(0, self.limits[category] - self.charged[category])

    def snapshot(self):
        with self.lock:
            return dict(self.charged), deepcopy(self.records)

    def reserve(self, model, messages, *, category='production', label, json_mode=False, category_limit=None):
        if category_limit is not None:
            category_limit = number(category_limit, 'category limit')
        encoded = json.dumps(messages, ensure_ascii=False).encode()
        input_bound = len(encoded) + 256
        output_bound = min(model.max_output_tokens, 8192)
        if input_bound + output_bound > model.context_window:
            raise ValueError('request exceeds conservative context bound')
        reserve = input_bound / 1000 * model.input_cost_per_1k + output_bound / 1000 * model.output_cost_per_1k
        with self.lock:
            if self.stopped:
                raise CancelledError('task execution stopped')
            if self.max_calls is not None and len(self.records) >= self.max_calls:
                raise ValueError('study-call-limit-exhausted')
            if self.charged[category] + reserve > min(self.limits[category], category_limit if category_limit is not None else float('inf')):
                raise ValueError(f'{category}-budget-exhausted before {label}')
            self.charged[category] += reserve
            row = {'label': label, 'model_id': model.model_id, 'category': category,
                   'reserved': reserve, 'charged': reserve, 'status': 'reserved',
                   'input_sha256': hashlib.sha256(encoded).hexdigest()}
            if category_limit is not None:
                row['category_limit'] = category_limit
            if self.capture_payload:
                row['request_messages'] = deepcopy(messages)
            self.records.append(row)
        reservation = Reservation(model, messages, row, json_mode)
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

    def invoke(self, reservation, *, timeout_seconds=None, cancel_event=None):
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
        call_client = self.client
        if timeout_seconds is not None and hasattr(call_client, 'for_task_call'):
            call_client = call_client.for_task_call(timeout_seconds)
        response = call_client.complete(model, reservation.messages, json_mode=reservation.json_mode)
        if self.on_response is not None:
            self.on_response(row, response)
        if self.capture_payload:
            with self.lock:
                row['response_output'] = response.content
        counts = (response.input_tokens, response.output_tokens, response.cached_input_tokens, response.reasoning_tokens)
        if not response.usage_available or (response.content.strip() and (response.input_tokens == 0 or response.output_tokens == 0)):
            raise ValueError('missing or unconfirmed model usage; reservation retained')
        if any(type(x) is not int or x < 0 for x in counts) or response.cached_input_tokens > response.input_tokens:
            raise ValueError('invalid model usage; reservation retained')
        actual = number(model_response_cost(model, response), 'model cost')
        with self.lock:
            self.charged[row['category']] += actual - row['charged']
            row.update(charged=actual, status='billed', input_tokens=response.input_tokens,
                       output_tokens=response.output_tokens, latency_ms=response.latency_ms,
                       request_id=response.request_id, finish_reason=response.finish_reason,
                       output_sha256=hashlib.sha256(response.content.encode()).hexdigest())
            if (actual > row['reserved'] + 1e-8
                    or self.charged[row['category']] > min(self.limits[row['category']], row.get('category_limit', float('inf')))):
                self.stop()
                raise ValueError('provider usage exceeded conservative budget reserve; execution stopped')
        if response.finish_reason != 'stop' or not response.content.strip():
            raise InvalidModelOutput(f"invalid or truncated output for {row['label']}")
        return response

    def complete(self, model, messages, *, category='production', label, json_mode=False, timeout_seconds=None):
        return self.invoke(self.reserve(model, messages, category=category, label=label, json_mode=json_mode),
                           timeout_seconds=timeout_seconds)
