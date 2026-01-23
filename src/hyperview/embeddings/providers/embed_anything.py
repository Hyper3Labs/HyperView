"""EmbedAnything embedding provider - default lightweight provider."""

from __future__ import annotations

from typing import Any

import numpy as np

from hyperview.core.sample import Sample
from hyperview.embeddings.providers import (
    BaseEmbeddingProvider,
    ModelSpec,
    register_provider,
)

__all__ = ["EmbedAnythingProvider"]


class EmbedAnythingProvider(BaseEmbeddingProvider):
    """Default embedding provider using EmbedAnything.

    Supports HuggingFace vision models via EmbedAnything's inference engine.
    Model is cached per model_id to avoid repeated initialization.
    """

    def __init__(self) -> None:
        self._computers: dict[str, Any] = {}  # model_id -> EmbeddingComputer

    @property
    def provider_id(self) -> str:
        return "embed_anything"

    def _get_computer(self, model_id: str) -> Any:
        """Get or create an EmbeddingComputer for the given model_id."""
        if model_id not in self._computers:
            from hyperview.embeddings.compute import EmbeddingComputer

            self._computers[model_id] = EmbeddingComputer(model=model_id)
        return self._computers[model_id]

    def compute_embeddings(
        self,
        samples: list[Sample],
        model_spec: ModelSpec,
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Compute embeddings using EmbedAnything."""
        computer = self._get_computer(model_spec.model_id)
        embeddings = computer.compute_batch(
            samples, batch_size=batch_size, show_progress=show_progress
        )
        return np.array(embeddings, dtype=np.float32)


# Auto-register on import
register_provider("embed_anything", EmbedAnythingProvider)
