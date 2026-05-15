"""Browserless static rendering for paper-quality embedding figures."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hyperview.core.dataset import Dataset
from hyperview.core.selection import (
    OrbitViewState3D,
    build_mvp_for_orbit,
    project_points_3d_to_screen,
)
from hyperview.figures.colors import (
    create_label_color_map,
    hex_to_rgba,
    normalize_label,
)
from hyperview.storage.schema import parse_layout_dimension

FigureTheme = Literal["dark", "light"]
FigureGuideStyle = Literal["paper", "rings", "outline", "none"]
FigureLegendMode = Literal["auto", "on", "off", "direct"]


@dataclass(frozen=True)
class FigureRenderOptions:
    width: int = 900
    height: int = 900
    scale: int = 2
    theme: FigureTheme = "light"
    background: str | None = None
    point_radius: float = 4.0
    show_guide: bool = True
    guide_style: FigureGuideStyle = "paper"
    guide_alpha: int | None = None
    legend: FigureLegendMode = "auto"
    title: str | None = None
    selected_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class FigureExportResult:
    output_path: Path
    layout_key: str
    geometry: str
    width: int
    height: int
    num_points: int

    def to_dict(self) -> dict[str, object]:
        return {
            "output_path": str(self.output_path),
            "layout_key": self.layout_key,
            "geometry": self.geometry,
            "width": self.width,
            "height": self.height,
            "num_points": self.num_points,
        }


def _normalize_spherical(coords: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(coords, axis=1, keepdims=True)
    out = np.zeros_like(coords, dtype=np.float32)
    valid = norms[:, 0] >= 1e-8
    out[valid] = coords[valid] / norms[valid]
    out[~valid] = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    return out


def _default_view(coords: np.ndarray, geometry: str) -> OrbitViewState3D:
    if coords.shape[0] == 0:
        return OrbitViewState3D(
            yaw=0.9,
            pitch=0.4,
            distance=3.2,
            target_x=0.0,
            target_y=0.0,
            target_z=0.0,
            ortho_scale=1.18,
        )

    if geometry == "spherical":
        radius = max(float(np.max(np.linalg.norm(coords, axis=1))), 1.0)
        return OrbitViewState3D(
            yaw=0.9,
            pitch=0.4,
            distance=max(radius * 3.2, 2.4),
            target_x=0.0,
            target_y=0.0,
            target_z=0.0,
            ortho_scale=max(radius * 1.18, 1.0),
        )

    center = np.mean(coords, axis=0)
    radius = float(np.max(np.linalg.norm(coords - center, axis=1)))
    radius = max(radius, 0.25)
    return OrbitViewState3D(
        yaw=0.7,
        pitch=0.35,
        distance=max(radius * 3.0, 1.5),
        target_x=float(center[0]),
        target_y=float(center[1]),
        target_z=float(center[2]),
        ortho_scale=max(radius * 1.4, 0.75),
    )


def _resolve_background(options: FigureRenderOptions) -> tuple[str, str, int, int, int]:
    guide_alpha = options.guide_alpha
    if options.background:
        front_alpha = guide_alpha if guide_alpha is not None else 52
        return options.background, "#64748b", front_alpha, max(18, front_alpha // 3), min(88, front_alpha + 14)
    if options.theme == "light":
        front_alpha = guide_alpha if guide_alpha is not None else 52
        return "#ffffff", "#475569", front_alpha, max(18, front_alpha // 3), min(88, front_alpha + 14)
    front_alpha = guide_alpha if guide_alpha is not None else 58
    return "#161b22", "#cbd5e1", front_alpha, max(20, front_alpha // 3), min(98, front_alpha + 16)


def _project(
    coords: np.ndarray,
    view: OrbitViewState3D,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    mvp = build_mvp_for_orbit(view, coords, width, height)
    return project_points_3d_to_screen(mvp, coords, width, height)


def _circle_points(radius: float, plane: Literal["xy", "xz", "yz"], segments: int = 128) -> np.ndarray:
    out = np.zeros((segments + 1, 3), dtype=np.float32)
    for i in range(segments + 1):
        angle = (i / segments) * math.tau
        c = radius * math.cos(angle)
        s = radius * math.sin(angle)
        if plane == "xy":
            out[i] = (c, s, 0.0)
        elif plane == "xz":
            out[i] = (c, 0.0, s)
        else:
            out[i] = (0.0, c, s)
    return out


def _draw_polyline(
    draw: ImageDraw.ImageDraw,
    points: np.ndarray,
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    if points.shape[0] < 2:
        return
    xy = [(float(x), float(y)) for x, y in points[:, :2]]
    draw.line(xy, fill=fill, width=width)


def _orbit_camera_axes(view: OrbitViewState3D) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cp = math.cos(view.pitch)
    sp = math.sin(view.pitch)
    cy = math.cos(view.yaw)
    sy = math.sin(view.yaw)

    z_axis = np.array([cp * sy, sp, cp * cy], dtype=np.float32)
    z_norm = float(np.linalg.norm(z_axis))
    if z_norm < 1e-9:
        z_axis = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    else:
        z_axis = z_axis / z_norm

    world_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    x_axis = np.cross(world_up, z_axis).astype(np.float32)
    x_norm = float(np.linalg.norm(x_axis))
    if x_norm < 1e-9:
        x_axis = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    else:
        x_axis = x_axis / x_norm

    y_axis = np.cross(z_axis, x_axis).astype(np.float32)
    y_norm = float(np.linalg.norm(y_axis))
    if y_norm < 1e-9:
        y_axis = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    else:
        y_axis = y_axis / y_norm
    return x_axis, y_axis, z_axis


def _silhouette_points(radius: float, view: OrbitViewState3D, segments: int = 192) -> np.ndarray:
    right, up, _toward_camera = _orbit_camera_axes(view)
    out = np.zeros((segments + 1, 3), dtype=np.float32)
    for i in range(segments + 1):
        angle = (i / segments) * math.tau
        out[i] = radius * (math.cos(angle) * right + math.sin(angle) * up)
    return out


def _draw_projected_segments(
    draw: ImageDraw.ImageDraw,
    points: np.ndarray,
    screen_xy: np.ndarray,
    *,
    toward_camera: np.ndarray,
    front_fill: tuple[int, int, int, int],
    back_fill: tuple[int, int, int, int],
    width: int,
) -> None:
    if points.shape[0] < 2:
        return

    back_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    front_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for index in range(points.shape[0] - 1):
        p0 = points[index]
        p1 = points[index + 1]
        midpoint = (p0 + p1) * 0.5
        segment = (
            (float(screen_xy[index, 0]), float(screen_xy[index, 1])),
            (float(screen_xy[index + 1, 0]), float(screen_xy[index + 1, 1])),
        )
        if float(np.dot(midpoint, toward_camera)) >= 0.0:
            front_segments.append(segment)
        else:
            back_segments.append(segment)

    for segment in back_segments:
        draw.line(segment, fill=back_fill, width=width)
    for segment in front_segments:
        draw.line(segment, fill=front_fill, width=width)


def _draw_guide(
    draw: ImageDraw.ImageDraw,
    *,
    geometry: str,
    coords: np.ndarray,
    view: OrbitViewState3D,
    width: int,
    height: int,
    guide_color: str,
    guide_front_alpha: int,
    guide_back_alpha: int,
    guide_outline_alpha: int,
    line_width: int,
    guide_style: FigureGuideStyle,
) -> None:
    if guide_style == "none":
        return

    if geometry == "spherical":
        radius = 1.0
        front = hex_to_rgba(guide_color, guide_front_alpha)
        back = hex_to_rgba(guide_color, guide_back_alpha)
        outline = hex_to_rgba(guide_color, guide_outline_alpha)

        if guide_style in {"paper", "outline"}:
            silhouette = _silhouette_points(radius, view)
            sx, sy, _depth, _pixel_index = _project(silhouette, view, width, height)
            _draw_polyline(
                draw,
                np.column_stack((sx, sy)),
                outline,
                max(line_width, 2),
            )

        if guide_style == "outline":
            return

        if guide_style == "paper":
            _right, _up, toward_camera = _orbit_camera_axes(view)
            for plane in ("xy",):
                guide = _circle_points(radius, plane)  # type: ignore[arg-type]
                sx, sy, _depth, _pixel_index = _project(guide, view, width, height)
                _draw_projected_segments(
                    draw,
                    guide,
                    np.column_stack((sx, sy)),
                    toward_camera=toward_camera,
                    front_fill=front,
                    back_fill=back,
                    width=line_width,
                )
            return

        for plane in ("xy", "xz", "yz"):
            guide = _circle_points(radius, plane)  # type: ignore[arg-type]
            sx, sy, _depth, _pixel_index = _project(guide, view, width, height)
            _draw_polyline(
                draw,
                np.column_stack((sx, sy)),
                front,
                line_width,
            )
        return

    if coords.shape[0] == 0:
        return

    center = np.mean(coords, axis=0)
    span = np.ptp(coords, axis=0)
    radius = max(float(np.max(span)) * 0.56, 0.2)
    axes = np.asarray(
        [
            [center[0] - radius, center[1], center[2]],
            [center[0] + radius, center[1], center[2]],
            [center[0], center[1] - radius, center[2]],
            [center[0], center[1] + radius, center[2]],
            [center[0], center[1], center[2] - radius],
            [center[0], center[1], center[2] + radius],
        ],
        dtype=np.float32,
    )
    sx, sy, _depth, _pixel_index = _project(axes, view, width, height)
    projected = np.column_stack((sx, sy))
    color = hex_to_rgba(guide_color, max(20, min(72, guide_front_alpha)))
    for start in (0, 2, 4):
        _draw_polyline(draw, projected[start : start + 2], color, line_width)


def _load_font(size: int) -> ImageFont.ImageFont:
    for font_path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    labels: list[str | None],
    label_color_map: dict[str, str],
    options: FigureRenderOptions,
) -> None:
    if options.legend == "off" or not labels:
        return

    items = [(label, color) for label, color in label_color_map.items()]
    if len(items) < 2:
        return
    if options.legend == "direct" or (options.legend == "auto" and len(items) <= 4):
        return
    if options.legend == "auto" and len(items) > 10:
        return
    if len(items) > 12:
        items = items[:12] + [("...", "#94a3b8")]

    scale = max(1, int(options.scale))
    font = _load_font(max(12, int(13 * scale)))
    pad = 6 * scale
    swatch = 9 * scale
    gap = 7 * scale
    line_gap = 4 * scale
    margin = 60 * scale
    text_color = "#0f172a" if options.theme == "light" else "#e5e7eb"
    border_color = "#cbd5e1" if options.theme == "light" else "#475569"
    fill_color = "#ffffff" if options.theme == "light" else "#111827"

    text_sizes: list[tuple[int, int]] = []
    for label, _color in items:
        bbox = draw.textbbox((0, 0), label, font=font)
        text_sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))

    row_height = max(swatch, max(height for _width, height in text_sizes))
    box_width = pad * 2 + swatch + gap + max(width for width, _height in text_sizes)
    box_height = pad * 2 + len(items) * row_height + (len(items) - 1) * line_gap
    x0 = max(margin, width - margin - box_width)
    y0 = margin
    x1 = x0 + box_width
    y1 = y0 + box_height

    if options.theme == "dark" or options.background:
        draw.rectangle(
            (x0, y0, x1, y1),
            fill=hex_to_rgba(fill_color, 232),
            outline=hex_to_rgba(border_color, 170),
            width=max(1, scale),
        )

    y = y0 + pad
    for (label, color), (_text_width, text_height) in zip(items, text_sizes, strict=True):
        cy = y + row_height / 2.0
        sx0 = x0 + pad
        sy0 = cy - swatch / 2.0
        draw.ellipse((sx0, sy0, sx0 + swatch, sy0 + swatch), fill=hex_to_rgba(color, 255))
        draw.text(
            (sx0 + swatch + gap, cy - text_height / 2.0 - 1),
            label,
            fill=hex_to_rgba(text_color, 255),
            font=font,
        )
        y += row_height + line_gap


def _draw_direct_labels(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    labels: list[str | None],
    screen_x: np.ndarray,
    screen_y: np.ndarray,
    pixel_index: np.ndarray,
    label_color_map: dict[str, str],
    options: FigureRenderOptions,
) -> None:
    items = [(label, color) for label, color in label_color_map.items()]
    if len(items) < 2:
        return
    if options.legend == "off" or options.legend == "on":
        return
    if options.legend == "auto" and len(items) > 4:
        return

    scale = max(1, int(options.scale))
    font = _load_font(max(12, int(13 * scale)))
    stroke_fill = "#ffffff" if options.theme == "light" else "#111827"
    label_array = np.asarray([normalize_label(label) for label in labels], dtype=object)

    for label, color in items:
        mask = (label_array == label) & (pixel_index >= 0)
        if not np.any(mask):
            continue
        xs = screen_x[mask]
        ys = screen_y[mask]
        x = float(np.median(xs))
        y = float(np.median(ys))
        x_min = float(np.quantile(xs, 0.05))
        x_max = float(np.quantile(xs, 0.95))
        y_min = float(np.quantile(ys, 0.05))
        y_max = float(np.quantile(ys, 0.95))
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        pad = 22 * scale
        label_on_right = x < width * 0.72
        if label_on_right:
            tx = x_max + pad
        else:
            tx = x_min - text_width - pad
        if y > height * 0.66:
            ty = y_min - text_height - pad
        elif y < height * 0.34:
            ty = y_max + pad
        else:
            ty = y - text_height / 2.0
        tx = min(max(12 * scale, tx), width - text_width - 12 * scale)
        ty = min(max(12 * scale, ty), height - text_height - 12 * scale)
        draw.text(
            (tx, ty),
            label,
            fill=hex_to_rgba("#0f172a" if options.theme == "light" else "#f8fafc", 255),
            font=font,
            stroke_width=max(2, scale),
            stroke_fill=hex_to_rgba(stroke_fill, 255),
        )
        dot_radius = 4 * scale
        dot_gap = 6 * scale
        dot_x = tx - dot_gap - dot_radius if label_on_right else tx + text_width + dot_gap + dot_radius
        dot_y = ty + text_height / 2.0
        draw.ellipse(
            (dot_x - dot_radius, dot_y - dot_radius, dot_x + dot_radius, dot_y + dot_radius),
            fill=hex_to_rgba(color, 255),
        )


def _draw_title(
    draw: ImageDraw.ImageDraw,
    *,
    options: FigureRenderOptions,
) -> None:
    if not options.title:
        return
    scale = max(1, int(options.scale))
    font = _load_font(max(13, int(14 * scale)))
    text_color = "#0f172a" if options.theme == "light" else "#f8fafc"
    draw.text(
        (20 * scale, 18 * scale),
        options.title,
        fill=hex_to_rgba(text_color, 255),
        font=font,
    )


def render_layout_figure(
    *,
    dataset: Dataset,
    layout_key: str,
    output_path: str | Path,
    view: OrbitViewState3D | None = None,
    options: FigureRenderOptions | None = None,
) -> FigureExportResult:
    options = options or FigureRenderOptions()
    layout_info = next((layout for layout in dataset.list_layouts() if layout.layout_key == layout_key), None)
    if layout_info is None:
        raise ValueError(f"Layout not found: {layout_key}")

    if parse_layout_dimension(layout_key) != 3:
        raise ValueError(
            f"Static figure export currently supports 3D layouts only, got '{layout_key}'"
        )

    ids, labels, coords = dataset.get_visualization_data(layout_key)
    coords = np.asarray(coords, dtype=np.float32)
    if coords.ndim != 2 or coords.shape[1] < 3:
        raise ValueError(f"Layout '{layout_key}' must contain 3D coordinates")
    coords = coords[:, :3]

    geometry = str(layout_info.geometry)
    if geometry == "spherical":
        coords = _normalize_spherical(coords)

    width = max(64, int(options.width) * max(1, int(options.scale)))
    height = max(64, int(options.height) * max(1, int(options.scale)))
    point_radius = max(0.5, float(options.point_radius) * max(1, int(options.scale)))
    line_width = max(1, int(round(max(1, int(options.scale)))))

    background, guide_color, guide_front_alpha, guide_back_alpha, guide_outline_alpha = _resolve_background(options)
    background_rgba = hex_to_rgba(background, 255)
    image = Image.new("RGBA", (width, height), background_rgba)
    draw = ImageDraw.Draw(image, "RGBA")

    resolved_view = view or _default_view(coords, geometry)
    label_color_map = create_label_color_map(labels)

    if options.show_guide:
        _draw_guide(
            draw,
            geometry=geometry,
            coords=coords,
            view=resolved_view,
            width=width,
            height=height,
            guide_color=guide_color,
            guide_front_alpha=guide_front_alpha,
            guide_back_alpha=guide_back_alpha,
            guide_outline_alpha=guide_outline_alpha,
            line_width=line_width,
            guide_style=options.guide_style,
        )

    if coords.shape[0] > 0:
        screen_x, screen_y, depth, pixel_index = _project(coords, resolved_view, width, height)
        visible_indices = np.flatnonzero(pixel_index >= 0)
        # Larger depth is farther from the camera. Draw far-to-near so nearer points win.
        ordered = visible_indices[np.argsort(depth[visible_indices])[::-1]]

        label_colors = [
            hex_to_rgba(label_color_map.get(normalize_label(label), "#8b949e"), 245)
            for label in labels
        ]

        for index in ordered:
            x = float(screen_x[index])
            y = float(screen_y[index])
            r = point_radius
            draw.ellipse((x - r, y - r, x + r, y + r), fill=label_colors[int(index)])

        selected = options.selected_ids
        if selected:
            selected_hex = "#111827" if options.theme == "light" else "#f59e0b"
            selected_color = hex_to_rgba(selected_hex, 255)
            ring_width = max(2, int(round(1.5 * max(1, int(options.scale)))))
            ring_radius = point_radius + ring_width + 1
            id_to_index = {sample_id: i for i, sample_id in enumerate(ids)}
            for sample_id in sorted(selected):
                index = id_to_index.get(sample_id)
                if index is None or pixel_index[index] < 0:
                    continue
                x = float(screen_x[index])
                y = float(screen_y[index])
                draw.ellipse(
                    (x - ring_radius, y - ring_radius, x + ring_radius, y + ring_radius),
                    outline=selected_color,
                    width=ring_width,
                )

        _draw_direct_labels(
            draw,
            width=width,
            height=height,
            labels=labels,
            screen_x=screen_x,
            screen_y=screen_y,
            pixel_index=pixel_index,
            label_color_map=label_color_map,
            options=options,
        )

    _draw_legend(
        draw,
        width=width,
        labels=labels,
        label_color_map=label_color_map,
        options=options,
    )
    _draw_title(draw, options=options)

    if background_rgba[3] == 255:
        flattened = Image.new("RGBA", image.size, background_rgba)
        flattened.alpha_composite(image)
        image = flattened

    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() in {".jpg", ".jpeg"}:
        image.convert("RGB").save(target, quality=95)
    else:
        image.save(target)

    return FigureExportResult(
        output_path=target,
        layout_key=layout_key,
        geometry=geometry,
        width=width,
        height=height,
        num_points=len(ids),
    )
