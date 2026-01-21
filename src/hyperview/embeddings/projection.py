"""Projection methods for dimensionality reduction."""

import logging
import warnings

import numpy as np
import umap

logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Engine for projecting high-dimensional embeddings to 2D."""

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

        # Radius R = 1/sqrt(c) for curvature -c
        R = 1.0 / np.sqrt(c)

        t = hyperboloid_embeddings[:, :1]
        x = hyperboloid_embeddings[:, 1:]

        # Map to ball radius R: u_R = x / (t + R)
        denom = t + R
        u_R = x / denom

        # Rescale to unit ball: u = u_R / R = sqrt(c) * u_R
        u = u_R / R

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
        curvature: float | None = None,
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        random_state: int = 42,
    ) -> np.ndarray:
        """Project embeddings to 2D with geometry-aware preprocessing.

        This separates two concerns:
        1) Geometry/model transforms for the *input* embeddings (e.g. hyperboloid -> Poincaré)
        2) Dimensionality reduction / layout (currently UMAP)

        Args:
            embeddings: Input embeddings (N x D) or hyperboloid (N x D+1).
            input_geometry: Geometry/model of the input embeddings (euclidean, hyperboloid).
            output_geometry: Geometry of the output coordinates (euclidean, poincare).
            curvature: Curvature parameter for hyperbolic embeddings (positive c).
            method: Layout method (currently only 'umap').
            n_neighbors: UMAP neighbors.
            min_dist: UMAP min_dist.
            metric: Input metric (used for euclidean inputs).
            random_state: Random seed.

        Returns:
            2D coordinates (N x 2).
        """
        if method != "umap":
            raise ValueError(f"Invalid method: {method}. Only 'umap' is supported.")

        prepared = embeddings
        prepared_metric: str = metric

        if input_geometry == "hyperboloid":
            # Convert to unit Poincaré ball and use UMAP's built-in hyperbolic distance.
            prepared = self.to_poincare_ball(embeddings, curvature=curvature)
            prepared_metric = "poincare"

        if output_geometry == "poincare":
            return self.project_to_poincare(
                prepared,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric=prepared_metric,
                random_state=random_state,
            )

        if output_geometry == "euclidean":
            return self.project_umap(
                prepared,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric=prepared_metric,
                n_components=2,
                random_state=random_state,
            )

        raise ValueError(
            f"Invalid output_geometry: {output_geometry}. Must be 'euclidean' or 'poincare'."
        )

    def project_umap(
        self,
        embeddings: np.ndarray,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        n_components: int = 2,
        random_state: int = 42,
    ) -> np.ndarray:
        """Project embeddings to Euclidean 2D using UMAP."""
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
