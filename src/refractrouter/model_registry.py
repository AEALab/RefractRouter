from __future__ import annotations

from collections.abc import Iterable, Mapping

from .schemas import ModelSpec


class ModelRegistry:
    """Registry of candidate models used by routing strategies."""

    def __init__(self, models: Iterable[ModelSpec]):
        self._models = {model.model_id: model for model in models}
        if not self._models:
            raise ValueError("ModelRegistry requires at least one model")

    @classmethod
    def from_mapping(cls, data: Mapping[str, Mapping[str, object]]) -> "ModelRegistry":
        models = []
        for model_id, values in data.items():
            models.append(
                ModelSpec(
                    model_id=model_id,
                    provider=str(values["provider"]),
                    input_cost_per_1k_usd=float(values["input_cost_per_1k_usd"]),
                    output_cost_per_1k_usd=float(values["output_cost_per_1k_usd"]),
                    capability=float(values["capability"]),
                    tags=tuple(str(tag) for tag in values.get("tags", [])),
                    api_model=str(values["api_model"]) if values.get("api_model") else None,
                    base_url=str(values["base_url"]) if values.get("base_url") else None,
                    api_key_env=str(values["api_key_env"]) if values.get("api_key_env") else None,
                    cached_input_cost_per_1k_usd=(
                        float(values["cached_input_cost_per_1k_usd"])
                        if values.get("cached_input_cost_per_1k_usd") is not None
                        else None
                    ),
                    context_window=(
                        int(values["context_window"])
                        if values.get("context_window") is not None
                        else None
                    ),
                    max_output_tokens=(
                        int(values["max_output_tokens"])
                        if values.get("max_output_tokens") is not None
                        else None
                    ),
                    snapshot_date=(
                        str(values["snapshot_date"]) if values.get("snapshot_date") else None
                    ),
                    role=str(values.get("role", "candidate")),
                    request_options=dict(values.get("request_options", {})),
                )
            )
        return cls(models)

    def get(self, model_id: str) -> ModelSpec:
        if model_id not in self._models:
            raise KeyError(f"Unknown model: {model_id}")
        return self._models[model_id]

    def list(self) -> tuple[ModelSpec, ...]:
        return tuple(self._models.values())

    def cheapest(self) -> ModelSpec:
        return min(
            self._models.values(),
            key=lambda model: (
                model.input_cost_per_1k_usd + model.output_cost_per_1k_usd,
                model.model_id,
            ),
        )

    def strongest(self) -> ModelSpec:
        return max(
            self._models.values(),
            key=lambda model: (model.capability, -model.input_cost_per_1k_usd, model.model_id),
        )
