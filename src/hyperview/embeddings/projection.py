"""Projection methods for dimensionality reduction."""

import logging
import warnings

import numpy as np
import umap

logger = logging.getLogger(__name__)

_MIN_PCA_SAMPLES = 2
_EPS = 1e-7


class ProjectionEngine:
    """Engine for projecting high-dimensional embeddings to low-dimensional layouts."""

    def l2_normalize_rows(self, embeddings: np.ndarray) -> np.ndarray:
        """L2-normalize embeddings row-wise with numerical safeguards."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-12)
        return (embeddings / norms).astype(np.float32)

    def logmap_0_hyperboloid(
        self,
        embeddings: np.ndarray,
        curvature: float = 1.0,
    ) -> np.ndarray:
        """Map hyperboloid points to the tangent space at the origin."""
        if embeddings.ndim != 2 or embeddings.shape[1] < 2:
            raise ValueError(
                "embeddings must have shape (N, D+1) with D >= 1, "
                f"got {embeddings.shape}"
            )

        c = float(curvature)
        sqrt_c = np.sqrt(c)

        t = embeddings[:, 0]
        x = embeddings[:, 1:]

        arg = np.clip(sqrt_c * t, 1.0, None)
        theta = np.arccosh(arg) / sqrt_c

        norm_x = np.linalg.norm(x, axis=1)
        safe_norm = np.where(norm_x > _EPS, norm_x, 1.0)
        scale = np.where(norm_x > _EPS, theta / safe_norm, 0.0)

        return (x * scale[:, np.newaxis]).astype(np.float32)

    def expmap_0_hyperboloid(
        self,
        tangent_vectors: np.ndarray,
        curvature: float = 1.0,
    ) -> np.ndarray:
        """Map tangent vectors at the origin back to the hyperboloid."""
        if tangent_vectors.ndim != 2:
            raise ValueError(
                f"tangent_vectors must be 2-D, got shape {tangent_vectors.shape}"
            )

        c = float(curvature)
        sqrt_c = np.sqrt(c)

        norm_v = np.linalg.norm(tangent_vectors, axis=1)
        scaled_norm = sqrt_c * norm_v

        t = np.cosh(scaled_norm) / sqrt_c
        safe_scaled = np.where(scaled_norm > _EPS, scaled_norm, 1.0)
        coeff = np.where(
            scaled_norm > _EPS,
            np.sinh(scaled_norm) / safe_scaled,
            1.0,
        )
        spatial = tangent_vectors * coeff[:, np.newaxis]

        return np.column_stack([t, spatial]).astype(np.float32)

    def to_poincare_ball(
        self,
        hyperboloid_embeddings: np.ndarray,
        curvature: float | None = None,
        clamp_radius: float = 0.999999,
    ) -> np.ndarray:
        """Convert hyperboloid (Lorentz) coordinates to Poincaré ball coordinates.

        Input is expected to be shape (N, D+1) with first coordinate being time-like.
        Points are assumed to satisfy: t^2 - ||x||^2 = 1/c (c > 0).

        Returns Poincaré ball coordinates of shape (N, D) in the unit ball.

        Notes:
        - Many hyperbolic libraries parameterize curvature as a positive number c
          where the manifold has sectional curvature -c.
        - We map to the unit ball for downstream distance metrics (UMAP 'poincare').
        """
        if hyperboloid_embeddings.ndim != 2 or hyperboloid_embeddings.shape[1] < 2:
            raise ValueError(
                "hyperboloid_embeddings must have shape (N, D+1) with D>=1"
            )

        c = float(curvature) if curvature is not None else 1.0
        if c <= 0:
            raise ValueError(f"curvature must be > 0, got {c}")

        # Radius is 1/sqrt(c) for curvature -c.
        radius = 1.0 / np.sqrt(c)

        t = hyperboloid_embeddings[:, :1]
        x = hyperboloid_embeddings[:, 1:]

        # Map to the ball with the target radius.
        denom = t + radius
        ball_coords = x / denom

        # Rescale to the unit ball.
        u = ball_coords / radius

        # Numerical guard: ensure inside the unit ball
        radii = np.linalg.norm(u, axis=1)
        mask = radii >= clamp_radius
        if np.any(mask):
            u[mask] = u[mask] / radii[mask][:, np.newaxis] * clamp_radius

        return u.astype(np.float32)

    def project(
        self,
        embeddings: np.ndarray,
        *,
        input_geometry: str = "euclidean",
        output_geometry: str = "euclidean",
        n_components: int = 2,
        normalize_input: bool = False,
        curvature: float | None = None,
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        random_state: int = 42,
        verbose: bool = False,
    ) -> np.ndarray:
        """Project embeddings with geometry-aware preprocessing.

        This separates two concerns:
        1) Geometry/model transforms for the *input* embeddings (e.g. hyperboloid -> Poincaré)
        2) Dimensionality reduction / layout (UMAP or PCA)

        Args:
            embeddings: Input embeddings (N x D) or hyperboloid (N x D+1).
            input_geometry: Geometry/model of the input embeddings (euclidean, hyperboloid).
            output_geometry: Geometry of the output coordinates (euclidean, poincare, spherical).
            n_components: Number of output dimensions.
            normalize_input: Whether to L2-normalize vectors before projection.
            curvature: Curvature parameter for hyperbolic embeddings (positive c).
            method: Layout method ('umap' or 'pca').
            n_neighbors: UMAP neighbors.
            min_dist: UMAP min_dist.
            metric: Input metric (used for euclidean inputs).
            random_state: Random seed.

        Returns:
            Layout coordinates (N x n_components).
        """
        if method not in ("umap", "pca"):
            raise ValueError(
                f"Invalid method: {method}. Supported methods: 'umap', 'pca'."
            )
        if n_components < 2:
            raise ValueError(f"n_components must be >= 2, got {n_components}")

        if method == "pca":
            return self._project_pca(
                embeddings,
                input_geometry=input_geometry,
                output_geometry=output_geometry,
                n_components=n_components,
                normalize_input=normalize_input,
                curvature=curvature or 1.0,
                verbose=verbose,
            )

        prepared = embeddings
        prepared_metric: str = metric

        if normalize_input:
            prepared = self.l2_normalize_rows(prepared)

        if input_geometry == "hyperboloid":
            # Convert to unit Poincaré ball and use UMAP's built-in hyperbolic distance.
            prepared = self.to_poincare_ball(embeddings, curvature=curvature)
            prepared_metric = "poincare"

        if output_geometry == "poincare":
            if n_components != 2:
                raise ValueError("Poincare layouts currently require 2D output")
            return self.project_to_poincare(
                prepared,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric=prepared_metric,
                random_state=random_state,
                verbose=verbose,
            )

        if output_geometry in ("euclidean", "spherical"):
            return self.project_umap(
                prepared,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric=prepared_metric,
                n_components=n_components,
                random_state=random_state,
                verbose=verbose,
            )

        raise ValueError(
            f"Invalid output_geometry: {output_geometry}. "
            "Must be 'euclidean', 'poincare', or 'spherical'."
        )

    def _project_pca(
        self,
        embeddings: np.ndarray,
        *,
        input_geometry: str,
        output_geometry: str,
        n_components: int,
        normalize_input: bool,
        curvature: float,
        verbose: bool,
    ) -> np.ndarray:
        """Project embeddings with deterministic PCA."""
        if output_geometry not in ("euclidean", "poincare", "spherical"):
            raise ValueError(
                f"Invalid output_geometry: {output_geometry}. "
                "Must be 'euclidean', 'poincare', or 'spherical'."
            )
        if output_geometry == "poincare" and n_components != 2:
            raise ValueError("Poincare layouts currently require 2D output")
        if len(embeddings) < _MIN_PCA_SAMPLES:
            raise ValueError(
                f"PCA requires at least {_MIN_PCA_SAMPLES} samples, got {len(embeddings)}"
            )
        if not np.all(np.isfinite(embeddings)):
            raise ValueError("Embeddings contain NaN or Inf values.")

        if input_geometry == "hyperboloid":
            data = self.logmap_0_hyperboloid(embeddings, curvature=curvature)
        else:
            data = embeddings
            if normalize_input:
                data = self.l2_normalize_rows(data)

        coords, explained = self._pca_svd(data, n_components=n_components)

        if verbose:
            explained_str = ", ".join(f"{ratio:.4f}" for ratio in explained)
            logger.info("PCA explained variance ratio: [%s]", explained_str)

        if output_geometry == "poincare":
            if input_geometry == "hyperboloid":
                hyperboloid_coords = self.expmap_0_hyperboloid(coords, curvature=curvature)
                projected = self.to_poincare_ball(hyperboloid_coords, curvature=curvature)
            else:
                projected = self._map_to_poincare_disk(coords)

            projected = self._center_poincare(projected)
            projected = self._scale_poincare(projected, factor=0.65)
            return projected.astype(np.float32)

        projected = self._normalize_coords(coords)
        if output_geometry == "spherical":
            projected = self.l2_normalize_rows(projected)

        return projected.astype(np.float32)

    def _pca_svd(
        self,
        data: np.ndarray,
        n_components: int = 2,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute PCA with NumPy SVD and pad missing components with zeros."""
        data = data.astype(np.float64, copy=False)
        centered = data - data.mean(axis=0, keepdims=True)

        _u, singular_values, vh = np.linalg.svd(centered, full_matrices=False)

        k = min(n_components, vh.shape[0])
        if k > 0:
            projected = centered @ vh[:k].T
        else:
            projected = np.empty((len(data), 0), dtype=np.float64)

        if k < n_components:
            padding = np.zeros((projected.shape[0], n_components - k), dtype=projected.dtype)
            projected = np.hstack([projected, padding])

        variance = singular_values**2 / max(len(data) - 1, 1)
        explained = np.zeros(n_components, dtype=np.float32)
        total_variance = float(variance.sum())
        if total_variance > 0 and k > 0:
            explained[:k] = variance[:k] / total_variance

        return projected.astype(np.float32), explained

    def _map_to_poincare_disk(
        self,
        coords_2d: np.ndarray,
        alpha: float = 1.0,
    ) -> np.ndarray:
        """Map 2D Euclidean coordinates into the open Poincare disk."""
        if coords_2d.ndim != 2 or coords_2d.shape[1] != 2:
            raise ValueError(f"coords_2d must have shape (N, 2), got {coords_2d.shape}")

        max_abs = np.abs(coords_2d).max()
        normalized = coords_2d if max_abs <= _EPS else coords_2d / max_abs

        radii = np.linalg.norm(normalized, axis=1)
        safe_radii = np.where(radii > _EPS, radii, 1.0)
        mapped_radii = np.tanh(alpha * radii)
        scale = np.where(radii > _EPS, mapped_radii / safe_radii, 0.0)

        return (normalized * scale[:, np.newaxis]).astype(np.float32)

    def project_umap(
        self,
        embeddings: np.ndarray,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        n_components: int = 2,
        random_state: int = 42,
        verbose: bool = False,
    ) -> np.ndarray:
        """Project embeddings to Euclidean layout coordinates using UMAP."""
        n_neighbors = min(n_neighbors, len(embeddings) - 1)
        if n_neighbors < 2:
            n_neighbors = 2

        n_jobs = 1 if random_state is not None else -1

        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            n_components=n_components,
            metric=metric,
            random_state=random_state,
            n_jobs=n_jobs,
            verbose=verbose,
        )

        coords = reducer.fit_transform(embeddings)
        coords = self._normalize_coords(coords)

        return coords

    def project_to_poincare(
        self,
        embeddings: np.ndarray,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        random_state: int = 42,
        verbose: bool = False,
    ) -> np.ndarray:
        """Project embeddings to the Poincaré disk using UMAP with hyperboloid output."""
        n_neighbors = min(n_neighbors, len(embeddings) - 1)
        if n_neighbors < 2:
            n_neighbors = 2

        n_jobs = 1 if random_state is not None else -1

        # Suppress warning about missing gradient for poincare metric (only affects inverse_transform)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="gradient function is not yet implemented")
            reducer = umap.UMAP(
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                n_components=2,
                metric=metric,
                output_metric="hyperboloid",
                random_state=random_state,
                n_jobs=n_jobs,
                verbose=verbose,
            )
            spatial_coords = reducer.fit_transform(embeddings)

        squared_norm = np.sum(spatial_coords**2, axis=1)
        t = np.sqrt(1 + squared_norm)

        # Project to Poincaré disk: u = x / (1 + t)
        denom = 1 + t
        poincare_coords = spatial_coords / denom[:, np.newaxis]

        # Clamp to unit disk for numerical stability
        radii = np.linalg.norm(poincare_coords, axis=1)
        max_radius = 0.999
        mask = radii > max_radius
        if np.any(mask):
            logger.warning(f"Clamping {np.sum(mask)} points to unit disk.")
            poincare_coords[mask] = (
                poincare_coords[mask] / radii[mask][:, np.newaxis] * max_radius
            )

        poincare_coords = self._center_poincare(poincare_coords)
        poincare_coords = self._scale_poincare(poincare_coords, factor=0.65)

        return poincare_coords

    def _scale_poincare(self, coords: np.ndarray, factor: float) -> np.ndarray:
        """Scale points towards the origin in hyperbolic space.

        Scales hyperbolic distance from origin by `factor`. If factor < 1, points move closer to center.
        """
        radii = np.linalg.norm(coords, axis=1)
        mask = radii > 1e-6

        r = radii[mask]
        r = np.minimum(r, 0.9999999)
        r_new = np.tanh(factor * np.arctanh(r))

        scale_ratios = np.ones_like(radii)
        scale_ratios[mask] = r_new / r

        return coords * scale_ratios[:, np.newaxis]

    def _center_poincare(self, coords: np.ndarray) -> np.ndarray:
        """Center points in the Poincaré disk using a Möbius transformation."""
        if len(coords) == 0:
            return coords

        z = coords[:, 0] + 1j * coords[:, 1]
        centroid = np.mean(z)

        if np.abs(centroid) > 0.99 or np.abs(centroid) < 1e-6:
            return coords

        # Möbius transformation: w = (z - a) / (1 - conj(a) * z)
        a = centroid
        w = (z - a) / (1 - np.conj(a) * z)

        return np.stack([w.real, w.imag], axis=1)

    def _normalize_coords(self, coords: np.ndarray) -> np.ndarray:
        """Normalize coordinates to [-1, 1] range."""
        if len(coords) == 0:
            return coords

        coords = coords - coords.mean(axis=0)
        max_abs = np.abs(coords).max()
        if max_abs > 0:
            coords = coords / max_abs * 0.95

        return coords

    def poincare_distance(self, u: np.ndarray, v: np.ndarray) -> float:
        """Compute the Poincaré distance between two points."""
        u_norm_sq = np.sum(u**2)
        v_norm_sq = np.sum(v**2)
        diff_norm_sq = np.sum((u - v) ** 2)

        u_norm_sq = min(u_norm_sq, 0.99999)
        v_norm_sq = min(v_norm_sq, 0.99999)

        delta = 2 * diff_norm_sq / ((1 - u_norm_sq) * (1 - v_norm_sq))
        return np.arccosh(1 + delta)
