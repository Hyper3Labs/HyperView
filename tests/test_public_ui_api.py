from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

import hyperview as hv
import hyperview.api as hv_api
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime
from hyperview.server.app import create_app


def _make_dataset() -> hv.Dataset:
    dataset = hv.Dataset("public_ui_api", persist=False)
    for index in range(6):
        dataset.add_sample(
            Sample(
                id=f"sample-{index}",
                filepath=f"/virtual/sample-{index}.png",
                label="cat" if index % 2 == 0 else "dog",
                metadata={"department": "home" if index < 3 else "outdoor"},
            )
        )
    return dataset


def test_public_ui_view_applies_runtime_panel_composition(tmp_path: Path) -> None:
    extension_dir = tmp_path / ".hyperview" / "extensions" / "readout"
    extension_dir.mkdir(parents=True)
    (extension_dir / "extension.toml").write_text(
        """
name = "readout"

[[panels]]
id = "summary"
title = "Readout"
position = "right"
file = "panel.js"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (extension_dir / "panel.js").write_text("export default function Panel() { return null; }\n")

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)
    session.ui.add_extension(extension_dir, workspace_id="demo")

    view = hv.ui.View(
        hv.ui.Horizontal(
            hv.ui.Scatter(
                id="clip-map",
                title="CLIP",
                layout_key="clip-layout",
                geometry="euclidean",
                layout_dimension=2,
            ),
            hv.ui.Scatter(
                id="hycoclip-map",
                title="HyCoCLIP",
                layout_key="hycoclip-layout",
                geometry="poincare",
                layout_dimension=2,
            ),
        ),
        hv.ui.ExtensionPanel(
            id="readout",
            extension="readout",
            panel="summary",
            position="right",
            layout=hv.ui.PanelLayout(width=340, min_width=280, max_width=520),
            props={"metric_set": "pilot"},
        ),
        active_panel="readout",
    )

    session.ui.apply_view(view, workspace_id="demo")

    workspace = runtime.get_workspace("demo")
    panels = workspace.ui.custom_panels
    assert [panel.id for panel in panels] == ["clip-map", "hycoclip-map", "readout"]
    assert panels[0].position == "center"
    assert panels[1].reference_panel_id == "clip-map"
    assert panels[1].direction == "right"
    assert panels[2].position == "right"
    assert panels[2].width == 340
    assert panels[2].min_width == 280
    assert panels[2].max_width == 520
    assert panels[2].extension == "readout"
    assert panels[2].extension_panel == "summary"
    assert panels[2].props == {"metric_set": "pilot"}
    assert workspace.ui.has_explicit_view is True
    assert workspace.ui.active_panel_id == "readout"
    assert workspace.ui.view_revision > 0


def test_public_ui_reapplying_same_view_does_not_bump_revision() -> None:
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    view = hv.ui.View(
        hv.ui.Scatter(
            id="clip-map",
            title="CLIP",
            layout_key="clip-layout",
            geometry="euclidean",
            layout_dimension=2,
        )
    )

    session.ui.apply_view(view, workspace_id="demo")
    first_revision = runtime.get_workspace("demo").ui.view_revision
    assert runtime.get_workspace("demo").ui.has_explicit_view is True

    session.ui.apply_view(view, workspace_id="demo")
    assert runtime.get_workspace("demo").ui.view_revision == first_revision

    changed_view = hv.ui.View(
        hv.ui.Scatter(
            id="clip-map",
            title="CLIP",
            layout_key="clip-layout",
            geometry="euclidean",
            layout_dimension=2,
            props={"demo": "updated"},
        )
    )

    session.ui.apply_view(changed_view, workspace_id="demo")
    assert runtime.get_workspace("demo").ui.view_revision == first_revision + 1


def test_public_ui_view_can_place_builtin_samples_panel() -> None:
    workspace_id = f"samples-view-{uuid4().hex}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    view = hv.ui.View(
        hv.ui.Horizontal(
            hv.ui.Scatter(
                id="map",
                title="Map",
                layout_key="layout-a",
                geometry="euclidean",
                layout_dimension=2,
            ),
            hv.ui.Samples(id="samples", title="Samples"),
        )
    )

    session.ui.apply_view(view, workspace_id=workspace_id)

    workspace = runtime.get_workspace(workspace_id)
    panels = workspace.ui.custom_panels
    assert [panel.id for panel in panels] == ["map", "samples"]
    assert panels[1].kind == "builtin"
    assert panels[1].builtin_panel == "samples"
    assert panels[1].reference_panel_id == "map"
    assert panels[1].direction == "right"

    snapshot = runtime.snapshot(workspace_id)
    samples_panel = snapshot["workspace"]["ui"]["custom_panels"][1]
    assert samples_panel["kind"] == "builtin"
    assert samples_panel["builtin_panel"] == "samples"
    assert samples_panel["data"]["module_src"] is None


def test_public_ui_view_rejects_duplicate_panel_ids() -> None:
    workspace_id = f"duplicate-view-{uuid4().hex}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    with pytest.raises(ValueError, match="Duplicate panel id"):
        session.ui.apply_view(
            hv.ui.View(hv.ui.Samples(), hv.ui.Samples()),
            workspace_id=workspace_id,
        )

    assert runtime.get_workspace(workspace_id).ui.custom_panels == []


def test_public_ui_empty_view_is_explicit() -> None:
    workspace_id = f"empty-view-{uuid4().hex}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    session.ui.apply_view(hv.ui.View(), workspace_id=workspace_id)

    workspace = runtime.get_workspace(workspace_id)
    assert workspace.ui.custom_panels == []
    assert workspace.ui.has_explicit_view is True
    assert workspace.ui.view_revision == 1


def test_public_ui_incremental_panel_does_not_create_explicit_view() -> None:
    workspace_id = f"incremental-panel-{uuid4().hex}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    session.ui.add_scatter(
        panel_id="extra-map",
        title="Extra Map",
        layout_key="layout-a",
        workspace_id=workspace_id,
    )

    workspace = runtime.get_workspace(workspace_id)
    assert [panel.id for panel in workspace.ui.custom_panels] == ["extra-map"]
    assert workspace.ui.has_explicit_view is False


def test_public_ui_panel_layout_helpers_update_runtime_view_state() -> None:
    workspace_id = f"panel-layout-{uuid4().hex}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    session.ui.add_scatter(
        panel_id="map",
        title="Map",
        layout_key="layout-a",
        workspace_id=workspace_id,
        geometry="euclidean",
        layout_dimension=2,
        layout=hv.ui.PanelLayout(width=500, height=360, min_width=240),
    )

    panel = runtime.get_workspace(workspace_id).ui.custom_panels[0]
    assert panel.width == 500
    assert panel.height == 360
    assert panel.min_width == 240

    session.ui.resize_panel(
        "map",
        workspace_id=workspace_id,
        width=620,
        min_height=220,
        max_width=900,
    )
    session.ui.move_panel(
        "map",
        workspace_id=workspace_id,
        position="right",
        reference_panel_id=None,
        direction=None,
    )
    session.ui.focus_panel("map", workspace_id=workspace_id)
    session.ui.close_panel("map", workspace_id=workspace_id)

    workspace = runtime.get_workspace(workspace_id)
    panel = workspace.ui.custom_panels[0]
    assert panel.width == 620
    assert panel.height == 360
    assert panel.min_width == 240
    assert panel.min_height == 220
    assert panel.max_width == 900
    assert panel.position == "right"
    assert panel.reference_panel_id is None
    assert panel.direction is None
    assert panel.visible is False
    assert workspace.ui.active_panel_id is None

    session.ui.show_panel("map", workspace_id=workspace_id)
    session.ui.focus_panel("map", workspace_id=workspace_id)
    workspace = runtime.get_workspace(workspace_id)
    assert workspace.ui.custom_panels[0].visible is True
    assert workspace.ui.active_panel_id == "map"


def test_public_ui_extension_panel_resolves_installed_extension(tmp_path: Path) -> None:
    workspace_id = f"extension-demo-{uuid4().hex}"
    extension_dir = tmp_path / ".hyperview" / "extensions" / "readout"
    extension_dir.mkdir(parents=True)
    (extension_dir / "extension.toml").write_text(
        """
name = "readout"
description = "Demo readout"

[[panels]]
id = "summary"
title = "Summary"
position = "right"
file = "panel.js"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    panel_file = extension_dir / "panel.js"
    panel_file.write_text("export default function Panel() { return null; }\n")

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    installation = session.ui.add_extension(extension_dir, workspace_id=workspace_id)
    assert installation.manifest.name == "readout"
    assert runtime.get_workspace(workspace_id).ui.custom_panels == []

    session.ui.apply_view(
        hv.ui.View(
            hv.ui.ExtensionPanel(
                id="summary-instance",
                extension="readout",
                panel="summary",
                props={"mode": "compact"},
            ),
        ),
        workspace_id=workspace_id,
    )

    panels = runtime.get_workspace(workspace_id).ui.custom_panels
    assert len(panels) == 1
    assert panels[0].id == "summary-instance"
    assert panels[0].title == "Summary"
    assert panels[0].extension == "readout"
    assert panels[0].extension_panel == "summary"
    assert panels[0].module_file == str(panel_file.resolve())
    assert panels[0].props == {"mode": "compact"}


def test_public_ui_add_panels_preserves_extension_identity(tmp_path: Path) -> None:
    workspace_id = f"add-panels-{uuid4().hex}"
    extension_dir = tmp_path / ".hyperview" / "extensions" / "readout"
    extension_dir.mkdir(parents=True)
    (extension_dir / "extension.toml").write_text(
        """
name = "readout"

[[panels]]
id = "summary"
title = "Summary"
position = "right"
file = "panel.js"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (extension_dir / "panel.js").write_text("export default function Panel() { return null; }\n")

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)

    runtime.install_extension(workspace_id, extension_dir, add_panels=True)

    panels = runtime.get_workspace(workspace_id).ui.custom_panels
    assert len(panels) == 1
    assert panels[0].extension == "readout"
    assert panels[0].extension_panel == "summary"


def test_public_ui_show_similar_resolves_layout_context() -> None:
    dataset = _make_dataset()
    sample_ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        sample_ids,
        np.asarray([[float(index), 0.0] for index, _ in enumerate(sample_ids)]),
    )
    space_key = dataset.list_layouts()[0].space_key

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", dataset, activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    session.ui.show_similar(
        "sample-2",
        workspace_id="demo",
        layout_key=layout_key,
        k=200,
        source="test",
    )

    workspace = runtime.get_workspace("demo")
    assert workspace.ui.selected_ids == []
    assert workspace.ui.similarity_query is not None
    assert workspace.ui.similarity_query.to_dict() == {
        "anchor_sample_id": "sample-2",
        "layout_key": layout_key,
        "space_key": space_key,
        "k": 100,
        "source": "test",
    }


def test_public_ui_state_helpers_update_workspace() -> None:
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262)

    session.ui.set_active_layout("layout-a", workspace_id="demo")
    session.ui.set_selection(["sample-1", "sample-3"], workspace_id="demo")

    workspace = runtime.get_workspace("demo")
    assert workspace.ui.active_layout_key == "layout-a"
    assert workspace.ui.selected_ids == ["sample-1", "sample-3"]


def test_reused_launch_rejects_launch_view(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset = _make_dataset()

    monkeypatch.setattr(hv_api, "_can_connect", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        hv_api,
        "_try_read_health",
        lambda *args, **kwargs: hv_api._HealthResponse(
            name="hyperview",
            session_id="existing",
            workspace_id="default",
            dataset=dataset.name,
            pid=None,
        ),
    )

    with pytest.raises(RuntimeError, match="Cannot apply a launch view"):
        hv.launch(
            dataset,
            reuse_server=True,
            view=hv.ui.View(),
            notebook=False,
            open_browser=False,
            block=False,
        )


def test_reused_session_ui_control_fails_explicitly() -> None:
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", _make_dataset(), activate_workspace=True)
    session = hv.Session(runtime, "127.0.0.1", 6262, controls_runtime=False)

    with pytest.raises(RuntimeError, match="attached to an existing HyperView server"):
        session.ui.set_selection(["sample-1"], workspace_id="demo")


def test_samples_query_and_aggregate_endpoints() -> None:
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", _make_dataset(), activate_workspace=True)
    client = TestClient(create_app(runtime=runtime))

    query_response = client.post(
        "/api/samples/query",
        json={
            "workspace_id": "demo",
            "labels": ["cat"],
            "include_thumbnails": False,
        },
    )
    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert query_payload["total"] == 3
    assert [sample["id"] for sample in query_payload["samples"]] == [
        "sample-0",
        "sample-2",
        "sample-4",
    ]

    aggregate_response = client.post(
        "/api/samples/aggregate",
        json={
            "workspace_id": "demo",
            "group_by": "metadata.department",
        },
    )
    assert aggregate_response.status_code == 200
    assert aggregate_response.json()["groups"] == [
        {"key": "home", "count": 3},
        {"key": "outdoor", "count": 3},
    ]


def test_selection_query_and_layout_key_similarity_search() -> None:
    dataset = _make_dataset()
    sample_ids = [sample.id for sample in dataset.samples]
    vectors = np.asarray(
        [[float(index), 0.0] for index in range(len(sample_ids))],
        dtype=np.float32,
    )
    dataset._storage.ensure_space(  # noqa: SLF001 - test setup for low-level API behavior
        "test-space",
        dim=2,
        config={"provider": "test", "geometry": "euclidean"},
    )
    dataset._storage.add_embeddings("test-space", sample_ids, vectors)  # noqa: SLF001
    dataset._storage.ensure_layout(  # noqa: SLF001
        layout_key="test-layout",
        space_key="test-space",
        method="test",
        geometry="euclidean",
        params=None,
    )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("demo", dataset, activate_workspace=True)
    client = TestClient(create_app(runtime=runtime))

    selection_response = client.post(
        "/api/control/ui/selection/query",
        json={
            "workspace_id": "demo",
            "labels": ["dog"],
        },
    )
    assert selection_response.status_code == 200
    assert selection_response.json()["workspace"]["ui"]["selected_ids"] == [
        "sample-1",
        "sample-3",
        "sample-5",
    ]

    similar_response = client.get(
        "/api/search/similar/sample-2",
        params={
            "workspace_id": "demo",
            "layout_key": "test-layout",
            "k": 2,
        },
    )
    assert similar_response.status_code == 200
    similar_payload = similar_response.json()
    assert similar_payload["space_key"] == "test-space"
    assert [sample["id"] for sample in similar_payload["results"]] == [
        "sample-1",
        "sample-3",
    ]
