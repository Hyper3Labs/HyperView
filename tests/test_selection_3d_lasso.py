from __future__ import annotations

import numpy as np

from hyperview.core.selection import (
    OrbitViewState3D,
    _build_mvp_for_orbit,
    _project_points_3d_to_screen,
    select_ids_for_3d_lasso,
)


def _square_around(x: float, y: float, radius: float = 4.0) -> np.ndarray:
    return np.array(
        [
            [x - radius, y - radius],
            [x + radius, y - radius],
            [x + radius, y + radius],
            [x - radius, y + radius],
        ],
        dtype=np.float32,
    )


def test_spherical_3d_lasso_matches_renderer_normalization() -> None:
    coords = np.array([[2.0, 0.0, 0.0]], dtype=np.float32)
    normalized_coords = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    view = OrbitViewState3D(
        yaw=0.0,
        pitch=0.0,
        distance=4.0,
        target_x=0.0,
        target_y=0.0,
        target_z=0.0,
        ortho_scale=1.5,
    )

    mvp = _build_mvp_for_orbit(view, normalized_coords, 200, 200)
    screen_x, screen_y, _, _ = _project_points_3d_to_screen(mvp, normalized_coords, 200, 200)
    polygon = _square_around(float(screen_x[0]), float(screen_y[0]))

    selected_ids = select_ids_for_3d_lasso(
        ids=["far"],
        labels=["cat"],
        coords=coords,
        geometry="spherical",
        polygon=polygon,
        view=view,
        viewport_width=200,
        viewport_height=200,
        label_filter=None,
    )

    assert selected_ids == ["far"]


def test_3d_lasso_label_filter_excludes_hidden_occluders() -> None:
    coords = np.array(
        [
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0],
        ],
        dtype=np.float32,
    )
    view = OrbitViewState3D(
        yaw=0.0,
        pitch=0.0,
        distance=4.0,
        target_x=0.0,
        target_y=0.0,
        target_z=0.0,
        ortho_scale=1.5,
    )

    mvp = _build_mvp_for_orbit(view, coords, 200, 200)
    screen_x, screen_y, _, _ = _project_points_3d_to_screen(mvp, coords, 200, 200)
    polygon = _square_around(float(screen_x[1]), float(screen_y[1]))

    selected_ids = select_ids_for_3d_lasso(
        ids=["front-dog", "back-cat"],
        labels=["dog", "cat"],
        coords=coords,
        geometry="euclidean",
        polygon=polygon,
        view=view,
        viewport_width=200,
        viewport_height=200,
        label_filter="cat",
    )

    assert selected_ids == ["back-cat"]
