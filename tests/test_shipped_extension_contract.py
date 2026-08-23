from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import hyperview as hv
from hyperview.core.sample import Sample
from hyperview.extensions import resolve_shipped_extension
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.server.app import create_app
from hyperview.static_export import export_runtime_workspace


def _runtime(tmp_path: Path, name: str) -> HyperViewRuntime:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / f"{name}-providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / f"{name}-workspaces.json"),
    )
    dataset = hv.Dataset("reference-contract", persist=False)
    dataset.add_sample(Sample(id="sample-1", text="Reference row", label="reference"))
    runtime.attach_dataset_instance("demo", dataset, activate_workspace=True)
    return runtime


def _portable_definition(definition: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in definition.items() if key != "source"}


def test_reference_extension_promotes_without_source_changes(tmp_path: Path) -> None:
    shipped_folder = resolve_shipped_extension("reference")
    local_folder = tmp_path / ".hyperview" / "extensions" / "reference"
    shutil.copytree(shipped_folder, local_folder)

    for file_name in ("extension.toml", "panel.jsx", "tools.py"):
        assert (local_folder / file_name).read_bytes() == (shipped_folder / file_name).read_bytes()

    local_runtime = _runtime(tmp_path, "local")
    local = local_runtime.install_extension("demo", local_folder, add_panels=True)

    shipped_runtime = _runtime(tmp_path, "shipped")
    shipped_session = hv.Session(shipped_runtime, "127.0.0.1", 6262)
    shipped = shipped_session.ui.add_shipped_extension(
        "reference",
        workspace_id="demo",
        add_panels=True,
    )

    local_definition = local.to_dict()["panel_definitions"][0]
    shipped_definition = shipped.to_dict()["panel_definitions"][0]
    assert local_definition["source"] == "extension"
    assert shipped_definition["source"] == "shipped"
    assert _portable_definition(local_definition) == _portable_definition(shipped_definition)
    assert shipped_definition["commands"] == ["workspace.panel.state.patch"]
    assert shipped_definition["queries"] == ["samples.query"]
    assert shipped_definition["data_capabilities"] == ["collection:samples", "selection"]
    assert shipped_definition["static_compatible"] is True

    local_panel = local_runtime.get_workspace("demo").ui.custom_panels[0]
    shipped_panel = shipped_runtime.get_workspace("demo").ui.custom_panels[0]
    assert local_panel.resolved_module_file().read_bytes() == shipped_panel.resolved_module_file().read_bytes()
    assert local_panel.props == shipped_panel.props == {"heading": "Extension contract"}
    assert local_runtime.get_panel_state("demo", "reference")["state"] == {
        "notes": "",
        "collection_id": "",
    }
    assert shipped_runtime.get_panel_state("demo", "reference")["state"] == {
        "notes": "",
        "collection_id": "",
    }
    assert local_runtime.run_tool("reference.describe", workspace_id="demo") == (
        shipped_runtime.run_tool("reference.describe", workspace_id="demo")
    )
    with pytest.raises(ValueError, match="panel 'reference' props.heading"):
        shipped_runtime.update_custom_panel(
            "demo",
            "reference",
            props={"heading": 42},
        )
    with pytest.raises(ValueError, match="panel 'reference' state.notes"):
        shipped_runtime.patch_panel_state("demo", "reference", {"notes": 42})

    output_dir = tmp_path / "static-reference"
    export_runtime_workspace(shipped_runtime, "demo", output_dir, similarity_k=0)
    snapshot = json.loads((output_dir / "api" / "runtime.json").read_text())
    exported_panel = snapshot["workspace"]["ui"]["custom_panels"][0]
    assert exported_panel["source"] == "shipped"
    assert exported_panel["data"]["static_compatible"] is True
    assert (output_dir / exported_panel["data"]["module_src"].lstrip("/")).is_file()


def test_shipped_extension_installs_through_authenticated_http_api(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "http")
    app = create_app(runtime=runtime)
    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {app.state.api_token}"},
    )

    response = client.post(
        "/api/control/extensions/install",
        json={"workspace_id": "demo", "shipped": "reference", "add_panels": True},
    )

    assert response.status_code == 200
    extension = response.json()["extension"]
    assert extension["name"] == "reference"
    assert extension["source"] == "shipped"
    assert extension["panels"] == ["reference"]


def test_extension_install_rejects_ambiguous_source(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, "ambiguous")
    app = create_app(runtime=runtime)
    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {app.state.api_token}"},
    )

    response = client.post(
        "/api/control/extensions/install",
        json={
            "workspace_id": "demo",
            "folder": str(resolve_shipped_extension("reference")),
            "shipped": "reference",
        },
    )

    assert response.status_code == 400
    assert "exactly one" in response.json()["detail"]
