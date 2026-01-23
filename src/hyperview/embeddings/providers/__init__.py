"""Embedding provider abstraction for HyperView."""

from __future__ import annotations

import hashlib
from importlib import import_module
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from hyperview.core.sample import Sample


@dataclass
class ModelSpec:
    """Structured specification for an embedding model.

    Attributes:
        provider: Provider identifier (e.g., "embed_anything", "hycoclip")
        model_id: Model identifier (HuggingFace model_id, checkpoint path, etc.)
        checkpoint: Optional checkpoint path or URL for weight-only models
        config_path: Optional config path for models that need it
        output_geometry: Geometry of the embedding space ("euclidean", "hyperboloid")
        curvature: Hyperbolic curvature (only relevant for hyperbolic geometries)
    """

    provider: str
    model_id: str
    checkpoint: str | None = None
    config_path: str | None = None
    output_geometry: str = "euclidean"
    curvature: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d: dict[str, Any] = {
            "provider": self.provider,
            "model_id": self.model_id,
            "geometry": self.output_geometry,
        }
        if self.checkpoint:
            d["checkpoint"] = self.checkpoint
        if self.config_path:
            d["config_path"] = self.config_path
        if self.curvature is not None:
            d["curvature"] = self.curvature
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModelSpec:
        """Create from dict (e.g., loaded from JSON)."""
        return cls(
            provider=d["provider"],
            model_id=d["model_id"],
            checkpoint=d.get("checkpoint"),
            config_path=d.get("config_path"),
            output_geometry=d.get("geometry", "euclidean"),
            curvature=d.get("curvature"),
        )

    def content_hash(self) -> str:
        """Generate a short hash of the spec for collision-resistant keys."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:12]


class BaseEmbeddingProvider(ABC):
    """Base class for embedding providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider."""
        ...

    @abstractmethod
    def compute_embeddings(
        self,
        samples: list[Sample],
        model_spec: ModelSpec,
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Compute embeddings for samples.

        Returns:
            Array of shape (N, D) where N is len(samples) and D is embedding dim.
        """
        ...

    def get_space_config(self, model_spec: ModelSpec, dim: int) -> dict[str, Any]:
        """Get config dict for SpaceInfo.config_json.

        Args:
            model_spec: Model specification.
            dim: Embedding dimension.

        Returns:
            Config dict with provider, geometry, model_id, dim, and any extras.
        """
        return {
            **model_spec.to_dict(),
            "dim": dim,
        }


_PROVIDER_CLASSES: dict[str, type[BaseEmbeddingProvider]] = {}
_PROVIDER_INSTANCES: dict[str, BaseEmbeddingProvider] = {}


_KNOWN_PROVIDER_MODULES: dict[str, str] = {
    "embed_anything": "hyperview.embeddings.providers.embed_anything",
    "hycoclip": "hyperview.embeddings.providers.hycoclip",
    "hycoclip_onnx": "hyperview.embeddings.providers.hycoclip_onnx",
}


def register_provider(provider_id: str, provider_class: type[BaseEmbeddingProvider]) -> None:
    """Register a new embedding provider class."""
    _PROVIDER_CLASSES[provider_id] = provider_class
    # Clear cached instance if re-registering
    _PROVIDER_INSTANCES.pop(provider_id, None)


def _try_auto_register(provider_id: str, *, silent: bool = True) -> None:
    """Attempt to auto-register a provider by importing its module.

    Args:
        provider_id: Provider identifier.
        silent: If True, swallow ImportError (used when listing providers).
            If False, let ImportError propagate (used when explicitly requesting
            a provider via get_provider()).
    """

    module_name = _KNOWN_PROVIDER_MODULES.get(provider_id)
    if not module_name:
        return

    if silent:
        try:
            import_module(module_name)
        except ImportError:
            return
    else:
        import_module(module_name)


def get_provider(provider_id: str) -> BaseEmbeddingProvider:
    """Get a provider singleton instance by ID.

    Providers are cached to preserve model state across calls.
    """
    if provider_id not in _PROVIDER_CLASSES:
        _try_auto_register(provider_id, silent=False)

    if provider_id not in _PROVIDER_CLASSES:
        available = ", ".join(sorted(_PROVIDER_CLASSES.keys())) or "(none registered)"
        raise ValueError(
            f"Unknown embedding provider: '{provider_id}'. "
            f"Available: {available}"
        )

    if provider_id not in _PROVIDER_INSTANCES:
        _PROVIDER_INSTANCES[provider_id] = _PROVIDER_CLASSES[provider_id]()

    return _PROVIDER_INSTANCES[provider_id]


def list_providers() -> list[str]:
    """List available provider IDs."""
    # Trigger auto-registration for known providers
    for pid in _KNOWN_PROVIDER_MODULES:
        _try_auto_register(pid, silent=True)
    return list(_PROVIDER_CLASSES.keys())


def make_provider_aware_space_key(model_spec: ModelSpec) -> str:
    """Generate a collision-resistant space_key from a ModelSpec.

    Format: {provider}__{slugified_model_id}__{content_hash}
    """
    from hyperview.storage.schema import slugify_model_id

    slug = slugify_model_id(model_spec.model_id)
    content_hash = model_spec.content_hash()

    return f"{model_spec.provider}__{slug}__{content_hash}"


__all__ = [
    "BaseEmbeddingProvider",
    "ModelSpec",
    "get_provider",
    "list_providers",
    "make_provider_aware_space_key",
    "register_provider",
]
