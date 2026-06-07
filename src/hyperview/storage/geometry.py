"""Geometry parameter resolution for embedding spaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

_EPS = 1e-12
_DEFAULT_CURVATURE = 1.0


@dataclass(frozen=True)
class ResolvedGeometry:
    """Embedding geometry plus concrete parameters used by downstream code."""

    geometry: str
    params: dict[str, Any]
    params_source: dict[str, str]

    def require_float(self, name: str) -> float:
        if name not in self.params:
            raise ValueError(f"Missing required geometry parameter: {name}")
        return validate_positive_float(name, self.params[name])


def validate_positive_float(name: str, value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number, got {value!r}") from exc
    if not np.isfinite(out) or out <= 0:
        raise ValueError(f"{name} must be > 0, got {out}")
    return out


def explicit_geometry_params(space: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """Return provider/user-declared geometry params."""

    config = getattr(space, "config", None) or {}
    params = dict(config.get("params") or {})
    sources = dict(config.get("params_source") or {})
    return params, sources


def infer_hyperboloid_curvature(vectors: list[float] | np.ndarray) -> float:
    """Infer positive curvature from hyperboloid vectors.

    Hyperboloid points satisfy ``t^2 - ||x||^2 = 1 / c`` for curvature ``-c``.
    Some providers do not publish ``c`` in metadata, so persisted vectors are
    the source of truth.
    """

    vector_array = np.asarray(vectors, dtype=np.float64)
    if vector_array.ndim == 1:
        vector_array = vector_array[np.newaxis, :]
    if vector_array.ndim != 2 or vector_array.shape[1] < 2:
        raise ValueError(
            f"hyperboloid vectors must have shape (N, D+1) with D >= 1, got {vector_array.shape}"
        )

    minkowski_norms = vector_array[:, 0] ** 2 - np.sum(vector_array[:, 1:] ** 2, axis=1)
    valid = minkowski_norms[np.isfinite(minkowski_norms) & (minkowski_norms > _EPS)]
    if valid.size == 0:
        return _DEFAULT_CURVATURE
    return float(1.0 / np.median(valid))


def resolve_geometry(
    space: Any, vectors: list[float] | np.ndarray | None = None
) -> ResolvedGeometry:
    """Resolve all known geometry parameters for a space.

    Provider/user metadata is authoritative. Inference is geometry-specific and
    only fills missing parameters that are mathematically recoverable from the
    vectors.
    """

    geometry = str(getattr(space, "geometry", "euclidean")).lower()
    params, sources = explicit_geometry_params(space)

    if geometry == "hyperboloid":
        if "curvature" in params:
            params["curvature"] = validate_positive_float("curvature", params["curvature"])
        elif vectors is not None:
            params["curvature"] = infer_hyperboloid_curvature(vectors)
            sources["curvature"] = "inferred"
        else:
            params["curvature"] = _DEFAULT_CURVATURE
            sources["curvature"] = "default"

    return ResolvedGeometry(geometry=geometry, params=params, params_source=sources)


def apply_inferred_geometry_params(config: dict[str, Any], vectors: np.ndarray) -> dict[str, Any]:
    """Return a config copy with inferable missing geometry params filled in."""

    out = dict(config)
    geometry = str(out.get("geometry", "euclidean")).lower()
    params = dict(out.get("params") or {})
    sources = dict(out.get("params_source") or {})

    if geometry == "hyperboloid" and "curvature" not in params:
        params["curvature"] = infer_hyperboloid_curvature(vectors)
        sources["curvature"] = "inferred"

    if params:
        out["params"] = params
    if sources:
        out["params_source"] = sources
    return out
