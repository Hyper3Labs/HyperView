import numpy as np
import pytest

from hyperview.embeddings.projection import ProjectionEngine


def _random_euclidean(n: int = 50, d: int = 64, seed: int = 42) -> np.ndarray:
    """Generate random Euclidean embeddings (N, D)."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, d)).astype(np.float32)


def _random_hyperboloid(n: int = 50, d: int = 64, seed: int = 42) -> np.ndarray:
    """Generate random points on the hyperboloid H^d (Lorentz model).

    Points satisfy t^2 - ||x||^2 = 1 (curvature c=1).
    We sample spatial components from a normal distribution scaled down,
    then compute t = sqrt(1 + ||x||^2).
    """
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((n, d)).astype(np.float64) * 0.5
    t = np.sqrt(1.0 + np.sum(x**2, axis=1, keepdims=True))
    return np.hstack([t, x]).astype(np.float32)


class TestPcaEuclideanToEuclidean:
    """Euclidean input -> Euclidean output (standard PCA)."""

    def test_output_shape(self):
        engine = ProjectionEngine()
        data = _random_euclidean(30, 32)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        assert coords.shape == (30, 2)

    def test_normalized_range(self):
        engine = ProjectionEngine()
        data = _random_euclidean(50, 64)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        assert np.all(coords >= -1.0)
        assert np.all(coords <= 1.0)

    def test_dtype_float32(self):
        engine = ProjectionEngine()
        data = _random_euclidean(20, 16)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        assert coords.dtype == np.float32


class TestPcaEuclideanToPoincare:
    """Euclidean input -> Poincare disk output."""

    def test_output_shape(self):
        engine = ProjectionEngine()
        data = _random_euclidean(30, 32)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="poincare")
        assert coords.shape == (30, 2)

    def test_inside_unit_disk(self):
        engine = ProjectionEngine()
        data = _random_euclidean(50, 64)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="poincare")
        radii = np.linalg.norm(coords, axis=1)
        assert np.all(radii < 1.0), f"Max radius: {radii.max()}"


class TestPcaHyperboloidToEuclidean:
    """Hyperboloid input -> Euclidean output (tangent PCA)."""

    def test_output_shape(self):
        engine = ProjectionEngine()
        data = _random_hyperboloid(30, 32)
        coords = engine.project(data, method="pca", input_geometry="hyperboloid", output_geometry="euclidean")
        assert coords.shape == (30, 2)

    def test_normalized_range(self):
        engine = ProjectionEngine()
        data = _random_hyperboloid(50, 64)
        coords = engine.project(data, method="pca", input_geometry="hyperboloid", output_geometry="euclidean")
        assert np.all(coords >= -1.0)
        assert np.all(coords <= 1.0)


class TestPcaHyperboloidToPoincare:
    """Hyperboloid input -> Poincare disk output (tangent PCA + expmap)."""

    def test_output_shape(self):
        engine = ProjectionEngine()
        data = _random_hyperboloid(30, 32)
        coords = engine.project(data, method="pca", input_geometry="hyperboloid", output_geometry="poincare")
        assert coords.shape == (30, 2)

    def test_inside_unit_disk(self):
        engine = ProjectionEngine()
        data = _random_hyperboloid(50, 64)
        coords = engine.project(data, method="pca", input_geometry="hyperboloid", output_geometry="poincare")
        radii = np.linalg.norm(coords, axis=1)
        assert np.all(radii < 1.0), f"Max radius: {radii.max()}"


class TestPcaDeterminism:
    """PCA should produce identical results on identical input."""

    def test_euclidean_deterministic(self):
        engine = ProjectionEngine()
        data = _random_euclidean(40, 32)
        c1 = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        c2 = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        np.testing.assert_array_equal(c1, c2)

    def test_hyperboloid_deterministic(self):
        engine = ProjectionEngine()
        data = _random_hyperboloid(40, 32)
        c1 = engine.project(data, method="pca", input_geometry="hyperboloid", output_geometry="poincare")
        c2 = engine.project(data, method="pca", input_geometry="hyperboloid", output_geometry="poincare")
        np.testing.assert_array_equal(c1, c2)


class TestLogmapExpmapRoundtrip:
    """logmap_0(expmap_0(v)) should approximately recover v."""

    def test_roundtrip(self):
        engine = ProjectionEngine()
        rng = np.random.default_rng(123)
        # Tangent vectors with moderate norms
        v = rng.standard_normal((20, 8)).astype(np.float32) * 0.5
        hyp = engine.expmap_0_hyperboloid(v, curvature=1.0)
        recovered = engine.logmap_0_hyperboloid(hyp, curvature=1.0)
        np.testing.assert_allclose(recovered, v, atol=1e-4)

    def test_roundtrip_nonunit_curvature(self):
        engine = ProjectionEngine()
        rng = np.random.default_rng(456)
        v = rng.standard_normal((15, 5)).astype(np.float32) * 0.3
        c = 2.0
        hyp = engine.expmap_0_hyperboloid(v, curvature=c)
        recovered = engine.logmap_0_hyperboloid(hyp, curvature=c)
        np.testing.assert_allclose(recovered, v, atol=1e-4)


class TestEdgeCases:

    def test_insufficient_samples(self):
        engine = ProjectionEngine()
        data = _random_euclidean(1, 16)
        with pytest.raises(ValueError, match="at least"):
            engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")

    def test_nan_input_raises(self):
        engine = ProjectionEngine()
        data = _random_euclidean(10, 16)
        data[3, 5] = np.nan
        with pytest.raises(ValueError, match="NaN or Inf"):
            engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")

    def test_inf_input_raises(self):
        engine = ProjectionEngine()
        data = _random_euclidean(10, 16)
        data[0, 0] = np.inf
        with pytest.raises(ValueError, match="NaN or Inf"):
            engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")

    def test_identical_embeddings(self):
        """All-same embeddings -> zero variance -> should not crash."""
        engine = ProjectionEngine()
        data = np.ones((10, 16), dtype=np.float32)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        assert coords.shape == (10, 2)
        assert np.allclose(coords, 0.0, atol=1e-6)

    def test_invalid_method(self):
        engine = ProjectionEngine()
        data = _random_euclidean(10, 16)
        with pytest.raises(ValueError, match="Invalid method"):
            engine.project(data, method="tsne", input_geometry="euclidean", output_geometry="euclidean")

    def test_two_samples_minimal(self):
        """Exactly 2 samples — the minimum for PCA."""
        engine = ProjectionEngine()
        data = _random_euclidean(2, 16)
        coords = engine.project(data, method="pca", input_geometry="euclidean", output_geometry="euclidean")
        assert coords.shape == (2, 2)


class TestIntegrationDatasetApi:

    def test_compute_visualization_pca_euclidean(self):
        from hyperview.core.dataset import Dataset
        from hyperview.core.sample import Sample

        ds = Dataset("test_pca", persist=False)

        for i in range(20):
            ds.add_sample(Sample(id=f"s{i}", filepath=f"/fake/{i}.png", label=f"c{i % 3}"))

        space_key = "test_space"
        ds._storage.ensure_space(
            model_id="test",
            dim=32,
            config={"provider": "test", "geometry": "euclidean"},
            space_key=space_key,
        )
        rng = np.random.default_rng(99)
        ids = [f"s{i}" for i in range(20)]
        vectors = rng.standard_normal((20, 32)).astype(np.float32)
        ds._storage.add_embeddings(space_key, ids, vectors)

        layout_key = ds.compute_visualization(
            space_key=space_key,
            method="pca",
            geometry="euclidean",
        )

        assert layout_key is not None
        vis_ids, vis_labels, vis_coords = ds.get_visualization_data(layout_key)
        assert len(vis_ids) == 20
        assert vis_coords.shape == (20, 2)

    def test_compute_visualization_pca_poincare(self):
        from hyperview.core.dataset import Dataset
        from hyperview.core.sample import Sample

        ds = Dataset("test_pca_poinc", persist=False)

        for i in range(20):
            ds.add_sample(Sample(id=f"s{i}", filepath=f"/fake/{i}.png", label=f"c{i % 3}"))

        space_key = "test_space"
        ds._storage.ensure_space(
            model_id="test",
            dim=32,
            config={"provider": "test", "geometry": "euclidean"},
            space_key=space_key,
        )
        rng = np.random.default_rng(99)
        ids = [f"s{i}" for i in range(20)]
        vectors = rng.standard_normal((20, 32)).astype(np.float32)
        ds._storage.add_embeddings(space_key, ids, vectors)

        layout_key = ds.compute_visualization(
            space_key=space_key,
            method="pca",
            geometry="poincare",
        )

        assert layout_key is not None
        vis_ids, _, vis_coords = ds.get_visualization_data(layout_key)
        assert len(vis_ids) == 20
        radii = np.linalg.norm(vis_coords, axis=1)
        assert np.all(radii < 1.0)

    def test_compute_visualization_pca_hyperboloid(self):
        """Integration test with hyperboloid input geometry."""
        from hyperview.core.dataset import Dataset
        from hyperview.core.sample import Sample

        ds = Dataset("test_pca_hyp", persist=False)

        for i in range(20):
            ds.add_sample(Sample(id=f"s{i}", filepath=f"/fake/{i}.png", label=f"c{i % 3}"))

        emb_dim = 33  # D+1 for hyperboloid
        space_key = "test_hyp_space"
        ds._storage.ensure_space(
            model_id="test_hyp",
            dim=emb_dim,
            config={"provider": "test", "geometry": "hyperboloid", "curvature": 1.0},
            space_key=space_key,
        )

        ids = [f"s{i}" for i in range(20)]
        vectors = _random_hyperboloid(20, emb_dim - 1, seed=77)
        ds._storage.add_embeddings(space_key, ids, vectors)

        for geom in ("euclidean", "poincare"):
            layout_key = ds.compute_visualization(
                space_key=space_key,
                method="pca",
                geometry=geom,
            )
            assert layout_key is not None
            vis_ids, _, vis_coords = ds.get_visualization_data(layout_key)
            assert len(vis_ids) == 20
            assert vis_coords.shape == (20, 2)
            assert np.all(np.isfinite(vis_coords))
