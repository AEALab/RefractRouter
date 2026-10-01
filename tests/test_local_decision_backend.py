"""本地判别后端合同与未登记后端的派发边界。"""
from dataclasses import replace

import pytest

import refractrouter.local_decision_backend as local_backends
from refractrouter.local_decision_backend import (backend_catalog, create_backend,
                                                   invoke_backend, require_backend)
from refractrouter.local_judge_service import LocalJudgeProcess
from refractrouter.planning_runtime import PlanningRuntime


def test_catalog_declares_registered_capabilities_without_claiming_quality(tmp_path):
    catalog = backend_catalog()
    assert catalog["contract"] == "local-decision-backends-v1"
    assert catalog["backends"] == [{
        "id": "laya-mlx", "label": "Laya-MLX",
        "operations": ["task", "stage", "advisor", "escalation", "decomposition"],
        "questionTypes": ["choice", "score", "noul"],
        "deployment": "local-artifact"}]
    assert PlanningRuntime(tmp_path).handle({"op": "local-backends"}) == catalog


def test_unknown_backend_rejected_before_loading_or_dispatch():
    with pytest.raises(ValueError, match="后端未登记"):
        create_backend({"adapter": "unverified-jev", "modelPath": "/tmp/unused"})
    with pytest.raises(ValueError, match="后端未登记"):
        require_backend("unverified-jev", "task")


def test_loaded_instances_are_separated_by_backend_and_weight_source():
    base = {"adapter": "laya-mlx", "modelPath": "/models/shared",
            "sourceModel": "publisher/model-a", "revision": "rev1"}
    first = PlanningRuntime.local_judge_key(base)
    assert first != PlanningRuntime.local_judge_key({**base, "sourceModel": "publisher/model-b"})
    assert first != PlanningRuntime.local_judge_key({**base, "revision": "rev2"})
    assert first != PlanningRuntime.local_judge_key({**base, "adapter": "future-backend"})


def test_all_strategies_use_one_backend_result_boundary():
    class FakeBackend:
        def decide(self, request): return ("task", request)
        def decide_stage(self, request): return ("stage", request)
        def decide_advisor(self, request): return ("advisor", request)
        def decide_escalation(self, request): return ("escalation", request)
        def decide_decomposition(self, request): return ("decomposition", request)

    backend = FakeBackend()
    for operation in backend_catalog()["backends"][0]["operations"]:
        assert invoke_backend(backend, operation, {"fixture": 1}, adapter="laya-mlx") == (
            operation, {"fixture": 1})
    with pytest.raises(ValueError, match="不支持"):
        invoke_backend(backend, "invented", {}, adapter="laya-mlx")


def test_registered_replacement_uses_its_factory_and_declared_operations(monkeypatch):
    class Replacement:
        def decide(self, request): return ("replacement", request)

    spec = replace(require_backend("laya-mlx"), id="fixture-local", label="夹具后端",
                   operations=("task",), factory=lambda _config: Replacement())
    monkeypatch.setitem(local_backends._BACKENDS, spec.id, spec)
    loaded = create_backend({"adapter": spec.id})
    assert invoke_backend(loaded, "task", {"id": 1}, adapter=spec.id) == (
        "replacement", {"id": 1})
    with pytest.raises(ValueError, match="不支持 stage"):
        invoke_backend(loaded, "stage", {}, adapter=spec.id)


def test_worker_rejects_unregistered_backend_without_loading_module():
    service = LocalJudgeProcess()
    try:
        with pytest.raises(ValueError, match="后端未登记"):
            service.call("load", "fixture", {"adapter": "unknown-module"}, timeout_ms=5000)
    finally:
        service.close()
