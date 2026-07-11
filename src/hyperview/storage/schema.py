"""LanceDB schema definitions for HyperView.

Storage architecture:
- samples: Core sample metadata (no embeddings)
- spaces: Registry of embedding spaces
- embeddings__<space_key>: One table per embedding space (id + vector)
- layouts__<layout_key>: One table per layout (id + x + y [+ z])
"""

import json
import re
from dataclasses import dataclass
from typing import Any

import pyarrow as pa

from hyperview.core.sample import Sample


def normalize_layout_dimension(layout_dimension: int) -> int:
    """Validate and normalize a visualization layout dimension."""
    if layout_dimension not in (2, 3):
        raise ValueError(f"layout_dimension must be one of (2, 3), got {layout_dimension}")
    return int(layout_dimension)


def parse_layout_dimension(layout_key: str) -> int:
    """Extract the visualization dimension from a layout key.

    Layout keys must end with ``__2d`` / ``__3d`` optionally followed by a
    params hash.
    """
    suffix = layout_key.rsplit("__", 1)[-1]
    dimension_token = suffix.split("_", 1)[0]
    if dimension_token not in ("2d", "3d"):
        raise ValueError(
            "layout_key must end with '__2d' or '__3d'"
            f" (optionally followed by a params hash), got '{layout_key}'"
        )
    return int(dimension_token[0])


def create_sample_schema() -> pa.Schema:
    """Create the PyArrow schema for samples.

    Samples are pure metadata - embeddings and layouts are stored separately.
    """
    return pa.schema(
        [
            pa.field("id", pa.utf8(), nullable=False),
            pa.field("filepath", pa.utf8(), nullable=False),
            pa.field("label", pa.utf8(), nullable=True),
            pa.field("text", pa.utf8(), nullable=True),
            pa.field("modality", pa.utf8(), nullable=False),
            pa.field("metadata_json", pa.utf8(), nullable=True),
            pa.field("thumbnail_base64", pa.utf8(), nullable=True),
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


def create_layouts_schema(layout_dimension: int = 2) -> pa.Schema:
    """Create the PyArrow schema for a layouts table.

    Layouts store dimension-specific scalar coordinate columns for visualization.

    Args:
        layout_dimension: Number of layout dimensions.
    """
    layout_dimension = normalize_layout_dimension(layout_dimension)

    fields: list[pa.Field] = [
        pa.field("id", pa.utf8(), nullable=False),
        pa.field("x", pa.float32(), nullable=False),
        pa.field("y", pa.float32(), nullable=False),
    ]

    if layout_dimension == 3:
        fields.append(pa.field("z", pa.float32(), nullable=False))

    return pa.schema(fields)


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

    @property
    def modality(self) -> str:
        return (self.config or {}).get("modality", "image")

    @property
    def index_id(self) -> str:
        return index_id_for_space_key(self.space_key)

    def to_representation_dict(self) -> dict[str, Any]:
        """Representation view of this space (architecture.md vocabulary).

        The representation is the derived vector field itself, independent of
        how it is searched; `space_key` doubles as the representation id until
        storage keys the two separately.
        """
        return {
            "id": self.space_key,
            "entity_set_id": "samples",
            "field_path": f"embeddings.{self.space_key}",
            "kind": "vector",
            "shape": [self.dim],
            "model_id": self.model_id,
            "provider": self.provider,
            "modality": self.modality,
            "geometry": self.geometry,
            "count": self.count,
        }

    def to_index_dict(self) -> dict[str, Any]:
        """Index view of this space: the searchable access path over the
        representation, addressable as `space:<space_key>` in retrieval
        queries and collection payloads."""
        from hyperview.storage.metrics import distance_metric_for_space

        query_modes = ["nearest"]
        if self.modality in ("text", "multimodal"):
            query_modes.append("text")
        return {
            "id": self.index_id,
            "representation_id": self.space_key,
            "query_modes": query_modes,
            "scorer": distance_metric_for_space(self),
        }

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

    Each row represents a layout projection of an embedding space.
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
    """Metadata for a layout projection."""

    layout_key: str
    space_key: str
    method: str
    geometry: str
    count: int
    created_at: int
    params: dict[str, Any] | None = None

    @property
    def layout_dimension(self) -> int:
        return parse_layout_dimension(self.layout_key)

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


INDEX_ID_PREFIX = "space:"


def index_id_for_space_key(space_key: str) -> str:
    return f"{INDEX_ID_PREFIX}{space_key}"


def space_key_from_index_ref(value: Any) -> str | None:
    """Resolve an index reference to a space_key.

    Accepts the canonical `space:<space_key>` index id as well as a bare
    space_key, so retrieval can be addressed by index id while storage still
    keys spaces by space_key.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    ref = value.strip()
    if ref.startswith(INDEX_ID_PREFIX):
        ref = ref[len(INDEX_ID_PREFIX) :]
    return ref or None


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
    layout_dimension: int = 2,
    params: dict | None = None,
) -> str:
    """Generate a layout_key from space, method, geometry, and params.

    The params are hashed to ensure different parameter sets get different keys.
    """
    layout_dimension = normalize_layout_dimension(layout_dimension)
    base = f"{space_key}__{geometry}_{method}__{layout_dimension}d"
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
        "text": sample.text,
        "modality": sample.modality,
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
        text=row.get("text"),
        modality=str(row.get("modality") or "image"),
        metadata=metadata,
        thumbnail_base64=row.get("thumbnail_base64"),
    )
