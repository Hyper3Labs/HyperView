"""The public composition API a launch script writes against.

These tests cover the pieces a demo needs to wire a workspace without reaching
around the API: naming a collection, finding a layout key that only exists
after the layout is computed, placing any registered panel type, declaring a
panel's opening state, and registering extensions in time for the view that
places their panels.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

import hyperview as hv
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime
from hyperview.storage.schema import make_layout_key


def _make_dataset(name: str = "panel_api") -> hv.Dataset:
    dataset = hv.Dataset(name, persist=False)
    dataset.add_samples(
        [
            Sample(
                id=f"sample-{index}",
                filepath=f"/virtual/sample-{index}.png",
                label="cat" if index % 2 == 0 else "dog",
            )
            for index in range(6)
        ]
    )
    return dataset


def _make_session(dataset: hv.Dataset | None = None) -> tuple[hv.Session, HyperViewRuntime, str]:
    workspace_id = f"panel-api-{uuid4().hex}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(
        workspace_id,
        dataset if dataset is not None else _make_dataset(),
        activate_workspace=True,
    )
    return hv.Session(runtime, "127.0.0.1", 6262), runtime, workspace_id


def _write_extension(root: Path, name: str, *, panel_type: str | None = None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    panel_type_line = f'panel_type = "{panel_type}"\n' if panel_type else ""
    (folder / "extension.toml").write_text(
        f'name = "{name}"\n'
        "\n"
        "[[panels]]\n"
        'id = "readout"\n'
        'title = "Readout"\n'
        'position = "right"\n'
        'file = "panel.jsx"\n'
        f"{panel_type_line}",
        encoding="utf-8",
    )
    (folder / "panel.jsx").write_text("export default function Panel() { return null; }\n")
    return folder


# --- Collections -----------------------------------------------------------


def test_create_collection_returns_an_id_bound_to_the_requested_order() -> None:
    session, runtime, workspace_id = _make_session()

    collection_id = session.create_collection(
        ["sample-3", "sample-1", "sample-3"],
        name="Top matches",
        workspace_id=workspace_id,
    )

    stored = runtime.get_workspace(workspace_id).collections[collection_id]
    assert stored.kind == "selection"
    assert stored.query["ids"] == ["sample-3", "sample-1"]
    assert stored.query["source"] == "Top matches"


def test_create_collection_does_not_disturb_the_samples_panel() -> None:
    session, runtime, workspace_id = _make_session()
    session.ui.apply_view(hv.ui.View(hv.ui.Samples()), workspace_id=workspace_id)
    before = session.ui.get_panel_state("samples", workspace_id=workspace_id)

    session.create_collection(["sample-0"], workspace_id=workspace_id)

    assert session.ui.get_panel_state("samples", workspace_id=workspace_id) == before


def test_create_collection_names_samples_the_dataset_does_not_have() -> None:
    session, _runtime, workspace_id = _make_session()

    with pytest.raises(KeyError, match="sample-99"):
        session.create_collection(["sample-0", "sample-99"], workspace_id=workspace_id)


def test_create_collection_rejects_an_empty_set() -> None:
    session, _runtime, workspace_id = _make_session()

    with pytest.raises(ValueError, match="at least one sample id"):
        session.create_collection([], workspace_id=workspace_id)


def test_list_collections_reports_what_the_workspace_stores() -> None:
    session, _runtime, workspace_id = _make_session()

    first = session.create_collection(["sample-0"], name="First", workspace_id=workspace_id)
    second = session.create_collection(["sample-1"], name="Second", workspace_id=workspace_id)

    listed = {
        collection["id"]: collection
        for collection in session.list_collections(workspace_id=workspace_id)
    }
    assert {first, second} <= set(listed)
    assert listed[first]["query"]["source"] == "First"


def test_created_collections_survive_static_export_when_a_view_binds_them(
    tmp_path: Path,
) -> None:
    session, _runtime, workspace_id = _make_session()
    bound = session.create_collection(
        ["sample-4", "sample-2"],
        name="Bound",
        workspace_id=workspace_id,
    )
    session.create_collection(["sample-0"], name="Unreferenced", workspace_id=workspace_id)
    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(mode="results", collection_id=bound)),
        workspace_id=workspace_id,
    )

    session.export(tmp_path / "bundle", workspace_id=workspace_id)

    exported = tmp_path / "bundle" / "api" / "collections" / bound / "items.json"
    assert exported.exists()
    items = [item["sample_id"] for item in _read_json(exported)["items"]]
    assert items == ["sample-4", "sample-2"]
    kept = {
        collection["id"]
        for collection in _read_json(tmp_path / "bundle" / "api" / "runtime.json")["workspace"][
            "collections"
        ]
    }
    assert bound in kept


def test_a_samples_panel_opens_on_its_authored_collection_whatever_its_id() -> None:
    session, runtime, workspace_id = _make_session()
    first = session.create_collection(["sample-4", "sample-2"], name="A", workspace_id=workspace_id)
    second = session.create_collection(["sample-1"], name="B", workspace_id=workspace_id)

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.Samples(id="samples", mode="results", collection_id=first),
            hv.ui.Samples(id="baseline", mode="results", collection_id=second),
            hv.ui.Samples(id="everything"),
        ),
        workspace_id=workspace_id,
    )

    panels = runtime.get_workspace(workspace_id).ui.panels
    # The default Samples panel used to be seeded with the all-samples collection
    # regardless of the view, so a Static Space opened on the whole dataset.
    assert panels["samples"].state["collection_id"] == first
    assert panels["samples"].state["collection"]["id"] == first
    assert panels["baseline"].state["collection_id"] == second
    assert panels["everything"].state["collection"]["kind"] == "all"


def test_reauthoring_the_samples_collection_moves_a_persisted_panel() -> None:
    session, runtime, workspace_id = _make_session()
    first = session.create_collection(["sample-4", "sample-2"], name="A", workspace_id=workspace_id)
    second = session.create_collection(["sample-1"], name="B", workspace_id=workspace_id)

    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(id="samples", mode="results", collection_id=first)),
        workspace_id=workspace_id,
    )
    # A visitor navigates elsewhere; re-applying the same view must not undo that.
    runtime.patch_panel_state(
        workspace_id,
        "samples",
        _samples_state_for(runtime, workspace_id, second),
    )
    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(id="samples", mode="results", collection_id=first)),
        workspace_id=workspace_id,
    )
    assert runtime.get_workspace(workspace_id).ui.panels["samples"].state["collection_id"] == second

    # The author changing the collection is a new statement, and it wins.
    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(id="samples", mode="results", collection_id=second)),
        workspace_id=workspace_id,
    )
    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(id="samples", mode="results", collection_id=first)),
        workspace_id=workspace_id,
    )
    state = runtime.get_workspace(workspace_id).ui.panels["samples"].state
    assert state["collection_id"] == first
    assert state["collection"]["id"] == first


def _samples_state_for(runtime, workspace_id: str, collection_id: str) -> dict:
    collection = runtime.get_workspace(workspace_id).collections[collection_id]
    return {"collection_id": collection.id, "collection": collection.to_dict()}


def test_an_unknown_authored_collection_falls_back_to_every_sample() -> None:
    session, runtime, workspace_id = _make_session()

    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(id="samples", collection_id="selection:missing")),
        workspace_id=workspace_id,
    )

    state = runtime.get_workspace(workspace_id).ui.panels["samples"].state
    assert state["collection"]["kind"] == "all"


def _read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


# --- Layout lookup ---------------------------------------------------------


def _add_layout(
    dataset: hv.Dataset,
    *,
    model_id: str,
    provider: str,
    geometry: str,
    method: str = "umap",
    layout_dimension: int = 2,
    modality: str = "image",
    space_key: str | None = None,
) -> str:
    space = dataset._storage.ensure_space(
        model_id,
        dim=8,
        config={"provider": provider, "geometry": geometry, "modality": modality},
        space_key=space_key,
    )
    layout_key = make_layout_key(
        space.space_key,
        method=method,
        geometry=geometry,
        layout_dimension=layout_dimension,
    )
    dataset._storage.ensure_layout(
        layout_key=layout_key,
        space_key=space.space_key,
        method=method,
        geometry=geometry,
        params={"n_neighbors": 15},
    )
    dataset._storage.add_layout_coords(
        layout_key,
        [sample.id for sample in dataset.samples],
        np.zeros((len(dataset.samples), layout_dimension), dtype=np.float32),
    )
    return layout_key


def test_list_layouts_describes_what_produced_each_layout() -> None:
    dataset = _make_dataset(f"layouts_{uuid4().hex}")
    layout_key = _add_layout(
        dataset,
        model_id="hycoclip-vit-s",
        provider="hyper-models",
        geometry="poincare",
    )

    record = next(item for item in dataset.list_layouts() if item.key == layout_key)

    assert record.model_id == "hycoclip-vit-s"
    assert record.provider == "hyper-models"
    assert record.geometry == "poincare"
    assert record.dimension == 2
    assert record.method == "umap"
    assert record.modality == "image"
    assert record.params == {"n_neighbors": 15}
    assert record.sample_count == 6
    assert record.space_id == record.space_key
    # The legacy field names keep working for callers that already use them.
    assert record.layout_key == record.key
    assert record.count == record.sample_count


def test_find_layout_matches_the_description_instead_of_a_pinned_key() -> None:
    dataset = _make_dataset(f"find_layout_{uuid4().hex}")
    poincare = _add_layout(
        dataset,
        model_id="hycoclip-vit-s",
        provider="hyper-models",
        geometry="poincare",
    )
    euclidean = _add_layout(
        dataset,
        model_id="openai/clip-vit-base-patch32",
        provider="embed-anything",
        geometry="euclidean",
    )

    assert dataset.find_layout(model="hycoclip-vit-s") == poincare
    assert dataset.find_layout(geometry="euclidean") == euclidean
    assert dataset.find_layout(provider="hyper-models", dimension=2) == poincare
    assert dataset.find_layout(method="umap", geometry="poincare") == poincare


def test_find_layout_separates_two_spaces_of_one_model_by_modality() -> None:
    dataset = _make_dataset(f"find_layout_modality_{uuid4().hex}")
    image_only = _add_layout(
        dataset,
        model_id="hyper3-clip-v0.5",
        provider="hyper-models",
        geometry="poincare",
        modality="image",
        space_key="hyper3-clip-v0_5__image",
    )
    multimodal = _add_layout(
        dataset,
        model_id="hyper3-clip-v0.5",
        provider="hyper-models",
        geometry="poincare",
        modality="multimodal",
        space_key="hyper3-clip-v0_5__multimodal",
    )
    assert image_only != multimodal

    assert dataset.find_layout(model="hyper3-clip-v0.5", modality="image") == image_only
    assert dataset.find_layout(model="hyper3-clip-v0.5", modality="multimodal") == multimodal

    # Without the modality the two are indistinguishable, and the error says so.
    with pytest.raises(ValueError) as error:
        dataset.find_layout(model="hyper3-clip-v0.5", geometry="poincare")
    assert "modality=image" in str(error.value)
    assert "modality=multimodal" in str(error.value)


def test_find_layout_returns_none_when_nothing_matches() -> None:
    dataset = _make_dataset(f"find_layout_none_{uuid4().hex}")
    _add_layout(dataset, model_id="a", provider="p", geometry="euclidean")

    assert dataset.find_layout(geometry="spherical") is None
    assert dataset.find_layout(model="not-a-model") is None


def test_find_layout_lists_the_candidates_when_the_description_is_ambiguous() -> None:
    dataset = _make_dataset(f"find_layout_many_{uuid4().hex}")
    _add_layout(dataset, model_id="model-a", provider="p", geometry="euclidean")
    _add_layout(dataset, model_id="model-b", provider="p", geometry="euclidean")

    with pytest.raises(ValueError) as error:
        dataset.find_layout(geometry="euclidean")

    message = str(error.value)
    assert "matched 2 layouts" in message
    assert "model=model-a" in message
    assert "model=model-b" in message


# --- The generic Panel primitive -------------------------------------------


def test_panel_places_any_registered_panel_type() -> None:
    session, runtime, workspace_id = _make_session()

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.Panel("explorer", id="labels", position="right"),
            hv.ui.Panel("samples", id="rows", title="Rows", position="center"),
        ),
        workspace_id=workspace_id,
    )

    panels = runtime.get_workspace(workspace_id).ui.custom_panels
    assert [(panel.id, panel.resolved_panel_type()) for panel in panels] == [
        ("labels", "explorer"),
        ("rows", "samples"),
    ]
    assert panels[1].title == "Rows"


def test_panel_can_pin_a_scatter_to_a_layout() -> None:
    session, runtime, workspace_id = _make_session()

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.Panel(
                "scatter",
                id="map",
                title="Map",
                layout_key="space__umap__2d",
                geometry="poincare",
                layout_dimension=2,
            )
        ),
        workspace_id=workspace_id,
    )

    panel = runtime.get_workspace(workspace_id).ui.custom_panels[0]
    assert panel.layout_key == "space__umap__2d"
    assert panel.geometry == "poincare"
    assert panel.builtin_panel == "scatter"


def test_sugar_classes_are_panels_with_a_fixed_panel_type() -> None:
    assert hv.ui.Samples(id="s").panel_type == "samples"
    assert hv.ui.Scatter(id="m", title="M", layout_key="k").panel_type == "scatter"
    assert hv.ui.Explorer(id="e").panel_type == "explorer"
    assert hv.ui.ExtensionPanel(id="r", extension="x", panel="y").panel_type == "x.y"
    assert isinstance(hv.ui.Samples(id="s"), hv.ui.Panel)


def test_apply_view_names_an_unknown_panel_type_and_what_is_registered() -> None:
    session, runtime, workspace_id = _make_session()

    with pytest.raises(ValueError) as error:
        session.ui.apply_view(
            hv.ui.View(hv.ui.Panel("sampels", id="typo")),
            workspace_id=workspace_id,
        )

    message = str(error.value)
    assert "'sampels'" in message
    assert "'typo'" in message
    assert "samples" in message and "scatter" in message and "explorer" in message
    assert runtime.get_workspace(workspace_id).ui.custom_panels == []


def test_apply_view_names_an_extension_panel_whose_extension_is_not_registered() -> None:
    session, _runtime, workspace_id = _make_session()

    with pytest.raises(ValueError, match="extension 'missing' panel 'readout'"):
        session.ui.apply_view(
            hv.ui.View(hv.ui.ExtensionPanel(id="readout", extension="missing", panel="readout")),
            workspace_id=workspace_id,
        )


def test_extension_panel_resolves_a_manifest_declared_panel_type(tmp_path: Path) -> None:
    session, runtime, workspace_id = _make_session()
    folder = _write_extension(tmp_path, "renamed", panel_type="vendor.readout")
    session.ui.add_extension(folder, workspace_id=workspace_id)

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.ExtensionPanel(id="by-id", extension="renamed", panel="readout"),
            hv.ui.Panel("vendor.readout", id="by-type"),
        ),
        workspace_id=workspace_id,
    )

    panels = runtime.get_workspace(workspace_id).ui.custom_panels
    assert [panel.resolved_panel_type() for panel in panels] == [
        "vendor.readout",
        "vendor.readout",
    ]
    assert all(panel.extension == "renamed" for panel in panels)


# --- Opening panel state ---------------------------------------------------


def test_panel_state_is_applied_when_the_view_is_applied(tmp_path: Path) -> None:
    session, _runtime, workspace_id = _make_session()
    folder = _write_extension(tmp_path, "readout")
    session.ui.add_extension(folder, workspace_id=workspace_id)

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.ExtensionPanel(
                id="readout",
                extension="readout",
                panel="readout",
                state={"activeCaseId": "facilities"},
            )
        ),
        workspace_id=workspace_id,
    )

    state = session.ui.get_panel_state("readout", workspace_id=workspace_id)
    assert state["state"] == {"activeCaseId": "facilities"}


def test_panel_state_wins_over_what_a_previous_run_left_behind(tmp_path: Path) -> None:
    session, _runtime, workspace_id = _make_session()
    folder = _write_extension(tmp_path, "readout")
    session.ui.add_extension(folder, workspace_id=workspace_id)
    view = hv.ui.View(
        hv.ui.ExtensionPanel(
            id="readout",
            extension="readout",
            panel="readout",
            state={"activeCaseId": "facilities"},
        )
    )
    session.ui.apply_view(view, workspace_id=workspace_id)
    session.ui.patch_panel_state(
        "readout",
        {"activeCaseId": "logistics", "scrolled": True},
        workspace_id=workspace_id,
    )

    session.ui.apply_view(view, workspace_id=workspace_id)

    state = session.ui.get_panel_state("readout", workspace_id=workspace_id)
    assert state["state"] == {"activeCaseId": "facilities"}


def test_reapplying_identical_state_is_not_an_edit(tmp_path: Path) -> None:
    session, runtime, workspace_id = _make_session()
    folder = _write_extension(tmp_path, "readout")
    session.ui.add_extension(folder, workspace_id=workspace_id)
    view = hv.ui.View(
        hv.ui.ExtensionPanel(
            id="readout",
            extension="readout",
            panel="readout",
            state={"activeCaseId": "facilities"},
        )
    )
    session.ui.apply_view(view, workspace_id=workspace_id)
    revision = runtime.get_workspace(workspace_id).ui.view_revision

    session.ui.apply_view(view, workspace_id=workspace_id)

    assert runtime.get_workspace(workspace_id).ui.view_revision == revision
    assert (
        session.ui.get_panel_state("readout", workspace_id=workspace_id)["state_revision"] == 0
    )


def test_samples_panel_state_keeps_the_runtime_seeded_collection() -> None:
    session, _runtime, workspace_id = _make_session()

    session.ui.apply_view(
        hv.ui.View(hv.ui.Samples(id="samples", state={"grid_size": "large"})),
        workspace_id=workspace_id,
    )

    state = session.ui.get_panel_state("samples", workspace_id=workspace_id)["state"]
    assert state["grid_size"] == "large"
    assert state["collection_id"]


# --- Typed props -----------------------------------------------------------


def test_samples_keyword_props_map_onto_the_documented_prop_names() -> None:
    panel = hv.ui.Samples(
        id="results",
        mode="results",
        collection_id="selection:abc",
        anchor_sample_id="sample-0",
        label_field="product_name",
        show_text_search=True,
        rank={"anchor_sample_id": "sample-0", "layout_key": "k", "k": 6, "show_distance": False},
    )

    assert panel.props == {
        "mode": "results",
        "collectionId": "selection:abc",
        "anchorSampleId": "sample-0",
        "labelField": "product_name",
        "showTextSearch": True,
        "rank": {
            "anchorSampleId": "sample-0",
            "layoutKey": "k",
            "k": 6,
            "showDistance": False,
        },
    }


def test_scatter_keyword_props_map_onto_the_documented_prop_names() -> None:
    panel = hv.ui.Scatter(id="map", title="Map", layout_key="k", preset="poincare-2d")

    assert panel.props == {"preset": "poincare-2d"}


def test_props_schema_rejects_a_misspelled_mode() -> None:
    session, _runtime, workspace_id = _make_session()

    with pytest.raises(ValueError, match="props.mode must be one of"):
        session.ui.apply_view(
            hv.ui.View(hv.ui.Samples(id="results", props={"mode": "reslts"})),
            workspace_id=workspace_id,
        )


def test_props_schema_rejects_a_documented_prop_with_the_wrong_type() -> None:
    session, _runtime, workspace_id = _make_session()

    with pytest.raises(ValueError, match="props.showTextSearch must match schema type"):
        session.ui.apply_view(
            hv.ui.View(hv.ui.Samples(id="results", props={"showTextSearch": "yes"})),
            workspace_id=workspace_id,
        )


def test_props_schema_still_lets_unknown_props_through() -> None:
    session, runtime, workspace_id = _make_session()

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.Samples(
                id="results",
                mode="results",
                props={"demoCaseId": "facilities", "experimentalDensity": 3},
            )
        ),
        workspace_id=workspace_id,
    )

    props = runtime.get_workspace(workspace_id).ui.custom_panels[0].props
    assert props["demoCaseId"] == "facilities"
    assert props["experimentalDensity"] == 3
    assert props["mode"] == "results"


# --- Extension registration ------------------------------------------------


def test_apply_view_installs_the_extensions_it_is_given(tmp_path: Path) -> None:
    session, runtime, workspace_id = _make_session()
    folder = _write_extension(tmp_path, "readout")

    session.ui.apply_view(
        hv.ui.View(hv.ui.ExtensionPanel(id="readout", extension="readout", panel="readout")),
        workspace_id=workspace_id,
        extensions=[folder],
    )

    assert runtime.get_extension("readout") is not None
    assert runtime.get_workspace(workspace_id).ui.custom_panels[0].extension == "readout"


def test_apply_view_installs_shipped_extensions_by_name() -> None:
    session, runtime, workspace_id = _make_session()

    session.ui.apply_view(
        hv.ui.View(hv.ui.Panel("hyperview.reference", id="reference")),
        workspace_id=workspace_id,
        extensions=["reference"],
    )

    assert runtime.get_extension("reference") is not None
    assert runtime.get_workspace(workspace_id).ui.custom_panels[0].extension == "reference"


def test_apply_view_reports_an_extension_folder_that_is_not_there(tmp_path: Path) -> None:
    session, _runtime, workspace_id = _make_session()

    with pytest.raises(FileNotFoundError, match="Extension folder not found"):
        session.ui.apply_view(
            hv.ui.View(hv.ui.Samples()),
            workspace_id=workspace_id,
            extensions=[tmp_path / "not-there"],
        )


def test_launch_signature_accepts_extensions() -> None:
    import inspect

    parameters = inspect.signature(hv.launch).parameters
    assert "extensions" in parameters
    assert parameters["extensions"].default is None
