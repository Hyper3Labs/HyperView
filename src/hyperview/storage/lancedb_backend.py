"""LanceDB storage backend for HyperView."""

import time
from collections.abc import Callable, Iterator

import lancedb
import numpy as np
import pyarrow as pa

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.config import StorageConfig
from hyperview.storage.schema import (
    LayoutInfo,
    SpaceInfo,
    create_embeddings_schema,
    create_layouts_registry_schema,
    create_layouts_schema,
    create_sample_schema,
    create_spaces_schema,
    dict_to_sample,
    make_space_key,
    sample_to_dict,
)


def _sql_escape(value: str) -> str:
    """Escape single quotes for SQL WHERE clauses."""
    return value.replace("'", "''")


class LanceDBBackend(StorageBackend):
    """LanceDB-based storage backend for HyperView datasets."""

    def __init__(self, dataset_name: str, config: StorageConfig | None = None):
        self.dataset_name = dataset_name
        self.config = config or StorageConfig.default()
        self._dataset_dir = self.config.datasets_dir / dataset_name
        self._dataset_dir.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self._dataset_dir))

        self._samples_table = self._get_or_create_samples_table()
        self._spaces_table = self._get_or_create_spaces_table()

    def _table_names(self) -> set[str]:
        """Return the set of table names in this LanceDB database."""
        res = self._db.list_tables()
        return set(res.tables)

    def _get_or_create_samples_table(self) -> lancedb.table.Table | None:
        if "samples" in self._table_names():
            return self._db.open_table("samples")
        return None

    def _ensure_samples_table(self, data: list[dict]) -> lancedb.table.Table:
        if self._samples_table is None:
            schema = create_sample_schema()
            arrow_table = pa.Table.from_pylist(data, schema=schema)
            self._samples_table = self._db.create_table("samples", data=arrow_table)
        return self._samples_table

    def _get_or_create_spaces_table(self) -> lancedb.table.Table:
        if "spaces" in self._table_names():
            return self._db.open_table("spaces")
        return self._db.create_table("spaces", schema=create_spaces_schema())

    def add_sample(self, sample: Sample) -> None:
        data = [sample_to_dict(sample)]
        if self._samples_table is None:
            self._ensure_samples_table(data)
        else:
            arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
            self._samples_table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(arrow)

    def add_samples_batch(self, samples: list[Sample]) -> None:
        if not samples:
            return
        data = [sample_to_dict(s) for s in samples]
        if self._samples_table is None:
            self._ensure_samples_table(data)
        else:
            arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
            self._samples_table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(arrow)

    def get_sample(self, sample_id: str) -> Sample | None:
        if self._samples_table is None:
            return None
        results = self._samples_table.search().where(f"id = '{_sql_escape(sample_id)}'").limit(1).to_list()
        return dict_to_sample(results[0]) if results else None

    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
    ) -> tuple[list[Sample], int]:
        if self._samples_table is None:
            return [], 0

        import pyarrow.compute as pc

        if label:
            arrow_table = self._samples_table.search().select(["label"]).to_arrow()
            mask = pc.fill_null(pc.equal(arrow_table.column("label"), pa.scalar(label)), False)
            total = pc.sum(pc.cast(mask, pa.int64())).as_py()
            results = self._samples_table.search().where(f"label = '{_sql_escape(label)}'").offset(offset).limit(limit).to_list()
        else:
            total = self._samples_table.count_rows()
            results = self._samples_table.search().offset(offset).limit(limit).to_list()

        return [dict_to_sample(row) for row in results], total

    def get_all_samples(self) -> list[Sample]:
        if self._samples_table is None:
            return []
        return [dict_to_sample(row) for row in self._samples_table.to_arrow().to_pylist()]

    def update_sample(self, sample: Sample) -> None:
        self.add_sample(sample)

    def update_samples_batch(self, samples: list[Sample]) -> None:
        self.add_samples_batch(samples)

    def delete_sample(self, sample_id: str) -> bool:
        if self._samples_table is None:
            return False
        self._samples_table.delete(f"id = '{_sql_escape(sample_id)}'")
        return True

    def __len__(self) -> int:
        return self._samples_table.count_rows() if self._samples_table else 0

    def __iter__(self) -> Iterator[Sample]:
        if self._samples_table is None:
            return iter([])
        for batch in self._samples_table.to_arrow().to_batches(max_chunksize=1000):
            batch_dict = batch.to_pydict()
            for i in range(batch.num_rows):
                yield dict_to_sample({k: batch_dict[k][i] for k in batch_dict})

    def __contains__(self, sample_id: str) -> bool:
        if self._samples_table is None:
            return False
        return len(self._samples_table.search().where(f"id = '{_sql_escape(sample_id)}'").limit(1).to_list()) > 0

    def get_unique_labels(self) -> list[str]:
        if self._samples_table is None:
            return []
        import pyarrow.compute as pc
        labels = pc.unique(self._samples_table.search().select(["label"]).to_arrow().column("label")).to_pylist()
        return sorted([l for l in labels if l is not None])

    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        if self._samples_table is None or not sample_ids:
            return set()
        existing: set[str] = set()
        for i in range(0, len(sample_ids), 1000):
            chunk = sample_ids[i : i + 1000]
            id_list = "', '".join(_sql_escape(sid) for sid in chunk)
            results = self._samples_table.search().where(f"id IN ('{id_list}')").select(["id"]).to_list()
            existing.update(r["id"] for r in results)
        return existing

    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        if self._samples_table is None or not sample_ids:
            return []
        rows_by_id: dict[str, dict] = {}
        for i in range(0, len(sample_ids), 1000):
            chunk = sample_ids[i : i + 1000]
            id_list = "', '".join(_sql_escape(sid) for sid in chunk)
            for r in self._samples_table.search().where(f"id IN ('{id_list}')").to_list():
                rows_by_id[r["id"]] = r
        return [dict_to_sample(rows_by_id[sid]) for sid in sample_ids if sid in rows_by_id]

    def get_labels_by_ids(self, sample_ids: list[str]) -> dict[str, str | None]:
        if self._samples_table is None or not sample_ids:
            return {}
        labels: dict[str, str | None] = {}
        for i in range(0, len(sample_ids), 1000):
            chunk = sample_ids[i : i + 1000]
            id_list = "', '".join(_sql_escape(sid) for sid in chunk)
            for r in self._samples_table.search().select(["id", "label"]).where(f"id IN ('{id_list}')").to_list():
                labels[r["id"]] = r.get("label")
        return labels

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        return [s for s in self if predicate(s)]

    def list_spaces(self) -> list[SpaceInfo]:
        return [SpaceInfo.from_dict(r) for r in self._spaces_table.to_arrow().to_pylist()]

    def get_space(self, space_key: str) -> SpaceInfo | None:
        results = self._spaces_table.search().where(f"space_key = '{_sql_escape(space_key)}'").limit(1).to_list()
        return SpaceInfo.from_dict(results[0]) if results else None

    def ensure_space(
        self,
        model_id: str,
        dim: int,
        config: dict | None = None,
        space_key: str | None = None,
    ) -> SpaceInfo:
        if space_key is None:
            space_key = make_space_key(model_id)
        existing = self.get_space(space_key)
        if existing is not None:
            if existing.dim != dim:
                raise ValueError(f"Space '{space_key}' exists with dim={existing.dim}, requested dim={dim}")
            return existing

        now = int(time.time())
        space_info = SpaceInfo(
            space_key=space_key, model_id=model_id, dim=dim, count=0,
            created_at=now, updated_at=now, config=config,
        )
        self._spaces_table.add(pa.Table.from_pylist([space_info.to_dict()], schema=create_spaces_schema()))
        self._db.create_table(f"embeddings__{space_key}", schema=create_embeddings_schema(dim))
        return space_info

    def delete_space(self, space_key: str) -> bool:
        self._spaces_table.delete(f"space_key = '{_sql_escape(space_key)}'")
        emb_table = f"embeddings__{space_key}"
        if emb_table in self._table_names():
            self._db.drop_table(emb_table)
        return True

    def add_embeddings(self, space_key: str, ids: list[str], vectors: np.ndarray) -> None:
        if len(ids) != len(vectors) or len(ids) == 0:
            return
        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            self._db.create_table(emb_table_name, schema=create_embeddings_schema(space.dim))

        emb_table = self._db.open_table(emb_table_name)
        data = [{"id": id_, "vector": vec.astype(np.float32).tolist()} for id_, vec in zip(ids, vectors)]
        emb_table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(
            pa.Table.from_pylist(data, schema=create_embeddings_schema(space.dim))
        )

        # Update space count
        self._spaces_table.update(where=f"space_key = '{_sql_escape(space_key)}'", values={
            "count": emb_table.count_rows(), "updated_at": int(time.time())
        })

    def get_embeddings(self, space_key: str, ids: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            return [], np.empty((0, space.dim), dtype=np.float32)

        emb_table = self._db.open_table(emb_table_name)
        if ids is not None:
            id_list = "', '".join(_sql_escape(sid) for sid in ids)
            rows = emb_table.search().where(f"id IN ('{id_list}')").to_list()
        else:
            rows = emb_table.to_arrow().to_pylist()

        if not rows:
            return [], np.empty((0, space.dim), dtype=np.float32)
        return [r["id"] for r in rows], np.array([r["vector"] for r in rows], dtype=np.float32)

    def get_embedded_ids(self, space_key: str) -> set[str]:
        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            return set()
        return {r["id"] for r in self._db.open_table(emb_table_name).search().select(["id"]).to_list()}

    def get_missing_embedding_ids(self, space_key: str) -> list[str]:
        if self._samples_table is None:
            return []
        all_ids = {r["id"] for r in self._samples_table.search().select(["id"]).to_list()}
        return list(all_ids - self.get_embedded_ids(space_key))

    def _get_layouts_registry_table(self) -> lancedb.table.Table | None:
        return self._db.open_table("layouts_registry") if "layouts_registry" in self._table_names() else None

    def _ensure_layouts_registry_table(self) -> lancedb.table.Table:
        if "layouts_registry" not in self._table_names():
            self._db.create_table("layouts_registry", schema=create_layouts_registry_schema())
        return self._db.open_table("layouts_registry")

    def list_layouts(self) -> list[LayoutInfo]:
        table = self._get_layouts_registry_table()
        return [LayoutInfo.from_dict(row) for row in table.search().to_list()] if table else []

    def get_layout(self, layout_key: str) -> LayoutInfo | None:
        table = self._get_layouts_registry_table()
        if table is None:
            return None
        rows = table.search().where(f"layout_key = '{_sql_escape(layout_key)}'").limit(1).to_list()
        return LayoutInfo.from_dict(rows[0]) if rows else None

    def ensure_layout(
        self,
        layout_key: str,
        space_key: str,
        method: str,
        geometry: str,
        params: dict | None = None,
    ) -> LayoutInfo:
        existing = self.get_layout(layout_key)
        if existing is not None:
            return existing

        layout_info = LayoutInfo(
            layout_key=layout_key, space_key=space_key, method=method, geometry=geometry,
            count=0, created_at=int(time.time()), params=params,
        )
        registry_table = self._ensure_layouts_registry_table()
        registry_table.add(pa.Table.from_pylist([layout_info.to_dict()], schema=create_layouts_registry_schema()))

        table_name = f"layouts__{layout_key}"
        if table_name not in self._table_names():
            self._db.create_table(table_name, schema=create_layouts_schema())
        return layout_info

    def delete_layout(self, layout_key: str) -> bool:
        table_name = f"layouts__{layout_key}"
        if table_name in self._table_names():
            self._db.drop_table(table_name)
        registry = self._get_layouts_registry_table()
        if registry:
            registry.delete(f"layout_key = '{_sql_escape(layout_key)}'")
        return True

    def add_layout_coords(self, layout_key: str, ids: list[str], coords: np.ndarray) -> None:
        if len(ids) != len(coords) or len(ids) == 0:
            return
        if self.get_layout(layout_key) is None:
            raise ValueError(f"Layout '{layout_key}' not registered")

        table_name = f"layouts__{layout_key}"
        if table_name not in self._table_names():
            self._db.create_table(table_name, schema=create_layouts_schema())

        table = self._db.open_table(table_name)
        data = [{"id": id_, "x": float(c[0]), "y": float(c[1])} for id_, c in zip(ids, coords)]
        table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(
            pa.Table.from_pylist(data, schema=create_layouts_schema())
        )

        # Update count
        registry = self._get_layouts_registry_table()
        if registry:
            registry.update(where=f"layout_key = '{_sql_escape(layout_key)}'", values={"count": table.count_rows()})

    def get_layout_coords(self, layout_key: str, ids: list[str] | None = None) -> tuple[list[str], np.ndarray]:
        table_name = f"layouts__{layout_key}"
        if table_name not in self._table_names():
            return [], np.empty((0, 2), dtype=np.float32)

        table = self._db.open_table(table_name)
        if ids is not None:
            id_list = "', '".join(_sql_escape(sid) for sid in ids)
            rows = table.search().where(f"id IN ('{id_list}')").to_list()
        else:
            rows = table.to_arrow().to_pylist()

        if not rows:
            return [], np.empty((0, 2), dtype=np.float32)
        return [r["id"] for r in rows], np.array([[r["x"], r["y"]] for r in rows], dtype=np.float32)

    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], np.ndarray]:
        table_name = f"layouts__{layout_key}"
        if table_name not in self._table_names():
            return [], np.empty((0, 2), dtype=np.float32)

        rows = self._db.open_table(table_name).search().where(
            f"x >= {x_min} AND x <= {x_max} AND y >= {y_min} AND y <= {y_max}"
        ).to_list()

        if not rows:
            return [], np.empty((0, 2), dtype=np.float32)
        return [r["id"] for r in rows], np.array([[r["x"], r["y"]] for r in rows], dtype=np.float32)

    def find_similar(self, sample_id: str, k: int = 10, space_key: str | None = None) -> list[tuple[Sample, float]]:
        if space_key is None:
            spaces = self.list_spaces()
            if not spaces:
                raise ValueError("No embedding spaces available")
            space_key = spaces[0].space_key

        ids, vecs = self.get_embeddings(space_key, [sample_id])
        if not ids:
            raise ValueError(f"Sample {sample_id} has no embedding in space {space_key}")

        results = self.find_similar_by_vector(vecs[0], k + 1, space_key)
        return [(s, d) for s, d in results if s.id != sample_id][:k]

    def find_similar_by_vector(
        self,
        vector: list[float] | np.ndarray,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        import math

        if space_key is None:
            spaces = self.list_spaces()
            if not spaces:
                raise ValueError("No embedding spaces available")
            space_key = spaces[0].space_key

        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            return []

        results = self._db.open_table(emb_table_name).search(vector, vector_column_name="vector").metric("cosine").limit(k).to_list()
        samples_by_id = {s.id: s for s in self.get_samples_by_ids([r["id"] for r in results])}

        return [
            (samples_by_id[r["id"]], 0.0 if math.isnan(d := r.get("_distance", 0.0)) else float(d))
            for r in results if r["id"] in samples_by_id
        ]

    def close(self) -> None:
        return
