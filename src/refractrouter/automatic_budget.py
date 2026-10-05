"""自动路由的多单位调用账本；不把订阅额度换算成现金。"""
from __future__ import annotations

from copy import deepcopy
from threading import RLock

from .task_budget import InvalidModelOutput, TaskCallBudget
from .node_routing import number


class AutomaticMixedBudget:
    """两本原生单位账共享调用名额、取消状态及必要路径的原子预留。"""

    def __init__(self, client, limits, *, max_calls=None, max_total_output_tokens=None,
                 adaptive_output_reservation=False):
        if not isinstance(limits, dict) or set(limits) != {'AFP', 'CNY'}:
            raise ValueError('automatic mixed budget requires AFP and CNY limits')
        self.lock = RLock()
        self.ledgers = {}
        for unit, row in limits.items():
            if not isinstance(row, dict) or set(row) != {'production', 'evaluation'}:
                raise ValueError(f'{unit} requires production and evaluation limits')
            for category, value in row.items():
                number(value, f'{unit} {category} limit')
            production = None if row['production'] == 0 else row['production']
            evaluation = 1e12 if row['evaluation'] == 0 else row['evaluation']
            self.ledgers[unit] = TaskCallBudget(client, production, evaluation,
                capture_payload=True, adaptive_output_reservation=adaptive_output_reservation)
            self.ledgers[unit].on_response = self._on_response
        self.max_calls = max_calls
        self.max_total_output_tokens = max_total_output_tokens
        self.records = []
        self.stopped = False
        self.on_reserve = None
        self.on_response = None

    def _on_response(self, row, response):
        if self.on_response is not None:
            self.on_response(row, response)

    def remaining(self, unit, category='production'):
        if unit not in self.ledgers:
            raise ValueError(f'unknown billing unit: {unit}')
        return self.ledgers[unit].remaining(category)

    def snapshot(self):
        with self.lock:
            return ({unit: dict(ledger.charged) for unit, ledger in self.ledgers.items()},
                    deepcopy(self.records))

    def deadline(self, deadline):
        return deadline + sum(ledger.planning_elapsed for ledger in self.ledgers.values())

    @property
    def planning_elapsed(self):
        return sum(ledger.planning_elapsed for ledger in self.ledgers.values())

    def _release(self, reservation):
        ledger, row = self.ledgers[reservation.model.billing_unit], reservation.row
        with ledger.lock:
            if row['status'] == 'cancelled-before-dispatch':
                return
            if row['status'] != 'reserved':
                raise ValueError('cannot release a dispatched model call')
            ledger.charged[row['category']] -= row['charged']
            row.update(charged=0, status='cancelled-before-dispatch')

    def reserve_many(self, requests):
        """一个必要调用路径的各单位额度一起保护，失败时释放全部未派发部分。"""
        if not isinstance(requests, (list, tuple)) or not requests:
            raise ValueError('mixed reservation requires calls')
        reservations = []
        writing_evidence = False
        with self.lock:
            if self.stopped:
                raise ValueError('automatic mixed budget stopped')
            active_calls = sum(row['status'] != 'cancelled-before-dispatch' for row in self.records)
            if self.max_calls is not None and active_calls + len(requests) > self.max_calls:
                raise ValueError('study-call-limit-exhausted')
            try:
                for request in requests:
                    model = request['model']
                    unit = model.billing_unit
                    if unit not in self.ledgers:
                        raise ValueError(f'unknown billing unit: {unit}')
                    params = {key: value for key, value in request.items() if key != 'model'}
                    reservation = self.ledgers[unit].reserve(model, **params)
                    reservation.row['billing_unit'] = unit
                    reservations.append(reservation)
                    self.records.append(reservation.row)
                    if self.max_total_output_tokens is not None and sum(
                            row['reserved_output_tokens'] for row in self.records
                            if row['status'] != 'cancelled-before-dispatch') > self.max_total_output_tokens:
                        raise ValueError('task-output-budget-exhausted')
                if self.on_reserve is not None:
                    writing_evidence = True
                    self.on_reserve(tuple(reservations))
            except Exception:
                for reservation in reservations:
                    self._release(reservation)
                if writing_evidence:
                    self.stop()
                raise
        return tuple(reservations)

    def reserve(self, model, messages, *, category='production', label, json_mode=False,
                category_limit=None, tools=None):
        return self.reserve_many([{'model': model, 'messages': messages,
            'category': category, 'label': label, 'json_mode': json_mode,
            'category_limit': category_limit, 'tools': tools}])[0]

    def dispatch(self, reservation, **kwargs):
        with self.lock:
            if self.stopped:
                raise ValueError('automatic mixed budget stopped')
            try:
                return self.ledgers[reservation.model.billing_unit].dispatch(reservation, **kwargs)
            except Exception:
                self.stop()
                raise

    def invoke(self, reservation, **kwargs):
        with self.lock:
            if self.stopped:
                raise ValueError('automatic mixed budget stopped')
        try:
            return self.ledgers[reservation.model.billing_unit].invoke(reservation, **kwargs)
        except InvalidModelOutput:
            raise
        except Exception:
            self.stop()
            raise

    def settle(self, reservation, response):
        with self.lock:
            try:
                return self.ledgers[reservation.model.billing_unit].settle(reservation, response)
            except InvalidModelOutput:
                raise
            except Exception:
                self.stop()
                raise

    def complete(self, model, messages, *, category='production', label, json_mode=False,
                 timeout_seconds=None, category_limit=None, unlimited=False):
        return self.invoke(self.reserve(model, messages, category=category, label=label,
            json_mode=json_mode, category_limit=category_limit),
            timeout_seconds=timeout_seconds, unlimited=unlimited)

    def stop(self):
        with self.lock:
            self.stopped = True
            for ledger in self.ledgers.values():
                ledger.stop()
