"""LanceDB storage backend for HyperView."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import lancedb
import pyarrow as pa

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.config import StorageConfig, get_default_database_dir
from hyperview.storage.schema import (
    create_metadata_schema,
    create_sample_schema,
    dict_to_sample,
    sample_to_dict,
)


class LanceDBBackend(StorageBackend):
    """LanceDB-based storage backend for HyperView datasets."""

    def __init__(
        self,
        dataset_name: str,
        config: StorageConfig | None = None,
    ):
        """Initialize LanceDB backend.

        Args:
            dataset_name: Name of the dataset (becomes table name).
            config: Storage configuration. Uses defaults if None.
        """
        self.dataset_name = dataset_name
        self.config = config or StorageConfig.default()

        self.config.ensure_dir_exists()

        self._db = lancedb.connect(str(self.config.database_dir))

        self._table_name = f"hyperview_{dataset_name}"
        self._metadata_table_name = f"hyperview_{dataset_name}_meta"

        self._table = self._get_or_create_table()
        self._metadata_table = self._get_or_create_metadata_table()

        self._label_colors_cache: dict[str, str] | None = None

    def _get_or_create_table(self) -> lancedb.table.Table | None:
        """Get existing table or return None if it doesn't exist yet."""
        if self._table_name in self._db.table_names():
            return self._db.open_table(self._table_name)
        return None

    def _ensure_table_exists(self, data: list[dict]) -> lancedb.table.Table:
        """Ensure table exists, creating it from data if needed.
        """
        if self._table is None:
            schema = create_sample_schema(self.config.embedding_dim)
            arrow_table = pa.Table.from_pylist(data, schema=schema)
            self._table = self._db.create_table(self._table_name, data=arrow_table)
        return self._table

    def _cast_rows_to_table_schema(self, rows: list[dict]) -> pa.Table:
        """Cast Python dict rows to the existing table schema."""
        if self._table is None:
            raise RuntimeError("Cannot cast rows: samples table not initialized")
        return pa.Table.from_pylist(rows, schema=self._table.schema)

    def _get_or_create_metadata_table(self) -> lancedb.table.Table:
        """Get or create metadata table."""
        if self._metadata_table_name in self._db.table_names():
            return self._db.open_table(self._metadata_table_name)
        else:
            schema = create_metadata_schema()
            return self._db.create_table(self._metadata_table_name, schema=schema)

    def _convert_embeddings_to_numpy(self, data: list[dict]) -> None:
        """Convert high-dim embedding lists to numpy arrays in-place.
        """
        import numpy as np

        for row in data:
            if row.get("embedding") is not None:
                row["embedding"] = np.array(row["embedding"], dtype=np.float32)

    def add_sample(self, sample: Sample) -> None:
        """Add a single sample to storage."""
        data = [sample_to_dict(sample, self.config.embedding_dim)]
        self._convert_embeddings_to_numpy(data)
        if self._table is None:
            self._ensure_table_exists(data)
        else:
            self._table.add(self._cast_rows_to_table_schema(data))

    def add_samples_batch(self, samples: list[Sample]) -> None:
        """Add multiple samples efficiently."""
        if not samples:
            return
        data = [sample_to_dict(s, self.config.embedding_dim) for s in samples]
        self._convert_embeddings_to_numpy(data)
        if self._table is None:
            self._ensure_table_exists(data)
        else:
            self._table.add(self._cast_rows_to_table_schema(data))

    def get_sample(self, sample_id: str) -> Sample | None:
        """Retrieve a sample by ID."""
        if self._table is None:
            return None
        safe_id = sample_id.replace("'", "''")
        results = self._table.search().where(f"id = '{safe_id}'").limit(1).to_list()
        if results:
            return dict_to_sample(results[0])
        return None

    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
    ) -> tuple[list[Sample], int]:
        """Get paginated samples using native LanceDB queries."""
        if self._table is None:
            return [], 0

        import pyarrow.compute as pc

        if label:
            arrow_table = self._table.search().select(["label"]).to_arrow()
            label_column = arrow_table.column("label")
            mask = pc.fill_null(pc.equal(label_column, pa.scalar(label)), False)
            total = pc.sum(pc.cast(mask, pa.int64())).as_py()
        else:
            total = self._table.count_rows()

        query = self._table.search()
        if label:
            safe_label = label.replace("'", "''")
            query = query.where(f"label = '{safe_label}'")

        results = query.offset(offset).limit(limit).to_list()
        samples = [dict_to_sample(row) for row in results]
        return samples, total

    def get_all_samples(self) -> list[Sample]:
        """Get all samples."""
        if self._table is None:
            return []
        arrow_table = self._table.to_arrow()
        rows = arrow_table.to_pylist()
        return [dict_to_sample(row) for row in rows]

    def update_sample(self, sample: Sample) -> None:
        """Update an existing sample."""
        self._delete_by_id(sample.id)
        self.add_sample(sample)

    def update_samples_batch(self, samples: list[Sample]) -> None:
        """Batch update samples."""
        if not samples:
            return

        if self._table is None:
            self.add_samples_batch(samples)
            return

        if self._needs_schema_migration(samples):
            self._migrate_table_schema(samples)
        else:
            updated_data = [sample_to_dict(s, self.config.embedding_dim) for s in samples]
            self._convert_embeddings_to_numpy(updated_data)

            arrow = self._cast_rows_to_table_schema(updated_data)
            (
                self._table.merge_insert("id")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(arrow)
            )

    def _needs_schema_migration(self, samples: list[Sample]) -> bool:
        """Check whether embedding columns exist with a non-null type."""
        schema = self._table.schema

        columns_to_check = [
            ("embedding", lambda s: s.embedding is not None),
            ("embedding_2d_euclidean", lambda s: s.embedding_2d is not None),
            ("embedding_2d_hyperbolic", lambda s: s.embedding_2d_hyperbolic is not None),
        ]

        for col_name, has_value_fn in columns_to_check:
            has_values = any(has_value_fn(s) for s in samples)
            if not has_values:
                continue
            try:
                field = schema.field(col_name)
                if str(field.type) == "null":
                    return True
            except KeyError:
                return True

        return False

    def _migrate_table_schema(self, updated_samples: list[Sample]) -> None:
        """Recreate the table with the current schema and merge updates."""
        existing_rows = self._table.to_arrow().to_pylist()
        updates_by_id = {s.id: s for s in updated_samples}

        new_data: list[dict] = []
        for row in existing_rows:
            sample_id = row.get("id")
            if sample_id in updates_by_id:
                new_data.append(sample_to_dict(updates_by_id[sample_id], self.config.embedding_dim))
            else:
                new_data.append(row)

        self._convert_embeddings_to_numpy(new_data)

        self._db.drop_table(self._table_name)
        self._table = None
        self._ensure_table_exists(new_data)

    def _delete_by_id(self, sample_id: str) -> bool:
        """Delete a sample by ID using native LanceDB delete."""
        if self._table is None:
            return False
        try:
            # Use LanceDB's native delete with SQL WHERE clause
            safe_id = sample_id.replace("'", "''")
            self._table.delete(f"id = '{safe_id}'")
            return True
        except Exception:
            return False

    def delete_sample(self, sample_id: str) -> bool:
        """Delete a sample by ID."""
        return self._delete_by_id(sample_id)

    def __len__(self) -> int:
        """Return total number of samples."""
        if self._table is None:
            return 0
        return self._table.count_rows()

    def __iter__(self) -> Iterator[Sample]:
        """Iterate over all samples."""
        if self._table is None:
            return iter([])
        arrow_table = self._table.to_arrow()
        for batch in arrow_table.to_batches(max_chunksize=1000):
            batch_dict = batch.to_pydict()
            for i in range(batch.num_rows):
                row = {k: batch_dict[k][i] for k in batch_dict}
                yield dict_to_sample(row)

    def __contains__(self, sample_id: str) -> bool:
        """Check if sample exists."""
        if self._table is None:
            return False
        safe_id = sample_id.replace("'", "''")
        try:
            results = self._table.search().where(f"id = '{safe_id}'").limit(1).to_list()
            return len(results) > 0
        except Exception:
            return False

    def get_unique_labels(self) -> list[str]:
        """Get all unique labels."""
        if self._table is None:
            return []
        import pyarrow.compute as pc

        # Label-only scan - don't pull thumbnails/metadata into RAM
        arrow_table = self._table.search().select(["label"]).to_arrow()
        label_column = arrow_table.column("label")
        unique_labels = pc.unique(label_column).to_pylist()
        return sorted([label for label in unique_labels if label is not None])

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        vector_column: str = "embedding",
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a sample."""
        sample = self.get_sample(sample_id)
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
        import math

        lance_column = self._map_vector_column(vector_column)

        try:
            results = (
                self._table.search(vector, vector_column_name=lance_column)
                .metric("cosine")
                .limit(k)
                .to_list()
            )

            # Normalize nan distances to 0.0 (can happen with identical vectors)
            return [
                (
                    dict_to_sample(row),
                    0.0
                    if math.isnan(d := row.get("_distance", 0.0))
                    else float(d),
                )
                for row in results
            ]
        except Exception:
            return self._brute_force_search(vector, k, vector_column)

    def _brute_force_search(
        self,
        vector: list[float],
        k: int,
        vector_column: str,
    ) -> list[tuple[Sample, float]]:
        """Fallback brute force search when vector index is not available."""
        import numpy as np

        query = np.array(vector)
        distances: list[tuple[Sample, float]] = []

        for sample in self:
            vec = self._get_vector(sample, vector_column)
            if vec is None:
                continue

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
        elif vector_column in ("embedding_2d_euclidean", "embedding_2d"):
            return sample.embedding_2d
        elif vector_column == "embedding_2d_hyperbolic":
            return sample.embedding_2d_hyperbolic
        else:
            raise ValueError(f"Unknown vector column: {vector_column}")

    def _map_vector_column(self, vector_column: str) -> str:
        """Map vector column name to LanceDB column name."""
        mapping = {
            "embedding": "embedding",
            "embedding_2d": "embedding_2d_euclidean",
            "embedding_2d_euclidean": "embedding_2d_euclidean",
            "embedding_2d_hyperbolic": "embedding_2d_hyperbolic",
        }
        return mapping.get(vector_column, vector_column)

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""
        return [s for s in self if predicate(s)]

    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        """Return the subset of sample_ids that exist in storage."""
        if self._table is None or not sample_ids:
            return set()

        existing: set[str] = set()

        def query_chunk(chunk: list[str]) -> set[str]:
            escaped = [sid.replace("'", "''") for sid in chunk]
            id_list = "', '".join(escaped)
            results = self._table.search().where(f"id IN ('{id_list}')").select(["id"]).to_list()
            return {r["id"] for r in results}

        chunk_size = 1000
        for i in range(0, len(sample_ids), chunk_size):
            chunk = sample_ids[i : i + chunk_size]
            try:
                existing.update(query_chunk(chunk))
            except Exception:
                existing.update(sid for sid in chunk if sid in self)

        return existing

    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        """Retrieve multiple samples by ID.

        Uses chunked `id IN (...)` queries to avoid per-ID round trips.
        """
        if self._table is None or not sample_ids:
            return []

        rows_by_id: dict[str, dict] = {}

        def query_chunk(chunk: list[str]) -> None:
            escaped = [sid.replace("'", "''") for sid in chunk]
            id_list = "', '".join(escaped)
            results = self._table.search().where(f"id IN ('{id_list}')").to_list()
            for r in results:
                rid = r.get("id")
                if isinstance(rid, str):
                    rows_by_id[rid] = r

        chunk_size = 500
        for i in range(0, len(sample_ids), chunk_size):
            query_chunk(sample_ids[i : i + chunk_size])

        out: list[Sample] = []
        for sid in sample_ids:
            row = rows_by_id.get(sid)
            if row is not None:
                out.append(dict_to_sample(row))
        return out

    def get_visualization_embeddings(
        self,
    ) -> tuple[list[str], list[str | None], list[list[float]], list[list[float]]]:
        """Return ids/labels and both 2D projections for the scatter."""
        if self._table is None:
            return [], [], [], []

        rows = (
            self._table.search()
            .select(["id", "label", "embedding_2d_euclidean", "embedding_2d_hyperbolic"])
            .where("embedding_2d_euclidean IS NOT NULL AND embedding_2d_hyperbolic IS NOT NULL")
            .to_list()
        )

        ids: list[str] = []
        labels: list[str | None] = []
        euclidean: list[list[float]] = []
        hyperbolic: list[list[float]] = []

        for r in rows:
            eid = r.get("id")
            e2 = r.get("embedding_2d_euclidean")
            h2 = r.get("embedding_2d_hyperbolic")
            if not isinstance(eid, str) or e2 is None or h2 is None:
                continue
            ids.append(eid)
            labels.append(r.get("label"))
            euclidean.append(list(e2))
            hyperbolic.append(list(h2))

        return ids, labels, euclidean, hyperbolic

    def get_lasso_candidates_aabb(
        self,
        *,
        space: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], "np.ndarray"]:
        """Return candidate (id, xy) rows within an AABB for a given projection."""
        if self._table is None:
            import numpy as np

            return [], np.empty((0, 2), dtype=np.float32)

        if space == "euclidean":
            col = "embedding_2d_euclidean"
        elif space == "hyperbolic":
            col = "embedding_2d_hyperbolic"
        else:
            raise ValueError(f"Unknown space: {space}")

        # Keep selection universe consistent with /api/embeddings: require both projections.
        expr = (
            "embedding_2d_euclidean IS NOT NULL AND "
            "embedding_2d_hyperbolic IS NOT NULL AND "
            f"{col}[1] >= {x_min} AND {col}[1] <= {x_max} AND "
            f"{col}[2] >= {y_min} AND {col}[2] <= {y_max}"
        )

        rows = self._table.search().select(["id", col]).where(expr).to_list()

        ids: list[str] = []
        coords: list[list[float]] = []
        for r in rows:
            sid = r.get("id")
            xy = r.get(col)
            if not isinstance(sid, str) or xy is None:
                continue
            if len(xy) != 2:
                continue
            ids.append(sid)
            coords.append([float(xy[0]), float(xy[1])])

        import numpy as np

        if not coords:
            return [], np.empty((0, 2), dtype=np.float32)
        return ids, np.asarray(coords, dtype=np.float32)

    def close(self) -> None:
        """Close the storage connection."""
        return

    @property
    def label_colors(self) -> dict[str, str]:
        """Get label color mapping."""
        if self._label_colors_cache is not None:
            return self._label_colors_cache

        rows = self._metadata_table.search().where("key = 'label_colors'").limit(1).to_list()
        if not rows:
            self._label_colors_cache = {}
            return self._label_colors_cache

        value = rows[0].get("value")
        self._label_colors_cache = json.loads(value) if value else {}

        return self._label_colors_cache

    @label_colors.setter
    def label_colors(self, colors: dict[str, str]) -> None:
        """Set label color mapping."""
        self._label_colors_cache = colors

        try:
            self._metadata_table.delete("key = 'label_colors'")
        except Exception:
            pass

        schema = create_metadata_schema()
        row = {"key": "label_colors", "value": json.dumps(colors)}
        self._metadata_table.add(pa.Table.from_pylist([row], schema=schema))

    def create_vector_index(self, vector_column: str = "embedding") -> None:
        """Create an ANN index for vector search."""
        if self._table is None:
            return
        num_rows = self._table.count_rows()
        if num_rows < 256:
            return

        lance_column = self._map_vector_column(vector_column)

        try:
            self._table.create_index(
                vector_column_name=lance_column,
                index_type="IVF_PQ",
                num_partitions=min(256, num_rows // 10),
                num_sub_vectors=16,
            )
        except Exception:
            return

    @classmethod
    def list_datasets(cls, database_dir: Path | None = None) -> list[str]:
        """List all available datasets in the database directory."""
        if database_dir is None:
            database_dir = get_default_database_dir()

        if not database_dir.exists():
            return []

        db = lancedb.connect(str(database_dir))
        datasets = []
        for table_name in db.table_names():
            if table_name.startswith("hyperview_") and not table_name.endswith("_meta"):
                datasets.append(table_name[len("hyperview_") :])
        return sorted(datasets)

    @classmethod
    def delete_dataset(cls, dataset_name: str, database_dir: Path | None = None) -> bool:
        """Delete a dataset from the database."""
        if database_dir is None:
            database_dir = get_default_database_dir()

        if not database_dir.exists():
            return False

        db = lancedb.connect(str(database_dir))
        table_name = f"hyperview_{dataset_name}"
        metadata_table_name = f"hyperview_{dataset_name}_meta"

        deleted = False
        if table_name in db.table_names():
            db.drop_table(table_name)
            deleted = True

        if metadata_table_name in db.table_names():
            db.drop_table(metadata_table_name)

        return deleted

    @classmethod
    def dataset_exists(cls, dataset_name: str, database_dir: Path | None = None) -> bool:
        """Check if a dataset exists."""
        if database_dir is None:
            database_dir = get_default_database_dir()

        if not database_dir.exists():
            return False

        db = lancedb.connect(str(database_dir))
        table_name = f"hyperview_{dataset_name}"
        return table_name in db.table_names()
