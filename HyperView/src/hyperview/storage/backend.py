"""Abstract storage backend interface for HyperView."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np

from hyperview.core.sample import Sample


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def add_sample(self, sample: Sample) -> None:
        """Add a single sample (idempotent upsert)."""

    @abstractmethod
    def add_samples_batch(self, samples: list[Sample]) -> None:
        """Add multiple samples (idempotent upsert)."""

    @abstractmethod
    def get_sample(self, sample_id: str) -> Sample | None:
        """Retrieve a sample by ID."""

    @abstractmethod
    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
    ) -> tuple[list[Sample], int]:
        """Get paginated samples. Returns (samples, total_count)."""

    @abstractmethod
    def get_all_samples(self) -> list[Sample]:
        """Get all samples."""

    @abstractmethod
    def update_sample(self, sample: Sample) -> None:
        """Update an existing sample."""

    @abstractmethod
    def update_samples_batch(self, samples: list[Sample]) -> None:
        """Batch update samples."""

    @abstractmethod
    def delete_sample(self, sample_id: str) -> bool:
        """Delete a sample by ID."""

    @abstractmethod
    def __len__(self) -> int:
        """Return total number of samples."""

    @abstractmethod
    def __iter__(self) -> Iterator[Sample]:
        """Iterate over all samples."""

    @abstractmethod
    def __contains__(self, sample_id: str) -> bool:
        """Check if sample exists."""

    @abstractmethod
    def get_unique_labels(self) -> list[str]:
        """Get all unique labels."""

    @abstractmethod
    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        """Return set of sample_ids that already exist in storage."""

    @abstractmethod
    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        """Retrieve multiple samples by ID."""

    @abstractmethod
    def get_labels_by_ids(self, sample_ids: list[str]) -> dict[str, str | None]:
        """Get labels for sample IDs. Missing IDs not included in result."""

    @abstractmethod
    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""

    @abstractmethod
    def list_spaces(self) -> list[Any]:
        """List all embedding spaces."""

    @abstractmethod
    def get_space(self, space_key: str) -> Any | None:
        """Get info for a specific embedding space."""

    @abstractmethod
    def ensure_space(
        self,
        model_id: str,
        dim: int,
        config: dict | None = None,
        space_key: str | None = None,
    ) -> Any:
        """Ensure an embedding space exists, creating if needed.

        Args:
            model_id: Model identifier for this space.
            dim: Vector dimension.
            config: Optional config dict for SpaceInfo.config_json.
            space_key: Optional explicit space key. If None, derived from model_id.
        """

    @abstractmethod
    def delete_space(self, space_key: str) -> bool:
        """Delete an embedding space and its embeddings."""

    @abstractmethod
    def add_embeddings(self, space_key: str, ids: list[str], vectors: np.ndarray) -> None:
        """Add embeddings to a space."""

    @abstractmethod
    def get_embeddings(self, space_key: str, ids: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        """Get embeddings from a space. Returns (ids, vectors)."""

    @abstractmethod
    def get_embedded_ids(self, space_key: str) -> set[str]:
        """Get sample IDs that have embeddings in a space."""

    @abstractmethod
    def get_missing_embedding_ids(self, space_key: str) -> list[str]:
        """Get sample IDs without embeddings in a space."""

    @abstractmethod
    def list_layouts(self) -> list[Any]:
        """List all layouts."""

    @abstractmethod
    def get_layout(self, layout_key: str) -> Any | None:
        """Get layout info."""

    @abstractmethod
    def ensure_layout(
        self,
        layout_key: str,
        space_key: str,
        method: str,
        geometry: str,
        params: dict | None = None,
    ) -> Any:
        """Ensure a layout exists."""

    @abstractmethod
    def delete_layout(self, layout_key: str) -> bool:
        """Delete a layout."""

    @abstractmethod
    def add_layout_coords(self, layout_key: str, ids: list[str], coords: np.ndarray) -> None:
        """Add layout coordinates (N x 2)."""

    @abstractmethod
    def get_layout_coords(
        self,
        layout_key: str,
        ids: list[str] | None = None,
    ) -> tuple[list[str], np.ndarray]:
        """Get layout coordinates. Returns (ids, coords)."""

    @abstractmethod
    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], np.ndarray]:
        """Return candidate (id, xy) rows within an axis-aligned bounding box."""

    @abstractmethod
    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors."""

    @abstractmethod
    def find_similar_by_vector(
        self,
        vector: list[float] | np.ndarray,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a query vector."""

    @abstractmethod
    def close(self) -> None:
        """Close the storage connection."""
