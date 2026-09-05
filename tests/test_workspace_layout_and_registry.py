"""Phase 7 coverage: workspace layout commands and the single panel registry."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.extensions import load_core_panel_definitions
from hyperview.runtime import (
    CustomPanelSpec,
    HyperViewRuntime,
    ProviderRegistry,
    WorkspaceRegistry,
)


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


def test_replacing_declared_view_invalidates_persisted_dockview_layout(
    tmp_path: Path,
) -> None:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.set_workspace_layout("default", {"activeGroup": "stale"})

    runtime.replace_custom_panels(
        "default",
        [CustomPanelSpec(id="samples", title="Samples", kind="builtin", builtin_panel="samples")],
        has_explicit_view=True,
    )

    workspace = runtime.get_workspace("default")
    assert workspace.ui.layout is None
    assert workspace.ui.layout_revision == 2

    runtime.set_workspace_layout("default", {"activeGroup": "stale-again"})
    runtime.replace_custom_panels(
        "default",
        [CustomPanelSpec(id="samples", title="Samples", kind="builtin", builtin_panel="samples")],
        has_explicit_view=True,
    )

    workspace = runtime.get_workspace("default")
    assert workspace.ui.layout is None
    assert workspace.ui.layout_revision == 4


def test_builtin_registry_covers_every_ui_panel_type(tmp_path: Path) -> None:
    definitions = {
        definition.panel_type: definition for definition in load_core_panel_definitions()
    }

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
        assert definition.source == "shipped"
        assert definition.renderer == f"native:{definition.panel_type}"
        assert definition.default_layout.get("id"), "default layout needs a stable panel id"
        assert definition.props_schema is not None
        assert definition.state_schema is not None
        assert definition.data_capabilities


def test_frontend_panel_registry_does_not_duplicate_runtime_metadata() -> None:
    root = Path(__file__).resolve().parents[1]
    registry_source = (root / "frontend/src/panels/registry.tsx").read_text()
    header_source = (root / "frontend/src/components/Header.tsx").read_text()

    assert "CENTER_PANEL_DEFS" not in registry_source
    assert "CENTER_PANEL_DEFS" not in header_source
    assert "definition.label" in header_source
    assert "definition.default_layout" in header_source


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


def test_parallel_workspace_registries_do_not_clobber_sibling_updates(tmp_path: Path) -> None:
    registry_path = tmp_path / "workspaces.json"
    first = WorkspaceRegistry(registry_path)
    first.create_workspace("space-a")
    first.create_workspace("space-b")

    runtime_a = WorkspaceRegistry(registry_path)
    runtime_b = WorkspaceRegistry(registry_path)
    space_a = runtime_a.get("space-a")
    space_b = runtime_b.get("space-b")
    assert space_a is not None
    assert space_b is not None

    space_a.dataset_name = "dataset-a-new"
    runtime_a.update_workspace(space_a)
    space_b.dataset_name = "dataset-b-new"
    runtime_b.update_workspace(space_b)

    reloaded = WorkspaceRegistry(registry_path)
    assert reloaded.get("space-a").dataset_name == "dataset-a-new"
    assert reloaded.get("space-b").dataset_name == "dataset-b-new"


def test_workspace_registry_reads_remain_valid_during_writes(tmp_path: Path) -> None:
    registry_path = tmp_path / "workspaces.json"
    registry = WorkspaceRegistry(registry_path)
    for index in range(40):
        registry.create_workspace(f"space-{index}")

    stop = threading.Event()
    parse_errors: list[Exception] = []

    def read_registry() -> None:
        while not stop.is_set():
            try:
                json.loads(registry_path.read_text(encoding="utf-8"))
            except Exception as exc:  # pragma: no cover - only populated on regression
                parse_errors.append(exc)
                stop.set()

    reader = threading.Thread(target=read_registry)
    reader.start()
    try:
        for index in range(40):
            workspace = registry.get(f"space-{index}")
            assert workspace is not None
            workspace.dataset_name = f"dataset-{index}"
            registry.update_workspace(workspace)
    finally:
        stop.set()
        reader.join(timeout=5)

    assert not parse_errors


def test_runtime_config_dir_follows_hyperview_home(monkeypatch, tmp_path) -> None:
    from hyperview.runtime import get_runtime_config_dir
    from hyperview.storage.config import get_default_datasets_dir, get_default_media_dir

    home = tmp_path / "home"
    monkeypatch.setenv("HYPERVIEW_HOME", str(home))
    monkeypatch.delenv("HYPERVIEW_DATASETS_DIR", raising=False)
    monkeypatch.delenv("HYPERVIEW_MEDIA_DIR", raising=False)

    assert get_default_datasets_dir() == home / "datasets"
    assert get_default_media_dir() == home / "media"
    assert get_runtime_config_dir() == home

    # A datasets dir elsewhere moves the data, not the registries.
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(tmp_path / "elsewhere" / "datasets"))
    assert get_runtime_config_dir() == home


def test_runtime_config_dir_without_home_is_the_datasets_parent(monkeypatch, tmp_path) -> None:
    from hyperview.runtime import get_runtime_config_dir

    monkeypatch.delenv("HYPERVIEW_HOME", raising=False)
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(tmp_path / "run" / "datasets"))
    assert get_runtime_config_dir() == tmp_path / "run"
