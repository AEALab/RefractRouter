from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from graphlib import TopologicalSorter

from .adapters import ModelAdapter
from .model_registry import ModelRegistry
from .schemas import NodeResult, TaskDAG, TaskResult
from .scoring import score_node, score_task
from .evidence_state import evidence_artifact, uses_evidence_state


class GraphExecutor:
    """Execute a fixed task DAG with per-node model assignments."""

    def __init__(
        self,
        task: TaskDAG,
        adapter: ModelAdapter,
        registry: ModelRegistry,
    ):
        self.task = task
        self.adapter = adapter
        self.registry = registry
        self._nodes = {node.node_id: node for node in task.nodes}
        self._validate_dag()

    def _validate_dag(self) -> None:
        if not self.task.nodes:
            raise ValueError("TaskDAG requires at least one node")
        node_ids = set(self._nodes)
        for node in self.task.nodes:
            for parent in node.parents:
                if parent not in node_ids:
                    raise ValueError(f"Unknown parent node: {parent}")

    def execute(self, assignments: Mapping[str, str], strategy: str) -> TaskResult:
        context: dict[str, str] = {}
        results: list[NodeResult] = []
        results_by_node: dict[str, NodeResult] = {}
        graph = {node.node_id: set(node.parents) for node in self.task.nodes}
        sorter = TopologicalSorter(graph)
        for node_id in sorter.static_order():
            model_id = assignments.get(node_id)
            if model_id is None:
                raise ValueError(f"Missing model assignment for node: {node_id}")
            node = self._nodes[node_id]
            failed_parents = [
                parent
                for parent in node.parents
                if results_by_node[parent].status != "ok"
            ]
            if failed_parents:
                result = NodeResult(
                    node_id=node_id,
                    node_type=node.node_type,
                    model_id=model_id,
                    output="",
                    input_tokens=0,
                    output_tokens=0,
                    cost=0.0,
                    billing_unit=self.registry.get(model_id).billing_unit,
                    latency_ms=0,
                    status="failed",
                    failure_type="upstream-failure",
                    attempts=0,
                    error_message=f"Failed parents: {', '.join(failed_parents)}",
                )
            else:
                result = self.probe_node(node_id, model_id, context)
            results.append(result)
            results_by_node[node_id] = result
            context[node_id] = result.output
        render_nodes = [node for node in self.task.nodes if node.node_type == "rendering"]
        final_node_id = render_nodes[-1].node_id if render_nodes else self.task.nodes[-1].node_id
        final_output = context.get(final_node_id, "")
        task_score = score_task(self.task, tuple(results), final_output)
        total_cost = sum(result.cost for result in results)
        billing_units = {result.billing_unit for result in results}
        if len(billing_units) != 1:
            raise ValueError("Task results contain mixed billing units")
        critical_path = self._critical_path_latency(results)
        failure_types = tuple(
            result.failure_type for result in results if result.failure_type is not None
        )
        return TaskResult(
            task_id=self.task.task_id,
            strategy=strategy,
            model_assignments=dict(assignments),
            node_results=tuple(results),
            final_output=final_output,
            task_score=task_score,
            total_cost=round(total_cost, 6),
            billing_unit=next(iter(billing_units)),
            critical_path_latency_ms=critical_path,
            failure_types=failure_types,
        )

    def probe_node(
        self,
        node_id: str,
        model_id: str,
        context: Mapping[str, str],
    ) -> NodeResult:
        """Run one node against a caller-supplied frozen upstream context."""
        if node_id not in self._nodes:
            raise KeyError(f"Unknown node: {node_id}")
        node = self._nodes[node_id]
        missing_parents = [parent for parent in node.parents if parent not in context]
        if missing_parents:
            raise ValueError(
                f"Missing upstream context for {node_id}: {', '.join(missing_parents)}"
            )
        model = self.registry.get(model_id)
        if uses_evidence_state(self.task) and node.node_type in {
                "synthesis", "generation", "rendering", "verification"}:
            try:
                evidence_artifact(self.task, context)
            except ValueError as exc:
                return NodeResult(node_id, node.node_type, model_id, "", 0, 0, 0, 0,
                                  billing_unit=model.billing_unit, status="failed", attempts=0,
                                  failure_type="invalid-reference-context", error_message=str(exc))
        prompt = self._build_prompt(node, dict(context))
        result = self.adapter.invoke(self.task, node, prompt, dict(context), model)
        return self._replace_score(result, score_node(self.task, node, result.output, context) if result.status == "ok" else 0.0)

    @staticmethod
    def _replace_score(result: NodeResult, score: float) -> NodeResult:
        return NodeResult(
            node_id=result.node_id,
            node_type=result.node_type,
            model_id=result.model_id,
            output=result.output,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost=result.cost,
            billing_unit=result.billing_unit,
            latency_ms=result.latency_ms,
            score=score,
            status=result.status,
            failure_type=result.failure_type,
            cached_input_tokens=result.cached_input_tokens,
            reasoning_tokens=result.reasoning_tokens,
            attempts=result.attempts,
            finish_reason=result.finish_reason,
            request_id=result.request_id,
            error_message=result.error_message,
        )

    def _build_prompt(self, node, context: dict[str, str]) -> str:
        parent_outputs = "\n".join(
            f"[{parent}]\n{context[parent]}" for parent in node.parents if parent in context
        )
        return f"{node.prompt_template}\n\n{parent_outputs}".strip()

    def _critical_path_latency(self, results: list[NodeResult]) -> int:
        latency = {result.node_id: result.latency_ms for result in results}
        best: dict[str, int] = {}
        graph = {node.node_id: set(node.parents) for node in self.task.nodes}
        sorter = TopologicalSorter(graph)
        for node_id in sorter.static_order():
            parents = graph[node_id]
            parent_max = max((best[parent] for parent in parents), default=0)
            best[node_id] = parent_max + latency[node_id]
        return max(best.values(), default=0)
