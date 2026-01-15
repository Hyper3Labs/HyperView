"""LanceDB schema definitions for HyperView samples."""

import json
from typing import Any

import pyarrow as pa

from hyperview.core.sample import Sample


def create_sample_schema(embedding_dim: int = 512) -> pa.Schema:
    """Create the PyArrow schema for samples.

    Using PyArrow schema instead of LanceModel allows dynamic embedding dimensions.

    Args:
        embedding_dim: Dimension of the high-dimensional embedding vector.

    Returns:
        PyArrow schema for the samples table.
    """
    # Use fixed-size lists for ANN index support in LanceDB
    return pa.schema(
        [
            pa.field("id", pa.utf8(), nullable=False),
            pa.field("filepath", pa.utf8(), nullable=False),
            pa.field("label", pa.utf8(), nullable=True),
            pa.field("metadata_json", pa.utf8(), nullable=True),
            pa.field("embedding", pa.list_(pa.float32(), embedding_dim), nullable=True),
            pa.field("embedding_2d_euclidean", pa.list_(pa.float32(), 2), nullable=True),
            pa.field("embedding_2d_hyperbolic", pa.list_(pa.float32(), 2), nullable=True),
            pa.field("thumbnail_base64", pa.utf8(), nullable=True),
        ]
    )


def create_metadata_schema() -> pa.Schema:
    """Create the PyArrow schema for dataset metadata."""
    return pa.schema(
        [
            pa.field("key", pa.utf8(), nullable=False),
            pa.field("value", pa.utf8(), nullable=True),
        ]
    )


def sample_to_dict(sample: Sample, embedding_dim: int = 512) -> dict[str, Any]:
    """Convert a Sample to a dictionary for LanceDB insertion.

    Args:
        sample: The Sample object to convert.
        embedding_dim: Expected embedding dimension for padding/validation.

    Returns:
        Dictionary suitable for LanceDB insertion.
    """
    # Handle embedding - ensure correct dimension or None
    embedding = None
    if sample.embedding is not None:
        embedding = list(sample.embedding)
        # Pad or truncate to expected dimension
        if len(embedding) < embedding_dim:
            embedding.extend([0.0] * (embedding_dim - len(embedding)))
        elif len(embedding) > embedding_dim:
            embedding = embedding[:embedding_dim]

    return {
        "id": sample.id,
        "filepath": sample.filepath,
        "label": sample.label,
        "metadata_json": json.dumps(sample.metadata) if sample.metadata else None,
        "embedding": embedding,
        "embedding_2d_euclidean": list(sample.embedding_2d) if sample.embedding_2d else None,
        "embedding_2d_hyperbolic": (
            list(sample.embedding_2d_hyperbolic) if sample.embedding_2d_hyperbolic else None
        ),
        "thumbnail_base64": sample.thumbnail_base64,
    }


def dict_to_sample(row: dict[str, Any]) -> Sample:
    """Convert a LanceDB row to a Sample object.

    Args:
        row: Dictionary from LanceDB query result.

    Returns:
        Sample object.
    """
    metadata = {}
    if row.get("metadata_json"):
        try:
            metadata = json.loads(row["metadata_json"])
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    # Convert numpy arrays to lists if needed
    embedding = row.get("embedding")
    if embedding is not None and hasattr(embedding, "tolist"):
        embedding = embedding.tolist()

    embedding_2d = row.get("embedding_2d_euclidean")
    if embedding_2d is not None and hasattr(embedding_2d, "tolist"):
        embedding_2d = embedding_2d.tolist()

    embedding_2d_hyperbolic = row.get("embedding_2d_hyperbolic")
    if embedding_2d_hyperbolic is not None and hasattr(embedding_2d_hyperbolic, "tolist"):
        embedding_2d_hyperbolic = embedding_2d_hyperbolic.tolist()

    return Sample(
        id=row["id"],
        filepath=row["filepath"],
        label=row.get("label"),
        metadata=metadata,
        embedding=embedding,
        embedding_2d=embedding_2d,
        embedding_2d_hyperbolic=embedding_2d_hyperbolic,
        thumbnail_base64=row.get("thumbnail_base64"),
    )
