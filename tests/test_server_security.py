from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from hyperview.capabilities import viewer_commands
from hyperview.cli import _http_headers
from hyperview.runtime import HyperViewRuntime
from hyperview.server.app import create_app
from hyperview.server.security import (
    command_allowed_without_token,
    read_server_info,
    remove_server_info,
    server_info_path,
    write_server_info,
)


def _runtime() -> HyperViewRuntime:
    runtime = HyperViewRuntime()
    runtime.workspace_registry.ensure_workspace("default", activate=True)
    return runtime


def test_mutating_api_route_requires_session_token() -> None:
    app = create_app(runtime=_runtime(), api_token="secret-token")
    client = TestClient(app)

    response = client.post(
        "/api/control/ui/selection",
        json={"workspace_id": "default", "sample_ids": []},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": (
            "Missing or invalid HyperView session token. "
            "Send Authorization: Bearer <token> or ?token=<token>."
        )
    }


def test_tool_run_route_requires_session_token() -> None:
    app = create_app(runtime=_runtime(), api_token="secret-token")
    client = TestClient(app)
    payload = {
        "tool": "missing.tool",
        "workspace_id": "default",
        "params": {},
    }

    unauthenticated_response = client.post("/api/tools/run", json=payload)
    authenticated_response = client.post(
        "/api/tools/run",
        json=payload,
        headers={"Authorization": "Bearer secret-token"},
    )

    assert unauthenticated_response.status_code == 401
    assert authenticated_response.status_code == 404


def test_mutating_api_route_accepts_bearer_or_query_token() -> None:
    app = create_app(runtime=_runtime(), api_token="secret-token")
    client = TestClient(app)
    payload = {"workspace_id": "default", "sample_ids": []}

    bearer_response = client.post(
        "/api/control/ui/selection",
        json=payload,
        headers={"Authorization": "Bearer secret-token"},
    )
    query_response = client.post(
        "/api/control/ui/selection?token=secret-token",
        json=payload,
    )

    assert bearer_response.status_code == 200
    assert query_response.status_code == 200


def test_no_auth_environment_bypasses_mutation_authentication(monkeypatch) -> None:
    monkeypatch.setenv("HYPERVIEW_NO_AUTH", "1")
    app = create_app(runtime=_runtime(), api_token="ignored-token")

    response = TestClient(app).post(
        "/api/control/ui/selection",
        json={"workspace_id": "default", "sample_ids": []},
    )

    assert response.status_code == 200
    assert app.state.api_token is None


def test_cors_uses_local_allowlist_and_extra_origins(monkeypatch) -> None:
    monkeypatch.setenv(
        "HYPERVIEW_EXTRA_ORIGINS",
        "https://trusted.example, https://second.example ",
    )
    client = TestClient(create_app(runtime=_runtime(), api_token="secret-token", port=7123))

    for origin in (
        "http://127.0.0.1:7123",
        "http://localhost:7123",
        "http://localhost:6363",
        "http://127.0.0.1:6363",
        "https://trusted.example",
        "https://second.example",
    ):
        response = client.options(
            "/api/control/ui/selection",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in response.headers

    rejected = client.options(
        "/api/control/ui/selection",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_server_info_drives_cli_bearer_header_and_cleanup(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(tmp_path / "datasets"))
    path = write_server_info(7444, "discovered-token")

    assert path == server_info_path(7444)
    assert path is not None
    info = read_server_info(7444)
    assert info is not None
    assert info["port"] == 7444
    assert info["token"] == "discovered-token"
    assert info["pid"] == os.getpid()
    assert isinstance(info["created_at"], float)
    assert json.loads(path.read_text(encoding="utf-8")) == info
    assert _http_headers("http://127.0.0.1:7444/api/runtime")["Authorization"] == (
        "Bearer discovered-token"
    )

    monkeypatch.setenv("HYPERVIEW_API_TOKEN", "override-token")
    assert _http_headers("http://127.0.0.1:7444/api/runtime")["Authorization"] == (
        "Bearer override-token"
    )

    remove_server_info(7444, "discovered-token")
    assert not path.exists()


def test_discovered_token_never_reaches_a_remote_host(tmp_path, monkeypatch) -> None:
    """A remote host on the same port must not be handed the local token."""

    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(tmp_path / "datasets"))
    monkeypatch.delenv("HYPERVIEW_API_TOKEN", raising=False)
    write_server_info(7444, "local-secret")

    for local_url in (
        "http://127.0.0.1:7444/api/runtime",
        "http://localhost:7444/api/runtime",
        "http://[::1]:7444/api/runtime",
        "http://0.0.0.0:7444/api/runtime",
    ):
        assert _http_headers(local_url)["Authorization"] == "Bearer local-secret"

    for remote_url in (
        "https://remote.example:7444/api/runtime",
        "http://10.0.0.5:7444/api/runtime",
        "http://[2001:db8::1]:7444/api/runtime",
    ):
        assert "Authorization" not in _http_headers(remote_url)

    # A remote server still reachable when the caller supplies the token.
    monkeypatch.setenv("HYPERVIEW_API_TOKEN", "explicit-token")
    assert _http_headers("https://remote.example:7444/api/runtime")["Authorization"] == (
        "Bearer explicit-token"
    )

    remove_server_info(7444, "local-secret")


def test_public_server_still_refuses_privileged_commands(monkeypatch) -> None:
    """HYPERVIEW_NO_AUTH=1 opens the viewer surface, not the whole control plane."""

    monkeypatch.setenv("HYPERVIEW_NO_AUTH", "1")
    client = TestClient(create_app(runtime=_runtime()))

    # Registering a provider imports an arbitrary module by name.
    blocked = client.post(
        "/api/control/provider/register",
        json={"alias": "pwn", "import_path": "os:system"},
    )
    assert blocked.status_code == 403
    assert "authenticated session" in blocked.json()["detail"]

    # The generic dispatcher must not be a way around the route-level guard.
    dispatched = client.post(
        "/api/control/commands/run",
        json={
            "command": "provider.register",
            "target": {"alias": "pwn"},
            "args": {"import_path": "os:system"},
        },
    )
    assert dispatched.status_code == 403

    for path, payload in (
        ("/api/control/extensions/install", {"workspace_id": "default", "source": "."}),
        (
            "/api/control/embeddings/compute",
            {"workspace_id": "default", "dataset_name": "d", "model": "x"},
        ),
        (
            "/api/control/layouts/compute",
            {"workspace_id": "default", "dataset_name": "d", "layouts": ["euclidean"]},
        ),
        ("/api/tools/run", {"tool": "anything", "workspace_id": "default", "params": {}}),
    ):
        assert client.post(path, json=payload).status_code == 403, path

    # What a Space visitor actually does stays open.
    allowed = client.post(
        "/api/control/ui/selection",
        json={"workspace_id": "default", "sample_ids": []},
    )
    assert allowed.status_code == 200


def test_public_command_allowlist_covers_viewer_actions() -> None:
    for command in (
        "workspace.panel.add",
        "workspace.panel.state.patch",
        "workspace.selection.set",
        "workspace.active-layout.set",
        "workspace.layout.set",
        "panel.samples.retrieval.set-text-query",
        "collection.search.create",
        "collection.filter.set",
    ):
        assert command_allowed_without_token(command), command

    for command in (
        "provider.register",
        "provider.unregister",
        "extension.install",
        "extension.remove",
        "embeddings.compute",
        "layouts.compute",
        "workspace.create",
        "workspace.delete",
        "workspace.activate",
        "workspace.dataset.set",
    ):
        assert not command_allowed_without_token(command), command


def test_capabilities_endpoint_reports_the_live_table(monkeypatch) -> None:
    """A Live Space publishes the same contract a Static Space ships (D6)."""

    app = create_app(runtime=_runtime(), api_token="secret-token")
    payload = TestClient(app).get("/api/capabilities").json()

    assert payload["mode"] == "live"
    assert payload["commands"] == viewer_commands("live")
    assert payload["text_search"] is True
    assert payload["python_tools"] is True
    assert payload["server_runtime"] is True
    assert payload["public"] is False

    monkeypatch.setenv("HYPERVIEW_NO_AUTH", "1")
    public_app = create_app(runtime=_runtime())
    assert TestClient(public_app).get("/api/capabilities").json()["public"] is True
