"""规划路由的多单位预算；各单位独立预留，调用次数与停止状态共享。"""
from .task_budget import TaskCallBudget


class PlanningBudget:
    def __init__(self, limits, *, max_calls=None):
        self.ledgers = {unit: TaskCallBudget(None, None if limit == 0 else limit, 1,
            capture_payload=True) for unit, limit in limits.items()}
        self.max_calls = max_calls
        self.records = []
        self.stopped = False

    def remaining(self, unit):
        return self.ledgers[unit].remaining()

    def reserve(self, model, messages, **kwargs):
        if self.stopped:
            raise ValueError("规划路由任务已停止")
        if self.max_calls is not None and len(self.records) >= self.max_calls:
            raise ValueError("study-call-limit-exhausted")
        unit = model.billing_unit
        if unit not in self.ledgers:
            raise ValueError(f"缺少 {unit} 生产预算")
        reservation = self.ledgers[unit].reserve(model, messages, **kwargs)
        reservation.row["billing_unit"] = unit
        self.records.append(reservation.row)
        return reservation

    def dispatch(self, reservation, **kwargs):
        return self.ledgers[reservation.model.billing_unit].dispatch(reservation, **kwargs)

    def settle(self, reservation, response):
        return self.ledgers[reservation.model.billing_unit].settle(reservation, response)

    def reserve_non_token(self, unit, amount, *, label, purpose, usage):
        if self.stopped:
            raise ValueError("规划路由任务已停止")
        if unit not in self.ledgers:
            raise ValueError(f"缺少 {unit} 生产预算")
        if self.max_calls is not None and len(self.records) >= self.max_calls:
            raise ValueError("study-call-limit-exhausted")
        ledger = self.ledgers[unit]
        with ledger.lock:
            if amount > ledger.remaining("production"):
                raise ValueError("production-budget-exhausted")
            ledger.charged["production"] += amount
            row = {"label": label, "model_id": usage.get("model"), "category": "production",
                   "provider": usage.get("provider"), "actual_model": usage.get("model"),
                   "billing_unit": unit, "reserved": amount, "charged": amount,
                   "status": "reserved", "purpose": purpose, "usage_type": "non-token",
                   "usage": dict(usage)}
            self.records.append(row)
        return row

    def dispatch_non_token(self, row, *, operation_id, provider_task_id=None):
        if row.get("status") != "reserved" or self.stopped:
            raise ValueError("媒体操作不能派发")
        row.update(status="unknown-usage", call_id=operation_id, disposition="pending")
        if provider_task_id is not None:
            row["provider_task_id"] = provider_task_id

    def cancel_non_token(self, row):
        """释放尚未向提供方派发的预留；派发后不得使用。"""
        if row.get("status") != "reserved":
            raise ValueError("只有未派发媒体操作可以释放预留")
        ledger = self.ledgers[row["billing_unit"]]
        with ledger.lock:
            ledger.charged["production"] -= row["charged"]
            row.update(charged=0, status="cancelled-before-dispatch",
                       usage={"basis": row["usage"]["basis"], "actualUnits": 0},
                       disposition="cancelled")
        return row

    def settle_non_token(self, row, amount, usage, *, artifacts=None, status="billed"):
        if row.get("status") != "unknown-usage":
            raise ValueError("媒体操作回执已结算或尚未派发")
        unit = row["billing_unit"]
        ledger = self.ledgers[unit]
        with ledger.lock:
            ledger.charged["production"] += amount - row["charged"]
            row.update(charged=amount, status=status, usage=dict(usage), disposition="accepted")
            if artifacts is not None:
                row["artifacts"] = list(artifacts)
            if amount > row["reserved"] + 1e-8 or ledger.charged["production"] > ledger.limits["production"]:
                self.stop()
                raise ValueError("媒体实际用量超过预留；执行已停止")
        return row

    def stop(self):
        self.stopped = True
        for ledger in self.ledgers.values():
            ledger.stop()

    def snapshot(self):
        costs = {unit: dict(ledger.charged) for unit, ledger in self.ledgers.items()}
        from copy import deepcopy
        return costs, deepcopy(self.records)
