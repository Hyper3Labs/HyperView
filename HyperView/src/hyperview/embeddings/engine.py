"""Embedding spec + engine built on LanceDB's embedding registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

# Register HyperView providers into LanceDB registry.
import hyperview.embeddings.providers.lancedb_providers as _lancedb_providers  # noqa: F401

__all__ = [
    "EmbeddingSpec",
    "EmbeddingEngine",
    "get_engine",
    "list_embedding_providers",
    "get_provider_info",
]

HYPERBOLIC_PROVIDERS = frozenset({"hyper-models"})


@dataclass
class EmbeddingSpec:
    """Specification for an embedding model.

    All providers live in the LanceDB registry. HyperView's custom providers
    (embed-anything, hyper-models) are registered on import.

    Attributes:
        provider: Provider identifier (e.g., 'embed-anything', 'hyper-models', 'open-clip')
        model_id: Model identifier (HuggingFace model_id, checkpoint name, etc.)
        checkpoint: Optional checkpoint path/URL for weight-only models
        provider_kwargs: Additional kwargs passed to the embedding function
        modality: What input type this embedder handles
    """

    provider: str
    model_id: str | None = None
    checkpoint: str | None = None
    provider_kwargs: dict[str, Any] = field(default_factory=dict)
    modality: Literal["image", "text", "multimodal"] = "image"

    @property
    def geometry(self) -> Literal["euclidean", "hyperboloid"]:
        """Get the output geometry for this spec."""

        if self.provider == "hyper-models":
            model_name = self.model_id or self.provider_kwargs.get("name")
            if model_name is None:
                return "hyperboloid"
            import hyper_models

            geom = str(hyper_models.get_model_info(str(model_name)).geometry)
            return "hyperboloid" if geom in ("hyperboloid", "poincare") else "euclidean"

        if self.provider in HYPERBOLIC_PROVIDERS:
            return "hyperboloid"
        return "euclidean"

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict for persistence."""
        d: dict[str, Any] = {
            "provider": self.provider,
            "modality": self.modality,
            "geometry": self.geometry,
        }
        if self.model_id:
            d["model_id"] = self.model_id
        if self.checkpoint:
            d["checkpoint"] = self.checkpoint
        if self.provider_kwargs:
            d["provider_kwargs"] = self.provider_kwargs
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EmbeddingSpec:
        """Create from dict (e.g., loaded from JSON)."""
        return cls(
            provider=d["provider"],
            model_id=d.get("model_id"),
            checkpoint=d.get("checkpoint"),
            provider_kwargs=d.get("provider_kwargs", {}),
            modality=d.get("modality", "image"),
        )

    def content_hash(self) -> str:
        """Generate a short hash of the spec for collision-resistant keys."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def make_space_key(self) -> str:
        """Generate a collision-resistant space_key from this spec.

        Format: {provider}__{slugified_model_id}__{content_hash}
        """
        from hyperview.storage.schema import slugify_model_id

        model_part = self.model_id or self.checkpoint or "default"
        slug = slugify_model_id(model_part)
        content_hash = self.content_hash()
        return f"{self.provider}__{slug}__{content_hash}"


class EmbeddingEngine:
    """Embedding engine using LanceDB registry.

    All providers are accessed through the LanceDB embedding registry.
    HyperView providers are registered automatically on import.
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}  # spec_hash -> embedding function

    def get_function(self, spec: EmbeddingSpec) -> Any:
        """Get an embedding function from LanceDB registry.

        Args:
            spec: Embedding specification.

        Returns:
            LanceDB EmbeddingFunction instance.

        Raises:
            ValueError: If provider not found in registry.
        """
        cache_key = spec.content_hash()
        if cache_key in self._cache:
            return self._cache[cache_key]

        from lancedb.embeddings import get_registry

        registry = get_registry()

        # Get provider factory from registry
        try:
            factory = registry.get(spec.provider)
        except KeyError:
            available = list_embedding_providers()
            raise ValueError(
                f"Unknown provider: '{spec.provider}'. "
                f"Available: {', '.join(sorted(available))}"
            ) from None

        create_kwargs: dict[str, Any] = {}
        if spec.model_id:
            create_kwargs["name"] = spec.model_id

        if spec.checkpoint:
            create_kwargs["checkpoint"] = spec.checkpoint

        create_kwargs.update(spec.provider_kwargs)

        try:
            func = factory.create(**create_kwargs)
        except ImportError as e:
            raise ImportError(
                f"Provider '{spec.provider}' requires additional dependencies. "
                "Install the provider's extra dependencies and try again."
            ) from e

        self._cache[cache_key] = func
        return func

    def embed_images(
        self,
        samples: list[Any],
        spec: EmbeddingSpec,
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Compute embeddings for image samples.

        Args:
            samples: List of Sample objects with image filepaths.
            spec: Embedding specification.
            batch_size: Batch size for processing.
            show_progress: Whether to show progress.

        Returns:
            Array of shape (N, D) where N is len(samples) and D is embedding dim.
        """
        func = self.get_function(spec)

        if show_progress:
            print(f"Computing embeddings for {len(samples)} samples...")

        all_embeddings: list[np.ndarray] = []
        for i in range(0, len(samples), batch_size):
            batch_samples = samples[i:i + batch_size]

            batch_paths = [s.filepath for s in batch_samples]
            batch_embeddings = func.compute_source_embeddings(batch_paths)
            all_embeddings.extend(batch_embeddings)

        return np.array(all_embeddings, dtype=np.float32)

    def embed_texts(
        self,
        texts: list[str],
        spec: EmbeddingSpec,
    ) -> np.ndarray:
        """Compute embeddings for text inputs.

        Args:
            texts: List of text strings.
            spec: Embedding specification.

        Returns:
            Array of shape (N, D).
        """
        func = self.get_function(spec)

        if hasattr(func, "generate_embeddings"):
            out = func.generate_embeddings(texts)
            return np.asarray(out, dtype=np.float32)

        embeddings: list[np.ndarray] = []
        for text in texts:
            out = func.compute_query_embeddings(text)
            if not out:
                raise RuntimeError(f"Provider '{spec.provider}' returned no embedding for query")
            embeddings.append(np.asarray(out[0], dtype=np.float32))
        return np.vstack(embeddings)

    def get_space_config(self, spec: EmbeddingSpec, dim: int) -> dict[str, Any]:
        """Get space configuration for storage.

        Args:
            spec: Embedding specification.
            dim: Embedding dimension.

        Returns:
            Config dict for SpaceInfo.config_json.
        """
        func = self.get_function(spec)

        config = spec.to_dict()
        config["dim"] = dim

        if hasattr(func, "geometry"):
            config["geometry"] = func.geometry
        if hasattr(func, "curvature") and func.curvature is not None:
            config["curvature"] = func.curvature

        if config.get("geometry") == "hyperboloid":
            config["spatial_dim"] = dim - 1

        return config


_ENGINE: EmbeddingEngine | None = None


def get_engine() -> EmbeddingEngine:
    """Get the global embedding engine singleton."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = EmbeddingEngine()
    return _ENGINE


def list_embedding_providers(available_only: bool = False) -> list[str]:
    """List all registered embedding providers.

    Args:
        available_only: If True, only return providers whose dependencies are installed.

    Returns:
        List of provider identifiers.
    """
    from lancedb.embeddings import get_registry

    registry = get_registry()

    all_providers = list(getattr(registry, "_functions", {}).keys())

    if not available_only:
        return sorted(all_providers)

    available: list[str] = []
    for provider in all_providers:
        try:
            factory = registry.get(provider)
            factory.create()
            available.append(provider)
        except ImportError:
            pass
        except (TypeError, ValueError):
            available.append(provider)

    return sorted(available)


def get_provider_info(provider: str) -> dict[str, Any]:
    """Get information about an embedding provider.

    Args:
        provider: Provider identifier.

    Returns:
        Dict with provider info.
    """
    from lancedb.embeddings import get_registry

    registry = get_registry()

    try:
        factory = registry.get(provider)
    except KeyError:
        raise ValueError(f"Unknown provider: {provider}") from None

    info: dict[str, Any] = {
        "provider": provider,
        "source": "hyperview" if provider in ("embed-anything", "hyper-models") else "lancedb",
        "geometry": "hyperboloid" if provider in HYPERBOLIC_PROVIDERS else "euclidean",
    }

    try:
        factory.create()
        info["installed"] = True
    except ImportError:
        info["installed"] = False
    except (TypeError, ValueError):
        info["installed"] = True

    return info
