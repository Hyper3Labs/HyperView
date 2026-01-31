"""HyperView - Open-source dataset curation with hyperbolic embeddings visualization."""

from hyperview.api import Dataset, launch
from hyperview.embeddings.engine import (
    EmbeddingSpec,
    get_provider_info,
    list_embedding_providers,
)

__version__ = "0.1.0"
__all__ = [
    "Dataset",
    "EmbeddingSpec",
    "get_provider_info",
    "launch",
    "list_embedding_providers",
    "__version__",
]
