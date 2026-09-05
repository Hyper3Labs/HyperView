"""Session authentication and local server discovery helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from hyperview.capabilities import command_allowed_in_mode
from hyperview.storage.config import StorageConfig

_LOCAL_HOST_NAMES = frozenset({"localhost", "0.0.0.0", "::"})


def is_local_host(host: str | None) -> bool:
    """Return whether ``host`` names this machine.

    The discovery file records a token some server on *this* machine minted,
    keyed only by port. Nothing stops a remote host from listening on the same
    port, so every automatic use of that token has to check where the request
    is actually going first -- otherwise the CLI hands a local session token to
    whoever answers.
    """

    if not host:
        return False
    candidate = host.strip("[]").lower()
    if candidate in _LOCAL_HOST_NAMES:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def auth_disabled() -> bool:
    """Return whether local API authentication was explicitly disabled."""

    return os.environ.get("HYPERVIEW_NO_AUTH") == "1"


def mint_api_token() -> str | None:
    """Mint a session token unless authentication is explicitly disabled."""

    return None if auth_disabled() else secrets.token_urlsafe(24)


def browser_url(base_url: str, token: str | None) -> str:
    """Add the session token to a browser URL without dropping existing query values."""

    if token is None:
        return base_url
    parts = urlsplit(base_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("token", token))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def server_info_path(port: int) -> Path:
    """Return the discovery-file path for a local server port."""

    return StorageConfig.default().datasets_dir.parent / f"server-{port}.json"


def write_server_info(port: int, token: str | None) -> Path | None:
    """Write local server discovery metadata, returning ``None`` on best-effort failure."""

    path = server_info_path(port)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = {
        "port": port,
        "token": token,
        "pid": os.getpid(),
        "created_at": time.time(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
        return path
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def read_server_info(port: int) -> dict[str, Any] | None:
    """Read discovery metadata when it is valid and belongs to the requested port."""

    try:
        payload = json.loads(server_info_path(port).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("port") != port:
        return None
    return payload


def remove_server_info(port: int, token: str | None) -> None:
    """Remove this process's discovery file without deleting a replacement server's file."""

    path = server_info_path(port)
    payload = read_server_info(port)
    if payload is None:
        return
    if payload.get("pid") != os.getpid() or payload.get("token") != token:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# Commands a visitor may run on a server that has no session token. They change
# what the viewer sees -- panels, selection, retrieval, collections -- and
# nothing else. Everything outside this set stays closed even under
# HYPERVIEW_NO_AUTH=1, because the rest of the command surface imports
# arbitrary modules, installs extension code, or starts unbounded compute.
#
# The set itself lives in hyperview.capabilities, which is the one table a Live
# Space, a Static Space export manifest, and the frontend all read.
def command_allowed_without_token(command: str) -> bool:
    """Return whether an anonymous visitor may run ``command``."""

    return command_allowed_in_mode(command, "live")
