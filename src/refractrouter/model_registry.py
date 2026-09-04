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
