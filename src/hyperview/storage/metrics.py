"""Distance metrics for embedding spaces."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

from hyperview.storage.geometry import (
    explicit_geometry_params,
    infer_hyperboloid_curvature,
    resolve_geometry,
)

EmbeddingDistanceMetric = Literal["cosine", "hyperboloid"]

__all__ = [
    "EmbeddingDistanceMetric",
    "configured_curvature_for_space",
    "curvature_for_space",
    "distance_metric_for_space",
    "hyperboloid_dot_query",
    "infer_hyperboloid_curvature",
    "pairwise_embedding_distances",
    "resolve_hyperboloid_curvature",
]

_EPS = 1e-12
_DEFAULT_CURVATURE = 1.0


def distance_metric_for_space(space: Any) -> EmbeddingDistanceMetric:
    """Return the distance metric that matches an embedding space geometry."""

    geometry = str(getattr(space, "geometry", "euclidean")).lower()
    if geometry == "hyperboloid":
        return "hyperboloid"
    return "cosine"


def curvature_for_space(space: Any) -> float:
    """Return the positive curvature parameter c for sectional curvature -c."""

    configured = configured_curvature_for_space(space)
    return _DEFAULT_CURVATURE if configured is None else configured


def configured_curvature_for_space(space: Any) -> float | None:
    """Return an explicitly configured curvature, if the space declares one."""

    params, _sources = explicit_geometry_params(space)
    if "curvature" not in params:
        return None

    raw_curvature = params["curvature"]
    try:
        curvature = float(raw_curvature)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"curvature must be a finite number, got {raw_curvature!r}") from exc
    if not np.isfinite(curvature) or curvature <= 0:
        raise ValueError(f"curvature must be > 0, got {curvature}")
    return curvature


def resolve_hyperboloid_curvature(
    space: Any,
    vectors: list[float] | np.ndarray,
) -> float:
    """Use configured curvature when present, otherwise infer it from vectors."""

    return resolve_geometry(space, vectors).require_float("curvature")


def pairwise_embedding_distances(
    query: list[float] | np.ndarray,
    vectors: np.ndarray,
    *,
    metric: EmbeddingDistanceMetric,
    curvature: float = 1.0,
) -> np.ndarray:
    """Compute exact distances from one query vector to many embedding vectors."""

    query_array = np.asarray(query, dtype=np.float64)
    vector_array = np.asarray(vectors, dtype=np.float64)
    if vector_array.ndim != 2:
        raise ValueError(f"vectors must be 2-D, got shape {vector_array.shape}")
    if query_array.ndim != 1:
        raise ValueError(f"query must be 1-D, got shape {query_array.shape}")
    if vector_array.shape[1] != query_array.shape[0]:
        raise ValueError(
            "query and vectors must have the same dimension, "
            f"got {query_array.shape[0]} and {vector_array.shape[1]}"
        )

    if metric == "cosine":
        return _cosine_distances(query_array, vector_array)
    if metric == "hyperboloid":
        return _hyperboloid_distances(query_array, vector_array, curvature)
    raise ValueError(f"Unsupported embedding distance metric: {metric}")


def hyperboloid_dot_query(query: list[float] | np.ndarray) -> np.ndarray:
    """Transform a hyperboloid query for exact native LanceDB dot-product ranking."""

    query_array = np.asarray(query, dtype=np.float32).copy()
    if query_array.ndim != 1:
        raise ValueError(f"query must be 1-D, got shape {query_array.shape}")
    if query_array.shape[0] < 2:
        raise ValueError("hyperboloid vectors must include time and spatial coordinates")
    query_array[0] *= -1.0
    return query_array


def _cosine_distances(query: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    query_norm = np.linalg.norm(query)
    vector_norms = np.linalg.norm(vectors, axis=1)
    denom = query_norm * vector_norms
    distances = np.ones(vectors.shape[0], dtype=np.float64)
    valid = denom > _EPS
    if np.any(valid):
        distances[valid] = 1.0 - (vectors[valid] @ query) / denom[valid]
    return distances


def _hyperboloid_distances(
    query: np.ndarray,
    vectors: np.ndarray,
    curvature: float,
) -> np.ndarray:
    if query.shape[0] < 2:
        raise ValueError("hyperboloid vectors must include time and spatial coordinates")

    sqrt_c = np.sqrt(curvature)
    lorentz_product = vectors[:, 0] * query[0] - vectors[:, 1:] @ query[1:]
    arg = np.maximum(curvature * lorentz_product, 1.0)
    return np.arccosh(arg) / sqrt_c
