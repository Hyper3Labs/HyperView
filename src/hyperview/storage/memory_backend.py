"""In-memory storage backend for testing and development."""

from collections.abc import Callable, Iterator

import numpy as np

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend


class MemoryBackend(StorageBackend):
    """In-memory storage backend (current behavior, for testing and backwards compatibility)."""

    def __init__(self, dataset_name: str):
        """Initialize in-memory backend.

        Args:
            dataset_name: Name of the dataset.
        """
        self.dataset_name = dataset_name
        self._samples: dict[str, Sample] = {}
        self._label_colors: dict[str, str] = {}

    def add_sample(self, sample: Sample) -> None:
        """Add a single sample to storage."""
        self._samples[sample.id] = sample

    def add_samples_batch(self, samples: list[Sample]) -> None:
        """Add multiple samples efficiently."""
        for sample in samples:
            self._samples[sample.id] = sample

    def get_sample(self, sample_id: str) -> Sample | None:
        """Retrieve a sample by ID."""
        return self._samples.get(sample_id)

    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
    ) -> tuple[list[Sample], int]:
        """Get paginated samples."""
        samples = list(self._samples.values())
        if label:
            samples = [s for s in samples if s.label == label]
        total = len(samples)
        return samples[offset : offset + limit], total

    def get_all_samples(self) -> list[Sample]:
        """Get all samples."""
        return list(self._samples.values())

    def update_sample(self, sample: Sample) -> None:
        """Update an existing sample."""
        self._samples[sample.id] = sample

    def update_samples_batch(self, samples: list[Sample]) -> None:
        """Batch update samples."""
        for sample in samples:
            self._samples[sample.id] = sample

    def delete_sample(self, sample_id: str) -> bool:
        """Delete a sample by ID."""
        if sample_id in self._samples:
            del self._samples[sample_id]
            return True
        return False

    def __len__(self) -> int:
        """Return total number of samples."""
        return len(self._samples)

    def __iter__(self) -> Iterator[Sample]:
        """Iterate over all samples."""
        return iter(self._samples.values())

    def __contains__(self, sample_id: str) -> bool:
        """Check if sample exists."""
        return sample_id in self._samples

    def get_unique_labels(self) -> list[str]:
        """Get all unique labels."""
        labels = {s.label for s in self._samples.values() if s.label}
        return sorted(labels)

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        vector_column: str = "embedding",
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a sample."""
        sample = self._samples.get(sample_id)
        if sample is None:
            raise ValueError(f"Sample not found: {sample_id}")

        query_vector = self._get_vector(sample, vector_column)
        if query_vector is None:
            raise ValueError(f"Sample {sample_id} has no {vector_column}")

        # Find similar, excluding self
        results = self.find_similar_by_vector(query_vector, k + 1, vector_column)
        return [(s, d) for s, d in results if s.id != sample_id][:k]

    def find_similar_by_vector(
        self,
        vector: list[float],
        k: int = 10,
        vector_column: str = "embedding",
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a query vector."""
        query = np.array(vector)
        distances: list[tuple[Sample, float]] = []

        for sample in self._samples.values():
            vec = self._get_vector(sample, vector_column)
            if vec is None:
                continue

            # Cosine distance
            vec_np = np.array(vec)
            norm_query = np.linalg.norm(query)
            norm_vec = np.linalg.norm(vec_np)

            if norm_query == 0 or norm_vec == 0:
                distance = 1.0
            else:
                cosine_sim = np.dot(query, vec_np) / (norm_query * norm_vec)
                distance = 1 - cosine_sim

            distances.append((sample, float(distance)))

        distances.sort(key=lambda x: x[1])
        return distances[:k]

    def _get_vector(self, sample: Sample, vector_column: str) -> list[float] | None:
        """Get the appropriate vector from a sample."""
        if vector_column == "embedding":
            return sample.embedding
        elif vector_column == "embedding_2d_euclidean":
            return sample.embedding_2d
        elif vector_column == "embedding_2d_hyperbolic":
            return sample.embedding_2d_hyperbolic
        else:
            raise ValueError(f"Unknown vector column: {vector_column}")

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""
        return [s for s in self._samples.values() if predicate(s)]

    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        """Return set of sample_ids that already exist in storage."""
        return {sid for sid in sample_ids if sid in self._samples}

    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        """Retrieve multiple samples by ID."""
        out: list[Sample] = []
        for sid in sample_ids:
            s = self._samples.get(sid)
            if s is not None:
                out.append(s)
        return out

    def get_visualization_embeddings(
        self,
    ) -> tuple[list[str], list[str | None], list[list[float]], list[list[float]]]:
        """Return ids/labels and both 2D projections for the scatter."""
        ids: list[str] = []
        labels: list[str | None] = []
        euclidean: list[list[float]] = []
        hyperbolic: list[list[float]] = []

        for s in self._samples.values():
            if s.embedding_2d is None or s.embedding_2d_hyperbolic is None:
                continue
            ids.append(s.id)
            labels.append(s.label)
            euclidean.append(s.embedding_2d)
            hyperbolic.append(s.embedding_2d_hyperbolic)

        return ids, labels, euclidean, hyperbolic

    def get_lasso_candidates_aabb(
        self,
        *,
        space: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], np.ndarray]:
        """Return candidate (id, xy) rows within an AABB for a given projection."""
        if space not in ("euclidean", "hyperbolic"):
            raise ValueError(f"Unknown space: {space}")

        ids: list[str] = []
        coords: list[list[float]] = []

        for s in self._samples.values():
            # Keep selection universe consistent with /api/embeddings: require both projections.
            if s.embedding_2d is None or s.embedding_2d_hyperbolic is None:
                continue

            xy = s.embedding_2d if space == "euclidean" else s.embedding_2d_hyperbolic
            if xy is None or len(xy) != 2:
                continue

            x, y = float(xy[0]), float(xy[1])
            if x < x_min or x > x_max or y < y_min or y > y_max:
                continue

            ids.append(s.id)
            coords.append([x, y])

        return ids, np.asarray(coords, dtype=np.float32)

    def close(self) -> None:
        """Close the storage connection (no-op for in-memory)."""
        return

    @property
    def label_colors(self) -> dict[str, str]:
        """Get label color mapping."""
        return self._label_colors

    @label_colors.setter
    def label_colors(self, colors: dict[str, str]) -> None:
        """Set label color mapping."""
        self._label_colors = colors
