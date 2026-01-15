"""Abstract storage backend interface for HyperView."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator

from hyperview.core.sample import Sample


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def add_sample(self, sample: Sample) -> None:
        """Add a single sample to storage."""

    @abstractmethod
    def add_samples_batch(self, samples: list[Sample]) -> None:
        """Add multiple samples efficiently."""

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
        """Get all samples (use with caution for large datasets)."""

    @abstractmethod
    def update_sample(self, sample: Sample) -> None:
        """Update an existing sample."""

    @abstractmethod
    def update_samples_batch(self, samples: list[Sample]) -> None:
        """Batch update samples (for embeddings, etc.)."""

    @abstractmethod
    def delete_sample(self, sample_id: str) -> bool:
        """Delete a sample by ID. Returns True if deleted."""

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
    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        vector_column: str = "embedding",
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors. Returns [(sample, distance), ...]."""

    @abstractmethod
    def find_similar_by_vector(
        self,
        vector: list[float],
        k: int = 10,
        vector_column: str = "embedding",
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a query vector."""

    @abstractmethod
    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""

    @abstractmethod
    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        """Return set of sample_ids that already exist in storage.

        Args:
            sample_ids: List of sample IDs to check.

        Returns:
            Set of IDs that exist in storage.
        """

    @abstractmethod
    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        """Retrieve multiple samples by ID.

        Implementations should preserve the input order when possible.
        Missing IDs should be skipped.
        """

    @abstractmethod
    def get_visualization_embeddings(
        self,
    ) -> tuple[list[str], list[str | None], list[list[float]], list[list[float]]]:
        """Return all 2D embedding coords needed by the frontend scatter.

        Returns:
            (ids, labels, euclidean_xy, hyperbolic_xy)

        Notes:
            This should avoid loading heavy fields (thumbnails, high-dim embeddings)
            when the backend supports column projection.
        """

    @abstractmethod
    def get_lasso_candidates_aabb(
        self,
        *,
        space: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], "np.ndarray"]:
        """Return candidate (id, xy) rows within an axis-aligned bounding box.

        Args:
            space: Projection key (e.g. "euclidean", "hyperbolic").
            x_min/x_max/y_min/y_max: Bounds in the same data space as /api/embeddings.

        Returns:
            (ids, coords_xy) where coords_xy has shape (n, 2) float32.
        """

    @abstractmethod
    def close(self) -> None:
        """Close the storage connection."""

    @property
    @abstractmethod
    def label_colors(self) -> dict[str, str]:
        """Get label color mapping."""

    @label_colors.setter
    @abstractmethod
    def label_colors(self, colors: dict[str, str]) -> None:
        """Set label color mapping."""
