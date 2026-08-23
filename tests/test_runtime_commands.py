from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.runtime import HyperViewRuntime, JobState, ProviderRegistry, WorkspaceRegistry


def _service(tmp_path: Path) -> ControlService:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    return ControlService(runtime, create_default_command_registry())


def _run(
    service: ControlService,
    command: str,
    *,
    target: dict[str, object],
    args: dict[str, object] | None = None,
):
    return service.run(
        CommandEnvelope(command=command, target=target, args=args or {})
    )


def test_workspace_mutations_share_the_command_service(tmp_path: Path) -> None:
    service = _service(tmp_path)

    created = _run(
        service,
        "workspace.create",
        target={"workspace_id": "research"},
        args={"dataset_name": "birds", "activate": True},
    )
    assert created.ok is True
    assert created.snapshot is not None
    assert created.snapshot["active_workspace_id"] == "research"
    assert created.workspace is not None
    assert created.workspace["dataset_name"] == "birds"

    updated = _run(
        service,
        "workspace.state.patch",
        target={"workspace_id": "research"},
        args={
            "set_active_layout": True,
            "active_layout_key": "layout-a",
            "set_selection": True,
            "selected_ids": ["sample-a", "sample-a", "sample-b"],
        },
    )
    assert updated.ok is True
    assert updated.workspace is not None
    assert updated.workspace["ui"]["active_layout_key"] == "layout-a"
    assert updated.workspace["ui"]["selected_ids"] == ["sample-a", "sample-b"]

    camera = {
        "yaw": 0.1,
        "pitch": 0.2,
        "distance": 3.0,
        "target_x": 0.0,
        "target_y": 0.0,
        "target_z": 0.0,
        "ortho_scale": 1.0,
    }
    view = _run(
        service,
        "workspace.layout-view.set",
        target={"workspace_id": "research"},
        args={"layout_key": "layout-a", "camera_3d": camera},
    )
    assert view.ok is True
    assert view.result["view"] == {"camera_3d": camera}

    activated = _run(
        service,
        "workspace.activate",
        target={"workspace_id": "default"},
    )
    assert activated.ok is True
    assert activated.snapshot is not None
    assert activated.snapshot["active_workspace_id"] == "default"

    deleted = _run(
        service,
        "workspace.delete",
        target={"workspace_id": "research"},
    )
    assert deleted.ok is True
    assert deleted.result["deleted_workspace_id"] == "research"
    assert service.runtime.workspace_registry.get("research") is None


def test_provider_commands_are_discoverable_and_versioned(tmp_path: Path) -> None:
    service = _service(tmp_path)
    before = service.runtime.version

    registered = _run(
        service,
        "provider.register",
        target={"alias": "local"},
        args={"import_path": "hyperview.core.dataset:Dataset"},
    )
    assert registered.ok is True
    assert registered.result["provider"]["alias"] == "local"
    assert service.runtime.version == before + 1

    removed = _run(
        service,
        "provider.unregister",
        target={"alias": "local"},
    )
    assert removed.ok is True
    assert service.runtime.provider_registry.get("local") is None

    missing = _run(
        service,
        "provider.unregister",
        target={"alias": "missing"},
    )
    assert missing.ok is False
    assert missing.error is not None
    assert missing.error.code == "not_found"


def test_compute_commands_return_jobs_in_the_common_envelope(tmp_path: Path) -> None:
    service = _service(tmp_path)
    embedding_job = JobState(
        id="embedding-job",
        kind="embeddings.compute",
        workspace_id="default",
        dataset_name="birds",
    )
    layout_job = JobState(
        id="layout-job",
        kind="layouts.compute",
        workspace_id="default",
        dataset_name="birds",
    )

    with (
        patch.object(service.runtime, "submit_embedding_job", return_value=embedding_job) as embed,
        patch.object(service.runtime, "submit_layout_job", return_value=layout_job) as layout,
    ):
        embedding = _run(
            service,
            "embeddings.compute",
            target={"workspace_id": "default"},
            args={"dataset_name": "birds", "model": "clip"},
        )
        layouts = _run(
            service,
            "layouts.compute",
            target={"workspace_id": "default"},
            args={"dataset_name": "birds", "layouts": ["euclidean:2d"]},
        )

    assert embedding.ok is True
    assert embedding.result["job"]["id"] == "embedding-job"
    assert layouts.ok is True
    assert layouts.result["job"]["id"] == "layout-job"
    assert embed.call_args.kwargs["workspace_id"] == "default"
    assert layout.call_args.kwargs["workspace_id"] == "default"


def test_shipped_extension_install_and_remove_use_commands(tmp_path: Path) -> None:
    service = _service(tmp_path)

    installed = _run(
        service,
        "extension.install",
        target={"workspace_id": "default"},
        args={"shipped": "reference", "add_panels": True},
    )
    assert installed.ok is True
    assert installed.result["extension"]["source"] == "shipped"
    assert service.runtime.get_extension("reference") is not None
    assert installed.workspace is not None
    assert installed.workspace["ui"]["custom_panels"][0]["renderer"] == "module:panel.jsx"

    removed = _run(
        service,
        "extension.remove",
        target={"name": "reference"},
    )
    assert removed.ok is True
    assert service.runtime.get_extension("reference") is None
    assert removed.workspace is not None
    assert removed.workspace["ui"]["custom_panels"] == []


def test_runtime_command_schemas_are_in_discovery() -> None:
    commands = {
        item.id: item for item in create_default_command_registry().list_metadata()
    }
    assert {
        "workspace.create",
        "workspace.delete",
        "workspace.activate",
        "workspace.dataset.set",
        "workspace.active-layout.set",
        "workspace.selection.set",
        "workspace.state.patch",
        "workspace.layout-view.set",
        "provider.register",
        "provider.unregister",
        "embeddings.compute",
        "layouts.compute",
        "extension.install",
        "extension.remove",
    }.issubset(commands)
    assert commands["extension.install"].args_schema["additionalProperties"] is False


def test_complete_workspace_view_reproduces_from_snapshot_via_public_commands(
    tmp_path: Path,
) -> None:
    source = _service(tmp_path / "source")
    target = _service(tmp_path / "target")
    for service in (source, target):
        installed = _run(
            service,
            "extension.install",
            target={"workspace_id": "default"},
            args={"shipped": "reference"},
        )
        assert installed.ok is True

    for command, target_payload, args in (
        (
            "workspace.panel.add",
            {"workspace_id": "default"},
            {
                "panel_id": "samples",
                "kind": "builtin",
                "builtin_panel": "samples",
                "position": "center",
                "width": 420,
                "min_width": 280,
                "props": {"mode": "browse"},
            },
        ),
        (
            "workspace.panel.add",
            {"workspace_id": "default"},
            {
                "panel_id": "map",
                "kind": "scatter",
                "title": "Map",
                "layout_key": "layout-a",
                "position": "center",
                "reference_panel_id": "samples",
                "direction": "right",
                "require_resolved_layout": False,
            },
        ),
        (
            "workspace.panel.add",
            {"workspace_id": "default"},
            {
                "panel_id": "reference",
                "kind": "extension",
                "extension": "reference",
                "extension_panel": "reference",
                "position": "bottom",
                "height": 230,
                "visible": False,
                "props": {"heading": "Reproduced"},
            },
        ),
        (
            "workspace.panel.state.patch",
            {"workspace_id": "default", "panel_id": "reference"},
            {"state": {"notes": "durable note", "collection_id": ""}},
        ),
        (
            "workspace.active-layout.set",
            {"workspace_id": "default"},
            {"layout_key": "layout-a"},
        ),
        (
            "workspace.selection.set",
            {"workspace_id": "default"},
            {"sample_ids": ["sample-a", "sample-b"]},
        ),
        (
            "workspace.layout-view.set",
            {"workspace_id": "default"},
            {
                "layout_key": "layout-a",
                "camera_3d": {
                    "yaw": 0.25,
                    "pitch": 0.5,
                    "distance": 4.0,
                    "target_x": 0.0,
                    "target_y": 0.1,
                    "target_z": 0.2,
                    "ortho_scale": 1.25,
                },
            },
        ),
        (
            "workspace.layout.set",
            {"workspace_id": "default"},
            {
                "layout": {
                    "orientation": "horizontal",
                    "panels": ["samples", "map", "reference"],
                }
            },
        ),
        (
            "workspace.panel.focus",
            {"workspace_id": "default", "panel_id": "map"},
            {},
        ),
    ):
        result = _run(source, command, target=target_payload, args=args)
        assert result.ok is True, result.error

    source_ui = source.runtime.snapshot("default")["workspace"]["ui"]

    for panel in source_ui["custom_panels"]:
        if panel["kind"] == "module":
            add_args = {
                "panel_id": panel["id"],
                "kind": "extension",
                "extension": panel["extension"],
                "extension_panel": panel["extension_panel"],
            }
        elif panel["panel_type"] == "scatter" and panel["layout_key"]:
            add_args = {
                "panel_id": panel["id"],
                "kind": "scatter",
                "layout_key": panel["layout_key"],
                "require_resolved_layout": False,
            }
        else:
            add_args = {
                "panel_id": panel["id"],
                "kind": "builtin",
                "builtin_panel": panel["panel_type"],
            }
        add_args.update(
            {
                "title": panel["title"],
                "position": panel["position"],
                "reference_panel_id": panel["reference_panel_id"],
                "direction": panel["direction"],
                "width": panel["width"],
                "height": panel["height"],
                "min_width": panel["min_width"],
                "min_height": panel["min_height"],
                "max_width": panel["max_width"],
                "max_height": panel["max_height"],
                "visible": panel["visible"],
                "props": panel["props"],
            }
        )
        assert _run(
            target,
            "workspace.panel.add",
            target={"workspace_id": "default"},
            args=add_args,
        ).ok

    for panel_id, state in source_ui["panels"].items():
        if panel_id not in {panel["id"] for panel in source_ui["custom_panels"]}:
            continue
        assert _run(
            target,
            "workspace.panel.state.patch",
            target={"workspace_id": "default", "panel_id": panel_id},
            args={"state": state["state"], "replace_state": True},
        ).ok

    assert _run(
        target,
        "workspace.active-layout.set",
        target={"workspace_id": "default"},
        args={"layout_key": source_ui["active_layout_key"]},
    ).ok
    assert _run(
        target,
        "workspace.selection.set",
        target={"workspace_id": "default"},
        args={"sample_ids": source_ui["selected_ids"]},
    ).ok
    for layout_key, view in source_ui["layout_views"].items():
        assert _run(
            target,
            "workspace.layout-view.set",
            target={"workspace_id": "default"},
            args={"layout_key": layout_key, **view},
        ).ok
    assert _run(
        target,
        "workspace.layout.set",
        target={"workspace_id": "default"},
        args={"layout": source_ui["layout"]},
    ).ok
    assert _run(
        target,
        "workspace.panel.focus",
        target={
            "workspace_id": "default",
            "panel_id": source_ui["active_panel_id"],
        },
    ).ok

    target_ui = target.runtime.snapshot("default")["workspace"]["ui"]
    comparable_fields = (
        "active_layout_key",
        "selected_ids",
        "layout",
        "layout_views",
        "custom_panels",
        "active_panel_id",
    )
    for field in comparable_fields:
        assert target_ui[field] == source_ui[field]
    assert {
        panel_id: entry["state"] for panel_id, entry in target_ui["panels"].items()
    } == {
        panel_id: entry["state"] for panel_id, entry in source_ui["panels"].items()
    }
