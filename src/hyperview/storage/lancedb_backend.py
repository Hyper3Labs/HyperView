"""LanceDB storage backend for HyperView."""

import time
from collections.abc import Callable, Iterator

import lancedb
import numpy as np
import pyarrow as pa
from lancedb.expr import col, lit

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.config import StorageConfig
from hyperview.storage.metrics import (
    distance_metric_for_space,
    hyperboloid_dot_query,
    pairwise_embedding_distances,
    resolve_hyperboloid_curvature,
)
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
    parse_layout_dimension,
    sample_to_dict,
)


def _eq_sql(column: str, value: object) -> str:
    return (col(column) == lit(value)).to_sql()


def _in_sql(column: str, values: list[str]) -> str:
    if not values:
        raise ValueError("SQL IN predicate requires at least one value")
    return f"{col(column).to_sql()} IN ({', '.join(lit(value).to_sql() for value in values)})"


def _replace_hyperboloid_distances(
    rows: list[dict],
    query: list[float] | np.ndarray,
    curvature: float,
) -> list[dict]:
    if not rows:
        return []

    vectors = np.asarray([row["vector"] for row in rows], dtype=np.float32)
    distances = pairwise_embedding_distances(
        query,
        vectors,
        metric="hyperboloid",
        curvature=curvature,
    )
    out: list[dict] = []
    for row, distance in zip(rows, distances, strict=False):
        updated = dict(row)
        updated["_distance"] = float(distance)
        out.append(updated)
    out.sort(key=lambda row: row["_distance"])
    return out


def _dedupe_rows_by_id(rows: list[dict]) -> list[dict]:
    """Return rows unique by id, keeping the last occurrence."""

    deduped: dict[str, dict] = {}
    for row in rows:
        row_id = str(row["id"])
        if row_id in deduped:
            del deduped[row_id]
        deduped[row_id] = row
    return list(deduped.values())


def _ensure_scalar_index(
    table: lancedb.table.Table,
    column: str,
    *,
    index_type: str = "BTREE",
) -> None:
    expected_type = index_type.lower()
    for index in table.list_indices():
        if column in list(getattr(index, "columns", []) or []):
            existing_type = str(getattr(index, "index_type", "")).lower()
            if existing_type == expected_type:
                return
            table.create_scalar_index(
                column,
                index_type=index_type,
                name=getattr(index, "name", None) or f"{column}_idx",
                replace=True,
            )
            return
    table.create_scalar_index(
        column,
        index_type=index_type,
        name=f"{column}_idx",
        replace=False,
    )


def _ensure_samples_indices(table: lancedb.table.Table) -> None:
    _ensure_scalar_index(table, "id")
    _ensure_scalar_index(table, "label", index_type="BITMAP")


def _ensure_layout_indices(table: lancedb.table.Table, *, layout_dimension: int) -> None:
    _ensure_scalar_index(table, "id")
    _ensure_scalar_index(table, "x")
    _ensure_scalar_index(table, "y")
    if layout_dimension == 3:
        _ensure_scalar_index(table, "z")


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
        if "layouts_registry" in self._table_names():
            self._ensure_layouts_registry_table()

    def _table_names(self) -> set[str]:
        """Return the set of table names in this LanceDB database."""
        res = self._db.list_tables()
        return set(res.tables)

    def _get_or_create_samples_table(self) -> lancedb.table.Table | None:
        if "samples" in self._table_names():
            table = self._db.open_table("samples")
            _ensure_samples_indices(table)
            return table
        return None

    def _ensure_samples_table(self, data: list[dict]) -> lancedb.table.Table:
        if self._samples_table is None:
            schema = create_sample_schema()
            arrow_table = pa.Table.from_pylist(data, schema=schema)
            self._samples_table = self._db.create_table("samples", data=arrow_table)
            _ensure_samples_indices(self._samples_table)
        return self._samples_table

    def _get_or_create_spaces_table(self) -> lancedb.table.Table:
        if "spaces" in self._table_names():
            table = self._db.open_table("spaces")
            _ensure_scalar_index(table, "space_key")
            return table
        return self._db.create_table("spaces", schema=create_spaces_schema())

    def add_sample(self, sample: Sample) -> None:
        self.add_samples_batch([sample])

    def add_samples_batch(self, samples: list[Sample]) -> None:
        if not samples:
            return
        data = _dedupe_rows_by_id([sample_to_dict(s) for s in samples])
        if self._samples_table is None:
            self._ensure_samples_table(data)
        else:
            _ensure_samples_indices(self._samples_table)
            arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
            self._samples_table.merge_insert(
                "id"
            ).when_matched_update_all().when_not_matched_insert_all().execute(arrow)

    def get_sample(self, sample_id: str) -> Sample | None:
        if self._samples_table is None:
            return None
        results = self._samples_table.search().where(col("id") == lit(sample_id)).limit(1).to_list()
        return dict_to_sample(results[0]) if results else None

    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
    ) -> tuple[list[Sample], int]:
        if self._samples_table is None:
            return [], 0

        if label:
            total = self._samples_table.count_rows(_eq_sql("label", label))
            results = (
                self._samples_table.search()
                .where(col("label") == lit(label))
                .offset(offset)
                .limit(limit)
                .to_list()
            )
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
        self._samples_table.delete(_eq_sql("id", sample_id))
        self._samples_table.optimize()
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
        return (
            len(self._samples_table.search().where(col("id") == lit(sample_id)).limit(1).to_list())
            > 0
        )

    def get_unique_labels(self) -> list[str]:
        if self._samples_table is None:
            return []
        import pyarrow.compute as pc

        labels = pc.unique(
            self._samples_table.search().select(["label"]).to_arrow().column("label")
        ).to_pylist()
        return sorted([label for label in labels if label is not None])

    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        if self._samples_table is None or not sample_ids:
            return set()
        existing: set[str] = set()
        for i in range(0, len(sample_ids), 1000):
            chunk = sample_ids[i : i + 1000]
            results = (
                self._samples_table.search().where(_in_sql("id", chunk)).select(["id"]).to_list()
            )
            existing.update(r["id"] for r in results)
        return existing

    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        if self._samples_table is None or not sample_ids:
            return []
        rows_by_id: dict[str, dict] = {}
        for i in range(0, len(sample_ids), 1000):
            chunk = sample_ids[i : i + 1000]
            for r in self._samples_table.search().where(_in_sql("id", chunk)).to_list():
                rows_by_id[r["id"]] = r
        return [dict_to_sample(rows_by_id[sid]) for sid in sample_ids if sid in rows_by_id]

    def get_labels_by_ids(self, sample_ids: list[str]) -> dict[str, str | None]:
        if self._samples_table is None or not sample_ids:
            return {}
        labels: dict[str, str | None] = {}
        for i in range(0, len(sample_ids), 1000):
            chunk = sample_ids[i : i + 1000]
            for r in (
                self._samples_table.search()
                .select(["id", "label"])
                .where(_in_sql("id", chunk))
                .to_list()
            ):
                labels[r["id"]] = r.get("label")
        return labels

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        return [s for s in self if predicate(s)]

    def list_spaces(self) -> list[SpaceInfo]:
        return [SpaceInfo.from_dict(r) for r in self._spaces_table.to_arrow().to_pylist()]

    def get_space(self, space_key: str) -> SpaceInfo | None:
        results = (
            self._spaces_table.search().where(col("space_key") == lit(space_key)).limit(1).to_list()
        )
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
                raise ValueError(
                    f"Space '{space_key}' exists with dim={existing.dim}, requested dim={dim}"
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
        _ensure_scalar_index(self._spaces_table, "space_key")
        self._spaces_table.add(
            pa.Table.from_pylist([space_info.to_dict()], schema=create_spaces_schema())
        )
        self._spaces_table.optimize()
        self._db.create_table(f"embeddings__{space_key}", schema=create_embeddings_schema(dim))
        return space_info

    def delete_space(self, space_key: str) -> bool:
        self._spaces_table.delete(_eq_sql("space_key", space_key))
        self._spaces_table.optimize()
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
        _ensure_scalar_index(emb_table, "id")
        data = _dedupe_rows_by_id(
            [
                {"id": id_, "vector": vec.astype(np.float32).tolist()}
                for id_, vec in zip(ids, vectors)
            ]
        )
        emb_table.merge_insert(
            "id"
        ).when_matched_update_all().when_not_matched_insert_all().execute(
            pa.Table.from_pylist(data, schema=create_embeddings_schema(space.dim))
        )
        emb_table.optimize()

        # Update space count
        self._spaces_table.update(
            where=_eq_sql("space_key", space_key),
            values={"count": emb_table.count_rows(), "updated_at": int(time.time())},
        )
        self._spaces_table.optimize()

    def get_embeddings(
        self, space_key: str, ids: list[str] | None = None
    ) -> tuple[list[str], np.ndarray]:
        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            return [], np.empty((0, space.dim), dtype=np.float32)

        emb_table = self._db.open_table(emb_table_name)
        if ids is not None:
            if not ids:
                return [], np.empty((0, space.dim), dtype=np.float32)
            rows = emb_table.search().where(_in_sql("id", ids)).to_list()
        else:
            rows = emb_table.to_arrow().to_pylist()

        if not rows:
            return [], np.empty((0, space.dim), dtype=np.float32)
        return [r["id"] for r in rows], np.array([r["vector"] for r in rows], dtype=np.float32)

    def get_embedded_ids(self, space_key: str) -> set[str]:
        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            return set()
        return {
            r["id"] for r in self._db.open_table(emb_table_name).search().select(["id"]).to_list()
        }

    def get_missing_embedding_ids(self, space_key: str) -> list[str]:
        if self._samples_table is None:
            return []
        all_ids = {r["id"] for r in self._samples_table.search().select(["id"]).to_list()}
        return list(all_ids - self.get_embedded_ids(space_key))

    def _get_layouts_registry_table(self) -> lancedb.table.Table | None:
        return (
            self._db.open_table("layouts_registry")
            if "layouts_registry" in self._table_names()
            else None
        )

    def _layout_table_name(self, layout_key: str) -> str:
        return f"layouts__{layout_key}"

    def _layout_table_has_expected_schema(
        self,
        table: lancedb.table.Table,
        *,
        layout_dimension: int,
    ) -> bool:
        return table.schema.equals(create_layouts_schema(layout_dimension=layout_dimension))

    def _ensure_layouts_registry_table(self) -> lancedb.table.Table:
        schema = create_layouts_registry_schema()
        if "layouts_registry" not in self._table_names():
            table = self._db.create_table("layouts_registry", schema=schema)
            _ensure_scalar_index(table, "layout_key")
            return table

        table = self._db.open_table("layouts_registry")
        if table.schema.equals(schema):
            _ensure_scalar_index(table, "layout_key")
            return table
        raise ValueError(
            "layouts_registry uses an unsupported persisted schema. "
            "Delete the dataset storage and recompute layouts."
        )

    def list_layouts(self) -> list[LayoutInfo]:
        table = self._get_layouts_registry_table()
        return [LayoutInfo.from_dict(row) for row in table.search().to_list()] if table else []

    def get_layout(self, layout_key: str) -> LayoutInfo | None:
        table = self._get_layouts_registry_table()
        if table is None:
            return None
        rows = table.search().where(col("layout_key") == lit(layout_key)).limit(1).to_list()
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

        layout_dimension = parse_layout_dimension(layout_key)

        layout_info = LayoutInfo(
            layout_key=layout_key,
            space_key=space_key,
            method=method,
            geometry=geometry,
            count=0,
            created_at=int(time.time()),
            params=params,
        )
        registry_table = self._ensure_layouts_registry_table()
        _ensure_scalar_index(registry_table, "layout_key")
        registry_table.add(
            pa.Table.from_pylist([layout_info.to_dict()], schema=create_layouts_registry_schema())
        )
        registry_table.optimize()

        table_name = self._layout_table_name(layout_key)
        if table_name not in self._table_names():
            self._db.create_table(
                table_name, schema=create_layouts_schema(layout_dimension=layout_dimension)
            )
        return layout_info

    def delete_layout(self, layout_key: str) -> bool:
        table_name = self._layout_table_name(layout_key)
        if table_name in self._table_names():
            self._db.drop_table(table_name)
        registry = self._get_layouts_registry_table()
        if registry:
            registry.delete(_eq_sql("layout_key", layout_key))
            registry.optimize()
        return True

    def add_layout_coords(self, layout_key: str, ids: list[str], coords: np.ndarray) -> None:
        if len(ids) != len(coords) or len(ids) == 0:
            return
        layout_info = self.get_layout(layout_key)
        if layout_info is None:
            raise ValueError(f"Layout '{layout_key}' not registered")

        layout_dimension = parse_layout_dimension(layout_key)

        coords_arr = np.asarray(coords, dtype=np.float32)
        if coords_arr.ndim != 2:
            raise ValueError(f"coords must be a 2D array, got shape {coords_arr.shape}")
        if coords_arr.shape[1] != layout_dimension:
            raise ValueError(
                f"coords must have shape (N, {layout_dimension}), got {coords_arr.shape}"
            )

        table_name = self._layout_table_name(layout_key)
        if table_name not in self._table_names():
            self._db.create_table(
                table_name,
                schema=create_layouts_schema(layout_dimension=layout_dimension),
            )

        table = self._db.open_table(table_name)
        if not self._layout_table_has_expected_schema(table, layout_dimension=layout_dimension):
            raise ValueError(
                f"Layout '{layout_key}' uses an unsupported persisted schema. "
                "Delete the stale dataset storage and recompute layouts."
            )
        _ensure_layout_indices(table, layout_dimension=layout_dimension)

        if layout_dimension == 2:
            data = _dedupe_rows_by_id(
                [
                    {
                        "id": id_,
                        "x": float(c[0]),
                        "y": float(c[1]),
                    }
                    for id_, c in zip(ids, coords_arr, strict=False)
                ]
            )
        else:
            data = _dedupe_rows_by_id(
                [
                    {
                        "id": id_,
                        "x": float(c[0]),
                        "y": float(c[1]),
                        "z": float(c[2]),
                    }
                    for id_, c in zip(ids, coords_arr, strict=False)
                ]
            )
        schema = create_layouts_schema(layout_dimension=layout_dimension)

        table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(
            pa.Table.from_pylist(data, schema=schema)
        )
        table.optimize()

        # Update count
        registry = self._get_layouts_registry_table()
        if registry:
            registry.update(
                where=_eq_sql("layout_key", layout_key),
                values={"count": table.count_rows()},
            )
            registry.optimize()

    def get_layout_coords(
        self, layout_key: str, ids: list[str] | None = None
    ) -> tuple[list[str], np.ndarray]:
        layout_dimension = parse_layout_dimension(layout_key)

        table_name = self._layout_table_name(layout_key)
        if table_name not in self._table_names():
            return [], np.empty((0, layout_dimension), dtype=np.float32)

        table = self._db.open_table(table_name)
        select_cols = ["id", "x", "y"]
        if layout_dimension == 3:
            select_cols.append("z")

        if ids is not None:
            if not ids:
                return [], np.empty((0, layout_dimension), dtype=np.float32)
            rows = table.search().select(select_cols).where(_in_sql("id", ids)).to_list()
        else:
            rows = table.search().select(select_cols).to_list()

        if not rows:
            return [], np.empty((0, layout_dimension), dtype=np.float32)

        if not self._layout_table_has_expected_schema(table, layout_dimension=layout_dimension):
            raise ValueError(
                f"Layout '{layout_key}' uses an unsupported persisted schema. "
                "Delete the stale dataset storage and recompute layouts."
            )

        if layout_dimension == 2:
            coords = np.array([[r["x"], r["y"]] for r in rows], dtype=np.float32)
        else:
            coords = np.array([[r["x"], r["y"], r["z"]] for r in rows], dtype=np.float32)

        return [r["id"] for r in rows], coords

    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        label_filter: str | None = None,
    ) -> tuple[list[str], np.ndarray]:
        layout_dimension = parse_layout_dimension(layout_key)
        if layout_dimension != 2:
            raise ValueError(
                f"Lasso AABB is only supported for 2D layouts, got {layout_dimension}D"
            )

        table_name = self._layout_table_name(layout_key)
        if table_name not in self._table_names():
            return [], np.empty((0, 2), dtype=np.float32)

        table = self._db.open_table(table_name)
        if not self._layout_table_has_expected_schema(table, layout_dimension=layout_dimension):
            raise ValueError(
                f"Layout '{layout_key}' uses an unsupported persisted schema. "
                "Delete the stale dataset storage and recompute layouts."
            )

        where = (
            (col("x") >= lit(float(x_min)))
            & (col("x") <= lit(float(x_max)))
            & (col("y") >= lit(float(y_min)))
            & (col("y") <= lit(float(y_max)))
        )
        rows = table.search().select(["id", "x", "y"]).where(where).to_list()

        if label_filter is not None and rows:
            if self._samples_table is None:
                return [], np.empty((0, 2), dtype=np.float32)

            matching_ids: set[str] = set()
            candidate_ids = [r["id"] for r in rows]
            for i in range(0, len(candidate_ids), 1000):
                chunk = candidate_ids[i : i + 1000]
                if not chunk:
                    continue
                where = f"{_in_sql('id', chunk)} AND {_eq_sql('label', label_filter)}"
                for r in self._samples_table.search().select(["id"]).where(where).to_list():
                    matching_ids.add(r["id"])

            rows = [r for r in rows if r["id"] in matching_ids]

        if not rows:
            return [], np.empty((0, 2), dtype=np.float32)

        coords = np.array([[r["x"], r["y"]] for r in rows], dtype=np.float32)

        return [r["id"] for r in rows], coords

    def find_similar(
        self, sample_id: str, k: int = 10, space_key: str | None = None
    ) -> list[tuple[Sample, float]]:
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

        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name not in self._table_names():
            return []

        emb_table = self._db.open_table(emb_table_name)
        metric = distance_metric_for_space(space)
        if metric == "hyperboloid":
            results = self._native_hyperboloid_search(
                emb_table,
                vector,
                k=k,
                space=space,
            )
        else:
            results = (
                emb_table.search(vector, vector_column_name="vector")
                .metric("cosine")
                .limit(k)
                .to_list()
            )
        samples_by_id = {s.id: s for s in self.get_samples_by_ids([r["id"] for r in results])}

        return [
            (samples_by_id[r["id"]], 0.0 if math.isnan(d := r.get("_distance", 0.0)) else float(d))
            for r in results
            if r["id"] in samples_by_id
        ]

    def _native_hyperboloid_search(
        self,
        emb_table: lancedb.table.Table,
        vector: list[float] | np.ndarray,
        *,
        k: int,
        space: SpaceInfo,
    ) -> list[dict]:
        rows = (
            emb_table.search(hyperboloid_dot_query(vector), vector_column_name="vector")
            .metric("dot")
            .bypass_vector_index()
            .limit(k)
            .to_list()
        )
        if rows:
            vectors = np.asarray([row["vector"] for row in rows], dtype=np.float32)
            curvature = resolve_hyperboloid_curvature(
                space, np.vstack([np.asarray(vector), vectors])
            )
        else:
            curvature = resolve_hyperboloid_curvature(space, vector)
        return _replace_hyperboloid_distances(rows, vector, curvature)

    def close(self) -> None:
        return
