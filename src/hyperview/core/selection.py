"""Selection / geometry helpers.

This module contains small, backend-agnostic utilities used by selection endpoints
(e.g. lasso selection over 2D embeddings).
"""

from __future__ import annotations

import numpy as np


def points_in_polygon(points_xy: np.ndarray, polygon_xy: np.ndarray) -> np.ndarray:
    """Vectorized point-in-polygon (even-odd rule / ray casting).

    Args:
        points_xy: Array of shape (m, 2) with point coordinates.
        polygon_xy: Array of shape (n, 2) with polygon vertices.

    Returns:
        Boolean mask of length m, True where point lies inside polygon.

    Notes:
        Boundary points may be classified as outside depending on floating point
        ties (common for lasso selection tools).
    """
    if polygon_xy.shape[0] < 3:
        return np.zeros((points_xy.shape[0],), dtype=bool)

    x = points_xy[:, 0]
    y = points_xy[:, 1]
    poly_x = polygon_xy[:, 0]
    poly_y = polygon_xy[:, 1]

    inside = np.zeros((points_xy.shape[0],), dtype=bool)
    j = polygon_xy.shape[0] - 1

    for i in range(polygon_xy.shape[0]):
        xi = poly_x[i]
        yi = poly_y[i]
        xj = poly_x[j]
        yj = poly_y[j]

        # Half-open y-interval to avoid double-counting vertices.
        intersects = (yi > y) != (yj > y)

        denom = yj - yi
        # denom == 0 => intersects is always False; add tiny epsilon to avoid warnings.
        x_intersect = (xj - xi) * (y - yi) / (denom + 1e-30) + xi

        inside ^= intersects & (x < x_intersect)
        j = i

    return inside
