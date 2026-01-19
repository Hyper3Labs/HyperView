"""In-memory storage backend for testing and development."""

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.schema import SpaceInfo, make_space_key


class MemoryBackend(StorageBackend):
    """In-memory storage backend for testing and development.

    Implements the same interface as LanceDBBackend but stores everything in memory.
    """

    def __init__(self, dataset_name: str):
        """Initialize in-memory backend.

        Args:
            dataset_name: Name of the dataset.
        """
        self.dataset_name = dataset_name
        self._samples: dict[str, Sample] = {}
        self._label_colors: dict[str, str] = {}

        # Spaces registry
        self._spaces: dict[str, SpaceInfo] = {}

        # Embeddings: space_key -> {sample_id -> vector}
        self._embeddings: dict[str, dict[str, np.ndarray]] = {}

        # Layouts: layout_key -> {sample_id -> (x, y)}
        self._layouts: dict[str, dict[str, tuple[float, float]]] = {}

    # =========================================================================
    # Sample CRUD
    # =========================================================================

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

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""
        return [s for s in self._samples.values() if predicate(s)]

    # =========================================================================
    # Spaces registry
    # =========================================================================

    def list_spaces(self) -> list[SpaceInfo]:
        """List all embedding spaces."""
        return list(self._spaces.values())

    def get_space(self, space_key: str) -> SpaceInfo | None:
        """Get info for a specific embedding space."""
        return self._spaces.get(space_key)

    def ensure_space(self, model_id: str, dim: int, config: dict | None = None) -> SpaceInfo:
        """Ensure an embedding space exists, creating if needed."""
        space_key = make_space_key(model_id)

        if space_key in self._spaces:
            existing = self._spaces[space_key]
            if existing.dim != dim:
                raise ValueError(
                    f"Space '{space_key}' exists with dim={existing.dim}, "
                    f"but requested dim={dim}"
                )
            return existing

        now = int(time.time())
        space_info = SpaceInfo(
            space_key=space_key,
            model_id=model_id,
            dim=dim,
            count=0,
            created_at=now,
            updated_at=now,
            config=config,
        )
        self._spaces[space_key] = space_info
        self._embeddings[space_key] = {}
        return space_info

    def delete_space(self, space_key: str) -> bool:
        """Delete an embedding space and its embeddings."""
        if space_key in self._spaces:
            del self._spaces[space_key]
            self._embeddings.pop(space_key, None)
            return True
        return False

    # =========================================================================
    # Embeddings
    # =========================================================================

    def add_embeddings(
        self,
        space_key: str,
        ids: list[str],
        vectors: np.ndarray,
    ) -> None:
        """Add embeddings to a space."""
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must have same length")
        if len(ids) == 0:
            return

        if space_key not in self._spaces:
            raise ValueError(f"Space not found: {space_key}")

        space = self._spaces[space_key]
        if vectors.shape[1] != space.dim:
            raise ValueError(f"Vector dim {vectors.shape[1]} != space dim {space.dim}")

        emb_store = self._embeddings.setdefault(space_key, {})
        for id_, vec in zip(ids, vectors):
            emb_store[id_] = vec.astype(np.float32)

        # Update count
        space.count = len(emb_store)
        space.updated_at = int(time.time())

    def get_embeddings(
        self,
        space_key: str,
        ids: list[str] | None = None,
    ) -> tuple[list[str], np.ndarray]:
        """Get embeddings from a space."""
        if space_key not in self._spaces:
            raise ValueError(f"Space not found: {space_key}")

        space = self._spaces[space_key]
        emb_store = self._embeddings.get(space_key, {})

        if ids is not None:
            out_ids = [id_ for id_ in ids if id_ in emb_store]
            if not out_ids:
                return [], np.empty((0, space.dim), dtype=np.float32)
            out_vecs = np.array([emb_store[id_] for id_ in out_ids], dtype=np.float32)
            return out_ids, out_vecs
        else:
            if not emb_store:
                return [], np.empty((0, space.dim), dtype=np.float32)
            out_ids = list(emb_store.keys())
            out_vecs = np.array([emb_store[id_] for id_ in out_ids], dtype=np.float32)
            return out_ids, out_vecs

    def get_embedded_ids(self, space_key: str) -> set[str]:
        """Get the set of sample IDs that have embeddings in a space."""
        return set(self._embeddings.get(space_key, {}).keys())

    def get_missing_embedding_ids(self, space_key: str) -> list[str]:
        """Get sample IDs that don't have embeddings in a space."""
        embedded = self.get_embedded_ids(space_key)
        return [id_ for id_ in self._samples.keys() if id_ not in embedded]

    # =========================================================================
    # Layouts
    # =========================================================================

    def list_layouts(self) -> list[str]:
        """List all layout keys."""
        return list(self._layouts.keys())

    def ensure_layout(self, layout_key: str) -> None:
        """Ensure a layout exists."""
        if layout_key not in self._layouts:
            self._layouts[layout_key] = {}

    def delete_layout(self, layout_key: str) -> bool:
        """Delete a layout."""
        if layout_key in self._layouts:
            del self._layouts[layout_key]
            return True
        return False

    def add_layout_coords(
        self,
        layout_key: str,
        ids: list[str],
        coords: np.ndarray,
    ) -> None:
        """Add layout coordinates."""
        if len(ids) != len(coords):
            raise ValueError("ids and coords must have same length")

        self.ensure_layout(layout_key)
        layout_store = self._layouts[layout_key]

        for id_, coord in zip(ids, coords):
            layout_store[id_] = (float(coord[0]), float(coord[1]))

    def get_layout_coords(
        self,
        layout_key: str,
        ids: list[str] | None = None,
    ) -> tuple[list[str], np.ndarray]:
        """Get layout coordinates."""
        layout_store = self._layouts.get(layout_key, {})

        if ids is not None:
            out_ids = [id_ for id_ in ids if id_ in layout_store]
        else:
            out_ids = list(layout_store.keys())

        if not out_ids:
            return [], np.empty((0, 2), dtype=np.float32)

        out_coords = np.array([layout_store[id_] for id_ in out_ids], dtype=np.float32)
        return out_ids, out_coords

    def get_visualization_data(
        self,
        layout_key: str,
    ) -> tuple[list[str], list[str | None], np.ndarray]:
        """Get visualization data for scatter plot."""
        layout_store = self._layouts.get(layout_key, {})

        if not layout_store:
            return [], [], np.empty((0, 2), dtype=np.float32)

        ids = []
        labels = []
        coords = []

        for id_, (x, y) in layout_store.items():
            sample = self._samples.get(id_)
            if sample is not None:
                ids.append(id_)
                labels.append(sample.label)
                coords.append([x, y])

        return ids, labels, np.array(coords, dtype=np.float32) if coords else np.empty((0, 2), dtype=np.float32)

    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], np.ndarray]:
        """Return candidate (id, xy) rows within an AABB."""
        layout_store = self._layouts.get(layout_key, {})

        ids = []
        coords = []

        for id_, (x, y) in layout_store.items():
            if x < x_min or x > x_max or y < y_min or y > y_max:
                continue
            ids.append(id_)
            coords.append([x, y])

        return ids, np.array(coords, dtype=np.float32) if coords else np.empty((0, 2), dtype=np.float32)

    # =========================================================================
    # Similarity search
    # =========================================================================

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a sample."""
        if space_key is None:
            if not self._spaces:
                raise ValueError("No embedding spaces available")
            space_key = list(self._spaces.keys())[0]

        emb_store = self._embeddings.get(space_key, {})
        if sample_id not in emb_store:
            raise ValueError(f"Sample {sample_id} has no embedding in space {space_key}")

        query_vector = emb_store[sample_id]
        results = self.find_similar_by_vector(query_vector, k + 1, space_key)
        return [(s, d) for s, d in results if s.id != sample_id][:k]

    def find_similar_by_vector(
        self,
        vector: list[float] | np.ndarray,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a query vector."""
        if space_key is None:
            if not self._spaces:
                raise ValueError("No embedding spaces available")
            space_key = list(self._spaces.keys())[0]

        emb_store = self._embeddings.get(space_key, {})
        query = np.array(vector, dtype=np.float32)

        distances: list[tuple[Sample, float]] = []
        for id_, vec in emb_store.items():
            sample = self._samples.get(id_)
            if sample is None:
                continue

            # Cosine distance
            norm_query = np.linalg.norm(query)
            norm_vec = np.linalg.norm(vec)

            if norm_query == 0 or norm_vec == 0:
                distance = 1.0
            else:
                cosine_sim = np.dot(query, vec) / (norm_query * norm_vec)
                distance = 1 - cosine_sim

            distances.append((sample, float(distance)))

        distances.sort(key=lambda x: x[1])
        return distances[:k]

    # =========================================================================
    # Lifecycle and metadata
    # =========================================================================

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
