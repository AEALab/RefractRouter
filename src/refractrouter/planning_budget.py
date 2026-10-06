"""规划路由的多单位预算；各单位独立预留，调用次数与停止状态共享。"""
from .task_budget import TaskCallBudget
from threading import RLock
import math

REFERENCE = "reference-CNY"
SUBSCRIPTION = "subscription-reference-CNY"

def _locked(method):
    from functools import wraps
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return call


class PlanningBudget:
    def __init__(self, limits, *, max_calls=None, reference_limit=None):
        self.ledgers = {unit: TaskCallBudget(None, None if limit == 0 else limit, 1,
            capture_payload=True) for unit, limit in limits.items()}
        self.lock = RLock()
        self.reference_limit = reference_limit
        if reference_limit is not None:
            if isinstance(reference_limit, bool) or not isinstance(reference_limit, (int, float)) or not math.isfinite(reference_limit) or reference_limit < 0:
                raise ValueError("参考成本上限无效")
            if set(limits) != {'CNY'}:
                raise ValueError("双金额账本只接受统一 CNY 费用")
            self.ledgers[SUBSCRIPTION] = TaskCallBudget(None, None, 1, capture_payload=True)
        self.max_calls = max_calls
        self.records = []
        self.stopped = False

    @_locked
    def remaining(self, unit):
        if unit == REFERENCE:
            if self.reference_limit is None:
                raise ValueError("缺少参考成本上限")
            used = sum(ledger.charged['production'] for ledger in self.ledgers.values())
            return float('inf') if self.reference_limit == 0 else max(0, self.reference_limit - used)
        return self.ledgers[unit].remaining()

    def requirements(self, model, amount):
        """供整条调用路径保护使用；同一金额可约束两个上限，但不能相加展示。"""
        if getattr(model, 'billing_mode', 'metered') not in ('metered', 'subscription'):
            raise ValueError("未知计费模式")
        if self.reference_limit is None:
            if getattr(model, 'billing_mode', 'metered') == 'subscription':
                raise ValueError("订阅估值需要新版参考成本账本")
            return {model.billing_unit: amount}
        if model.billing_unit != 'CNY':
            raise ValueError("双金额账本需要先统一换算为 CNY")
        result = {REFERENCE: amount}
        if getattr(model, 'billing_mode', 'metered') != 'subscription':
            result['CNY'] = amount
        return result

    def add_required(self, target, model, amount, *, maximum=False):
        if model is None:  # Jev 按量判别
            values = {'CNY': amount}
            if self.reference_limit is not None:
                values[REFERENCE] = amount
        else:
            values = self.requirements(model, amount)
        for unit, value in values.items():
            target[unit] = max(target.get(unit, 0), value) if maximum else target.get(unit, 0) + value

    def _check_reference_settlement(self):
        if self.reference_limit and sum(ledger.charged['production'] for ledger in self.ledgers.values()) > self.reference_limit + 1e-8:
            self.stop()
            raise ValueError("实际参考成本超过上限；保留用量并停止执行")

    def _ledger(self, model):
        return self.ledgers[SUBSCRIPTION if getattr(model, 'billing_mode', 'metered') == 'subscription'
                            else model.billing_unit]


    @_locked
    def reserve(self, model, messages, **kwargs):
        if self.stopped:
            raise ValueError("规划路由任务已停止")
        if self.max_calls is not None and len(self.records) >= self.max_calls:
            raise ValueError("study-call-limit-exhausted")
        unit = model.billing_unit
        if unit not in self.ledgers:
            raise ValueError(f"缺少 {unit} 生产预算")
        from .task_budget import request_input_bound
        from .responses_api import available_output_limit
        bound = request_input_bound(messages, kwargs.get('tools'))
        amount = bound / 1000 * max(model.input_cost_per_1k, getattr(model, "cache_write_cost_per_1k", None) or 0) + available_output_limit(model, bound) / 1000 * model.output_cost_per_1k
        for dimension, required in self.requirements(model, amount).items():
            if required > self.remaining(dimension):
                raise ValueError(f"{dimension} production-budget-exhausted")
        reservation = self._ledger(model).reserve(model, messages, **kwargs)
        reservation.row['billing_mode'] = getattr(model, 'billing_mode', 'metered')
        reservation.row["billing_unit"] = unit
        self.records.append(reservation.row)
        return reservation

    @_locked
    def dispatch(self, reservation, **kwargs):
        return self._ledger(reservation.model).dispatch(reservation, **kwargs)

    @_locked
    def settle(self, reservation, response):
        result = self._ledger(reservation.model).settle(reservation, response)
        if self.reference_limit is not None:
            row = reservation.row
            row['reference_cost_cny'] = row['charged']
            subscribed = row['billing_mode'] == 'subscription'
            row['cash_cost_cny'] = None if subscribed else row['charged']
            row['cost_basis'] = 'subscription-reference-valuation' if subscribed else 'public-price-calculation'
            row['cash_cost_status'] = 'not-attributed-per-call' if subscribed else 'calculated-not-provider-confirmed'
            self._check_reference_settlement()
        return result

    @_locked
    def reserve_non_token(self, unit, amount, *, label, purpose, usage, billing_mode="metered"):
        if self.stopped:
            raise ValueError("规划路由任务已停止")
        if unit not in self.ledgers:
            raise ValueError(f"缺少 {unit} 生产预算")
        if self.max_calls is not None and len(self.records) >= self.max_calls:
            raise ValueError("study-call-limit-exhausted")
        if self.reference_limit is not None and amount > self.remaining(REFERENCE):
            raise ValueError("参考成本预算不足")
        if billing_mode not in ('metered', 'subscription'):
            raise ValueError("未知计费模式")
        if billing_mode == 'subscription' and (self.reference_limit is None or unit != 'CNY'):
            raise ValueError("订阅估值需要新版参考成本账本")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            raise ValueError("媒体预留金额无效")
        ledger = self.ledgers[SUBSCRIPTION if billing_mode == 'subscription' else unit]
        with ledger.lock:
            if amount > ledger.remaining("production"):
                raise ValueError("production-budget-exhausted")
            ledger.charged["production"] += amount
            row = {"label": label, "model_id": usage.get("model"), "category": "production",
                   "provider": usage.get("provider"), "actual_model": usage.get("model"),
                   "billing_unit": unit, "billing_mode": billing_mode, "reserved": amount, "charged": amount,
                   "status": "reserved", "purpose": purpose, "usage_type": "non-token",
                   "usage": dict(usage)}
            # TaskCallBudget.stop() 会从自己的 records 重算已占用金额；非 token
            # 调用也必须登记在该单位账本，否则结束任务后总费用会被清零。
            ledger.records.append(row)
            self.records.append(row)
        return row

    @_locked
    def dispatch_non_token(self, row, *, operation_id, provider_task_id=None):
        if row.get("status") != "reserved" or self.stopped:
            raise ValueError("媒体操作不能派发")
        row.update(status="unknown-usage", call_id=operation_id, disposition="pending")
        if provider_task_id is not None:
            row["provider_task_id"] = provider_task_id

    @_locked
    def cancel_non_token(self, row):
        """释放尚未向提供方派发的预留；派发后不得使用。"""
        if row.get("status") != "reserved":
            raise ValueError("只有未派发媒体操作可以释放预留")
        ledger = self.ledgers[SUBSCRIPTION if row.get("billing_mode") == "subscription" else row["billing_unit"]]
        with ledger.lock:
            ledger.charged["production"] -= row["charged"]
            row.update(charged=0, status="cancelled-before-dispatch",
                       usage={"basis": row["usage"]["basis"], "actualUnits": 0},
                       disposition="cancelled")
        return row

    @_locked
    def settle_non_token(self, row, amount, usage, *, artifacts=None, status="billed"):
        if row.get("status") != "unknown-usage":
            raise ValueError("媒体操作回执已结算或尚未派发")
        unit = row["billing_unit"]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            self.stop()
            raise ValueError("媒体实际金额无效；保留预留")
        ledger = self.ledgers[SUBSCRIPTION if row.get("billing_mode") == "subscription" else unit]
        with ledger.lock:
            ledger.charged["production"] += amount - row["charged"]
            row.update(charged=amount, status=status, usage=dict(usage), disposition="accepted")
            if artifacts is not None:
                row["artifacts"] = list(artifacts)
            if amount > row["reserved"] + 1e-8 or ledger.charged["production"] > ledger.limits["production"]:
                self.stop()
                raise ValueError("媒体实际用量超过预留；执行已停止")
            if self.reference_limit is not None:
                subscribed = row.get('billing_mode') == 'subscription'
                row.update(reference_cost_cny=amount, cash_cost_cny=None if subscribed else amount,
                           cost_basis='subscription-reference-valuation' if subscribed else 'public-price-calculation',
                           cash_cost_status='not-attributed-per-call' if subscribed else 'calculated-not-provider-confirmed')
            self._check_reference_settlement()
        return row

    @_locked
    def stop(self):
        self.stopped = True
        for ledger in self.ledgers.values():
            ledger.stop()

    @_locked
    def snapshot(self):
        costs = {unit: dict(ledger.charged) for unit, ledger in self.ledgers.items() if unit != SUBSCRIPTION}
        from copy import deepcopy
        return costs, deepcopy(self.records)

    @_locked
    def reference_snapshot(self):
        if self.reference_limit is None:
            return None
        return {'currency': 'CNY', 'limit': self.reference_limit,
                'occupied': sum(ledger.charged['production'] for ledger in self.ledgers.values()),
                'basis': 'public-reference-valuation', 'includesCashCalls': True}
