"""In-memory storage backend for testing and development."""

import time
from collections.abc import Callable, Iterator

import numpy as np

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.schema import LayoutInfo, SpaceInfo, make_space_key


class MemoryBackend(StorageBackend):
    """In-memory storage backend for testing and development."""

    def __init__(self, dataset_name: str):
        self.dataset_name = dataset_name
        self._samples: dict[str, Sample] = {}
        self._spaces: dict[str, SpaceInfo] = {}
        self._embeddings: dict[str, dict[str, np.ndarray]] = {}
        self._layout_registry: dict[str, LayoutInfo] = {}
        self._layouts: dict[str, dict[str, tuple[float, float]]] = {}

    def add_sample(self, sample: Sample) -> None:
        self._samples[sample.id] = sample

    def add_samples_batch(self, samples: list[Sample]) -> None:
        for sample in samples:
            self._samples[sample.id] = sample

    def get_sample(self, sample_id: str) -> Sample | None:
        return self._samples.get(sample_id)

    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
    ) -> tuple[list[Sample], int]:
        samples = list(self._samples.values())
        if label:
            samples = [s for s in samples if s.label == label]
        total = len(samples)
        return samples[offset : offset + limit], total

    def get_all_samples(self) -> list[Sample]:
        return list(self._samples.values())

    def update_sample(self, sample: Sample) -> None:
        self._samples[sample.id] = sample

    def update_samples_batch(self, samples: list[Sample]) -> None:
        for sample in samples:
            self._samples[sample.id] = sample

    def delete_sample(self, sample_id: str) -> bool:
        if sample_id in self._samples:
            del self._samples[sample_id]
            return True
        return False

    def __len__(self) -> int:
        return len(self._samples)

    def __iter__(self) -> Iterator[Sample]:
        return iter(self._samples.values())

    def __contains__(self, sample_id: str) -> bool:
        return sample_id in self._samples

    def get_unique_labels(self) -> list[str]:
        return sorted({s.label for s in self._samples.values() if s.label})

    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        return {sid for sid in sample_ids if sid in self._samples}

    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        return [s for sid in sample_ids if (s := self._samples.get(sid)) is not None]

    def get_labels_by_ids(self, sample_ids: list[str]) -> dict[str, str | None]:
        return {sid: s.label for sid in sample_ids if (s := self._samples.get(sid)) is not None}

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        return [s for s in self._samples.values() if predicate(s)]

    def list_spaces(self) -> list[SpaceInfo]:
        return list(self._spaces.values())

    def get_space(self, space_key: str) -> SpaceInfo | None:
        return self._spaces.get(space_key)

    def ensure_space(
        self,
        model_id: str,
        dim: int,
        config: dict | None = None,
        space_key: str | None = None,
    ) -> SpaceInfo:
        if space_key is None:
            space_key = make_space_key(model_id)
        if space_key in self._spaces:
            existing = self._spaces[space_key]
            if existing.dim != dim:
                raise ValueError(f"Space '{space_key}' exists with dim={existing.dim}, requested dim={dim}")
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
        if space_key in self._spaces:
            del self._spaces[space_key]
            self._embeddings.pop(space_key, None)
            return True
        return False

    def add_embeddings(self, space_key: str, ids: list[str], vectors: np.ndarray) -> None:
        if len(ids) != len(vectors) or len(ids) == 0:
            return
        if space_key not in self._spaces:
            raise ValueError(f"Space not found: {space_key}")

        space = self._spaces[space_key]
        emb_store = self._embeddings.setdefault(space_key, {})
        for id_, vec in zip(ids, vectors):
            emb_store[id_] = vec.astype(np.float32)
        space.count = len(emb_store)
        space.updated_at = int(time.time())

    def get_embeddings(self, space_key: str, ids: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        if space_key not in self._spaces:
            raise ValueError(f"Space not found: {space_key}")

        space = self._spaces[space_key]
        emb_store = self._embeddings.get(space_key, {})

        if ids is not None:
            out_ids = [id_ for id_ in ids if id_ in emb_store]
        else:
            out_ids = list(emb_store.keys())

        if not out_ids:
            return [], np.empty((0, space.dim), dtype=np.float32)
        return out_ids, np.array([emb_store[id_] for id_ in out_ids], dtype=np.float32)

    def get_embedded_ids(self, space_key: str) -> set[str]:
        return set(self._embeddings.get(space_key, {}).keys())

    def get_missing_embedding_ids(self, space_key: str) -> list[str]:
        embedded = self.get_embedded_ids(space_key)
        return [id_ for id_ in self._samples.keys() if id_ not in embedded]

    def list_layouts(self) -> list[LayoutInfo]:
        return list(self._layout_registry.values())

    def get_layout(self, layout_key: str) -> LayoutInfo | None:
        return self._layout_registry.get(layout_key)

    def ensure_layout(
        self,
        layout_key: str,
        space_key: str,
        method: str,
        geometry: str,
        params: dict | None = None,
    ) -> LayoutInfo:
        if layout_key in self._layout_registry:
            return self._layout_registry[layout_key]

        layout_info = LayoutInfo(
            layout_key=layout_key,
            space_key=space_key,
            method=method,
            geometry=geometry,
            count=0,
            created_at=int(time.time()),
            params=params,
        )
        self._layout_registry[layout_key] = layout_info
        self._layouts[layout_key] = {}
        return layout_info

    def delete_layout(self, layout_key: str) -> bool:
        deleted = layout_key in self._layouts or layout_key in self._layout_registry
        self._layouts.pop(layout_key, None)
        self._layout_registry.pop(layout_key, None)
        return deleted

    def add_layout_coords(self, layout_key: str, ids: list[str], coords: np.ndarray) -> None:
        if len(ids) != len(coords):
            raise ValueError("ids and coords must have same length")
        if layout_key not in self._layout_registry:
            raise ValueError(f"Layout '{layout_key}' not registered")

        layout_store = self._layouts.setdefault(layout_key, {})
        for id_, coord in zip(ids, coords):
            layout_store[id_] = (float(coord[0]), float(coord[1]))
        self._layout_registry[layout_key].count = len(layout_store)

    def get_layout_coords(self, layout_key: str, ids: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        layout_store = self._layouts.get(layout_key, {})
        out_ids = [id_ for id_ in ids if id_ in layout_store] if ids is not None else list(layout_store.keys())
        if not out_ids:
            return [], np.empty((0, 2), dtype=np.float32)
        return out_ids, np.array([layout_store[id_] for id_ in out_ids], dtype=np.float32)

    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], np.ndarray]:
        layout_store = self._layouts.get(layout_key, {})
        ids, coords = [], []
        for id_, (x, y) in layout_store.items():
            if x_min <= x <= x_max and y_min <= y <= y_max:
                ids.append(id_)
                coords.append([x, y])
        return ids, np.array(coords, dtype=np.float32) if coords else np.empty((0, 2), dtype=np.float32)

    def find_similar(self, sample_id: str, k: int = 10, space_key: str | None = None) -> list[tuple[Sample, float]]:
        if space_key is None:
            if not self._spaces:
                raise ValueError("No embedding spaces available")
            space_key = next(iter(self._spaces))

        emb_store = self._embeddings.get(space_key, {})
        if sample_id not in emb_store:
            raise ValueError(f"Sample {sample_id} has no embedding in space {space_key}")

        results = self.find_similar_by_vector(emb_store[sample_id], k + 1, space_key)
        return [(s, d) for s, d in results if s.id != sample_id][:k]

    def find_similar_by_vector(
        self,
        vector: list[float] | np.ndarray,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        if space_key is None:
            if not self._spaces:
                raise ValueError("No embedding spaces available")
            space_key = next(iter(self._spaces))

        emb_store = self._embeddings.get(space_key, {})
        query = np.array(vector, dtype=np.float32)
        norm_query = np.linalg.norm(query)

        distances: list[tuple[Sample, float]] = []
        for id_, vec in emb_store.items():
            sample = self._samples.get(id_)
            if sample is None:
                continue
            norm_vec = np.linalg.norm(vec)
            if norm_query == 0 or norm_vec == 0:
                distance = 1.0
            else:
                distance = 1 - np.dot(query, vec) / (norm_query * norm_vec)
            distances.append((sample, float(distance)))

        distances.sort(key=lambda x: x[1])
        return distances[:k]

    def close(self) -> None:
        pass
