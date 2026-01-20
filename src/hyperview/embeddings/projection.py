"""Projection methods for dimensionality reduction."""

import logging

import numpy as np
import umap

logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Engine for projecting high-dimensional embeddings to 2D."""

    def project_umap(
        self,
        embeddings: np.ndarray,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        n_components: int = 2,
        random_state: int = 42,
    ) -> np.ndarray:
        """Project embeddings to Euclidean 2D using UMAP.

        Args:
            embeddings: High-dimensional embeddings (N x D).
            n_neighbors: Number of neighbors for UMAP.
            min_dist: Minimum distance between points.
            metric: Distance metric to use.
            n_components: Number of output dimensions.
            random_state: Random seed for reproducibility.

        Returns:
            2D coordinates (N x 2).
        """
        # Safety check for small datasets
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

        # Normalize to [-1, 1] range for visualization consistency
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
        """Project embeddings to the Poincaré disk.

        This uses UMAP with a hyperbolic output metric. UMAP computes the embedding
        in the Hyperboloid model (Lorentz model). We then project this to the
        Poincaré disk.

        Args:
            embeddings: High-dimensional embeddings (N x D).
            n_neighbors: Number of neighbors for UMAP.
            min_dist: Minimum distance between points.
            metric: Input distance metric.
            random_state: Random seed for reproducibility.

        Returns:
            2D coordinates in Poincaré disk (N x 2), with norm < 1.
        """
        # Safety check for small datasets
        n_neighbors = min(n_neighbors, len(embeddings) - 1)
        if n_neighbors < 2:
            n_neighbors = 2

        n_jobs = 1 if random_state is not None else -1
        # The time-like coordinate t is implicit: t = sqrt(1 + x^2 + y^2).
        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            n_components=2,  # We want a 2D manifold
            metric=metric,
            output_metric="hyperboloid",
            random_state=random_state,
            n_jobs=n_jobs,
        )

        # These are spatial coordinates (x, y) in the Hyperboloid model
        spatial_coords = reducer.fit_transform(embeddings)

        # Calculate implicit time coordinate t
        # t = sqrt(1 + x^2 + y^2)
        # Note: In some conventions it's t^2 - x^2 - y^2 = 1, so t = sqrt(1 + r^2)
        squared_norm = np.sum(spatial_coords**2, axis=1)
        t = np.sqrt(1 + squared_norm)

        # Project to Poincaré disk
        # Formula: u = x / (1 + t)
        # This maps the upper sheet of the hyperboloid (t >= 1) to the unit disk.
        denom = 1 + t
        poincare_coords = spatial_coords / denom[:, np.newaxis]

        # Ensure numerical stability - clamp to slightly less than 1.0 if needed
        # theoretically it should be < 1, but float precision might cause issues
        radii = np.linalg.norm(poincare_coords, axis=1)
        max_radius = 0.999
        mask = radii > max_radius
        if np.any(mask):
            logger.warning(f"Clamping {np.sum(mask)} points to unit disk.")
            poincare_coords[mask] = (
                poincare_coords[mask] / radii[mask][:, np.newaxis] * max_radius
            )

        # Center the embeddings in the Poincaré disk
        poincare_coords = self._center_poincare(poincare_coords)

        # Apply radial scaling to reduce crowding at the boundary
        # This effectively "zooms out" in hyperbolic space, pulling points
        # towards the center for better visualization.
        poincare_coords = self._scale_poincare(poincare_coords, factor=0.65)

        return poincare_coords

    def _scale_poincare(self, coords: np.ndarray, factor: float) -> np.ndarray:
        """Scale points towards the origin in hyperbolic space.

        This scales the hyperbolic distance from the origin by `factor`.
        If factor < 1, points move closer to the center.
        """
        radii = np.linalg.norm(coords, axis=1)
        # Avoid division by zero
        mask = radii > 1e-6

        # Calculate hyperbolic distance from origin
        # d = 2 * arctanh(r)
        # We want d_new = factor * d
        # r_new = tanh(d_new / 2) = tanh(factor * arctanh(r))

        # Use numpy operations for efficiency
        r = radii[mask]
        # Clip r to avoid infinity in arctanh
        r = np.minimum(r, 0.9999999)

        # d = 2 * np.arctanh(r)
        # r_new = np.tanh(factor * d / 2)
        # Simplified: r_new = tanh(factor * arctanh(r))
        r_new = np.tanh(factor * np.arctanh(r))

        # Update coordinates
        # new_coords = coords * (r_new / r)
        scale_ratios = np.ones_like(radii)
        scale_ratios[mask] = r_new / r

        return coords * scale_ratios[:, np.newaxis]

    def _center_poincare(self, coords: np.ndarray) -> np.ndarray:
        """Center points in the Poincaré disk using a Möbius transformation.

        This moves the geometric centroid of the points to the origin.
        """
        if len(coords) == 0:
            return coords

        # Treat as complex numbers for easier Möbius math
        z = coords[:, 0] + 1j * coords[:, 1]

        # Compute the centroid (Euclidean mean in the disk)
        # This is a heuristic; the true hyperbolic center of mass is harder
        # but this works well for visualization centering.
        centroid = np.mean(z)

        # If centroid is too close to boundary, don't center (unstable)
        if np.abs(centroid) > 0.99 or np.abs(centroid) < 1e-6:
            return coords

        # Möbius transformation to move centroid to origin:
        # w = (z - a) / (1 - conj(a) * z)
        a = centroid
        w = (z - a) / (1 - np.conj(a) * z)

        return np.stack([w.real, w.imag], axis=1)

    def _normalize_coords(self, coords: np.ndarray) -> np.ndarray:
        """Normalize coordinates to [-1, 1] range."""
        if len(coords) == 0:
            return coords

        # Center the coordinates
        coords = coords - coords.mean(axis=0)

        # Scale to fit in [-1, 1]
        max_abs = np.abs(coords).max()
        if max_abs > 0:
            coords = coords / max_abs * 0.95  # Leave some margin

        return coords

    def poincare_distance(self, u: np.ndarray, v: np.ndarray) -> float:
        """Compute the Poincaré distance between two points.

        Args:
            u: First point in Poincaré disk.
            v: Second point in Poincaré disk.

        Returns:
            Hyperbolic distance.
        """
        u_norm_sq = np.sum(u**2)
        v_norm_sq = np.sum(v**2)
        diff_norm_sq = np.sum((u - v) ** 2)

        # Poincaré distance formula
        # d(u, v) = arccosh(1 + 2 * |u-v|^2 / ((1-|u|^2)(1-|v|^2)))

        # Clip values to avoid division by zero or negative logs
        u_norm_sq = min(u_norm_sq, 0.99999)
        v_norm_sq = min(v_norm_sq, 0.99999)

        delta = 2 * diff_norm_sq / ((1 - u_norm_sq) * (1 - v_norm_sq))
        return np.arccosh(1 + delta)
