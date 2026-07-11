from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient as FastAPITestClient
from PIL import Image

import hyperview.ui as hv_ui
from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.extensions import discover_local_extensions
from hyperview.runtime import CustomPanelSpec, HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.server.app import MAX_SAMPLE_PAGE_SIZE, create_app


class TestClient(FastAPITestClient):
    def __init__(self, app):
        super().__init__(
            app,
            headers={"Authorization": f"Bearer {app.state.api_token}"},
        )


class LocalCheckpointProvider:
    def __init__(
        self,
        *,
        name: str | None = None,
        checkpoint: str | None = None,
        dim: int | None = None,
        scale: float | None = None,
        bias: list[float] | None = None,
        **_: object,
    ) -> None:
        payload: dict[str, object] = {}
        if checkpoint is not None:
            payload = json.loads(Path(checkpoint).read_text())

        self.name = name or "test-checkpoint"
        self.dim = int(dim or payload.get("dim") or 8)
        self.scale = float(scale or payload.get("scale") or 1.0)
        bias_values = bias or payload.get("bias") or [0.0] * self.dim
        if len(bias_values) < self.dim:
            bias_values = list(bias_values) + [0.0] * (self.dim - len(bias_values))
        self.bias = np.asarray(bias_values[: self.dim], dtype=np.float32)

    def set_progress_enabled(self, _enabled: bool) -> None:
        return

    def compute_source_embeddings(self, paths: list[str]) -> list[np.ndarray]:
        embeddings: list[np.ndarray] = []
        for path in paths:
            digest = hashlib.sha256(f"{self.name}:{path}".encode()).digest()
            seed = int.from_bytes(digest[:8], "big", signed=False)
            rng = np.random.default_rng(seed)
            vector = rng.standard_normal(self.dim).astype(np.float32)
            embeddings.append(((vector * self.scale) + self.bias).astype(np.float32))
        return embeddings


def _make_dataset() -> Dataset:
    dataset = Dataset("runtime_control", persist=False)
    for index in range(6):
        dataset.add_sample(
            Sample(
                id=f"sample-{index}",
                filepath=f"/virtual/sample-{index}.png",
                label="cat" if index % 2 == 0 else "dog",
            )
        )
    return dataset


def _write_checkpoint(path: Path, *, scale: float, bias: list[float]) -> None:
    path.write_text(
        json.dumps(
            {
                "dim": len(bias),
                "scale": scale,
                "bias": bias,
            }
        )
    )


def _write_panel_module(path: Path, title: str) -> None:
    path.write_text(
        f"""const sdk = globalThis.HyperViewPanelSDK;

export default function Panel() {{
  return sdk.React.createElement("main", null, {title!r});
}}
"""
    )


def _write_extension_files(folder: Path, *, panel_exists: bool = True) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "extension.toml").write_text(
        "\n".join(
            [
                'name = "demo-ext"',
                'description = "demo extension"',
                "",
                "[[tools]]",
                'file = "tools.py"',
                "",
                "[[panels]]",
                'id = "demo-panel"',
                'title = "Demo Panel"',
                'position = "right"',
                'file = "panel.js"',
            ]
        )
    )
    (folder / "tools.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                "from hyperview.tools import tool",
                "",
                '@tool("demo.echo")',
                'def echo(ctx, *, value: str = "ok"):',
                '    return {"value": value}',
                "",
                '@tool("demo.write_artifact")',
                'def write_artifact(ctx, *, name: str = "artifact.txt"):',
                "    target = ctx.extension_storage / Path(name).name",
                '    target.write_text("artifact ok", encoding="utf-8")',
                '    return {"url": ctx.url_for(target)}',
            ]
        )
    )
    if panel_exists:
        (folder / "panel.js").write_text("export default function Panel() { return null; }\n")


def _write_panel_extension(folder: Path, *, name: str, panel_id: str, title: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "extension.toml").write_text(
        "\n".join(
            [
                f'name = "{name}"',
                "",
                "[[panels]]",
                f'id = "{panel_id}"',
                f'title = "{title}"',
                'position = "right"',
                'file = "panel.js"',
            ]
        )
    )
    panel_file = folder / "panel.js"
    _write_panel_module(panel_file, title)
    return panel_file


def test_discovers_project_local_extensions_from_nested_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    extension_folder = tmp_path / ".hyperview" / "extensions" / "demo-ext"
    _write_extension_files(extension_folder)
    nested_folder = tmp_path / "experiments" / "run-1"
    nested_folder.mkdir(parents=True)

    monkeypatch.chdir(nested_folder)

    assert discover_local_extensions() == [extension_folder.resolve()]


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    deadline = time.time() + 30.0
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed"}:
            return payload
        time.sleep(0.05)

    raise AssertionError(f"Job {job_id} did not finish in time")


def _run_control_command(
    client: TestClient,
    command: str,
    *,
    target: dict[str, object],
    args: dict[str, object] | None = None,
):
    response = client.post(
        "/api/control/commands/run",
        json={
            "command": command,
            "target": target,
            "args": args or {},
        },
    )
    assert response.status_code == 200
    return response


def test_runtime_control_api_supports_checkpoint_jobs_panels_and_ui_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_registry_path = tmp_path / "providers.json"
    workspace_registry_path = tmp_path / "workspaces.json"

    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    provider_registry = ProviderRegistry(provider_registry_path)
    workspace_registry = WorkspaceRegistry(workspace_registry_path)
    runtime = HyperViewRuntime(
        provider_registry=provider_registry,
        workspace_registry=workspace_registry,
    )
    runtime.attach_dataset_instance("default", _make_dataset())

    client = TestClient(create_app(runtime=runtime))

    register_response = client.post(
        "/api/control/provider/register",
        json={
            "alias": "test-provider",
            "import_path": "tests.test_runtime_control_api:LocalCheckpointProvider",
        },
    )
    assert register_response.status_code == 200

    checkpoint_a = tmp_path / "checkpoint-a.json"
    checkpoint_b = tmp_path / "checkpoint-b.json"
    _write_checkpoint(checkpoint_a, scale=1.0, bias=[0.0, 0.0, 0.0, 0.0])
    _write_checkpoint(checkpoint_b, scale=2.0, bias=[0.5, 0.5, 0.5, 0.5])

    response_a = client.post(
        "/api/control/embeddings/compute",
        json={
            "workspace_id": "default",
            "dataset_name": "runtime_control",
            "model": "experiment-a",
            "provider": "test-provider",
            "checkpoint": str(checkpoint_a),
            "layouts": ["euclidean:2d"],
            "method": "pca",
        },
    )
    assert response_a.status_code == 200
    job_a = _wait_for_job(client, response_a.json()["job"]["id"])
    assert job_a["status"] == "completed"
    assert job_a["result"]["layout_keys"]

    response_b = client.post(
        "/api/control/embeddings/compute",
        json={
            "workspace_id": "default",
            "dataset_name": "runtime_control",
            "model": "experiment-a",
            "provider": "test-provider",
            "checkpoint": str(checkpoint_b),
            "layouts": ["euclidean:2d"],
            "method": "pca",
        },
    )
    assert response_b.status_code == 200
    job_b = _wait_for_job(client, response_b.json()["job"]["id"])
    assert job_b["status"] == "completed"

    dataset_response = client.get("/api/dataset")
    assert dataset_response.status_code == 200
    dataset_payload = dataset_response.json()
    assert len(dataset_payload["spaces"]) == 2
    assert len(dataset_payload["layouts"]) == 2
    assert dataset_payload["spaces"][0]["space_key"] != dataset_payload["spaces"][1]["space_key"]

    right_panel_file = _write_panel_extension(
        tmp_path / "label-histogram-ext",
        name="label-histogram-ext",
        panel_id="label-histogram",
        title="Label Histogram",
    )
    _write_panel_extension(
        tmp_path / "notes-ext",
        name="notes-ext",
        panel_id="notes",
        title="Notes",
    )
    runtime.install_extension("default", tmp_path / "label-histogram-ext")
    runtime.install_extension("default", tmp_path / "notes-ext")

    histogram_panel_response = _run_control_command(
        client,
        "workspace.panel.add",
        target={"workspace_id": "default"},
        args={
            "panel_id": "label-histogram",
            "kind": "extension",
            "extension": "label-histogram-ext",
            "extension_panel": "label-histogram",
            "position": "right",
            "width": 320,
            "min_width": 240,
        },
    )
    assert histogram_panel_response.json()["ok"] is True

    text_panel_response = _run_control_command(
        client,
        "workspace.panel.add",
        target={"workspace_id": "default"},
        args={
            "panel_id": "notes",
            "kind": "extension",
            "extension": "notes-ext",
            "extension_panel": "notes",
            "position": "bottom",
        },
    )
    assert text_panel_response.json()["ok"] is True

    update_panel_response = _run_control_command(
        client,
        "workspace.panel.update",
        target={"workspace_id": "default", "panel_id": "notes"},
        args={
            "title": "Ranked Notes",
            "position": "right",
            "reference_panel_id": "label-histogram",
            "direction": "right",
            "height": 260,
            "min_height": 180,
            "active": True,
            "props": {
                "mode": "ranked",
                "rank": {
                    "anchorSampleId": "sample-1",
                    "k": 24,
                },
            },
        },
    )
    assert update_panel_response.json()["ok"] is True

    target_layout = job_b["result"]["layout_keys"][0]
    scatter_panel_response = _run_control_command(
        client,
        "workspace.panel.add",
        target={"workspace_id": "default"},
        args={
            "panel_id": "experiment-b-scatter",
            "title": "Experiment B",
            "kind": "scatter",
            "layout_key": target_layout,
            "position": "center",
            "reference_panel_id": "label-histogram",
            "direction": "right",
        },
    )
    assert scatter_panel_response.json()["ok"] is True

    set_layout_response = client.post(
        "/api/control/ui/layout",
        json={
            "workspace_id": "default",
            "layout_key": target_layout,
        },
    )
    assert set_layout_response.status_code == 200

    set_selection_response = client.post(
        "/api/control/ui/selection",
        json={
            "workspace_id": "default",
            "sample_ids": ["sample-1", "sample-3"],
        },
    )
    assert set_selection_response.status_code == 200

    runtime_response = client.get("/api/runtime")
    assert runtime_response.status_code == 200
    runtime_payload = runtime_response.json()

    assert runtime_payload["runtime_id"] == runtime.runtime_id
    assert runtime_payload["workspace"]["dataset_name"] == "runtime_control"
    assert runtime_payload["workspace"]["ui"]["active_layout_key"] == target_layout
    assert runtime_payload["workspace"]["ui"]["selected_ids"] == ["sample-1", "sample-3"]
    assert runtime_payload["workspace"]["ui"]["active_panel_id"] == "notes"
    assert runtime_payload["workspace"]["ui"]["view_revision"] > 0
    assert len(runtime_payload["workspace"]["ui"]["custom_panels"]) == 3

    histogram_panel = next(
        panel
        for panel in runtime_payload["workspace"]["ui"]["custom_panels"]
        if panel["id"] == "label-histogram"
    )
    text_panel = next(
        panel
        for panel in runtime_payload["workspace"]["ui"]["custom_panels"]
        if panel["id"] == "notes"
    )
    scatter_panel = next(
        panel
        for panel in runtime_payload["workspace"]["ui"]["custom_panels"]
        if panel["id"] == "experiment-b-scatter"
    )

    assert histogram_panel["kind"] == "module"
    assert histogram_panel["data"]["module_src"].startswith(
        "/api/panels/content/default/label-histogram/panel.js"
    )
    assert histogram_panel["module_file"] == str(right_panel_file.resolve())
    assert histogram_panel["width"] == 320
    assert histogram_panel["min_width"] == 240
    assert text_panel["title"] == "Ranked Notes"
    assert text_panel["position"] == "right"
    assert text_panel["reference_panel_id"] == "label-histogram"
    assert text_panel["direction"] == "right"
    assert text_panel["height"] == 260
    assert text_panel["min_height"] == 180
    assert text_panel["props"] == {
        "mode": "ranked",
        "rank": {
            "anchorSampleId": "sample-1",
            "k": 24,
        },
    }
    assert text_panel["data"]["module_src"].startswith("/api/panels/content/default/notes/panel.js")
    assert scatter_panel["kind"] == "builtin"
    assert scatter_panel["layout_key"] == target_layout
    assert scatter_panel["geometry"] == "euclidean"
    assert scatter_panel["layout_dimension"] == 2
    assert scatter_panel["reference_panel_id"] == "label-histogram"
    assert scatter_panel["direction"] == "right"
    assert scatter_panel["data"]["module_src"] is None

    panel_asset_response = client.get(histogram_panel["data"]["module_src"])
    assert panel_asset_response.status_code == 200
    assert "Label Histogram" in panel_asset_response.text

    remove_scatter_response = _run_control_command(
        client,
        "workspace.panel.remove",
        target={"workspace_id": "default", "panel_id": "experiment-b-scatter"},
    )
    assert remove_scatter_response.json()["ok"] is True

    after_remove_response = client.get("/api/runtime")
    assert after_remove_response.status_code == 200
    remaining_panel_ids = {
        panel["id"] for panel in after_remove_response.json()["workspace"]["ui"]["custom_panels"]
    }
    assert "experiment-b-scatter" not in remaining_panel_ids
    assert {"label-histogram", "notes"}.issubset(remaining_panel_ids)


def test_runtime_panel_patch_omits_or_clears_placement_fields() -> None:
    workspace_id = f"panel-patch-{time.time_ns()}"
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    client = TestClient(create_app(runtime=runtime))

    response = _run_control_command(
        client,
        "workspace.panel.add",
        target={"workspace_id": workspace_id},
        args={
            "panel_id": "samples",
            "kind": "builtin",
            "builtin_panel": "samples",
            "position": "right",
            "reference_panel_id": "map",
            "direction": "right",
            "width": 320,
            "min_width": 240,
        },
    )
    assert response.json()["ok"] is True

    response = _run_control_command(
        client,
        "workspace.panel.update",
        target={"workspace_id": workspace_id, "panel_id": "samples"},
        args={"props": {"mode": "ranked"}},
    )
    assert response.json()["ok"] is True
    panel = runtime.get_workspace(workspace_id).ui.custom_panels[0]
    assert panel.reference_panel_id == "map"
    assert panel.direction == "right"
    assert panel.width == 320
    assert panel.min_width == 240

    response = _run_control_command(
        client,
        "workspace.panel.update",
        target={"workspace_id": workspace_id, "panel_id": "samples"},
        args={
            "position": "right",
            "reference_panel_id": None,
            "direction": None,
            "width": None,
            "min_width": None,
        },
    )
    assert response.json()["ok"] is True
    panel = runtime.get_workspace(workspace_id).ui.custom_panels[0]
    assert panel.position == "right"
    assert panel.reference_panel_id is None
    assert panel.direction is None
    assert panel.width is None
    assert panel.min_width is None


def test_runtime_snapshot_panel_contract_includes_state_and_layout(tmp_path: Path) -> None:
    workspace_id = f"panel-contract-{time.time_ns()}"
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance(workspace_id, _make_dataset(), activate_workspace=True)
    runtime.add_runtime_panel(
        workspace_id,
        panel_id="samples",
        kind="builtin",
        builtin_panel="samples",
        position="right",
        width=360,
        min_width=260,
        props={"mode": "browse"},
    )
    runtime.patch_panel_state(
        workspace_id,
        "samples",
        {"view": {"density": "compact"}},
        source_client_id="test-client",
    )

    snapshot = runtime.snapshot(workspace_id)
    panel = snapshot["workspace"]["ui"]["custom_panels"][0]

    assert panel["id"] == "samples"
    assert panel["panel_type"] == "samples"
    assert panel["source"] == "builtin"
    assert panel["props"] == {"mode": "browse"}
    assert "state" not in panel
    assert panel["state_revision"] == 1
    assert panel["layout"] == {
        "position": "right",
        "reference_panel_id": None,
        "direction": None,
        "width": 360,
        "height": None,
        "min_width": 260,
        "min_height": None,
        "max_width": None,
        "max_height": None,
    }
    assert snapshot["workspace"]["ui"]["panels"]["samples"] == {
        "state": {"view": {"density": "compact"}},
        "state_revision": 1,
    }


def test_extension_panel_definition_drives_runtime_panel_defaults(
    tmp_path: Path,
) -> None:
    extension_dir = tmp_path / "readout-ext"
    extension_dir.mkdir()
    (extension_dir / "extension.toml").write_text(
        """
name = "readout"

[[panels]]
id = "summary"
title = "Summary"
label = "Summary card"
panel_type = "analysis.summary"
position = "right"
file = "panel.js"
commands = ["workspace.panel.state.get", "custom.refresh"]
queries = ["samples.query"]
allow_multiple = false
icon = "chart"
category = "analysis"

[panels.default_props]
mode = "compact"

[panels.default_state]
collapsed = false
threshold = 0.75

[panels.default_layout]
position = "bottom"
height = 240
min_height = 180
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (extension_dir / "panel.js").write_text(
        "export default function Panel() { return null; }\n",
        encoding="utf-8",
    )
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    client = TestClient(create_app(runtime=runtime))

    installation = runtime.install_extension("default", extension_dir, add_panels=True)
    definition = runtime.get_panel_definition(
        "analysis.summary",
        source="extension",
        extension="readout",
    )
    assert definition is not None

    definition_payload = definition.to_dict()
    assert definition_payload == installation.to_dict()["panel_definitions"][0]
    assert definition_payload["label"] == "Summary card"
    assert definition_payload["default_props"] == {"mode": "compact"}
    assert definition_payload["default_state"] == {
        "collapsed": False,
        "threshold": 0.75,
    }
    assert definition_payload["default_layout"] == {
        "position": "bottom",
        "height": 240,
        "min_height": 180,
    }
    assert definition_payload["commands"] == ["workspace.panel.state.get", "custom.refresh"]
    assert definition_payload["queries"] == ["samples.query"]
    assert definition_payload["allow_multiple"] is False

    workspace = runtime.get_workspace("default")
    panel = workspace.ui.custom_panels[0]
    assert panel.id == "summary"
    assert panel.panel_type == "analysis.summary"
    assert panel.source == "extension"
    assert panel.extension == "readout"
    assert panel.extension_panel == "summary"
    assert panel.position == "bottom"
    assert panel.height == 240
    assert panel.min_height == 180
    assert panel.props == {"mode": "compact"}
    assert workspace.ui.panels["summary"].state == {
        "collapsed": False,
        "threshold": 0.75,
    }
    assert workspace.ui.panels["summary"].state_revision == 0

    snapshot = runtime.snapshot("default")
    definitions_by_type = {
        item["panel_type"]: item for item in snapshot["panel_definitions"]
    }
    assert {"samples", "scatter", "analysis.summary"}.issubset(definitions_by_type)
    assert "state" not in snapshot["workspace"]["ui"]["custom_panels"][0]

    response = client.get("/api/panel-definitions")
    assert response.status_code == 200
    endpoint_definitions = {
        item["panel_type"]: item for item in response.json()["panel_definitions"]
    }
    assert endpoint_definitions["analysis.summary"] == definition_payload

    runtime.remove_custom_panel("default", "summary")
    runtime.add_runtime_panel(
        "default",
        panel_id="summary-manual",
        kind="extension",
        extension="readout",
        extension_panel="summary",
    )
    manual_panel = runtime.get_workspace("default").ui.custom_panels[0]
    assert manual_panel.id == "summary-manual"
    assert manual_panel.position == "bottom"
    assert manual_panel.height == 240
    assert manual_panel.min_height == 180
    assert manual_panel.props == {"mode": "compact"}
    assert runtime.get_workspace("default").ui.panels["summary-manual"].state == {
        "collapsed": False,
        "threshold": 0.75,
    }


def test_runtime_panel_builder_matches_public_ui_compilation(tmp_path: Path) -> None:
    dataset = _make_dataset()
    sample_ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        sample_ids,
        np.asarray([[float(index), 0.0] for index, _ in enumerate(sample_ids)]),
    )

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("default", dataset)
    panel_file = _write_panel_extension(
        tmp_path / "readout-ext",
        name="readout-ext",
        panel_id="summary",
        title="Summary",
    )
    runtime.install_extension("default", tmp_path / "readout-ext")

    runtime_specs = [
        runtime.build_custom_panel(
            "default",
            panel_id="map",
            title="Map",
            kind="scatter",
            layout_key=layout_key,
            position="center",
        ),
        runtime.build_custom_panel(
            "default",
            panel_id="samples",
            title=None,
            kind="builtin",
            builtin_panel="samples",
            position="right",
            reference_panel_id="map",
            direction="right",
        ),
        runtime.build_custom_panel(
            "default",
            panel_id="summary",
            title=None,
            kind="extension",
            extension="readout-ext",
            extension_panel="summary",
            position="bottom",
            props={"mode": "compact"},
        ),
    ]

    ui_specs = hv_ui.compile_view(
        hv_ui.View(
            hv_ui.Scatter(
                id="map",
                title="Map",
                layout_key=layout_key,
                position="center",
            ),
            hv_ui.Samples(
                id="samples",
                title="Samples",
                position="right",
                reference_panel_id="map",
                direction="right",
            ),
            hv_ui.ExtensionPanel(
                id="summary",
                extension="readout-ext",
                panel="summary",
                position="bottom",
                props={"mode": "compact"},
            ),
        ),
        runtime=runtime,
        workspace_id="default",
    )

    assert [spec.to_dict() for spec in runtime_specs] == [spec.to_dict() for spec in ui_specs]
    assert runtime_specs[0].geometry == "euclidean"
    assert runtime_specs[0].layout_dimension == 2
    assert runtime_specs[2].module_file == str(panel_file.resolve())


def test_panel_add_command_requires_existing_layout(tmp_path: Path) -> None:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("default", _make_dataset())
    client = TestClient(create_app(runtime=runtime))

    response = _run_control_command(
        client,
        "workspace.panel.add",
        target={"workspace_id": "default"},
        args={
            "panel_id": "missing-layout",
            "title": "Missing Layout",
            "kind": "scatter",
            "layout_key": "missing-layout",
        },
    )

    assert response.json() == {
        "ok": False,
        "command": "workspace.panel.add",
        "result": {},
        "error": {
            "code": "not_found",
            "message": "Layout not found: missing-layout",
        },
    }


def test_runtime_embedding_job_uses_injected_provider_registry(tmp_path: Path) -> None:
    provider_registry = ProviderRegistry(tmp_path / "isolated-providers.json")
    workspace_registry = WorkspaceRegistry(tmp_path / "isolated-workspaces.json")
    runtime = HyperViewRuntime(
        provider_registry=provider_registry,
        workspace_registry=workspace_registry,
    )
    runtime.attach_dataset_instance("default", _make_dataset())
    client = TestClient(create_app(runtime=runtime))

    alias = f"isolated-provider-{time.time_ns()}"
    register_response = client.post(
        "/api/control/provider/register",
        json={
            "alias": alias,
            "import_path": "tests.test_runtime_control_api:LocalCheckpointProvider",
        },
    )
    assert register_response.status_code == 200

    checkpoint = tmp_path / "isolated-checkpoint.json"
    _write_checkpoint(checkpoint, scale=1.0, bias=[0.0, 0.0, 0.0, 0.0])

    compute_response = client.post(
        "/api/control/embeddings/compute",
        json={
            "workspace_id": "default",
            "dataset_name": "runtime_control",
            "model": "isolated-model",
            "provider": alias,
            "checkpoint": str(checkpoint),
            "layouts": [],
        },
    )

    assert compute_response.status_code == 200
    job = _wait_for_job(client, compute_response.json()["job"]["id"])
    assert job["status"] == "completed"
    assert job["result"]["space_key"].startswith(f"{alias}__isolated-model__")


def test_health_reports_package_version() -> None:
    from hyperview import __version__

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", _make_dataset())
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/__hyperview__/health")

    assert response.status_code == 200
    assert response.json()["version"] == __version__


def test_ui_similarity_query_is_explicit_and_cleared_with_selection(tmp_path: Path) -> None:
    workspace_id = f"similarity-ui-{time.time_ns()}"
    dataset = _make_dataset()
    ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        ids,
        [[float(index), float(index % 2)] for index, _ in enumerate(ids)],
    )
    space_key = dataset.list_layouts()[0].space_key

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance(workspace_id, dataset, activate_workspace=True)
    runtime.set_selection(workspace_id, ["sample-2"])
    client = TestClient(create_app(runtime=runtime))

    response = _run_control_command(
        client,
        "panel.samples.retrieval.set-anchor",
        target={"workspace_id": workspace_id},
        args={
            "sample_id": "sample-2",
            "layout_key": layout_key,
            "k": 12,
            "source": "test",
        },
    )

    assert response.json()["ok"] is True
    ui = response.json()["workspace"]["ui"]
    assert ui["selected_ids"] == []
    expected_retrieval = {
        "anchor_sample_id": "sample-2",
        "layout_key": layout_key,
        "space_key": space_key,
        "k": 12,
        "source": "test",
    }
    samples_state = ui["panels"]["samples"]["state"]
    assert samples_state["mode"] == "retrieval"
    assert samples_state["retrieval"] == expected_retrieval
    assert "similarity_query" not in ui
    assert samples_state["collection"]["kind"] == "neighbors"

    selection_response = client.post(
        "/api/control/ui/selection",
        json={"workspace_id": workspace_id, "sample_ids": ["sample-3"]},
    )
    assert selection_response.status_code == 200
    selection_ui = selection_response.json()["workspace"]["ui"]
    assert "similarity_query" not in selection_ui
    assert selection_ui["panels"]["samples"]["state"] == {}

    clear_response = _run_control_command(
        client,
        "panel.samples.retrieval.clear",
        target={"workspace_id": workspace_id},
    )
    assert clear_response.json()["ok"] is True
    assert "similarity_query" not in clear_response.json()["workspace"]["ui"]


def test_workspace_load_drops_legacy_similarity_anchor_selection(tmp_path: Path) -> None:
    registry_path = tmp_path / "workspaces.json"
    registry_path.write_text(
        json.dumps(
            {
                "active_workspace_id": "default",
                "workspaces": [
                    {
                        "id": "default",
                        "dataset_name": "demo",
                        "created_at": 1,
                        "ui": {
                            "selected_ids": ["sample-2"],
                            "similarity_query": {
                                "anchor_sample_id": "sample-2",
                                "layout_key": "layout-a",
                                "k": 12,
                                "source": "cli",
                            },
                        },
                    }
                ],
            }
        )
    )

    registry = WorkspaceRegistry(registry_path)
    workspace = registry.get("default")

    assert workspace is not None
    assert workspace.ui.selected_ids == []
    samples_retrieval = workspace.ui.panels["samples"].state["retrieval"]
    assert samples_retrieval["anchor_sample_id"] == "sample-2"
    assert workspace.ui.panels["samples"].state == {
        "mode": "retrieval",
        "retrieval": samples_retrieval,
    }


def test_ui_similarity_query_rejects_mismatched_layout_and_space() -> None:
    dataset = _make_dataset()
    ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        ids,
        [[float(index), float(index % 2)] for index, _ in enumerate(ids)],
    )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    client = TestClient(create_app(runtime=runtime))

    response = _run_control_command(
        client,
        "panel.samples.retrieval.set-anchor",
        target={"workspace_id": "default"},
        args={
            "sample_id": "sample-2",
            "layout_key": layout_key,
            "space_key": "different-space",
        },
    )

    assert response.json() == {
        "ok": False,
        "command": "panel.samples.retrieval.set-anchor",
        "result": {},
        "error": {
            "code": "validation_error",
            "message": "space_key does not match the requested layout_key",
        },
    }


def test_ui_state_patch_batches_layout_and_selection() -> None:
    dataset = _make_dataset()
    ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        ids,
        [[float(index), float(index % 2)] for index, _ in enumerate(ids)],
    )
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    runtime.patch_ui_state(
        "default",
        set_active_layout=True,
        active_layout_key=layout_key,
        set_selection=True,
        selected_ids=["sample-1"],
    )
    before_version = runtime.version
    client = TestClient(create_app(runtime=runtime))

    response = client.patch(
        "/api/control/ui/state",
        json={
            "workspace_id": "default",
            "set_active_layout": True,
            "active_layout_key": None,
            "set_selection": True,
            "selected_ids": ["sample-5"],
        },
    )

    assert response.status_code == 200
    assert runtime.version == before_version + 1
    assert runtime.version_source_client_id is None
    ui = response.json()["workspace"]["ui"]
    assert ui["active_layout_key"] is None
    assert ui["selected_ids"] == ["sample-5"]
    assert "similarity_query" not in ui

    sourced_response = client.patch(
        "/api/control/ui/state",
        json={
            "workspace_id": "default",
            "client_id": "client-1",
            "set_active_layout": True,
            "active_layout_key": layout_key,
        },
    )
    assert sourced_response.status_code == 200
    assert runtime.version_source_client_id == "client-1"


def test_ui_state_patch_rejects_samples_retrieval_fields() -> None:
    dataset = _make_dataset()
    ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        ids,
        [[float(index), float(index % 2)] for index, _ in enumerate(ids)],
    )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    initial_selected_ids = list(runtime.get_workspace("default").ui.selected_ids)
    client = TestClient(create_app(runtime=runtime))

    response = client.patch(
        "/api/control/ui/state",
        json={
            "workspace_id": "default",
            "set_selection": True,
            "selected_ids": ["sample-3"],
            "set_similarity_query": True,
            "similarity_query": {
                "sample_id": "sample-2",
                "layout_key": layout_key,
            },
        },
    )

    assert response.status_code == 422
    workspace = runtime.get_workspace("default")
    assert workspace.ui.selected_ids == initial_selected_ids
    assert runtime.get_samples_retrieval_query("default") is None


def test_sample_responses_include_media_url_and_content_endpoint_serves_file(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (12, 12), color=(32, 128, 224)).save(image_path)

    dataset = Dataset("runtime_media", persist=False)
    dataset.add_sample(
        Sample(
            id="sample-1",
            filepath=str(image_path),
            label="blue",
        )
    )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    client = TestClient(create_app(runtime=runtime))

    samples_response = client.get("/api/samples")
    assert samples_response.status_code == 200
    payload = samples_response.json()
    assert payload["samples"][0]["media_url"] == "/api/samples/sample-1/content"
    assert payload["samples"][0]["thumbnail_url"] == "/api/samples/sample-1/thumbnail"
    assert payload["samples"][0]["thumbnail"] is None
    assert payload["samples"][0]["width"] is None
    assert payload["samples"][0]["height"] is None

    detail_response = client.get("/api/samples/sample-1")
    assert detail_response.status_code == 200
    assert detail_response.json()["width"] == 12
    assert detail_response.json()["height"] == 12

    inline_response = client.get("/api/samples", params={"include_thumbnails": "true"})
    assert inline_response.status_code == 200
    assert inline_response.json()["samples"][0]["thumbnail"] is not None

    content_response = client.get("/api/samples/sample-1/content")
    assert content_response.status_code == 200
    assert content_response.headers["content-type"].startswith("image/png")

    thumbnail_response = client.get("/api/samples/sample-1/thumbnail")
    assert thumbnail_response.status_code == 200
    assert thumbnail_response.headers["content-type"].startswith("image/jpeg")
    assert thumbnail_response.headers["cache-control"].startswith("public")

    batch_response = client.post("/api/samples/batch", json={"sample_ids": ["sample-1"]})
    assert batch_response.status_code == 200
    assert batch_response.json()["samples"][0]["thumbnail"] is None

    inline_batch_response = client.post(
        "/api/samples/batch",
        json={"sample_ids": ["sample-1"], "include_thumbnails": True},
    )
    assert inline_batch_response.status_code == 200
    assert inline_batch_response.json()["samples"][0]["thumbnail"] is not None


def test_samples_endpoint_filters_missing_labels() -> None:
    dataset = Dataset("runtime_missing_labels", persist=False)
    dataset.add_samples(
        [
            Sample(id="sample-1", filepath="/virtual/sample-1.png", label="cat"),
            Sample(id="sample-2", filepath="/virtual/sample-2.png"),
            Sample(id="sample-3", filepath="/virtual/sample-3.png", label="dog"),
        ]
    )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/api/samples", params={"missing_label": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [sample["id"] for sample in payload["samples"]] == ["sample-2"]
    assert payload["samples"][0]["label"] is None


def test_samples_batch_allows_exact_id_reads_larger_than_page_limit() -> None:
    sample_count = MAX_SAMPLE_PAGE_SIZE + 1
    dataset = Dataset("runtime_large_batch", persist=False)
    dataset.add_samples(
        [
            Sample(id=f"sample-{index}", filepath=f"/tmp/sample-{index}.png")
            for index in range(sample_count)
        ]
    )

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    client = TestClient(create_app(runtime=runtime))

    response = client.post(
        "/api/samples/batch",
        json={"sample_ids": [f"sample-{index}" for index in range(sample_count)]},
    )

    assert response.status_code == 200
    assert len(response.json()["samples"]) == sample_count


def test_relative_sample_media_paths_are_normalized_at_ingestion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "relative.png"
    Image.new("RGB", (12, 12), color=(224, 128, 32)).save(image_path)
    monkeypatch.chdir(tmp_path)

    dataset = Dataset("runtime_relative_media", persist=False)
    dataset.add_sample(Sample(id="sample-1", filepath="relative.png", label="orange"))
    sample = dataset["sample-1"]

    assert Path(sample.filepath).is_absolute()
    assert sample.filepath == str(image_path.resolve())

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    client = TestClient(create_app(runtime=runtime))

    content_response = client.get("/api/samples/sample-1/content")

    assert content_response.status_code == 200
    assert content_response.headers["content-type"].startswith("image/png")


def test_set_workspace_dataset_clears_dataset_scoped_ui_state(tmp_path: Path, monkeypatch) -> None:
    provider_registry_path = tmp_path / "providers.json"
    workspace_registry_path = tmp_path / "workspaces.json"

    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(provider_registry_path),
        workspace_registry=WorkspaceRegistry(workspace_registry_path),
    )
    runtime.attach_dataset_instance("default", _make_dataset())
    runtime.set_active_layout("default", "layout-a")
    runtime.set_selection("default", ["sample-1", "sample-3"])
    runtime.set_samples_retrieval(
        "default",
        runtime.resolve_similarity_query("default", "sample-1", source="test"),
    )
    assert runtime.get_workspace("default").ui.panels["samples"].state["mode"] == "retrieval"

    workspace = runtime.set_workspace_dataset("default", "second-dataset")

    assert workspace.dataset_name == "second-dataset"
    assert workspace.ui.active_layout_key is None
    assert workspace.ui.selected_ids == []
    assert workspace.ui.panels == {}

    snapshot = runtime.snapshot()
    assert snapshot["workspace"]["dataset_name"] == "second-dataset"
    assert snapshot["workspace"]["ui"]["active_layout_key"] is None
    assert snapshot["workspace"]["ui"]["selected_ids"] == []
    assert "similarity_query" not in snapshot["workspace"]["ui"]
    assert snapshot["workspace"]["ui"]["panels"] == {}


def test_runtime_panel_module_src_changes_when_module_file_changes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_registry_path = tmp_path / "providers.json"
    workspace_registry_path = tmp_path / "workspaces.json"
    panel_file = tmp_path / "catalog-panel.js"

    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(provider_registry_path),
        workspace_registry=WorkspaceRegistry(workspace_registry_path),
    )
    _write_panel_module(panel_file, "Initial Catalog Panel")
    runtime.add_custom_panel(
        "default",
        CustomPanelSpec(
            id="catalog-hierarchy-readout",
            title="Catalog Hierarchy Readout",
            module_file=str(panel_file),
        ),
    )

    first_snapshot = runtime.snapshot()
    first_panel = first_snapshot["workspace"]["ui"]["custom_panels"][0]
    first_module_src = first_panel["data"]["module_src"]

    assert first_panel["id"] == "catalog-hierarchy-readout"
    assert "?hv_rev=" in first_module_src

    _write_panel_module(panel_file, "Updated Catalog Panel")

    second_snapshot = runtime.snapshot()
    second_panel = second_snapshot["workspace"]["ui"]["custom_panels"][0]

    assert second_panel["id"] == "catalog-hierarchy-readout"
    assert second_panel["data"]["module_src"] != first_module_src
    assert second_snapshot["version"] > first_snapshot["version"]


def test_runtime_rejects_duplicate_custom_panel_ids(tmp_path: Path) -> None:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )

    with pytest.raises(ValueError, match="Duplicate panel id"):
        runtime.replace_custom_panels(
            "default",
            [
                CustomPanelSpec(id="dupe", title="One"),
                CustomPanelSpec(id="dupe", title="Two"),
            ],
        )

    assert runtime.get_workspace("default").ui.custom_panels == []


def test_failed_extension_reinstall_preserves_previous_installation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_registry_path = tmp_path / "providers.json"
    workspace_registry_path = tmp_path / "workspaces.json"

    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(provider_registry_path),
        workspace_registry=WorkspaceRegistry(workspace_registry_path),
    )

    extension_dir = tmp_path / "demo-ext"
    _write_extension_files(extension_dir, panel_exists=True)
    runtime.install_extension("default", extension_dir, add_panels=True)

    installed = runtime.get_extension("demo-ext")
    assert installed is not None
    assert [panel.id for panel in runtime.get_workspace("default").ui.custom_panels] == [
        "demo-panel"
    ]
    assert runtime.tools.get("demo.echo") is not None

    (extension_dir / "panel.js").unlink()

    try:
        runtime.install_extension("default", extension_dir, add_panels=True)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected reinstall to fail when panel.js is missing")

    restored = runtime.get_extension("demo-ext")
    assert restored is installed
    assert [panel.id for panel in runtime.get_workspace("default").ui.custom_panels] == [
        "demo-panel"
    ]
    assert runtime.tools.get("demo.echo") is not None


def test_extension_tool_artifact_url_serves_extension_storage_file(
    tmp_path: Path,
) -> None:
    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", _make_dataset())
    client = TestClient(create_app(runtime=runtime))

    extension_dir = tmp_path / "demo-ext"
    _write_extension_files(extension_dir, panel_exists=True)
    runtime.install_extension("default", extension_dir)

    response = client.post(
        "/api/tools/run",
        json={
            "tool": "demo.write_artifact",
            "workspace_id": "default",
            "params": {"name": "artifact.txt"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    artifact_response = client.get(payload["result"]["url"])
    assert artifact_response.status_code == 200
    assert artifact_response.text == "artifact ok"
