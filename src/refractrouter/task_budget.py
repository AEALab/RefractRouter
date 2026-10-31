"""并发调用的原子预留、派发、结算与取消账本。"""
from __future__ import annotations

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import dataclass, asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from threading import RLock
import time

from .responses_api import output_token_limit, available_output_limit
from .node_routing import number
from .openai_compatible import ModelInvocationError, model_response_cost


def request_input_bound(messages, tools=None, request_options=None):
    """模型请求与节点准入共用相同的保守序列化计数。"""
    payload = {"messages": messages, "tools": tools} if tools else messages
    if request_options:
        payload = {'request': payload, 'executionOptions': request_options}
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
                 max_total_output_tokens=None, adaptive_output_reservation=False, cash_limits=None):
        self.client = client
        self.limits = {'production': float('inf') if production is None else number(production, 'production budget', positive=True),
                       'evaluation': number(evaluation, 'evaluation budget', positive=True)}
        self.charged = {'production': 0.0, 'evaluation': 0.0}
        self.cash_limits = None
        if cash_limits is not None:
            if not isinstance(cash_limits, dict) or set(cash_limits) != {'production', 'evaluation'}:
                raise ValueError('cash limits require production and evaluation')
            self.cash_limits = {key: float('inf') if number(value, 'cash limit') == 0 else value
                                for key, value in cash_limits.items()}
        self.records = []
        self.lock = RLock()
        self.stopped = False
        self.max_calls = max_calls
        self.capture_payload = capture_payload
        self.max_total_output_tokens = max_total_output_tokens
        self.adaptive_output_reservation = adaptive_output_reservation
        self.planning_elapsed = 0.0
        self.on_reserve = None
        self.on_dispatch = None
        self.on_response = None

    def deadline(self, deadline):
        return deadline + self.planning_elapsed

    def remaining(self, category='production'):
        with self.lock:
            return max(0, self.limits[category] - self.charged[category])

    def cash_snapshot(self):
        with self.lock:
            return {category: sum(row['charged'] for row in self.records
                if row['category'] == category and row.get('billing_mode', 'metered') != 'subscription')
                for category in ('production', 'evaluation')}

    def remaining_cash(self, category='production'):
        """返回包含在途预留后的现金余额；None 表示未设置或明确不限额。"""
        with self.lock:
            if self.cash_limits is None or math.isinf(self.cash_limits[category]):
                return None
            return max(0, self.cash_limits[category] - self.cash_snapshot()[category])

    def snapshot(self):
        with self.lock:
            return dict(self.charged), deepcopy(self.records)

    def reserve(self, model, messages, *, category='production', label, json_mode=False, category_limit=None, tools=None,
                future_input_bound=None, request_options=None, context_token_envelope=None, native_output_budget=False):
        if category_limit is not None:
            category_limit = number(category_limit, 'category limit')
        encoded = json.dumps({"messages": messages, "tools": tools} if tools else messages, ensure_ascii=False).encode()
        if request_options:
            encoded = json.dumps({'request': json.loads(encoded), 'executionOptions': request_options}, ensure_ascii=False).encode()
        input_bound = request_input_bound(messages, tools, request_options)
        if future_input_bound is not None:
            if type(future_input_bound) is not int or future_input_bound < input_bound or tools:
                raise ValueError('invalid future review input envelope')
            input_bound = future_input_bound
        native_bound=None
        if native_output_budget:
            if self.adaptive_output_reservation or context_token_envelope is not None:
                raise ValueError('原生规划预留不能与缩减输出或研究包络混用')
            from .planning_output_budget import reservation_bound
            native_bound=reservation_bound(model,input_bound)
        output_bound = native_bound['wireOutputTokens'] if native_bound else available_output_limit(model, input_bound)
        if output_bound <= 0:
            raise ValueError('request leaves no model output capacity')
        if getattr(model, 'unrestricted_execution_output', False):
            model = replace(model, max_output_tokens=output_bound)
        if input_bound + output_bound > model.context_window:
            raise ValueError('request exceeds conservative context bound')
        if context_token_envelope is not None:
            if (type(context_token_envelope) is not int or not model.context_window <= context_token_envelope <= 10_000_000
                    or future_input_bound is not None or self.adaptive_output_reservation
                    or getattr(model, 'price_policy', None) or getattr(model, 'reference_pricing', None)):
                raise ValueError('invalid shared context token envelope')
            # 回答上限不等于“回答＋思考”上限。保留原线缆上限，以整个上下文和最贵边际价
            # 保护输入＋全部输出；两者共享上下文，不将各自上界再次相加。
            marginal = max(number(v, 'token price') for v in (
                model.input_cost_per_1k, model.output_cost_per_1k,
                model.cached_input_cost_per_1k or 0, getattr(model, 'cache_write_cost_per_1k', None) or 0))
        with self.lock:
            if self.stopped:
                raise CancelledError('task execution stopped')
            if self.max_calls is not None and sum(r['status'] != 'cancelled-before-dispatch' for r in self.records) >= self.max_calls:
                raise ValueError('study-call-limit-exhausted')
            ceiling = min(self.limits[category], category_limit if category_limit is not None else float('inf'))
            input_reserve = input_bound / 1000 * max(model.input_cost_per_1k, getattr(model, 'cache_write_cost_per_1k', None) or 0)
            if native_bound is not None:input_reserve=input_bound/1000*native_bound['pricesPer1k']['input']
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
            protected_output = output_bound
            if native_bound is not None:
                reserve=native_bound['amount']
                protected_output=native_bound['reservedTotalOutputTokens']
            if context_token_envelope is not None:
                reserve = context_token_envelope / 1000 * marginal
                protected_output = context_token_envelope
            reserved_output = sum(row.get('reserved_output_tokens', 0) for row in self.records
                                  if row['status'] != 'cancelled-before-dispatch')
            if (self.max_total_output_tokens is not None
                    and reserved_output + protected_output > self.max_total_output_tokens):
                raise ValueError(f'task-output-budget-exhausted before {label}')
            if self.charged[category] + reserve > ceiling + 1e-12:
                raise ValueError(f'{category}-budget-exhausted before {label}')
            if self.cash_limits is not None and getattr(model, 'billing_mode', 'metered') != 'subscription':
                if model.billing_unit != 'CNY':
                    raise ValueError('cash limits require CNY prices')
                if self.cash_snapshot()[category] + reserve > self.cash_limits[category] + 1e-12:
                    raise ValueError(f'{category}-cash-budget-exhausted before {label}')
            self.charged[category] += reserve
            row = {'label': label, 'model_id': model.model_id, 'category': category,
                   'billing_mode': getattr(model, 'billing_mode', 'metered'),
                   'reserved': reserve, 'charged': reserve, 'status': 'reserved',
                   'reserved_output_tokens': protected_output,
                   'input_sha256': hashlib.sha256(encoded).hexdigest()}
            if context_token_envelope is not None:
                row.update(reservation_basis='shared-context-token-envelope',
                           protected_total_tokens=context_token_envelope, reserved_answer_tokens=output_bound)
            if native_bound is not None:
                row.update(reservation_basis=native_bound['reservationBasis'],native_output_budget=deepcopy(native_bound),
                    protected_total_tokens=native_bound['protectedTotalTokens'],
                    reserved_answer_tokens=output_bound if native_bound['contract']['scope']=='answer-only' else None,
                    wire_output_tokens=output_bound,output_limit_scope=native_bound['contract']['scope'])
            if request_options:
                row['request_options_sha256'] = hashlib.sha256(json.dumps(
                    request_options, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if future_input_bound is not None:
                row.update(reservation_basis='future-input-envelope', protected_input_bound=future_input_bound,
                           input_bound_confirmed=False)
            if category_limit is not None:
                row['category_limit'] = category_limit
            if self.capture_payload:
                row['request_messages'] = deepcopy(messages)
                if tools:
                    row['request_tools'] = deepcopy(tools)
                if request_options:
                    row['request_options'] = deepcopy(request_options)
            self.records.append(row)
        reservation = Reservation(model, messages, row, json_mode, tools)
        if self.on_reserve is not None:
            try:
                self.on_reserve(reservation)
            except Exception:
                self.stop()
                raise
        return reservation

    def release(self, reservation):
        """释放一个尚未派发的预留；不能释放已派发的未知用量。"""
        with self.lock:
            row = reservation.row
            if row['status'] == 'cancelled-before-dispatch':
                return
            if row['status'] != 'reserved':
                raise ValueError('cannot release a dispatched model call')
            self.charged[row['category']] -= row['charged']
            row.update(charged=0, status='cancelled-before-dispatch')

    def reserve_many(self, requests):
        """原子保护一个必要调用路径，任一额度不足时释放所有未派发部分。"""
        if not isinstance(requests, (list, tuple)) or not requests:
            raise ValueError('reservation path requires calls')
        reservations = []
        with self.lock:
            try:
                for request in requests:
                    reservations.append(self.reserve(**request))
            except BaseException:
                for reservation in reservations:
                    self.release(reservation)
                raise
        return reservations

    def bind_future_input(self, reservation, messages):
        """将保护的输入包络绑定到真实请求，不改变已保护额度或调用名额。"""
        encoded = json.dumps(messages, ensure_ascii=False).encode()
        bound = request_input_bound(messages)
        with self.lock:
            row = reservation.row
            if (self.stopped or row['status'] != 'reserved'
                    or row.get('reservation_basis') != 'future-input-envelope'
                    or row.get('input_bound_confirmed') is not False):
                raise ValueError('future review reservation cannot be rebound')
            if bound > row['protected_input_bound']:
                raise ValueError('final correction review exceeds protected input envelope')
            reservation.messages = deepcopy(messages)
            row.update(input_sha256=hashlib.sha256(encoded).hexdigest(), input_bound_confirmed=True,
                       actual_input_bound=bound)
            if self.capture_payload:
                row['request_messages'] = deepcopy(messages)

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
            if row.get('reservation_basis') == 'future-input-envelope' and row.get('input_bound_confirmed') is not True:
                raise ValueError('future input must be bound before dispatch')
            if timeout_seconds is not None and timeout_seconds <= 0:
                self.stop()
                raise ValueError('task-deadline-exhausted')
            row.update(status='unknown-usage', dispatch_monotonic=time.monotonic(),
                       dispatch_at=datetime.now(timezone.utc).isoformat())
        if self.on_dispatch is not None:
            try:
                self.on_dispatch(reservation)
            except BaseException:
                self.stop()
                raise

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
            self.settle_failure(reservation, exc)
            raise
        finally:
            if unlimited:
                self.planning_elapsed += time.monotonic() - planning_started
        return self.settle(reservation, response)

    def settle_failure(self, reservation, error):
        """有效终止用量照常记账；失败候选始终拒绝，缺失用量继续占预留。"""
        with self.lock:
            reservation.row['failure'] = error.public_details()
        receipt = error.confirmed_response
        if receipt is not None:
            # 固定为错误结束，避免异常携带的回复被当作工具调用或正常正文。
            receipt = replace(receipt, finish_reason='error', tool_calls=())
            try:
                self.settle(reservation, receipt)
            except InvalidModelOutput:
                pass

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
        if getattr(response, 'actual_model', None) is not None:
            row['observed_actual_model'] = response.actual_model
        if getattr(response, 'provider_revision', None) is not None:
            row['observed_provider_revision'] = response.provider_revision
        if getattr(response, 'price_binding_confirmed', None) is not None:
            row['price_binding_confirmed'] = response.price_binding_confirmed
        if getattr(response, 'price_binding_confirmed', None) is False:
            raise ValueError('provider price binding unconfirmed; reservation retained')
        if not response.usage_available or ((response.content.strip() or getattr(response, "tool_calls", ())) and (response.input_tokens == 0 or response.output_tokens == 0)):
            raise ValueError('missing or unconfirmed model usage; reservation retained')
        if (any(type(x) is not int or x < 0 for x in counts)
                or response.cached_input_tokens > response.input_tokens
                or response.reasoning_tokens > response.output_tokens):
            raise ValueError('invalid model usage; reservation retained')
        if getattr(model, 'price_policy', None) == 'deepseek-official-cny-v1':
            from .deepseek_official_pricing import pricing
            rates = pricing(model.api_model, at=datetime.fromisoformat(row['dispatch_at']))
            model = replace(model, input_cost_per_1k=rates['inputPer1k'],
                cached_input_cost_per_1k=rates['cachedInputPer1k'], output_cost_per_1k=rates['outputPer1k'])
            row['price_snapshot'] = dict(rates, unit='CNY', basis='dispatch-time-official-estimate')
        raw_usage = response.raw_usage if isinstance(response.raw_usage, dict) else {}
        answer_bound_valid = True
        native=row.get('native_output_budget')
        if native is not None:
            from .cache_usage import observed_details
            _,observed_reasoning=observed_details(response)
            answer_tokens=response.output_tokens-observed_reasoning if observed_reasoning is not None else None
            scope=native['contract']['scope']
            if scope=='answer-and-reasoning-total':
                answer_bound_valid=response.output_tokens<=native['wireOutputTokens']
            elif scope=='answer-only':
                answer_bound_valid=(answer_tokens<=native['wireOutputTokens'] if answer_tokens is not None
                    else response.output_tokens<=native['wireOutputTokens'])
            row.update(observed_answer_tokens=answer_tokens,
                answer_bound_confirmed=answer_bound_valid if scope=='answer-only' else None,
                total_output_bound_confirmed=(response.output_tokens<=native['reservedTotalOutputTokens']),
                observed_reasoning_tokens=observed_reasoning)
        if row.get('reservation_basis') == 'shared-context-token-envelope':
            from .cache_usage import observed_details
            _, observed_reasoning = observed_details(response)
            answer_tokens = response.output_tokens - observed_reasoning if observed_reasoning is not None else None
            # 思考细分缺失时仍可结算总费用，但不能把占位零当成已验证的纯回答长度。
            answer_bound_valid = (answer_tokens <= row['reserved_answer_tokens'] if answer_tokens is not None
                                  else response.output_tokens <= row['reserved_answer_tokens'])
            row.update(observed_answer_tokens=answer_tokens, answer_bound_confirmed=answer_bound_valid)
        write_known = raw_usage.get('cacheWriteUsageAvailable', 'cacheWriteTokens' in raw_usage) is True
        input_rate, write_rate = model.input_cost_per_1k, getattr(model, 'cache_write_cost_per_1k', None)
        reference = getattr(model, 'reference_pricing', None)
        if reference and reference.get('schedule'):
            from .currency_pricing import reference_price
            rates = dict(reference_price(reference, input_tokens=response.input_tokens).rates)
            input_rate, write_rate = rates['input'], rates.get('cacheWrite', rates['input'])
        if write_rate is not None and write_rate != input_rate and not write_known:
            raise ValueError('unconfirmed cache write usage; reservation retained')
        actual = number(model_response_cost(model, response), 'model cost')
        with self.lock:
            if model.billing_unit in {'CNY', 'USD'}:
                row['cost_basis'] = 'subscription-reference-valuation' if getattr(model, 'billing_mode', 'metered') == 'subscription' else 'public-price-calculation'
                row['provider_cost_confirmed'] = False
            self.charged[row['category']] += actual - row['charged']
            row.update(charged=actual, status='billed', input_tokens=response.input_tokens,
                       output_tokens=response.output_tokens, cached_input_tokens=response.cached_input_tokens,
                       cache_usage_source=response.cache_usage_source,
                       cache_usage_available=response.cache_usage_source is not None, ttft_ms=response.ttft_ms,
                       cache_write_tokens=raw_usage.get('cacheWriteTokens') if write_known else None,
                       cache_write_usage_available=write_known,
                       first_tool_ms=response.first_tool_ms,
                       reasoning_tokens=response.reasoning_tokens, latency_ms=response.latency_ms,
                       request_id=response.request_id, finish_reason=response.finish_reason,
                       output_sha256=hashlib.sha256((json.dumps({'content': response.content, 'tool_calls': response.tool_calls},
                           ensure_ascii=False) if getattr(response, 'tool_calls', ()) else response.content).encode()).hexdigest())
            if self.cash_limits is not None:
                row['reference_cost_cny'] = actual
                row['cash_cost_cny'] = None if getattr(model, 'billing_mode', 'metered') == 'subscription' else actual
                row['cash_cost_status'] = 'not-attributed-per-call' if getattr(model, 'billing_mode', 'metered') == 'subscription' else 'calculated-not-provider-confirmed'
                if self.cash_snapshot()[row['category']] > self.cash_limits[row['category']] + 1e-8:
                    self.stop()
                    raise ValueError('actual cash cost exceeded limit; execution stopped')
            if (not answer_bound_valid or actual > row['reserved'] + 1e-8
                    or row.get('protected_total_tokens') is not None
                       and response.input_tokens + response.output_tokens > row['protected_total_tokens']
                    or self.charged[row['category']] > min(self.limits[row['category']], row.get('category_limit', float('inf')))):
                self.stop()
                raise ValueError('provider usage exceeded conservative budget reserve; execution stopped')
        if response.finish_reason == 'stop' and not getattr(response, 'tool_calls', ()) and response.content.strip().startswith('<|FunctionCallBegin|>'):
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
