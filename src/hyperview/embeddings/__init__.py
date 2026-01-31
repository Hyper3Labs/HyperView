"""Embedding computation and projection."""

from hyperview.embeddings.compute import EmbeddingComputer
from hyperview.embeddings.engine import (
    EmbeddingSpec,
    get_engine,
    get_provider_info,
    list_embedding_providers,
)

# Register HyperView providers into LanceDB registry.
import hyperview.embeddings.providers.lancedb_providers as _lancedb_providers  # noqa: F401


def __getattr__(name: str):
    """Lazy import for heavy dependencies (UMAP/numba)."""
    if name == "ProjectionEngine":
        from hyperview.embeddings.projection import ProjectionEngine
        return ProjectionEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EmbeddingComputer",
    "EmbeddingSpec",
    "ProjectionEngine",
    # Provider utilities
    "get_engine",
    "get_provider_info",
    "list_embedding_providers",
]
