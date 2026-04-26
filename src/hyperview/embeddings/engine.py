"""Embedding spec + engine built on LanceDB's embedding registry."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

# Register HyperView providers into LanceDB registry.
import hyperview.embeddings.providers.lancedb_providers as _lancedb_providers  # noqa: F401
from hyperview.runtime import ProviderRegistry

__all__ = [
    "EmbeddingSpec",
    "EmbeddingEngine",
    "get_engine",
    "list_embedding_providers",
    "get_provider_info",
]

HYPERBOLIC_PROVIDERS = frozenset({"hyper-models"})


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    total_seconds = int(round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s"


def _format_eta(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds < 0:
        return "unknown"
    return _format_elapsed(seconds)


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

        custom_registry = ProviderRegistry()
        custom_registration = custom_registry.get(spec.provider)
        if custom_registration is not None:
            create_kwargs: dict[str, Any] = {}
            if spec.model_id:
                create_kwargs["name"] = spec.model_id
            if spec.checkpoint:
                create_kwargs["checkpoint"] = spec.checkpoint
            create_kwargs.update(spec.provider_kwargs)

            func = custom_registry.instantiate(spec.provider, **create_kwargs)
            self._cache[cache_key] = func
            return func

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
        provider_target = spec.model_id or spec.checkpoint or spec.provider
        if show_progress:
            print(
                f"Preparing embedding provider '{spec.provider}' ({provider_target})...",
                flush=True,
            )

        func = self.get_function(spec)

        if hasattr(func, "set_progress_enabled"):
            func.set_progress_enabled(show_progress)

        if show_progress:
            print(f"Computing embeddings for {len(samples)} samples...", flush=True)

        all_embeddings: list[np.ndarray] = []
        total_samples = len(samples)
        total_batches = max(1, math.ceil(total_samples / batch_size))
        report_every_batches = 1 if total_batches <= 20 else max(1, total_batches // 20)
        started_at = time.perf_counter()
        last_report_at = started_at

        for batch_index, i in enumerate(range(0, len(samples), batch_size), start=1):
            batch_samples = samples[i:i + batch_size]

            batch_paths = [s.filepath for s in batch_samples]
            batch_embeddings = func.compute_source_embeddings(batch_paths)
            all_embeddings.extend(batch_embeddings)

            if not show_progress:
                continue

            completed = len(all_embeddings)
            now = time.perf_counter()
            should_report = batch_index == 1 or batch_index == total_batches
            if batch_index % report_every_batches == 0:
                should_report = True
            if now - last_report_at >= 10.0:
                should_report = True
            if not should_report:
                continue

            elapsed = max(now - started_at, 1e-9)
            rate = completed / elapsed
            remaining = total_samples - completed
            eta_seconds = remaining / rate if rate > 0 else float("inf")
            print(
                f"Embedded {completed}/{total_samples} samples "
                f"({completed / total_samples:.0%}, batch {batch_index}/{total_batches}, "
                f"{rate:.1f}/s, elapsed {_format_elapsed(elapsed)}, "
                f"ETA {_format_eta(eta_seconds)})",
                flush=True,
            )
            last_report_at = now

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
    custom_registry = ProviderRegistry()
    all_known_providers = sorted(
        set(all_providers) | {provider.alias for provider in custom_registry.list()}
    )

    if not available_only:
        return all_known_providers

    available: list[str] = []
    for provider in all_known_providers:
        if custom_registry.get(provider) is not None:
            if custom_registry.is_available(provider):
                available.append(provider)
            continue

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
    custom_registry = ProviderRegistry()
    custom_registration = custom_registry.get(provider)
    if custom_registration is not None:
        return {
            "provider": provider,
            "source": "custom",
            "kind": custom_registration.kind,
            "import_path": custom_registration.import_path,
            "installed": custom_registry.is_available(provider),
            "geometry": "custom",
        }

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
