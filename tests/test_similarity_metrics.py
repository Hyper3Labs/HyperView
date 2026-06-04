from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from hyperview.core.sample import Sample
from hyperview.storage.config import StorageConfig
from hyperview.storage.lancedb_backend import LanceDBBackend
from hyperview.storage.metrics import (
    curvature_for_space,
    hyperboloid_dot_query,
    infer_hyperboloid_curvature,
    pairwise_embedding_distances,
)
from hyperview.storage.schema import SpaceInfo


def _hyperboloid_from_tangent(tangent: np.ndarray, curvature: float) -> np.ndarray:
    sqrt_c = np.sqrt(curvature)
    norm = np.linalg.norm(tangent, axis=1)
    scaled = sqrt_c * norm
    time = np.cosh(scaled) / sqrt_c
    safe_scaled = np.where(scaled > 1e-12, scaled, 1.0)
    coeff = np.where(scaled > 1e-12, np.sinh(scaled) / safe_scaled, 1.0)
    spatial = tangent * coeff[:, np.newaxis]
    return np.column_stack([time, spatial]).astype(np.float32)


def test_hyperboloid_dot_query_matches_geodesic_ranking() -> None:
    rng = np.random.default_rng(19)
    curvature = 1.7
    vectors = _hyperboloid_from_tangent(rng.normal(size=(80, 5)) * 0.6, curvature)
    query = vectors[7]

    geodesic_order = np.argsort(
        pairwise_embedding_distances(
            query,
            vectors,
            metric="hyperboloid",
            curvature=curvature,
        )
    )
    dot_order = np.argsort(1.0 - vectors @ hyperboloid_dot_query(query))

    assert dot_order[:20].tolist() == geodesic_order[:20].tolist()


def test_lancedb_backend_uses_exact_hyperboloid_distance(tmp_path: Path) -> None:
    backend = LanceDBBackend(
        "hyperboloid_similarity",
        StorageConfig(datasets_dir=tmp_path / "datasets", media_dir=tmp_path / "media"),
    )
    ids = ["q", "near", "far"]
    for sample_id in ids:
        backend.add_sample(Sample(id=sample_id, filepath=f"/missing/{sample_id}.png"))

    near_distance = 0.25
    far_distance = 0.75
    vectors = np.array(
        [
            [1.0, 0.0, 0.0],
            [np.cosh(near_distance), np.sinh(near_distance), 0.0],
            [np.cosh(far_distance), 0.0, np.sinh(far_distance)],
        ],
        dtype=np.float32,
    )
    space_key = "hyperboloid_space"
    backend.ensure_space(
        model_id="hyper-model",
        dim=3,
        config={"provider": "test", "geometry": "hyperboloid", "curvature": 1.0},
        space_key=space_key,
    )
    backend.add_embeddings(space_key, ids, vectors)

    results = backend.find_similar("q", k=2, space_key=space_key)

    assert [sample.id for sample, _ in results] == ["near", "far"]
    assert results[0][1] == pytest.approx(near_distance, abs=1e-6)
    assert results[1][1] == pytest.approx(far_distance, abs=1e-6)


def test_lancedb_backend_infers_missing_hyperboloid_curvature(tmp_path: Path) -> None:
    backend = LanceDBBackend(
        "hyperboloid_inferred_curvature",
        StorageConfig(datasets_dir=tmp_path / "datasets", media_dir=tmp_path / "media"),
    )
    ids = ["q", "near", "far"]
    for sample_id in ids:
        backend.add_sample(Sample(id=sample_id, filepath=f"/missing/{sample_id}.png"))

    curvature = 0.1
    near_distance = 0.25
    far_distance = 0.75
    vectors = _hyperboloid_from_tangent(
        np.array(
            [
                [0.0, 0.0],
                [near_distance, 0.0],
                [0.0, far_distance],
            ],
            dtype=np.float32,
        ),
        curvature,
    )
    space_key = "hyperboloid_space"
    backend.ensure_space(
        model_id="hyper-model",
        dim=3,
        config={"provider": "test", "geometry": "hyperboloid"},
        space_key=space_key,
    )
    backend.add_embeddings(space_key, ids, vectors)

    results = backend.find_similar("q", k=2, space_key=space_key)

    assert infer_hyperboloid_curvature(vectors) == pytest.approx(curvature)
    assert [sample.id for sample, _ in results] == ["near", "far"]
    assert results[0][1] == pytest.approx(near_distance, abs=1e-6)
    assert results[1][1] == pytest.approx(far_distance, abs=1e-6)


def test_curvature_for_space_reads_geometry_params() -> None:
    space = SpaceInfo(
        space_key="nested",
        model_id="test",
        dim=3,
        count=0,
        created_at=0,
        updated_at=0,
        config={
            "geometry": "hyperboloid",
            "params": {"curvature": 0.1},
            "params_source": {"curvature": "provider"},
        },
    )

    assert curvature_for_space(space) == pytest.approx(0.1)


@pytest.mark.parametrize("curvature", [0.0, -1.0, float("nan"), float("inf"), None])
def test_curvature_for_space_rejects_invalid_values(curvature: object) -> None:
    space = SpaceInfo(
        space_key="bad",
        model_id="model",
        dim=3,
        count=0,
        created_at=0,
        updated_at=0,
        config={"geometry": "hyperboloid", "curvature": curvature},
    )

    with pytest.raises(ValueError, match="curvature"):
        curvature_for_space(space)
