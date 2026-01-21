"""Embedding computation, projection, and provider modules."""

from hyperview.embeddings.compute import EmbeddingComputer
from hyperview.embeddings.providers import (
    BaseEmbeddingProvider,
    ModelSpec,
    get_provider,
    list_providers,
    make_provider_aware_space_key,
    register_provider,
)


def __getattr__(name: str):
    """Lazy import for heavy dependencies (UMAP/numba)."""
    if name == "ProjectionEngine":
        from hyperview.embeddings.projection import ProjectionEngine
        return ProjectionEngine
    if name == "EmbedAnythingProvider":
        from hyperview.embeddings.providers.embed_anything import EmbedAnythingProvider
        return EmbedAnythingProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EmbeddingComputer",
    "ProjectionEngine",
    # Provider types
    "BaseEmbeddingProvider",
    "EmbedAnythingProvider",
    "ModelSpec",
    # Provider utilities
    "get_provider",
    "list_providers",
    "register_provider",
    "make_provider_aware_space_key",
]
