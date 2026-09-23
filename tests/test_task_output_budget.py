"""任务级输出总量门：保守预留且不改变费用账本。"""
import pytest
from dataclasses import replace

from refractrouter.task_budget import TaskCallBudget
from tests.test_native_tool_runtime import Client, real_model


def test_total_output_limit_rejects_second_conservative_reservation():
    model = real_model()
    budget = TaskCallBudget(Client([]), 100, 100, max_total_output_tokens=model.max_output_tokens)
    budget.reserve(model, [{'role': 'user', 'content': 'a'}], label='first')
    with pytest.raises(ValueError, match='task-output-budget-exhausted'):
        budget.reserve(model, [{'role': 'user', 'content': 'b'}], label='second')


def test_total_output_limit_is_optional():
    model = real_model()
    budget = TaskCallBudget(Client([]), 100, 100)
    budget.reserve(model, [{'role': 'user', 'content': 'a'}], label='first')
    budget.reserve(model, [{'role': 'user', 'content': 'b'}], label='second')


def test_remaining_cost_caps_node_output_before_dispatch():
    model = replace(real_model(), input_cost_per_1k=0, output_cost_per_1k=1,
                    max_output_tokens=10000)
    budget = TaskCallBudget(Client([]), 2, 2, adaptive_output_reservation=True)
    reserved = budget.reserve(model, [{'role': 'user', 'content': 'a'}], label='bounded')
    assert reserved.model.max_output_tokens == 2000
    assert reserved.row['reserved_output_tokens'] == 2000
    assert reserved.row['reserved'] == 2
