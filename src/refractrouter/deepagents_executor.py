from __future__ import annotations

from typing import Any

from .adapters import ModelAdapter
from .graph_executor import GraphExecutor
from .model_registry import ModelRegistry
from .schemas import TaskDAG, TaskResult


class DeepAgentsGraphExecutor:
    """Optional DeepAgents-backed executor.

    The v0.1 graph is fixed by ``TaskDAG``. This wrapper intentionally does not
    enable DeepAgents' autonomous planner or dynamic sub-agent generation.
    """

    def __init__(
        self,
        task: TaskDAG,
        adapter: ModelAdapter,
        registry: ModelRegistry,
    ):
        self.task = task
        self.adapter = adapter
        self.registry = registry
        self._fallback = GraphExecutor(task, adapter, registry)

    def execute(self, assignments: dict[str, str], strategy: str) -> TaskResult:
        try:
            from deepagents import create_deep_agent
            from langchain_core.language_models.fake_chat_models import (
                FakeMessagesListChatModel,
            )
            from langchain_core.messages import AIMessage, HumanMessage
        except ImportError as exc:
            raise RuntimeError(
                "DeepAgentsGraphExecutor requires the optional 'deepagents' extra. "
                "Install with: uv sync --extra deepagents"
            ) from exc

        captured: dict[str, TaskResult] = {}

        def execute_refractrouter_dag() -> dict[str, str | float]:
            """Execute the fixed RefractRouter DAG and return a summary."""
            result = self._fallback.execute(assignments, strategy)
            captured["result"] = result
            return {
                "task_id": result.task_id,
                "strategy": result.strategy,
                "task_score": result.task_score,
            }

        class DeterministicToolModel(FakeMessagesListChatModel):
            def bind_tools(self, tools: Any, **kwargs: Any) -> "DeterministicToolModel":
                return self

        # The offline model makes exactly one deterministic tool call. This keeps
        # the DeepAgents runtime in the execution path without adding model noise.
        agent = create_deep_agent(
            model=DeterministicToolModel(
                responses=(
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "execute_refractrouter_dag",
                                "args": {},
                                "id": "refractrouter-dag",
                            }
                        ],
                    ),
                    AIMessage(content="Fixed DAG execution complete."),
                )
            ),
            tools=[execute_refractrouter_dag],
            system_prompt="Execute RefractRouter only through the fixed DAG tool.",
            name="refractrouter-v0.1",
        )
        agent.invoke(
            {
                "messages": [
                    HumanMessage(content=f"Execute task {self.task.task_id} with strategy {strategy}.")
                ]
            }
        )
        if "result" not in captured:
            raise RuntimeError("DeepAgents execution did not invoke the fixed DAG tool")
        return captured["result"]
