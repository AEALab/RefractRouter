"""本地结构化 Judge 的版本化后端边界；配置不能指定任意可导入代码。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


CONTRACT = "local-decision-backends-v1"
OPERATION_METHODS = {
    "task": "decide",
    "stage": "decide_stage",
    "advisor": "decide_advisor",
    "escalation": "decide_escalation",
    "decomposition": "decide_decomposition",
}


class DecisionBackend(Protocol):
    """后端实现对应操作的方法，并返回现有 LocalDecisionResult 合同。"""
    model: str
    cold_start_ms: float | None


@dataclass(frozen=True)
class BackendSpec:
    id: str
    label: str
    operations: tuple[str, ...]
    question_types: tuple[str, ...]
    artifact_files: tuple[str, ...]
    dependency_module: str
    allowed_sources: tuple[str, ...]
    manifest_name: str
    factory: Callable[[dict], DecisionBackend]


def _load_laya(config):
    from .planning_decision import LayaDecisionAdapter
    return LayaDecisionAdapter(config)


_LAYA = BackendSpec(
    id="laya-mlx", label="Laya-MLX", operations=tuple(OPERATION_METHODS),
    question_types=("choice", "score", "noul"),
    artifact_files=("model.safetensors", "mlx_config.json", "rl_agent_config.json",
                    "encoder/config.json"),
    dependency_module="laya_mlx",
    allowed_sources=("aac6fef/laya-multilingual-mlx", "aac6fef/laya-mlx",
                     "aac6fef/laya-typed-decisions-mlx"),
    manifest_name="refractrouter-laya.json",
    factory=_load_laya,
)
_BACKENDS = {_LAYA.id: _LAYA}


def require_backend(adapter, operation=None):
    """只认可核心登记的本地后端与明确声明的判别操作。"""
    spec = _BACKENDS.get(adapter) if isinstance(adapter, str) else None
    if spec is None:
        raise ValueError(f"本地 Judge 后端未登记：{adapter}")
    if operation is not None and operation not in spec.operations:
        raise ValueError(f"本地 Judge 后端 {adapter} 不支持 {operation}")
    return spec


def backend_catalog():
    return {"contract": CONTRACT, "backends": [
        {"id": spec.id, "label": spec.label, "operations": list(spec.operations),
         "questionTypes": list(spec.question_types), "deployment": "local-artifact"}
        for spec in _BACKENDS.values()]}


def create_backend(config):
    """工厂由核心代码固定；配置只能选已登记 ID，不能指定模块路径。"""
    spec = require_backend(config.get("adapter"))
    return spec.factory(config)


def invoke_backend(backend: DecisionBackend, operation, request, *, adapter):
    require_backend(adapter, operation)
    method = getattr(backend, OPERATION_METHODS[operation], None)
    if not callable(method):
        raise ValueError(f"本地 Judge 后端 {adapter} 未实现 {operation} 合同")
    return method(request)
