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

    def stop(self):
        self.stopped = True
        for ledger in self.ledgers.values():
            ledger.stop()

    def snapshot(self):
        costs = {unit: dict(ledger.charged) for unit, ledger in self.ledgers.items()}
        from copy import deepcopy
        return costs, deepcopy(self.records)
