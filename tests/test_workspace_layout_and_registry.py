"""Phase 7 coverage: workspace layout commands and the single panel registry."""

from __future__ import annotations

from pathlib import Path

from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.panel_definitions import BUILTIN_PANEL_DEFINITIONS
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry


def _service(tmp_path: Path) -> ControlService:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    return ControlService(runtime, create_default_command_registry())


def test_workspace_layout_set_get_round_trip(tmp_path: Path) -> None:
    service = _service(tmp_path)

    initial = service.run(
        CommandEnvelope(
            command="workspace.layout.get",
            target={"workspace_id": "default"},
            args={},
        )
    )
    assert initial.ok
    assert initial.result == {"layout": None, "layout_revision": 0}

    layout = {"grid": {"root": {}}, "panels": {"samples": {"id": "samples"}}}
    updated = service.run(
        CommandEnvelope(
            command="workspace.layout.set",
            target={"workspace_id": "default"},
            args={"layout": layout, "client_id": "client-a"},
        )
    )
    assert updated.ok
    assert updated.result["layout"] == layout
    assert updated.result["layout_revision"] == 1

    fetched = service.run(
        CommandEnvelope(
            command="workspace.layout.get",
            target={"workspace_id": "default"},
            args={},
        )
    )
    assert fetched.ok
    assert fetched.result["layout"] == layout
    assert fetched.result["layout_revision"] == 1

    cleared = service.run(
        CommandEnvelope(
            command="workspace.layout.set",
            target={"workspace_id": "default"},
            args={"layout": None},
        )
    )
    assert cleared.ok
    assert cleared.result["layout"] is None
    assert cleared.result["layout_revision"] == 2


def test_workspace_layout_set_rejects_stale_revision(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.run(
        CommandEnvelope(
            command="workspace.layout.set",
            target={"workspace_id": "default"},
            args={"layout": {"grid": {}}},
        )
    )

    stale = service.run(
        CommandEnvelope(
            command="workspace.layout.set",
            target={"workspace_id": "default"},
            args={"layout": {"grid": {"changed": True}}, "expected_revision": 0},
        )
    )
    assert not stale.ok
    assert stale.error is not None
    assert stale.error.code == "conflict"


def test_workspace_layout_appears_in_snapshot(tmp_path: Path) -> None:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    layout = {"grid": {}, "panels": {}}
    runtime.set_workspace_layout("default", layout, source_client_id="client-a")

    snapshot = runtime.snapshot("default")
    ui_state = snapshot["workspace"]["ui"]
    assert ui_state["layout"] == layout
    assert ui_state["layout_revision"] == 1


def test_builtin_registry_covers_every_ui_panel_type(tmp_path: Path) -> None:
    definitions = {definition.panel_type: definition for definition in BUILTIN_PANEL_DEFINITIONS}

    # The frontend registry maps exactly these panel types to components.
    assert set(definitions) >= {"samples", "scatter", "explorer"}

    scatter = definitions["scatter"]
    presets = scatter.default_props.get("presets")
    assert isinstance(presets, dict) and presets, "scatter variants must live in presets"
    assert scatter.default_props.get("preset") in presets
    for preset in presets.values():
        assert preset.get("geometry")
        assert preset.get("layout_dimension") in (2, 3)

    explorer = definitions["explorer"]
    assert explorer.allow_multiple is False

    for definition in definitions.values():
        assert definition.default_layout.get("id"), "default layout needs a stable panel id"


def test_legacy_workspace_payload_without_layout_still_loads(tmp_path: Path) -> None:
    registry_path = tmp_path / "workspaces.json"
    service = _service(tmp_path)
    service.run(
        CommandEnvelope(
            command="workspace.layout.set",
            target={"workspace_id": "default"},
            args={"layout": {"grid": {}}},
        )
    )

    # Simulate a registry written before workspace layouts existed.
    import json

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    for workspace in payload.get("workspaces", []):
        workspace.get("ui", {}).pop("layout", None)
        workspace.get("ui", {}).pop("layout_revision", None)
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(registry_path),
    )
    state = reloaded.get_workspace_layout("default")
    assert state == {"layout": None, "layout_revision": 0}
