from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.extensions import discover_local_extensions
from hyperview.runtime import CustomPanelSpec, HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.server.app import create_app


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
                "def echo(ctx, *, value: str = \"ok\"):",
                "    return {\"value\": value}",
                "",
                '@tool("demo.write_artifact")',
                "def write_artifact(ctx, *, name: str = \"artifact.txt\"):",
                "    target = ctx.extension_storage / Path(name).name",
                "    target.write_text(\"artifact ok\", encoding=\"utf-8\")",
                "    return {\"url\": ctx.url_for(target)}",
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

    histogram_panel_response = client.post(
        "/api/control/ui/panels",
        json={
            "workspace_id": "default",
            "panel_id": "label-histogram",
            "kind": "extension",
            "extension": "label-histogram-ext",
            "extension_panel": "label-histogram",
            "position": "right",
        },
    )
    assert histogram_panel_response.status_code == 200

    text_panel_response = client.post(
        "/api/control/ui/panels",
        json={
            "workspace_id": "default",
            "panel_id": "notes",
            "kind": "extension",
            "extension": "notes-ext",
            "extension_panel": "notes",
            "position": "bottom",
        },
    )
    assert text_panel_response.status_code == 200

    target_layout = job_b["result"]["layout_keys"][0]
    scatter_panel_response = client.post(
        "/api/control/ui/panels",
        json={
            "workspace_id": "default",
            "panel_id": "experiment-b-scatter",
            "title": "Experiment B",
            "kind": "scatter",
            "layout_key": target_layout,
            "position": "center",
            "reference_panel_id": "label-histogram",
            "direction": "right",
        },
    )
    assert scatter_panel_response.status_code == 200

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
    assert text_panel["data"]["module_src"].startswith(
        "/api/panels/content/default/notes/panel.js"
    )
    assert scatter_panel["kind"] == "scatter"
    assert scatter_panel["layout_key"] == target_layout
    assert scatter_panel["geometry"] == "euclidean"
    assert scatter_panel["layout_dimension"] == 2
    assert scatter_panel["reference_panel_id"] == "label-histogram"
    assert scatter_panel["direction"] == "right"
    assert scatter_panel["data"]["module_src"] is None

    panel_asset_response = client.get(histogram_panel["data"]["module_src"])
    assert panel_asset_response.status_code == 200
    assert "Label Histogram" in panel_asset_response.text

    remove_scatter_response = client.request(
        "DELETE",
        "/api/control/ui/panels",
        json={
            "workspace_id": "default",
            "panel_id": "experiment-b-scatter",
        },
    )
    assert remove_scatter_response.status_code == 200

    after_remove_response = client.get("/api/runtime")
    assert after_remove_response.status_code == 200
    remaining_panel_ids = {
        panel["id"]
        for panel in after_remove_response.json()["workspace"]["ui"]["custom_panels"]
    }
    assert "experiment-b-scatter" not in remaining_panel_ids
    assert {"label-histogram", "notes"}.issubset(remaining_panel_ids)


def test_health_reports_package_version() -> None:
    from hyperview import __version__

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", _make_dataset())
    client = TestClient(create_app(runtime=runtime))

    response = client.get("/__hyperview__/health")

    assert response.status_code == 200
    assert response.json()["version"] == __version__


def test_ui_similarity_query_is_explicit_and_cleared_with_selection() -> None:
    dataset = _make_dataset()
    ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        ids,
        [[float(index), float(index % 2)] for index, _ in enumerate(ids)],
    )
    space_key = dataset.list_layouts()[0].space_key

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    client = TestClient(create_app(runtime=runtime))

    response = client.post(
        "/api/control/ui/similarity",
        json={
            "workspace_id": "default",
            "sample_id": "sample-2",
            "layout_key": layout_key,
            "k": 12,
            "source": "test",
        },
    )

    assert response.status_code == 200
    ui = response.json()["workspace"]["ui"]
    assert ui["selected_ids"] == ["sample-2"]
    assert ui["similarity_query"] == {
        "anchor_sample_id": "sample-2",
        "layout_key": layout_key,
        "space_key": space_key,
        "k": 12,
        "source": "test",
    }

    selection_response = client.post(
        "/api/control/ui/selection",
        json={"workspace_id": "default", "sample_ids": ["sample-3"]},
    )
    assert selection_response.status_code == 200
    assert selection_response.json()["workspace"]["ui"]["similarity_query"] is None

    clear_response = client.request(
        "DELETE",
        "/api/control/ui/similarity",
        json={"workspace_id": "default"},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["workspace"]["ui"]["similarity_query"] is None


def test_ui_state_patch_batches_layout_selection_and_similarity() -> None:
    dataset = _make_dataset()
    ids = [sample.id for sample in dataset]
    layout_key = dataset.set_coords(
        "euclidean",
        ids,
        [[float(index), float(index % 2)] for index, _ in enumerate(ids)],
    )
    space_key = dataset.list_layouts()[0].space_key

    runtime = HyperViewRuntime()
    runtime.attach_dataset_instance("default", dataset)
    before_version = runtime.version
    client = TestClient(create_app(runtime=runtime))

    response = client.patch(
        "/api/control/ui/state",
        json={
            "workspace_id": "default",
            "set_active_layout": True,
            "active_layout_key": layout_key,
            "set_selection": True,
            "selected_ids": ["sample-2"],
            "set_similarity_query": True,
            "similarity_query": {
                "sample_id": "sample-2",
                "layout_key": layout_key,
                "k": 12,
                "source": "test",
            },
        },
    )

    assert response.status_code == 200
    assert runtime.version == before_version + 1
    assert runtime.version_source_client_id is None
    ui = response.json()["workspace"]["ui"]
    assert ui["active_layout_key"] == layout_key
    assert ui["selected_ids"] == ["sample-2"]
    assert ui["similarity_query"] == {
        "anchor_sample_id": "sample-2",
        "layout_key": layout_key,
        "space_key": space_key,
        "k": 12,
        "source": "test",
    }

    sourced_response = client.patch(
        "/api/control/ui/state",
        json={
            "workspace_id": "default",
            "client_id": "client-1",
            "set_active_layout": True,
            "active_layout_key": None,
        },
    )
    assert sourced_response.status_code == 200
    assert runtime.version_source_client_id == "client-1"


def test_ui_state_patch_rejects_similarity_anchor_outside_selection() -> None:
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

    assert response.status_code == 400
    assert "anchor_sample_id must be included" in response.json()["detail"]


def test_sample_responses_include_media_url_and_content_endpoint_serves_file(tmp_path: Path) -> None:
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
    assert payload["samples"][0]["thumbnail"] is not None

    content_response = client.get("/api/samples/sample-1/content")
    assert content_response.status_code == 200
    assert content_response.headers["content-type"].startswith("image/png")


def test_relative_sample_media_paths_are_normalized_at_ingestion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "relative.png"
    Image.new("RGB", (12, 12), color=(224, 128, 32)).save(image_path)
    monkeypatch.chdir(tmp_path)

    dataset = Dataset("runtime_relative_media", persist=False)
    sample = dataset.add_image("relative.png", label="orange", sample_id="sample-1")

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
    runtime.set_similarity_query(
        "default",
        runtime.resolve_similarity_query("default", "sample-1", source="test"),
    )

    workspace = runtime.set_workspace_dataset("default", "second-dataset")

    assert workspace.dataset_name == "second-dataset"
    assert workspace.ui.active_layout_key is None
    assert workspace.ui.selected_ids == []
    assert workspace.ui.similarity_query is None

    snapshot = runtime.snapshot()
    assert snapshot["workspace"]["dataset_name"] == "second-dataset"
    assert snapshot["workspace"]["ui"]["active_layout_key"] is None
    assert snapshot["workspace"]["ui"]["selected_ids"] == []
    assert snapshot["workspace"]["ui"]["similarity_query"] is None


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
    assert [panel.id for panel in runtime.get_workspace("default").ui.custom_panels] == ["demo-panel"]
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
    assert [panel.id for panel in runtime.get_workspace("default").ui.custom_panels] == ["demo-panel"]
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
