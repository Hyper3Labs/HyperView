from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from hyperview import Dataset, Session
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.static_export import export_runtime_workspace


def _write_extension(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "extension.toml").write_text(
        "\n".join(
            [
                'name = "export-demo"',
                "",
                "[[panels]]",
                'id = "readout"',
                'title = "Readout"',
                'position = "right"',
                'file = "panel.js"',
            ]
        ),
        encoding="utf-8",
    )
    (folder / "panel.js").write_text(
        "export default function Panel() { return null; }\n",
        encoding="utf-8",
    )


def _make_runtime(tmp_path: Path) -> HyperViewRuntime:
    dataset = Dataset("static_export_dataset", persist=False)
    sample_ids: list[str] = []
    for index, label in enumerate(["cat", "dog", "cat"]):
        image_path = tmp_path / f"sample-{index}.png"
        Image.new("RGB", (12 + index, 10 + index), (index * 40, 40, 180)).save(image_path)
        sample_id = f"sample-{index}"
        sample_ids.append(sample_id)
        dataset.add_sample(
            Sample(
                id=sample_id,
                filepath=str(image_path),
                label=label,
                metadata={"index": index},
            )
        )
    layout_key = dataset.set_coords(
        "euclidean",
        sample_ids,
        np.asarray([[0.0, 0.0], [1.0, 0.5], [2.0, 0.25]], dtype=np.float32),
    )

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("demo", dataset, activate_workspace=True)
    runtime.set_active_layout("demo", layout_key)

    extension_dir = tmp_path / "export-demo-extension"
    _write_extension(extension_dir)
    runtime.install_extension("demo", extension_dir, add_panels=True)
    return runtime


def test_static_export_writes_bundle_snapshot_samples_media_and_flag(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    out_dir = tmp_path / "bundle"

    result = export_runtime_workspace(runtime, "demo", out_dir)

    assert result.workspace_id == "demo"
    assert result.num_samples == 3
    assert result.num_layouts == 1

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "window.__HYPERVIEW_STATIC__ = true;" in index_html

    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text(encoding="utf-8"))
    assert snapshot["workspace"]["id"] == "demo"
    assert snapshot["workspace"]["ui"]["active_layout_key"]
    assert snapshot["panel_definitions"]

    samples_index = json.loads((out_dir / "api" / "samples" / "index.json").read_text(encoding="utf-8"))
    assert samples_index["total"] == 3
    shard = json.loads(
        (out_dir / "api" / "samples" / samples_index["shards"][0]).read_text(encoding="utf-8")
    )
    assert shard["samples"][0]["media_url"] == "/api/samples/sample-0/content"
    assert shard["samples"][0]["thumbnail_url"] == "/api/samples/sample-0/thumbnail"

    assert (out_dir / "api" / "samples" / "sample-0" / "content").is_file()
    assert (out_dir / "api" / "samples" / "sample-0" / "thumbnail").is_file()
    assert (out_dir / "media" / "samples" / "sample-0" / "sample-0.png").is_file()
    assert (out_dir / "media" / "thumbnails" / "sample-0.jpg").is_file()
    assert (out_dir / "api" / "embeddings" / "default.json").is_file()
    assert (out_dir / "api" / "panels" / "content" / "demo" / "readout" / "panel.js").is_file()


def test_session_export_uses_runtime_workspace(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    session = Session(runtime, "127.0.0.1", 6262)
    out_dir = tmp_path / "session-bundle"

    payload = session.export(out_dir, workspace_id="demo")

    assert payload["workspace_id"] == "demo"
    assert Path(payload["output_dir"]).is_dir()
    assert (out_dir / "hyperview-static.json").is_file()
