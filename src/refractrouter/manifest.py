from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .model_registry import ModelRegistry
from .schemas import ModelSpec


_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass(frozen=True, slots=True)
class ModelManifest:
    schema_version: str
    pricing_snapshot_date: str
    billing_unit: str
    models: tuple[ModelSpec, ...]
    documentation_urls: tuple[str, ...] = ()

    @property
    def candidates(self) -> tuple[ModelSpec, ...]:
        return tuple(model for model in self.models if model.role == "candidate")

    @property
    def judge(self) -> ModelSpec:
        judges = tuple(model for model in self.models if model.role == "judge")
        if len(judges) != 1:
            raise ValueError("Model manifest requires exactly one judge model")
        return judges[0]

    def candidate_registry(self) -> ModelRegistry:
        return ModelRegistry(self.candidates)


def load_model_manifest(path: Path) -> ModelManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "v0.2":
        raise ValueError("Unsupported model manifest schema_version")
    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("Model manifest defaults must be an object")
    models_data = data.get("models")
    if not isinstance(models_data, list):
        raise ValueError("Model manifest models must be an array")
    models = tuple(_load_model(item, defaults) for item in models_data)
    billing_units = {model.billing_unit for model in models}
    if len(billing_units) != 1:
        raise ValueError("Model manifest requires one billing_unit across all models")
    candidate_count = sum(model.role == "candidate" for model in models)
    judge_count = sum(model.role == "judge" for model in models)
    if candidate_count < 3:
        raise ValueError("Model manifest requires at least three candidate models")
    if judge_count != 1:
        raise ValueError("Model manifest requires exactly one judge model")
    model_ids = [model.model_id for model in models]
    if len(model_ids) != len(set(model_ids)):
        raise ValueError("Model manifest model_id values must be unique")
    return ModelManifest(
        schema_version="v0.2",
        pricing_snapshot_date=str(data["pricing_snapshot_date"]),
        billing_unit=next(iter(billing_units)),
        models=models,
        documentation_urls=tuple(str(url) for url in data.get("documentation_urls", [])),
    )


def _load_model(data: object, defaults: Mapping[str, Any]) -> ModelSpec:
    if not isinstance(data, dict):
        raise ValueError("Each model manifest entry must be an object")
    merged = {**defaults, **data}
    api_key_env = str(merged["api_key_env"])
    if not _ENV_NAME.fullmatch(api_key_env):
        raise ValueError(f"Invalid api_key_env: {api_key_env}")
    role = str(merged.get("role", "candidate"))
    if role not in {"candidate", "judge"}:
        raise ValueError(f"Unsupported model role: {role}")
    request_options = merged.get("request_options", {})
    if not isinstance(request_options, dict):
        raise ValueError("request_options must be an object")
    json_mode_strategy = merged.get("json_mode_strategy", "json-object-hint")
    if json_mode_strategy not in {"json-object-hint", "prompt-only"}:
        raise ValueError("Unsupported json_mode_strategy")
    billing_unit = str(merged["billing_unit"]).upper()
    if billing_unit not in {"USD", "AFP"}:
        raise ValueError(f"Unsupported billing_unit: {billing_unit}")
    wire_api = str(merged.get("wire_api", "chat-completions"))
    if wire_api not in {"chat-completions", "dsh-llm"}:
        raise ValueError(f"Unsupported wire_api: {wire_api}")
    base_url = merged.get("base_url")
    if wire_api == "chat-completions" and not base_url:
        raise ValueError("chat-completions models require base_url")
    return ModelSpec(
        model_id=str(merged["model_id"]),
        provider=str(merged["provider"]),
        api_model=str(merged["api_model"]),
        base_url=str(base_url).rstrip("/") if base_url else None,
        api_key_env=api_key_env,
        input_cost_per_1k=float(merged["input_cost_per_1k"]),
        cached_input_cost_per_1k=float(merged["cached_input_cost_per_1k"]),
        output_cost_per_1k=float(merged["output_cost_per_1k"]),
        capability=float(merged["capability"]),
        billing_unit=billing_unit,
        context_window=int(merged["context_window"]),
        max_output_tokens=int(merged["max_output_tokens"]),
        snapshot_date=str(merged["snapshot_date"]),
        role=role,
        wire_api=wire_api,
        tags=tuple(str(tag) for tag in merged.get("tags", [])),
        request_options=dict(request_options),
        json_mode_strategy=json_mode_strategy,
    )
