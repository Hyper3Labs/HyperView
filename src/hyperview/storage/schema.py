"""LanceDB schema definitions for HyperView.

Storage architecture:
- samples: Core sample metadata (no embeddings)
- metadata: Key-value pairs for dataset config
- spaces: Registry of embedding spaces
- embeddings__<space_key>: One table per embedding space (id + vector)
- layouts__<layout_key>: One table per layout (id + x + y)
"""

import json
import re
from dataclasses import dataclass
from typing import Any

import pyarrow as pa

from hyperview.core.sample import Sample


def create_sample_schema() -> pa.Schema:
    """Create the PyArrow schema for samples.

    Samples are pure metadata - embeddings and layouts are stored separately.
    """
    return pa.schema(
        [
            pa.field("id", pa.utf8(), nullable=False),
            pa.field("filepath", pa.utf8(), nullable=False),
            pa.field("label", pa.utf8(), nullable=True),
            pa.field("metadata_json", pa.utf8(), nullable=True),
            pa.field("thumbnail_base64", pa.utf8(), nullable=True),
        ]
    )


def create_metadata_schema() -> pa.Schema:
    """Create the PyArrow schema for dataset metadata (key-value store)."""
    return pa.schema(
        [
            pa.field("key", pa.utf8(), nullable=False),
            pa.field("value", pa.utf8(), nullable=True),
        ]
    )


def create_spaces_schema() -> pa.Schema:
    """Create the PyArrow schema for the spaces registry.

    Each row represents an embedding space (one per model).
    """
    return pa.schema(
        [
            pa.field("space_key", pa.utf8(), nullable=False),
            pa.field("model_id", pa.utf8(), nullable=False),
            pa.field("dim", pa.int32(), nullable=False),
            pa.field("count", pa.int64(), nullable=False),
            pa.field("created_at", pa.int64(), nullable=False),
            pa.field("updated_at", pa.int64(), nullable=False),
            pa.field("config_json", pa.utf8(), nullable=True),
        ]
    )


def create_embeddings_schema(dim: int) -> pa.Schema:
    """Create the PyArrow schema for an embeddings table.

    Args:
        dim: Vector dimension for this embedding space.
    """
    return pa.schema(
        [
            pa.field("id", pa.utf8(), nullable=False),
            pa.field("vector", pa.list_(pa.float32(), dim), nullable=False),
        ]
    )


def create_layouts_schema() -> pa.Schema:
    """Create the PyArrow schema for a layouts table.

    Layouts store 2D coordinates for visualization.
    """
    return pa.schema(
        [
            pa.field("id", pa.utf8(), nullable=False),
            pa.field("x", pa.float32(), nullable=False),
            pa.field("y", pa.float32(), nullable=False),
        ]
    )


@dataclass
class SpaceInfo:
    """Metadata for an embedding space."""

    space_key: str
    model_id: str
    dim: int
    count: int
    created_at: int
    updated_at: int
    config: dict[str, Any] | None = None

    @property
    def provider(self) -> str:
        return (self.config or {}).get("provider", "unknown")

    @property
    def geometry(self) -> str:
        return (self.config or {}).get("geometry", "euclidean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "space_key": self.space_key,
            "model_id": self.model_id,
            "dim": self.dim,
            "count": self.count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "config_json": json.dumps(self.config) if self.config else None,
        }

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "space_key": self.space_key,
            "model_id": self.model_id,
            "dim": self.dim,
            "count": self.count,
            "provider": self.provider,
            "geometry": self.geometry,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "SpaceInfo":
        config_json = row.get("config_json")
        config = json.loads(config_json) if config_json else None
        return cls(
            space_key=row["space_key"],
            model_id=row["model_id"],
            dim=row["dim"],
            count=row["count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            config=config,
        )


def create_layouts_registry_schema() -> pa.Schema:
    """Create the PyArrow schema for the layouts registry.

    Each row represents a layout (2D projection of an embedding space).
    """
    return pa.schema(
        [
            pa.field("layout_key", pa.utf8(), nullable=False),
            pa.field("space_key", pa.utf8(), nullable=False),
            pa.field("method", pa.utf8(), nullable=False),
            pa.field("geometry", pa.utf8(), nullable=False),
            pa.field("count", pa.int64(), nullable=False),
            pa.field("created_at", pa.int64(), nullable=False),
            pa.field("params_json", pa.utf8(), nullable=True),
        ]
    )


@dataclass
class LayoutInfo:
    """Metadata for a layout (2D projection)."""

    layout_key: str
    space_key: str
    method: str
    geometry: str
    count: int
    created_at: int
    params: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layout_key": self.layout_key,
            "space_key": self.space_key,
            "method": self.method,
            "geometry": self.geometry,
            "count": self.count,
            "created_at": self.created_at,
            "params_json": json.dumps(self.params) if self.params else None,
        }

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "layout_key": self.layout_key,
            "space_key": self.space_key,
            "method": self.method,
            "geometry": self.geometry,
            "count": self.count,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "LayoutInfo":
        params_json = row.get("params_json")
        params = json.loads(params_json) if params_json else None
        return cls(
            layout_key=row["layout_key"],
            space_key=row["space_key"],
            method=row["method"],
            geometry=row["geometry"],
            count=row["count"],
            created_at=row["created_at"],
            params=params,
        )


def slugify_model_id(model_id: str) -> str:
    """Convert a model ID to a safe table name component.

    Examples:
        "openai/clip-vit-base-patch32" -> "openai_clip-vit-base-patch32"
        "sentence-transformers/all-MiniLM-L6-v2" -> "sentence-transformers_all-MiniLM-L6-v2"
    """
    # Replace / with _
    slug = model_id.replace("/", "_")
    # Replace any other unsafe characters with _
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", slug)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    return slug.strip("_")


def make_space_key(model_id: str) -> str:
    """Generate a space_key from a model_id.

    For simplicity, this is just the slugified model_id.
    """
    return slugify_model_id(model_id)


def make_layout_key(
    space_key: str,
    method: str = "umap",
    geometry: str = "euclidean",
    params: dict | None = None,
) -> str:
    """Generate a layout_key from space, method, geometry, and params.

    The params are hashed to ensure different parameter sets get different keys.
    """
    base = f"{space_key}__{geometry}_{method}"
    if params:
        # Create a stable hash of params
        import hashlib
        params_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"{base}_{params_hash}"
    return base


def sample_to_dict(sample: Sample) -> dict[str, Any]:
    """Convert a Sample to a dictionary for LanceDB insertion."""
    return {
        "id": sample.id,
        "filepath": sample.filepath,
        "label": sample.label,
        "metadata_json": json.dumps(sample.metadata) if sample.metadata else None,
        "thumbnail_base64": sample.thumbnail_base64,
    }


def dict_to_sample(row: dict[str, Any]) -> Sample:
    """Convert a LanceDB row to a Sample object."""
    metadata_json = row.get("metadata_json")
    metadata = json.loads(metadata_json) if metadata_json else {}

    return Sample(
        id=row["id"],
        filepath=row["filepath"],
        label=row.get("label"),
        metadata=metadata,
        thumbnail_base64=row.get("thumbnail_base64"),
    )

