"""Selection / geometry helpers.

This module contains small, backend-agnostic utilities used by selection
endpoints for both 2D and 3D lasso selection.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel


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


class OrbitViewState3D(BaseModel):
    """Orbit camera state for server-side 3D lasso projection."""

    yaw: float
    pitch: float
    distance: float
    target_x: float
    target_y: float
    target_z: float
    ortho_scale: float


def _normalize_vec(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm < 1e-9:
        return np.zeros_like(v, dtype=np.float32)
    return (v / norm).astype(np.float32)


def _mat4_look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Column-major lookAt matrix matching hyper-scatter 3D renderer math."""
    z_axis = _normalize_vec(eye - target)
    if float(np.linalg.norm(z_axis)) < 1e-9:
        z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    x_axis = _normalize_vec(np.cross(up, z_axis))
    if float(np.linalg.norm(x_axis)) < 1e-9:
        x_axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    y_axis = np.cross(z_axis, x_axis).astype(np.float32)

    out = np.zeros(16, dtype=np.float32)
    out[0] = x_axis[0]
    out[1] = y_axis[0]
    out[2] = z_axis[0]
    out[3] = 0.0

    out[4] = x_axis[1]
    out[5] = y_axis[1]
    out[6] = z_axis[1]
    out[7] = 0.0

    out[8] = x_axis[2]
    out[9] = y_axis[2]
    out[10] = z_axis[2]
    out[11] = 0.0

    out[12] = -float(np.dot(x_axis, eye))
    out[13] = -float(np.dot(y_axis, eye))
    out[14] = -float(np.dot(z_axis, eye))
    out[15] = 1.0
    return out


def _mat4_ortho(
    left: float,
    right: float,
    bottom: float,
    top: float,
    near: float,
    far: float,
) -> np.ndarray:
    """Column-major orthographic matrix matching hyper-scatter 3D renderer math."""
    rl = right - left
    tb = top - bottom
    fn = far - near

    if abs(rl) < 1e-12 or abs(tb) < 1e-12 or abs(fn) < 1e-12:
        raise ValueError("Invalid orthographic projection bounds")

    out = np.zeros(16, dtype=np.float32)
    out[0] = 2.0 / rl
    out[5] = 2.0 / tb
    out[10] = -2.0 / fn
    out[12] = -(right + left) / rl
    out[13] = -(top + bottom) / tb
    out[14] = -(far + near) / fn
    out[15] = 1.0
    return out


def _mat4_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Column-major matrix multiply matching hyper-scatter mat4Multiply."""
    out = np.zeros(16, dtype=np.float32)
    for col in range(4):
        for row in range(4):
            out[col * 4 + row] = (
                a[0 * 4 + row] * b[col * 4 + 0]
                + a[1 * 4 + row] * b[col * 4 + 1]
                + a[2 * 4 + row] * b[col * 4 + 2]
                + a[3 * 4 + row] * b[col * 4 + 3]
            )
    return out


def _build_mvp_for_orbit(
    view: OrbitViewState3D,
    coords: np.ndarray,
    viewport_width: int,
    viewport_height: int,
) -> np.ndarray:
    cp = math.cos(view.pitch)
    sp = math.sin(view.pitch)
    cy = math.cos(view.yaw)
    sy = math.sin(view.yaw)

    dir_target_to_eye = np.array([cp * sy, sp, cp * cy], dtype=np.float32)
    target = np.array([view.target_x, view.target_y, view.target_z], dtype=np.float32)
    eye = target + dir_target_to_eye * float(view.distance)

    world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    view_matrix = _mat4_look_at(eye, target, world_up)

    aspect = float(viewport_width) / float(max(1, viewport_height))
    half_h = max(0.01, float(view.ortho_scale))
    half_w = half_h * aspect

    center = np.mean(coords, axis=0)
    scene_radius = float(np.max(np.linalg.norm(coords - center, axis=1)))
    scene_radius = max(scene_radius, 0.25)

    near = 0.01
    far = max(near + 1.0, float(view.distance) + scene_radius * 6.0 + 10.0)

    proj_matrix = _mat4_ortho(-half_w, half_w, -half_h, half_h, near, far)
    return _mat4_multiply(proj_matrix, view_matrix)


def _project_points_3d_to_screen(
    mvp: np.ndarray,
    coords: np.ndarray,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = coords[:, 0]
    y = coords[:, 1]
    z = coords[:, 2]

    clip_x = mvp[0] * x + mvp[4] * y + mvp[8] * z + mvp[12]
    clip_y = mvp[1] * x + mvp[5] * y + mvp[9] * z + mvp[13]
    clip_z = mvp[2] * x + mvp[6] * y + mvp[10] * z + mvp[14]
    clip_w = mvp[3] * x + mvp[7] * y + mvp[11] * z + mvp[15]

    inv_w = np.zeros_like(clip_w)
    np.divide(1.0, clip_w, out=inv_w, where=np.abs(clip_w) > 1e-12)
    ndc_x = clip_x * inv_w
    ndc_y = clip_y * inv_w
    ndc_z = clip_z * inv_w

    finite = np.isfinite(ndc_x) & np.isfinite(ndc_y) & np.isfinite(ndc_z)
    in_clip = (
        finite
        & (ndc_x >= -1.0)
        & (ndc_x <= 1.0)
        & (ndc_y >= -1.0)
        & (ndc_y <= 1.0)
        & (ndc_z >= -1.0)
        & (ndc_z <= 1.0)
    )

    screen_x = (ndc_x * 0.5 + 0.5) * float(width)
    screen_y = (1.0 - (ndc_y * 0.5 + 0.5)) * float(height)
    depth = ndc_z * 0.5 + 0.5

    pixel_x = np.floor(screen_x).astype(np.int64)
    pixel_y = np.floor(screen_y).astype(np.int64)
    pixel_ok = (
        in_clip
        & (pixel_x >= 0)
        & (pixel_x < width)
        & (pixel_y >= 0)
        & (pixel_y < height)
    )

    pixel_index = np.full(coords.shape[0], -1, dtype=np.int64)
    pixel_index[pixel_ok] = pixel_y[pixel_ok] * width + pixel_x[pixel_ok]

    return screen_x, screen_y, depth, pixel_index


def select_ids_for_3d_lasso(
    *,
    ids: list[str],
    labels: list[str | None],
    coords: np.ndarray,
    geometry: str,
    polygon: np.ndarray,
    view: OrbitViewState3D,
    viewport_width: int,
    viewport_height: int,
    label_filter: str | None,
) -> list[str]:
    width = max(1, int(viewport_width))
    height = max(1, int(viewport_height))

    if label_filter is not None:
        label_mask = np.fromiter(
            (label == label_filter for label in labels),
            dtype=bool,
            count=len(labels),
        )
        if not np.any(label_mask):
            return []
        kept_indices = np.flatnonzero(label_mask)
        ids = [ids[int(i)] for i in kept_indices]
        coords = coords[label_mask]

    if geometry == "spherical":
        norms = np.linalg.norm(coords, axis=1, keepdims=True)
        coords = coords / np.maximum(norms, 1e-8)

    mvp = _build_mvp_for_orbit(view, coords, width, height)
    screen_x, screen_y, depth, pixel_index = _project_points_3d_to_screen(
        mvp, coords, width, height
    )

    pixel_count = max(1, width * height)
    depth_buffer = np.full(pixel_count, np.inf, dtype=np.float32)

    valid_mask = pixel_index >= 0
    valid_pixels = pixel_index[valid_mask]
    valid_depth = depth[valid_mask]
    np.minimum.at(depth_buffer, valid_pixels, valid_depth)

    visible_mask = np.zeros(coords.shape[0], dtype=bool)
    visible_mask[valid_mask] = depth[valid_mask] <= depth_buffer[valid_pixels] + 1e-4

    x_min = float(np.min(polygon[:, 0]))
    x_max = float(np.max(polygon[:, 0]))
    y_min = float(np.min(polygon[:, 1]))
    y_max = float(np.max(polygon[:, 1]))

    candidate_mask = (
        visible_mask
        & (screen_x >= x_min)
        & (screen_x <= x_max)
        & (screen_y >= y_min)
        & (screen_y <= y_max)
    )

    candidate_indices = np.flatnonzero(candidate_mask)
    if candidate_indices.size == 0:
        return []

    candidate_points = np.column_stack(
        (screen_x[candidate_indices], screen_y[candidate_indices])
    ).astype(np.float32)
    inside = points_in_polygon(candidate_points, polygon)
    selected_indices = candidate_indices[np.flatnonzero(inside)]

    return [ids[int(i)] for i in selected_indices]
