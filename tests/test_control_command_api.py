from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.server.app import create_app


def _client_with_panel(tmp_path: Path) -> TestClient:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.add_runtime_panel(
        "default",
        panel_id="samples",
        kind="builtin",
        builtin_panel="samples",
        position="right",
        width=320,
        min_width=240,
    )
    return TestClient(create_app(runtime=runtime))


def test_control_commands_endpoint_lists_backend_panel_commands(tmp_path: Path) -> None:
    client = _client_with_panel(tmp_path)

    response = client.get("/api/control/commands")

    assert response.status_code == 200
    command_ids = {command["id"] for command in response.json()["commands"]}
    assert {
        "workspace.panel.resize",
        "workspace.panel.move",
        "workspace.panel.close",
        "workspace.panel.show",
        "workspace.panel.focus",
        "workspace.panel.add",
        "workspace.panel.update",
        "workspace.panel.remove",
        "workspace.panel.state.get",
        "workspace.panel.state.patch",
        "panel.samples.retrieval.set-anchor",
        "panel.samples.retrieval.set-text-query",
        "panel.samples.retrieval.clear",
        "panel.samples.retrieval.set-k",
        "collection.filter.set",
        "collection.neighbors.create",
    }.issubset(command_ids)
    commands = {command["id"]: command for command in response.json()["commands"]}
    add_kind_schema = commands["workspace.panel.add"]["args_schema"]["properties"]["kind"]
    assert "module" not in add_kind_schema["enum"]
    builtin_panel_schema = commands["workspace.panel.add"]["args_schema"]["properties"][
        "builtin_panel"
    ]
    assert "samples" not in str(builtin_panel_schema.get("enum", ""))


def test_control_command_run_mutates_runtime_panel_state(tmp_path: Path) -> None:
    client = _client_with_panel(tmp_path)

    resize_response = client.post(
        "/api/control/commands/run",
        json={
            "command": "workspace.panel.resize",
            "target": {"workspace_id": "default", "panel_id": "samples"},
            "args": {"width": 420, "min_width": None},
        },
    )

    assert resize_response.status_code == 200
    resize_payload = resize_response.json()
    assert resize_payload["ok"] is True
    assert resize_payload["workspace"]["ui"]["custom_panels"][0]["width"] == 420
    assert resize_payload["snapshot"]["workspace"]["ui"]["custom_panels"][0]["width"] == 420
    assert resize_payload["snapshot"]["panel_definitions"]
    assert resize_payload["workspace"]["ui"]["custom_panels"][0]["min_width"] is None

    focus_response = client.post(
        "/api/control/commands/run",
        json={
            "command": "workspace.panel.focus",
            "target": {"workspace_id": "default", "panel_id": "samples"},
        },
    )

    assert focus_response.status_code == 200
    focus_payload = focus_response.json()
    assert focus_payload["ok"] is True
    assert focus_payload["workspace"]["ui"]["active_panel_id"] == "samples"


def test_control_command_run_returns_machine_readable_errors(tmp_path: Path) -> None:
    client = _client_with_panel(tmp_path)

    response = client.post(
        "/api/control/commands/run",
        json={
            "command": "workspace.panel.resize",
            "target": {"workspace_id": "default", "panel_id": "missing"},
            "args": {"width": 420},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_deprecated_alias_warning_is_returned_by_control_api(tmp_path: Path) -> None:
    client = _client_with_panel(tmp_path)

    response = client.post(
        "/api/control/commands/run",
        json={
            "command": "ui.panel.resize",
            "target": {"workspace_id": "default", "panel_id": "samples"},
            "args": {"width": 420},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["command"] == "workspace.panel.resize"
    assert payload["messages"] == [
        "Deprecated command 'ui.panel.resize'; use 'workspace.panel.resize' instead. "
        "This alias will be removed after 2026-10-01."
    ]


def test_panel_rest_adapter_routes_are_not_registered(tmp_path: Path) -> None:
    client = _client_with_panel(tmp_path)

    route_paths = {getattr(route, "path", "") for route in client.app.routes}
    assert not any(path.startswith("/api/control/ui/panels") for path in route_paths)
