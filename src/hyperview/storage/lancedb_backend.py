"""LanceDB storage backend for HyperView.

Storage architecture (per-dataset directory):
    ~/.hyperview/datasets/<dataset_name>/
        - samples table: core sample metadata
        - metadata table: key-value config
        - spaces table: registry of embedding spaces
        - embeddings__<space_key> tables: one per embedding model
        - layouts__<layout_key> tables: one per layout
"""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import lancedb
import numpy as np
import pyarrow as pa

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.config import StorageConfig, get_default_datasets_dir
from hyperview.storage.schema import (
    SpaceInfo,
    create_embeddings_schema,
    create_layouts_schema,
    create_metadata_schema,
    create_sample_schema,
    create_spaces_schema,
    dict_to_sample,
    make_layout_key,
    make_space_key,
    sample_to_dict,
)


class LanceDBBackend(StorageBackend):
    """LanceDB-based storage backend for HyperView datasets.

    Each dataset gets its own directory with isolated LanceDB tables.
    """

    def __init__(
        self,
        dataset_name: str,
        config: StorageConfig | None = None,
    ):
        """Initialize LanceDB backend.

        Args:
            dataset_name: Name of the dataset (becomes directory name).
            config: Storage configuration. Uses defaults if None.
        """
        self.dataset_name = dataset_name
        self.config = config or StorageConfig.default()

        # Per-dataset directory
        self._dataset_dir = self.config.datasets_dir / dataset_name
        self._dataset_dir.mkdir(parents=True, exist_ok=True)

        # Connect to this dataset's LanceDB
        self._db = lancedb.connect(str(self._dataset_dir))

        # Table names (no prefix needed since we have per-dataset isolation)
        self._samples_table_name = "samples"
        self._metadata_table_name = "metadata"
        self._spaces_table_name = "spaces"

        # Initialize core tables
        self._samples_table = self._get_or_create_samples_table()
        self._metadata_table = self._get_or_create_metadata_table()
        self._spaces_table = self._get_or_create_spaces_table()

        self._label_colors_cache: dict[str, str] | None = None

    # =========================================================================
    # Table initialization
    # =========================================================================

    def _get_or_create_samples_table(self) -> lancedb.table.Table | None:
        """Get existing samples table or return None."""
        if self._samples_table_name in self._db.table_names():
            return self._db.open_table(self._samples_table_name)
        return None

    def _ensure_samples_table(self, data: list[dict]) -> lancedb.table.Table:
        """Ensure samples table exists, creating from data if needed."""
        if self._samples_table is None:
            schema = create_sample_schema()
            arrow_table = pa.Table.from_pylist(data, schema=schema)
            self._samples_table = self._db.create_table(self._samples_table_name, data=arrow_table)
        return self._samples_table

    def _get_or_create_metadata_table(self) -> lancedb.table.Table:
        """Get or create metadata table."""
        if self._metadata_table_name in self._db.table_names():
            return self._db.open_table(self._metadata_table_name)
        schema = create_metadata_schema()
        return self._db.create_table(self._metadata_table_name, schema=schema)

    def _get_or_create_spaces_table(self) -> lancedb.table.Table:
        """Get or create spaces registry table."""
        if self._spaces_table_name in self._db.table_names():
            return self._db.open_table(self._spaces_table_name)
        schema = create_spaces_schema()
        return self._db.create_table(self._spaces_table_name, schema=schema)

    # =========================================================================
    # Sample CRUD operations
    # =========================================================================

    def add_sample(self, sample: Sample) -> None:
        """Add a single sample to storage."""
        data = [sample_to_dict(sample)]
        if self._samples_table is None:
            self._ensure_samples_table(data)
        else:
            arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
            self._samples_table.add(arrow)

    def add_samples_batch(self, samples: list[Sample]) -> None:
        """Add multiple samples efficiently."""
        if not samples:
            return
        data = [sample_to_dict(s) for s in samples]
        if self._samples_table is None:
            self._ensure_samples_table(data)
        else:
            arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
            self._samples_table.add(arrow)

    def get_sample(self, sample_id: str) -> Sample | None:
        """Retrieve a sample by ID."""
        if self._samples_table is None:
            return None
        safe_id = sample_id.replace("'", "''")
        results = self._samples_table.search().where(f"id = '{safe_id}'").limit(1).to_list()
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
        if self._samples_table is None:
            return [], 0

        import pyarrow.compute as pc

        if label:
            arrow_table = self._samples_table.search().select(["label"]).to_arrow()
            label_column = arrow_table.column("label")
            mask = pc.fill_null(pc.equal(label_column, pa.scalar(label)), False)
            total = pc.sum(pc.cast(mask, pa.int64())).as_py()
        else:
            total = self._samples_table.count_rows()

        query = self._samples_table.search()
        if label:
            safe_label = label.replace("'", "''")
            query = query.where(f"label = '{safe_label}'")

        results = query.offset(offset).limit(limit).to_list()
        samples = [dict_to_sample(row) for row in results]
        return samples, total

    def get_all_samples(self) -> list[Sample]:
        """Get all samples."""
        if self._samples_table is None:
            return []
        arrow_table = self._samples_table.to_arrow()
        rows = arrow_table.to_pylist()
        return [dict_to_sample(row) for row in rows]

    def update_sample(self, sample: Sample) -> None:
        """Update an existing sample."""
        if self._samples_table is None:
            self.add_sample(sample)
            return
        data = [sample_to_dict(sample)]
        arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
        (
            self._samples_table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(arrow)
        )

    def update_samples_batch(self, samples: list[Sample]) -> None:
        """Batch update samples."""
        if not samples:
            return
        if self._samples_table is None:
            self.add_samples_batch(samples)
            return
        data = [sample_to_dict(s) for s in samples]
        arrow = pa.Table.from_pylist(data, schema=self._samples_table.schema)
        (
            self._samples_table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(arrow)
        )

    def delete_sample(self, sample_id: str) -> bool:
        """Delete a sample by ID."""
        if self._samples_table is None:
            return False
        try:
            safe_id = sample_id.replace("'", "''")
            self._samples_table.delete(f"id = '{safe_id}'")
            return True
        except Exception:
            return False

    def __len__(self) -> int:
        """Return total number of samples."""
        if self._samples_table is None:
            return 0
        return self._samples_table.count_rows()

    def __iter__(self) -> Iterator[Sample]:
        """Iterate over all samples."""
        if self._samples_table is None:
            return iter([])
        arrow_table = self._samples_table.to_arrow()
        for batch in arrow_table.to_batches(max_chunksize=1000):
            batch_dict = batch.to_pydict()
            for i in range(batch.num_rows):
                row = {k: batch_dict[k][i] for k in batch_dict}
                yield dict_to_sample(row)

    def __contains__(self, sample_id: str) -> bool:
        """Check if sample exists."""
        if self._samples_table is None:
            return False
        safe_id = sample_id.replace("'", "''")
        try:
            results = self._samples_table.search().where(f"id = '{safe_id}'").limit(1).to_list()
            return len(results) > 0
        except Exception:
            return False

    def get_unique_labels(self) -> list[str]:
        """Get all unique labels."""
        if self._samples_table is None:
            return []
        import pyarrow.compute as pc

        arrow_table = self._samples_table.search().select(["label"]).to_arrow()
        label_column = arrow_table.column("label")
        unique_labels = pc.unique(label_column).to_pylist()
        return sorted([label for label in unique_labels if label is not None])

    def get_existing_ids(self, sample_ids: list[str]) -> set[str]:
        """Return the subset of sample_ids that exist in storage."""
        if self._samples_table is None or not sample_ids:
            return set()

        existing: set[str] = set()

        def query_chunk(chunk: list[str]) -> set[str]:
            escaped = [sid.replace("'", "''") for sid in chunk]
            id_list = "', '".join(escaped)
            results = self._samples_table.search().where(f"id IN ('{id_list}')").select(["id"]).to_list()
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
        """Retrieve multiple samples by ID."""
        if self._samples_table is None or not sample_ids:
            return []

        rows_by_id: dict[str, dict] = {}

        def query_chunk(chunk: list[str]) -> None:
            escaped = [sid.replace("'", "''") for sid in chunk]
            id_list = "', '".join(escaped)
            results = self._samples_table.search().where(f"id IN ('{id_list}')").to_list()
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

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""
        return [s for s in self if predicate(s)]

    # =========================================================================
    # Spaces registry (embedding spaces)
    # =========================================================================

    def list_spaces(self) -> list[SpaceInfo]:
        """List all embedding spaces."""
        rows = self._spaces_table.to_arrow().to_pylist()
        return [SpaceInfo.from_dict(r) for r in rows]

    def get_space(self, space_key: str) -> SpaceInfo | None:
        """Get info for a specific embedding space."""
        safe_key = space_key.replace("'", "''")
        results = self._spaces_table.search().where(f"space_key = '{safe_key}'").limit(1).to_list()
        if results:
            return SpaceInfo.from_dict(results[0])
        return None

    def ensure_space(self, model_id: str, dim: int, config: dict | None = None) -> SpaceInfo:
        """Ensure an embedding space exists, creating it if needed.

        Args:
            model_id: The model identifier (e.g., "openai/clip-vit-base-patch32").
            dim: Vector dimension for this model.
            config: Optional config dict for the space.

        Returns:
            SpaceInfo for the space (existing or newly created).

        Raises:
            ValueError: If space exists with different dimension.
        """
        space_key = make_space_key(model_id)
        existing = self.get_space(space_key)

        if existing is not None:
            if existing.dim != dim:
                raise ValueError(
                    f"Space '{space_key}' exists with dim={existing.dim}, "
                    f"but requested dim={dim}"
                )
            return existing

        # Create new space
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

        # Add to registry
        schema = create_spaces_schema()
        arrow = pa.Table.from_pylist([space_info.to_dict()], schema=schema)
        self._spaces_table.add(arrow)

        # Create embeddings table for this space
        emb_table_name = f"embeddings__{space_key}"
        emb_schema = create_embeddings_schema(dim)
        self._db.create_table(emb_table_name, schema=emb_schema)

        return space_info

    def delete_space(self, space_key: str) -> bool:
        """Delete an embedding space and its embeddings table."""
        safe_key = space_key.replace("'", "''")

        # Delete from registry
        try:
            self._spaces_table.delete(f"space_key = '{safe_key}'")
        except Exception:
            return False

        # Drop embeddings table
        emb_table_name = f"embeddings__{space_key}"
        if emb_table_name in self._db.table_names():
            self._db.drop_table(emb_table_name)

        return True

    def _update_space_count(self, space_key: str, count: int) -> None:
        """Update the count and updated_at for a space."""
        now = int(time.time())
        self._spaces_table.update(
            where=f"space_key = '{space_key}'",
            values={"count": count, "updated_at": now},
        )

    # =========================================================================
    # Embeddings operations
    # =========================================================================

    def get_embeddings_table_name(self, space_key: str) -> str:
        """Get the table name for an embedding space."""
        return f"embeddings__{space_key}"

    def add_embeddings(
        self,
        space_key: str,
        ids: list[str],
        vectors: np.ndarray,
    ) -> None:
        """Add embeddings to a space.

        Args:
            space_key: The embedding space key.
            ids: Sample IDs.
            vectors: Embedding vectors (N x dim).
        """
        if len(ids) != len(vectors):
            raise ValueError("ids and vectors must have same length")
        if len(ids) == 0:
            return

        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        if vectors.shape[1] != space.dim:
            raise ValueError(f"Vector dim {vectors.shape[1]} != space dim {space.dim}")

        emb_table_name = self.get_embeddings_table_name(space_key)
        emb_table = self._db.open_table(emb_table_name)

        # Convert to list of dicts
        data = [
            {"id": id_, "vector": vec.astype(np.float32)}
            for id_, vec in zip(ids, vectors)
        ]
        schema = create_embeddings_schema(space.dim)
        arrow = pa.Table.from_pylist(data, schema=schema)

        # Use merge_insert for idempotent upsert (handles retries/partial runs)
        (
            emb_table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(arrow)
        )

        # Update count
        new_count = emb_table.count_rows()
        self._update_space_count(space_key, new_count)

    def get_embeddings(
        self,
        space_key: str,
        ids: list[str] | None = None,
    ) -> tuple[list[str], np.ndarray]:
        """Get embeddings from a space.

        Args:
            space_key: The embedding space key.
            ids: Optional list of IDs to fetch. If None, fetch all.

        Returns:
            (ids, vectors) where vectors is (N x dim).
        """
        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        emb_table_name = self.get_embeddings_table_name(space_key)
        if emb_table_name not in self._db.table_names():
            return [], np.empty((0, space.dim), dtype=np.float32)

        emb_table = self._db.open_table(emb_table_name)

        if ids is not None:
            # Fetch specific IDs
            escaped = [sid.replace("'", "''") for sid in ids]
            id_list = "', '".join(escaped)
            rows = emb_table.search().where(f"id IN ('{id_list}')").to_list()
        else:
            # Fetch all
            rows = emb_table.to_arrow().to_pylist()

        if not rows:
            return [], np.empty((0, space.dim), dtype=np.float32)

        out_ids = [r["id"] for r in rows]
        out_vecs = np.array([r["vector"] for r in rows], dtype=np.float32)
        return out_ids, out_vecs

    def get_embedded_ids(self, space_key: str) -> set[str]:
        """Get the set of sample IDs that have embeddings in a space."""
        emb_table_name = self.get_embeddings_table_name(space_key)
        if emb_table_name not in self._db.table_names():
            return set()

        emb_table = self._db.open_table(emb_table_name)
        rows = emb_table.search().select(["id"]).to_list()
        return {r["id"] for r in rows}

    def get_missing_embedding_ids(self, space_key: str) -> list[str]:
        """Get sample IDs that don't have embeddings in a space."""
        if self._samples_table is None:
            return []

        all_ids = {r["id"] for r in self._samples_table.search().select(["id"]).to_list()}
        embedded_ids = self.get_embedded_ids(space_key)
        return list(all_ids - embedded_ids)

    # =========================================================================
    # Layouts operations
    # =========================================================================

    def get_layout_table_name(self, layout_key: str) -> str:
        """Get the table name for a layout."""
        return f"layouts__{layout_key}"

    def list_layouts(self) -> list[str]:
        """List all layout keys."""
        layouts = []
        for name in self._db.table_names():
            if name.startswith("layouts__"):
                layouts.append(name[len("layouts__") :])
        return layouts

    def ensure_layout(self, layout_key: str) -> None:
        """Ensure a layout table exists."""
        table_name = self.get_layout_table_name(layout_key)
        if table_name not in self._db.table_names():
            schema = create_layouts_schema()
            self._db.create_table(table_name, schema=schema)

    def delete_layout(self, layout_key: str) -> bool:
        """Delete a layout table."""
        table_name = self.get_layout_table_name(layout_key)
        if table_name in self._db.table_names():
            self._db.drop_table(table_name)
            return True
        return False

    def add_layout_coords(
        self,
        layout_key: str,
        ids: list[str],
        coords: np.ndarray,
    ) -> None:
        """Add layout coordinates.

        Args:
            layout_key: The layout key.
            ids: Sample IDs.
            coords: 2D coordinates (N x 2).
        """
        if len(ids) != len(coords):
            raise ValueError("ids and coords must have same length")
        if len(ids) == 0:
            return

        self.ensure_layout(layout_key)

        table_name = self.get_layout_table_name(layout_key)
        table = self._db.open_table(table_name)

        data = [
            {"id": id_, "x": float(coord[0]), "y": float(coord[1])}
            for id_, coord in zip(ids, coords)
        ]
        schema = create_layouts_schema()
        arrow = pa.Table.from_pylist(data, schema=schema)

        # Use merge_insert to handle updates
        (
            table.merge_insert("id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(arrow)
        )

    def get_layout_coords(
        self,
        layout_key: str,
        ids: list[str] | None = None,
    ) -> tuple[list[str], np.ndarray]:
        """Get layout coordinates.

        Args:
            layout_key: The layout key.
            ids: Optional list of IDs to fetch. If None, fetch all.

        Returns:
            (ids, coords) where coords is (N x 2).
        """
        table_name = self.get_layout_table_name(layout_key)
        if table_name not in self._db.table_names():
            return [], np.empty((0, 2), dtype=np.float32)

        table = self._db.open_table(table_name)

        if ids is not None:
            escaped = [sid.replace("'", "''") for sid in ids]
            id_list = "', '".join(escaped)
            rows = table.search().where(f"id IN ('{id_list}')").to_list()
        else:
            rows = table.to_arrow().to_pylist()

        if not rows:
            return [], np.empty((0, 2), dtype=np.float32)

        out_ids = [r["id"] for r in rows]
        out_coords = np.array([[r["x"], r["y"]] for r in rows], dtype=np.float32)
        return out_ids, out_coords

    def get_visualization_data(
        self,
        layout_key: str,
    ) -> tuple[list[str], list[str | None], np.ndarray]:
        """Get visualization data (ids, labels, coords) for a layout.

        This joins samples with layout coords for the scatter plot.

        Returns:
            (ids, labels, coords) where coords is (N x 2).
        """
        table_name = self.get_layout_table_name(layout_key)
        if table_name not in self._db.table_names():
            return [], [], np.empty((0, 2), dtype=np.float32)

        if self._samples_table is None:
            return [], [], np.empty((0, 2), dtype=np.float32)

        layout_table = self._db.open_table(table_name)

        # Get all layout coords
        layout_rows = layout_table.to_arrow().to_pylist()
        if not layout_rows:
            return [], [], np.empty((0, 2), dtype=np.float32)

        # Build id -> coords map
        coords_by_id = {r["id"]: (r["x"], r["y"]) for r in layout_rows}
        layout_ids = list(coords_by_id.keys())

        # Get labels for these IDs
        escaped = [sid.replace("'", "''") for sid in layout_ids]
        id_list = "', '".join(escaped)
        sample_rows = self._samples_table.search().select(["id", "label"]).where(f"id IN ('{id_list}')").to_list()
        labels_by_id = {r["id"]: r.get("label") for r in sample_rows}

        # Build aligned output
        ids = []
        labels = []
        coords = []
        for id_ in layout_ids:
            if id_ in labels_by_id:
                ids.append(id_)
                labels.append(labels_by_id[id_])
                coords.append(coords_by_id[id_])

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
        """Return candidate (id, xy) rows within an AABB for a layout."""
        table_name = self.get_layout_table_name(layout_key)
        if table_name not in self._db.table_names():
            return [], np.empty((0, 2), dtype=np.float32)

        table = self._db.open_table(table_name)

        expr = f"x >= {x_min} AND x <= {x_max} AND y >= {y_min} AND y <= {y_max}"
        rows = table.search().where(expr).to_list()

        if not rows:
            return [], np.empty((0, 2), dtype=np.float32)

        ids = [r["id"] for r in rows]
        coords = np.array([[r["x"], r["y"]] for r in rows], dtype=np.float32)
        return ids, coords

    # =========================================================================
    # Similarity search
    # =========================================================================

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a sample.

        Args:
            sample_id: The query sample ID.
            k: Number of neighbors.
            space_key: Embedding space to use. If None, uses default.

        Returns:
            List of (sample, distance) tuples.
        """
        if space_key is None:
            spaces = self.list_spaces()
            if not spaces:
                raise ValueError("No embedding spaces available")
            space_key = spaces[0].space_key

        # Get query vector
        ids, vecs = self.get_embeddings(space_key, [sample_id])
        if not ids:
            raise ValueError(f"Sample {sample_id} has no embedding in space {space_key}")

        query_vector = vecs[0]
        results = self.find_similar_by_vector(query_vector, k + 1, space_key)
        return [(s, d) for s, d in results if s.id != sample_id][:k]

    def find_similar_by_vector(
        self,
        vector: list[float] | np.ndarray,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k nearest neighbors to a query vector."""
        import math

        if space_key is None:
            spaces = self.list_spaces()
            if not spaces:
                raise ValueError("No embedding spaces available")
            space_key = spaces[0].space_key

        space = self.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        emb_table_name = self.get_embeddings_table_name(space_key)
        if emb_table_name not in self._db.table_names():
            return []

        emb_table = self._db.open_table(emb_table_name)

        try:
            results = (
                emb_table.search(vector, vector_column_name="vector")
                .metric("cosine")
                .limit(k)
                .to_list()
            )

            # Get sample info for results
            result_ids = [r["id"] for r in results]
            samples = self.get_samples_by_ids(result_ids)
            samples_by_id = {s.id: s for s in samples}

            return [
                (
                    samples_by_id[r["id"]],
                    0.0 if math.isnan(d := r.get("_distance", 0.0)) else float(d),
                )
                for r in results
                if r["id"] in samples_by_id
            ]
        except Exception:
            return []

    # =========================================================================
    # Vector index creation
    # =========================================================================

    def create_vector_index(self, space_key: str) -> None:
        """Create an ANN index for an embedding space."""
        emb_table_name = self.get_embeddings_table_name(space_key)
        if emb_table_name not in self._db.table_names():
            return

        emb_table = self._db.open_table(emb_table_name)
        num_rows = emb_table.count_rows()
        if num_rows < 256:
            return

        try:
            emb_table.create_index(
                vector_column_name="vector",
                index_type="IVF_PQ",
                num_partitions=min(256, num_rows // 10),
                num_sub_vectors=16,
            )
        except Exception:
            pass

    # =========================================================================
    # Label colors
    # =========================================================================

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

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def close(self) -> None:
        """Close the storage connection."""
        pass

    # =========================================================================
    # Class methods for dataset management
    # =========================================================================

    @classmethod
    def list_datasets(cls, datasets_dir: Path | None = None) -> list[str]:
        """List all available datasets."""
        if datasets_dir is None:
            datasets_dir = get_default_datasets_dir()

        if not datasets_dir.exists():
            return []

        datasets = []
        for path in datasets_dir.iterdir():
            if path.is_dir():
                # Check if it looks like a LanceDB dataset
                if (path / "samples.lance").exists() or any(
                    p.name.endswith(".lance") for p in path.iterdir() if p.is_dir()
                ):
                    datasets.append(path.name)
        return sorted(datasets)

    @classmethod
    def delete_dataset(cls, dataset_name: str, datasets_dir: Path | None = None) -> bool:
        """Delete a dataset directory."""
        if datasets_dir is None:
            datasets_dir = get_default_datasets_dir()

        dataset_path = datasets_dir / dataset_name
        if not dataset_path.exists():
            return False

        import shutil

        shutil.rmtree(dataset_path)
        return True

    @classmethod
    def dataset_exists(cls, dataset_name: str, datasets_dir: Path | None = None) -> bool:
        """Check if a dataset exists."""
        if datasets_dir is None:
            datasets_dir = get_default_datasets_dir()

        dataset_path = datasets_dir / dataset_name
        return dataset_path.exists() and dataset_path.is_dir()
