from __future__ import annotations

import json
import os

from fastapi.testclient import TestClient

from hyperview.cli import _http_headers
from hyperview.runtime import HyperViewRuntime
from hyperview.server.app import create_app
from hyperview.server.security import (
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
