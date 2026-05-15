from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.figures import FigureRenderOptions, render_layout_figure


def _make_spherical_dataset() -> tuple[Dataset, str]:
    dataset = Dataset("figure_export", persist=False)
    ids = ["north", "east", "south", "west"]
    labels = ["arcface", "arcface", "sphereface", "sphereface"]
    for sample_id, label in zip(ids, labels, strict=True):
        dataset.add_sample(Sample(id=sample_id, filepath=f"/virtual/{sample_id}.png", label=label))

    layout_key = dataset.set_coords(
        "spherical",
        ids,
        np.asarray(
            [
                [0.0, 1.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, -1.0, 0.0],
                [-1.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        ),
    )
    return dataset, layout_key


def test_render_layout_figure_writes_nonblank_png(tmp_path: Path) -> None:
    dataset, layout_key = _make_spherical_dataset()
    output = tmp_path / "paper.png"

    result = render_layout_figure(
        dataset=dataset,
        layout_key=layout_key,
        output_path=output,
        options=FigureRenderOptions(width=240, height=180, scale=1),
    )

    assert result.output_path == output.resolve()
    assert result.width == 240
    assert result.height == 180
    assert result.num_points == 4

    image = Image.open(output).convert("RGBA")
    assert image.size == (240, 180)
    assert image.getpixel((0, 0)) == (255, 255, 255, 255)
    colors = image.getcolors(maxcolors=240 * 180)
    assert colors is not None
    assert len(colors) > 1


def test_render_layout_figure_rejects_2d_layout(tmp_path: Path) -> None:
    dataset = Dataset("figure_export_2d", persist=False)
    dataset.add_sample(Sample(id="a", filepath="/virtual/a.png", label="a"))
    layout_key = dataset.set_coords("euclidean", ["a"], [[0.0, 0.0]])

    try:
        render_layout_figure(
            dataset=dataset,
            layout_key=layout_key,
            output_path=tmp_path / "paper.png",
        )
    except ValueError as exc:
        assert "3D layouts only" in str(exc)
    else:
        raise AssertionError("Expected 2D figure export to fail")


def test_render_layout_figure_handles_empty_3d_layout(tmp_path: Path) -> None:
    dataset = Dataset("figure_export_empty", persist=False)
    layout_key = dataset.set_coords("euclidean", [], np.empty((0, 3), dtype=np.float32))
    output = tmp_path / "empty.png"

    result = render_layout_figure(
        dataset=dataset,
        layout_key=layout_key,
        output_path=output,
        options=FigureRenderOptions(width=120, height=80, scale=1),
    )

    assert result.num_points == 0
    image = Image.open(output)
    assert image.size == (120, 80)
