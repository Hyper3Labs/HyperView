from __future__ import annotations

import numpy as np
import pytest

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.embeddings.projection import ProjectionEngine


def _random_euclidean(n: int = 50, d: int = 64, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, d)).astype(np.float32)


def _random_hyperboloid(n: int = 50, d: int = 64, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    spatial = rng.standard_normal((n, d)).astype(np.float64) * 0.5
    time = np.sqrt(1.0 + np.sum(spatial**2, axis=1, keepdims=True))
    return np.hstack([time, spatial]).astype(np.float32)


def _make_dataset_with_embeddings(
    name: str,
    vectors: np.ndarray,
    *,
    geometry: str = "euclidean",
    curvature: float | None = None,
) -> tuple[Dataset, str]:
    dataset = Dataset(name, persist=False)
    ids = [f"s{i}" for i in range(len(vectors))]

    for index, sample_id in enumerate(ids):
        dataset.add_sample(
            Sample(
                id=sample_id,
                filepath=f"/fake/{index}.png",
                label=f"c{index % 3}",
            )
        )

    config: dict[str, object] = {
        "provider": "test",
        "geometry": geometry,
    }
    if curvature is not None:
        config["curvature"] = curvature

    space_key = f"{name}_space"
    dataset._storage.ensure_space(
        model_id="test-model",
        dim=vectors.shape[1],
        config=config,
        space_key=space_key,
    )
    dataset._storage.add_embeddings(space_key, ids, vectors)

    return dataset, space_key


def test_pca_projects_euclidean_embeddings_to_bounded_2d_coords() -> None:
    engine = ProjectionEngine()

    coords = engine.project(
        _random_euclidean(30, 32),
        method="pca",
        input_geometry="euclidean",
        output_geometry="euclidean",
    )

    assert coords.shape == (30, 2)
    assert coords.dtype == np.float32
    assert np.all(coords >= -1.0)
    assert np.all(coords <= 1.0)


def test_pca_projects_to_poincare_inside_unit_disk() -> None:
    engine = ProjectionEngine()

    coords = engine.project(
        _random_euclidean(40, 64),
        method="pca",
        input_geometry="euclidean",
        output_geometry="poincare",
    )

    assert coords.shape == (40, 2)
    assert np.all(np.linalg.norm(coords, axis=1) < 1.0)


def test_pca_projects_hyperboloid_embeddings_to_poincare_inside_unit_disk() -> None:
    engine = ProjectionEngine()

    coords = engine.project(
        _random_hyperboloid(40, 32),
        method="pca",
        input_geometry="hyperboloid",
        output_geometry="poincare",
    )

    assert coords.shape == (40, 2)
    assert np.all(np.linalg.norm(coords, axis=1) < 1.0)


def test_pca_supports_spherical_3d_layouts() -> None:
    engine = ProjectionEngine()

    coords = engine.project(
        _random_euclidean(25, 48),
        method="pca",
        input_geometry="euclidean",
        output_geometry="spherical",
        n_components=3,
        normalize_input=True,
    )

    assert coords.shape == (25, 3)
    norms = np.linalg.norm(coords, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_pca_is_deterministic() -> None:
    engine = ProjectionEngine()
    data = _random_euclidean(40, 32)

    first = engine.project(
        data,
        method="pca",
        input_geometry="euclidean",
        output_geometry="euclidean",
    )
    second = engine.project(
        data,
        method="pca",
        input_geometry="euclidean",
        output_geometry="euclidean",
    )

    np.testing.assert_array_equal(first, second)


def test_logmap_and_expmap_round_trip_for_non_unit_curvature() -> None:
    engine = ProjectionEngine()
    rng = np.random.default_rng(456)
    tangent_vectors = rng.standard_normal((15, 5)).astype(np.float32) * 0.3

    hyperboloid_points = engine.expmap_0_hyperboloid(tangent_vectors, curvature=2.0)
    recovered = engine.logmap_0_hyperboloid(hyperboloid_points, curvature=2.0)

    np.testing.assert_allclose(recovered, tangent_vectors, atol=1e-4)


def test_pca_rejects_non_finite_inputs() -> None:
    engine = ProjectionEngine()
    data = _random_euclidean(10, 16)
    data[0, 0] = np.nan

    with pytest.raises(ValueError, match="NaN or Inf"):
        engine.project(
            data,
            method="pca",
            input_geometry="euclidean",
            output_geometry="euclidean",
        )


def test_pca_requires_at_least_two_samples() -> None:
    engine = ProjectionEngine()

    with pytest.raises(ValueError, match="at least 2 samples"):
        engine.project(
            _random_euclidean(1, 16),
            method="pca",
            input_geometry="euclidean",
            output_geometry="euclidean",
        )


def test_dataset_compute_visualization_supports_pca_2d_and_3d_layouts() -> None:
    dataset, space_key = _make_dataset_with_embeddings(
        "test_pca_layouts",
        _random_euclidean(20, 32, seed=99),
    )

    euclidean_layout = dataset.compute_visualization(
        space_key=space_key,
        method="pca",
        layout="euclidean",
    )
    spherical_layout = dataset.compute_visualization(
        space_key=space_key,
        method="pca",
        layout="spherical",
    )

    euclidean_ids, _, euclidean_coords = dataset.get_visualization_data(euclidean_layout)
    spherical_ids, _, spherical_coords = dataset.get_visualization_data(spherical_layout)

    assert len(euclidean_ids) == 20
    assert euclidean_coords.shape == (20, 2)
    assert len(spherical_ids) == 20
    assert spherical_coords.shape == (20, 3)
    assert np.allclose(np.linalg.norm(spherical_coords, axis=1), 1.0, atol=1e-5)


def test_dataset_compute_visualization_supports_pca_poincare_layouts() -> None:
    dataset, space_key = _make_dataset_with_embeddings(
        "test_pca_poincare",
        _random_hyperboloid(20, 32, seed=77),
        geometry="hyperboloid",
        curvature=1.0,
    )

    layout_key = dataset.compute_visualization(
        space_key=space_key,
        method="pca",
        layout="poincare",
    )

    ids, _, coords = dataset.get_visualization_data(layout_key)

    assert len(ids) == 20
    assert coords.shape == (20, 2)
    assert np.all(np.linalg.norm(coords, axis=1) < 1.0)


def test_dataset_pipeline_allows_two_sample_pca_layout() -> None:
    dataset, space_key = _make_dataset_with_embeddings(
        "test_pca_two_samples",
        _random_euclidean(2, 16, seed=7),
    )

    layout_key = dataset.compute_visualization(
        space_key=space_key,
        method="pca",
        layout="euclidean:3d",
    )

    ids, _, coords = dataset.get_visualization_data(layout_key)

    assert len(ids) == 2
    assert coords.shape == (2, 3)
    assert np.all(np.isfinite(coords))