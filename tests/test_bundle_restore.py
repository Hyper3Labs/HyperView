"""A bundle must round-trip: what was exported is what comes back.

`hyperview export` writes one folder. Hosting it as files is a Static Space;
`hyperview serve --from` restores it as a Live Space. These tests build a small
workspace, export it, restore it into a fresh datasets directory, and check
that the identities the exported view pins -- sample ids, space ids, layout
keys, collection ids, panel definitions and instances and state -- come back
unchanged, because anything regenerated leaves the view pointing at nothing.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hyperview.bundle_restore import (
    restore_bundle,
    restored_extensions_dir,
    restored_media_dir,
)
from hyperview.core.dataset import Dataset
from hyperview.core.sample import Sample
from hyperview.extensions import resolve_shipped_extension
from hyperview.runtime import (
    CustomPanelSpec,
    HyperViewRuntime,
    ProviderRegistry,
    WorkspaceRegistry,
)
from hyperview.server.app import create_app
from hyperview.static_export import export_runtime_workspace

WORKSPACE_ID = "roundtrip"
DATASET_NAME = "bundle_roundtrip_dataset"
SPACE_KEY = "roundtrip_space"
MODEL_ID = "test/roundtrip-model"
PANEL_ID = "reference"
PANEL_NOTES = "restored panel state"

_VECTORS = np.asarray(
    [[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.0, 1.0, 0.0], [0.0, 0.9, 0.1]],
    dtype=np.float32,
)
_COORDS = np.asarray(
    [[0.0, 0.0], [1.0, 0.5], [2.0, 0.25], [3.0, -0.5]],
    dtype=np.float32,
)


def _source_dataset(media_dir: Path, *, persist: bool = False) -> tuple[Dataset, list[str], str]:
    media_dir.mkdir(parents=True, exist_ok=True)
    dataset = Dataset(DATASET_NAME, persist=persist)
    sample_ids: list[str] = []
    for index, label in enumerate(["cat", "cat", "dog", "dog"]):
        image_path = media_dir / f"sample-{index}.png"
        Image.new("RGB", (10 + index, 12 + index), (index * 30, 90, 200)).save(image_path)
        sample_id = f"sample-{index}"
        sample_ids.append(sample_id)
        dataset.add_sample(
            Sample(
                id=sample_id,
                filepath=str(image_path),
                label=label,
                text=f"a photo of a {label} number {index}",
                metadata={"index": index, "split": "train" if index < 2 else "val"},
            )
        )

    dataset.register_embeddings(
        SPACE_KEY,
        MODEL_ID,
        sample_ids,
        _VECTORS,
        config={"provider": "test", "geometry": "euclidean", "modality": "multimodal"},
    )
    layout_key = dataset.register_layout(
        f"{SPACE_KEY}__euclidean_umap__2d",
        SPACE_KEY,
        sample_ids,
        _COORDS,
        method="umap",
        geometry="euclidean",
        params={"n_neighbors": 4},
    )
    return dataset, sample_ids, layout_key


def _source_runtime(
    tmp_path: Path, *, persist: bool = False
) -> tuple[HyperViewRuntime, list[str], str]:
    """A workspace with samples, a space, a layout, a collection, and a panel."""

    dataset, sample_ids, layout_key = _source_dataset(
        tmp_path / "source-media", persist=persist
    )
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "source-providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "source-workspaces.json"),
    )
    runtime.attach_dataset_instance(WORKSPACE_ID, dataset, activate_workspace=True)
    runtime.set_active_layout(WORKSPACE_ID, layout_key)

    runtime.install_extension(
        WORKSPACE_ID,
        resolve_shipped_extension("reference"),
        add_panels=True,
        source="shipped",
    )
    runtime.patch_panel_state(WORKSPACE_ID, PANEL_ID, {"notes": PANEL_NOTES})
    # A selection collection is referenced by the samples panel state, so the
    # export keeps it and the restored view has to resolve the same id.
    runtime.set_samples_selection(WORKSPACE_ID, sample_ids[:2])
    return runtime, sample_ids, layout_key


def _export(tmp_path: Path) -> tuple[Path, dict, list[str], str]:
    runtime, sample_ids, layout_key = _source_runtime(tmp_path)
    out_dir = tmp_path / "bundle"
    export_runtime_workspace(runtime, WORKSPACE_ID, out_dir)
    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text(encoding="utf-8"))
    return out_dir, snapshot, sample_ids, layout_key


@pytest.fixture
def fresh_datasets_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point storage and the runtime registries at an empty directory.

    The runtime config dir is the datasets dir's parent, so this isolates
    workspaces.json and jobs.json from the developer's real ~/.hyperview too.
    """

    datasets_dir = tmp_path / "restored-home" / "datasets"
    datasets_dir.mkdir(parents=True)
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(datasets_dir))
    monkeypatch.setenv("HYPERVIEW_MEDIA_DIR", str(tmp_path / "restored-home" / "media"))
    return datasets_dir


def test_bundle_carries_vectors_and_extension_folders(tmp_path: Path) -> None:
    out_dir, _snapshot, sample_ids, layout_key = _export(tmp_path)

    manifest = json.loads((out_dir / "hyperview-static.json").read_text(encoding="utf-8"))
    restore = manifest["restore"]

    # Every field a Static Space consumer already reads is still there.
    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "hyperview-static-space"
    assert manifest["static"] is True
    assert manifest["capabilities"]["layouts"] is True
    assert manifest["artifacts"]["runtime"] == "api/runtime.json"
    assert manifest["deployment"]["cloudflare"]["mode"] == "static-assets-only"

    assert restore["supported"] is True
    assert restore["workspace_id"] == WORKSPACE_ID
    assert restore["dataset"]["name"] == DATASET_NAME
    assert manifest["producer"]["hyperview"] == manifest["hyperview_version"]
    assert "hyper_models" in manifest["producer"]

    space_entry = next(item for item in restore["spaces"] if item["space_key"] == SPACE_KEY)
    assert space_entry["model_id"] == MODEL_ID
    assert space_entry["provider"] == "test"
    assert space_entry["dim"] == 3
    with np.load(out_dir / space_entry["vectors"], allow_pickle=False) as payload:
        assert [str(item) for item in payload["ids"].tolist()] == sample_ids
        np.testing.assert_allclose(payload["vectors"], _VECTORS)

    layout_entry = next(item for item in restore["layouts"] if item["layout_key"] == layout_key)
    assert layout_entry["space_key"] == SPACE_KEY
    assert layout_entry["params"] == {"n_neighbors": 4}

    extension_entry = next(item for item in restore["extensions"] if item["name"] == "reference")
    extension_dir = out_dir / extension_entry["path"]
    # The static copy publishes browser-loadable panel source only. The Live
    # Space copy is the whole folder, manifest and Python tools included.
    assert (extension_dir / "extension.toml").is_file()
    assert (extension_dir / "tools.py").is_file()
    assert (extension_dir / "panel.jsx").is_file()
    assert (out_dir / "api" / "panels" / "content" / WORKSPACE_ID / PANEL_ID / "panel.js").is_file()


def test_restore_reproduces_the_exported_workspace(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    out_dir, snapshot, sample_ids, layout_key = _export(tmp_path)

    runtime, result = restore_bundle(out_dir)

    assert result.warnings == ()
    assert result.workspace_id == WORKSPACE_ID
    assert result.dataset_name == DATASET_NAME
    assert result.reused_dataset is False

    dataset = runtime.get_dataset(WORKSPACE_ID)
    assert [sample.id for sample in dataset.samples] == sample_ids

    restored = {sample.id: sample for sample in dataset.samples}
    assert restored["sample-0"].label == "cat"
    assert restored["sample-2"].label == "dog"
    assert restored["sample-3"].text == "a photo of a dog number 3"
    assert restored["sample-1"].metadata == {"index": 1, "split": "train"}
    # Media resolves against the restored dataset's own copy, never the bundle.
    assert Path(restored["sample-0"].filepath).is_file()
    assert not Path(restored["sample-0"].filepath).is_relative_to(out_dir)
    assert Path(restored["sample-0"].filepath).is_relative_to(restored_media_dir(DATASET_NAME))
    assert result.num_media_copied == len(sample_ids)
    assert result.num_media_reused == 0

    assert [space.space_key for space in dataset.list_spaces()] == [SPACE_KEY]
    space = dataset.list_spaces()[0]
    assert space.model_id == MODEL_ID
    assert space.provider == "test"
    stored_ids, stored_vectors = dataset._storage.get_embeddings(SPACE_KEY)
    order = [stored_ids.index(sample_id) for sample_id in sample_ids]
    np.testing.assert_allclose(stored_vectors[order], _VECTORS)

    assert [layout.layout_key for layout in dataset.list_layouts()] == [layout_key]
    layout_ids, _labels, layout_coords = dataset.get_visualization_data(layout_key)
    coord_order = [layout_ids.index(sample_id) for sample_id in sample_ids]
    np.testing.assert_allclose(layout_coords[coord_order], _COORDS)

    workspace = runtime.get_workspace(WORKSPACE_ID)
    assert workspace.ui.active_layout_key == layout_key

    exported_collection_ids = sorted(
        item["id"] for item in snapshot["workspace"]["collections"]
    )
    assert sorted(workspace.collections) == exported_collection_ids

    exported_definitions = {
        item["panel_type"]: item for item in snapshot["panel_definitions"]
    }
    restored_definitions = {
        item.panel_type: item.to_dict() for item in runtime.list_panel_definitions()
    }
    assert restored_definitions == exported_definitions

    exported_panels = {
        item["id"]: item for item in snapshot["workspace"]["ui"]["custom_panels"]
    }
    restored_panels = {panel.id: panel for panel in workspace.ui.custom_panels}
    assert set(restored_panels) == set(exported_panels)
    for panel_id, exported in exported_panels.items():
        panel = restored_panels[panel_id]
        assert panel.resolved_panel_type() == exported["panel_type"]
        assert panel.resolved_renderer() == exported["renderer"]
        assert panel.props == exported["props"]
        assert panel.layout_dict() == exported["layout"]
        # The export strips the exporting host's module path; the restored
        # panel points at the copy of the extension folder the dataset owns.
        module_file = Path(panel.resolved_module_file())
        assert not module_file.is_relative_to(out_dir)
        assert module_file.is_relative_to(restored_extensions_dir(DATASET_NAME))

    exported_states = snapshot["workspace"]["ui"]["panels"]
    restored_states = {
        panel_id: entry.to_dict() for panel_id, entry in workspace.ui.panels.items()
    }
    assert restored_states == exported_states
    assert runtime.get_panel_state(WORKSPACE_ID, PANEL_ID)["state"]["notes"] == PANEL_NOTES

    assert {item.manifest.name for item in runtime.list_extensions()} == {"reference"}


def test_restoring_twice_into_the_same_datasets_dir_reuses_the_dataset(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    out_dir, _snapshot, sample_ids, layout_key = _export(tmp_path)

    _first_runtime, first = restore_bundle(out_dir)
    assert first.reused_dataset is False

    # A row written by an older HyperView, or by a restore of a bundle that has
    # since moved: a restart has to repair it, not preserve it.
    stale = Dataset(DATASET_NAME)[sample_ids[0]]
    stale.media_type = None
    stale.filepath = "/gone/sample-0.png"
    stale.label = "stale"
    Dataset(DATASET_NAME).add_sample(stale)

    # A restarted container restores the same bundle against storage that
    # already holds it. Nothing may be duplicated and nothing re-ingested.
    second_runtime, second = restore_bundle(out_dir)
    assert second.reused_dataset is True
    assert second.warnings == ()
    assert second.workspace_id == first.workspace_id

    dataset = second_runtime.get_dataset(WORKSPACE_ID)
    assert [sample.id for sample in dataset.samples] == sample_ids
    assert [space.space_key for space in dataset.list_spaces()] == [SPACE_KEY]
    assert [layout.layout_key for layout in dataset.list_layouts()] == [layout_key]
    assert len(dataset._storage.get_embeddings(SPACE_KEY)[0]) == len(sample_ids)
    assert len(dataset.get_visualization_data(layout_key)[0]) == len(sample_ids)

    repaired = dataset[sample_ids[0]]
    assert repaired.label == "cat"
    assert repaired.media_type == "image/png"
    assert Path(repaired.filepath).is_relative_to(restored_media_dir(DATASET_NAME))
    # Only the row whose file had gone missing was re-pointed; the other three
    # already had a readable file of their own and were left alone.
    assert second.num_media_copied == 1
    assert second.num_media_reused == len(sample_ids) - 1

    workspace = second_runtime.get_workspace(WORKSPACE_ID)
    assert workspace.ui.active_layout_key == layout_key
    assert second_runtime.get_panel_state(WORKSPACE_ID, PANEL_ID)["state"]["notes"] == PANEL_NOTES


def test_restore_beside_the_source_dataset_keeps_the_source_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported corruption: serving a bundle where the source dataset lives.

    `hyperview serve --from` on the machine that exported the bundle reuses the
    dataset of the same name. Re-pointing its samples at the bundle's own media
    copies would make the source dataset depend on a folder the next export
    clears, so a sample whose file is readable and outside the bundle keeps it.
    """

    datasets_dir = tmp_path / "source-home" / "datasets"
    datasets_dir.mkdir(parents=True)
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(datasets_dir))
    monkeypatch.setenv("HYPERVIEW_MEDIA_DIR", str(tmp_path / "source-home" / "media"))

    runtime, sample_ids, _layout_key = _source_runtime(tmp_path, persist=True)
    out_dir = tmp_path / "bundle"
    export_runtime_workspace(runtime, WORKSPACE_ID, out_dir)
    source_paths = {sample.id: sample.filepath for sample in Dataset(DATASET_NAME).samples}

    restored_runtime, result = restore_bundle(out_dir)

    assert result.reused_dataset is True
    assert result.num_media_reused == len(sample_ids)
    assert result.num_media_copied == 0
    dataset = restored_runtime.get_dataset(WORKSPACE_ID)
    assert {sample.id: sample.filepath for sample in dataset.samples} == source_paths

    # The bundle is now disposable: deleting it leaves the dataset intact.
    shutil.rmtree(out_dir)
    for sample in Dataset(DATASET_NAME).samples:
        assert Path(sample.filepath).is_file()


def test_restore_into_a_fresh_dir_copies_media_and_extensions_out_of_the_bundle(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    out_dir, _snapshot, sample_ids, _layout_key = _export(tmp_path)

    runtime, result = restore_bundle(out_dir)

    assert result.link_media is False
    assert result.num_media_copied == len(sample_ids)
    assert result.num_media_linked == 0
    assert result.num_media_reused == 0
    assert result.media_dir == restored_media_dir(DATASET_NAME)

    dataset = runtime.get_dataset(WORKSPACE_ID)
    for sample in dataset.samples:
        assert not Path(sample.filepath).is_relative_to(out_dir)
    installation = next(iter(runtime.list_extensions()))
    assert not installation.manifest.folder.is_relative_to(out_dir)
    assert installation.manifest.folder.is_relative_to(restored_extensions_dir(DATASET_NAME))

    # Nothing the Space serves may depend on the bundle folder surviving.
    shutil.rmtree(out_dir)
    client = TestClient(create_app(runtime=runtime, api_token="secret-token"))
    media_response = client.get(f"/api/samples/{sample_ids[0]}/content")
    assert media_response.status_code == 200
    assert media_response.content.startswith(b"\x89PNG")
    assert Path(
        next(
            panel.resolved_module_file()
            for panel in runtime.get_workspace(WORKSPACE_ID).ui.custom_panels
        )
    ).is_file()


def test_restore_refreshes_the_copy_it_owns_when_the_bundle_media_changed(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    """Owning the media must not mean serving a stale copy of it.

    Re-exporting a bundle and restarting the Space against the same datasets
    directory has to bring the new bytes across. Only the dataset's own copy is
    ever rewritten; a file that lives anywhere else is left alone.
    """

    out_dir, _snapshot, sample_ids, _layout_key = _export(tmp_path)
    runtime, _first = restore_bundle(out_dir)
    owned_copy = Path(runtime.get_dataset(WORKSPACE_ID)[sample_ids[0]].filepath)

    bundle_media = out_dir / "api" / "samples" / sample_ids[0] / "content"
    Image.new("RGB", (40, 40), (255, 0, 0)).save(bundle_media, format="PNG")

    second_runtime, second = restore_bundle(out_dir)

    # The path is unchanged -- nothing was re-pointed -- but the bytes are new.
    assert Path(second_runtime.get_dataset(WORKSPACE_ID)[sample_ids[0]].filepath) == owned_copy
    assert second.num_media_reused == len(sample_ids)
    assert second.num_media_copied == 0
    assert owned_copy.read_bytes() == bundle_media.read_bytes()


def test_link_media_points_at_the_bundle_and_a_later_restore_takes_ownership(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    out_dir, _snapshot, sample_ids, _layout_key = _export(tmp_path)

    runtime, result = restore_bundle(out_dir, link_media=True)

    assert result.link_media is True
    assert result.media_dir is None
    assert result.num_media_linked == len(sample_ids)
    assert result.num_media_copied == 0
    dataset = runtime.get_dataset(WORKSPACE_ID)
    for sample in dataset.samples:
        assert Path(sample.filepath).is_relative_to(out_dir)
    assert next(iter(runtime.list_extensions())).manifest.folder.is_relative_to(out_dir)

    # Restoring the same bundle again without the flag has to take the rows
    # back off the bundle: a path inside it is not a file worth keeping.
    second_runtime, second = restore_bundle(out_dir)

    assert second.num_media_copied == len(sample_ids)
    assert second.num_media_reused == 0
    for sample in second_runtime.get_dataset(WORKSPACE_ID).samples:
        assert not Path(sample.filepath).is_relative_to(out_dir)


def test_export_refuses_to_clear_the_bundle_it_reads_media_from(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    """The second half of the reported corruption.

    A workspace restored with `--link-media` reads its media out of the bundle.
    Exporting it back over that same folder would clear the files it is about
    to copy, so the export refuses before anything is removed.
    """

    out_dir, _snapshot, sample_ids, _layout_key = _export(tmp_path)
    runtime, _result = restore_bundle(out_dir, link_media=True)
    before = sorted(path.name for path in out_dir.iterdir())

    with pytest.raises(RuntimeError, match="own output directory"):
        export_runtime_workspace(runtime, WORKSPACE_ID, out_dir)

    assert sorted(path.name for path in out_dir.iterdir()) == before
    assert (out_dir / "api" / "samples" / sample_ids[0] / "content").is_file()
    assert (out_dir / "extensions" / "reference" / "extension.toml").is_file()


def test_restored_runtime_serves_the_workspace_over_http(
    tmp_path: Path, fresh_datasets_dir: Path
) -> None:
    out_dir, _snapshot, sample_ids, layout_key = _export(tmp_path)
    runtime, _result = restore_bundle(out_dir)

    client = TestClient(create_app(runtime=runtime, api_token="secret-token"))

    snapshot = client.get("/api/runtime", params={"workspace_id": WORKSPACE_ID}).json()
    assert snapshot["workspace"]["id"] == WORKSPACE_ID
    assert snapshot["workspace"]["dataset_name"] == DATASET_NAME
    assert snapshot["workspace"]["ui"]["active_layout_key"] == layout_key
    assert PANEL_ID in {panel["id"] for panel in snapshot["workspace"]["ui"]["custom_panels"]}

    state_response = client.post(
        "/api/control/commands/run",
        json={
            "command": "workspace.panel.state.get",
            "target": {"workspace_id": WORKSPACE_ID, "panel_id": PANEL_ID},
            "args": {},
        },
        headers={"Authorization": "Bearer secret-token"},
    )
    assert state_response.status_code == 200
    assert state_response.json()["result"]["state"]["notes"] == PANEL_NOTES

    media_response = client.get(f"/api/samples/{sample_ids[0]}/content")
    assert media_response.status_code == 200
    assert media_response.content.startswith(b"\x89PNG")
    # The bundle stores media under the sample id with no extension, so the
    # type has to come from the sample rather than from the path.
    assert media_response.headers["content-type"] == "image/png"

    thumbnail_response = client.get(f"/api/samples/{sample_ids[0]}/thumbnail")
    assert thumbnail_response.status_code == 200
    assert thumbnail_response.headers["content-type"] == "image/jpeg"


def test_public_serving_allows_viewer_commands_and_refuses_privileged_ones(
    tmp_path: Path, fresh_datasets_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir, _snapshot, _sample_ids, _layout_key = _export(tmp_path)
    runtime, _result = restore_bundle(out_dir)

    # `hyperview serve --public` sets exactly this.
    monkeypatch.setenv("HYPERVIEW_NO_AUTH", "1")
    client = TestClient(create_app(runtime=runtime))

    viewer = client.post(
        "/api/control/commands/run",
        json={
            "command": "workspace.panel.state.patch",
            "target": {"workspace_id": WORKSPACE_ID, "panel_id": PANEL_ID},
            "args": {"state": {"notes": "viewer edit"}},
        },
    )
    assert viewer.status_code == 200
    assert viewer.json()["ok"] is True

    privileged = client.post(
        "/api/control/commands/run",
        json={
            "command": "embeddings.compute",
            "target": {"workspace_id": WORKSPACE_ID},
            "args": {"model_id": "test/roundtrip-model"},
        },
    )
    assert privileged.status_code == 403


def test_serve_from_flag_reaches_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    from hyperview.cli import _build_control_parser

    args = _build_control_parser().parse_args(
        ["serve", "--from", "dist/research", "--public", "--port", "6363"]
    )

    assert args.from_bundle == "dist/research"
    assert args.public is True
    assert args.port == 6363
    assert args.workspace_id is None
    assert os.environ.get("HYPERVIEW_NO_AUTH") != "1"


def test_export_from_a_runtime_that_installed_nothing_still_carries_extensions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`hyperview export` builds a bare runtime and reads the persisted workspace.

    Nothing is installed in that process, so the extension folders have to be
    found through the panels' persisted module paths instead. This walks the
    real CLI shape: a persisted dataset, an export by a runtime that installed
    nothing, and a restore into a different datasets directory.
    """

    source_datasets = tmp_path / "source-home" / "datasets"
    source_datasets.mkdir(parents=True)
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(source_datasets))
    monkeypatch.setenv("HYPERVIEW_MEDIA_DIR", str(tmp_path / "source-home" / "media"))

    _runtime, sample_ids, layout_key = _source_runtime(tmp_path, persist=True)

    # A second runtime over the same persisted registry, with no installs.
    bare = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "bare-providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "source-workspaces.json"),
    )
    assert bare.list_extensions() == []

    out_dir = tmp_path / "bare-bundle"
    result = export_runtime_workspace(bare, WORKSPACE_ID, out_dir)
    assert result.warnings == ()
    assert result.num_samples == len(sample_ids)

    manifest = json.loads((out_dir / "hyperview-static.json").read_text(encoding="utf-8"))
    assert [item["name"] for item in manifest["restore"]["extensions"]] == ["reference"]
    assert (out_dir / "extensions" / "reference" / "extension.toml").is_file()

    restored_datasets = tmp_path / "restored-home" / "datasets"
    restored_datasets.mkdir(parents=True)
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(restored_datasets))
    monkeypatch.setenv("HYPERVIEW_MEDIA_DIR", str(tmp_path / "restored-home" / "media"))

    restored_runtime, restored = restore_bundle(out_dir)

    assert restored.warnings == ()
    workspace = restored_runtime.get_workspace(WORKSPACE_ID)
    assert [panel.id for panel in workspace.ui.custom_panels] == [PANEL_ID]
    assert workspace.ui.active_layout_key == layout_key
    dataset = restored_runtime.get_dataset(WORKSPACE_ID)
    assert sorted(sample.id for sample in dataset.samples) == sorted(sample_ids)
    assert restored_runtime.get_panel_state(WORKSPACE_ID, PANEL_ID)["state"]["notes"] == (
        PANEL_NOTES
    )


def test_export_warns_when_a_panel_extension_is_not_on_this_host(tmp_path: Path) -> None:
    dataset, sample_ids, layout_key = _source_dataset(tmp_path / "source-media")
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "orphan-providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "orphan-workspaces.json"),
    )
    runtime.attach_dataset_instance(WORKSPACE_ID, dataset, activate_workspace=True)
    runtime.set_active_layout(WORKSPACE_ID, layout_key)
    # A workspace persisted on another machine: the panel names an extension
    # whose folder does not exist here. The export has to say so, because the
    # Live Space will open without that panel.
    runtime.add_custom_panel(
        WORKSPACE_ID,
        CustomPanelSpec(
            id="orphan",
            title="Orphan",
            panel_type="elsewhere.orphan",
            extension="elsewhere",
            extension_panel="orphan",
            module_file=str(tmp_path / "not-here" / "panel.jsx"),
        ),
    )

    result = export_runtime_workspace(runtime, WORKSPACE_ID, tmp_path / "orphan-bundle")

    assert any(
        "will be missing when the bundle runs as a Live Space" in item
        for item in result.warnings
    )
    assert not (tmp_path / "orphan-bundle" / "extensions").exists()
    assert len(sample_ids) == 4


def test_restore_rejects_a_bundle_without_restore_data(tmp_path: Path) -> None:
    out_dir, _snapshot, _sample_ids, _layout_key = _export(tmp_path)
    manifest_path = out_dir / "hyperview-static.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["restore"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="Static Space"):
        restore_bundle(out_dir)
