"""The capability table is the only definition of the viewer surface (D6)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hyperview.capabilities import (
    HOSTING_MODES,
    capabilities_payload,
    capability_flags,
    capability_surface,
    command_allowed_in_mode,
    viewer_commands,
)
from hyperview.control import create_default_command_registry
from hyperview.server.security import command_allowed_without_token

ROOT = Path(__file__).resolve().parents[1]
GENERATED_TS = ROOT / "frontend" / "src" / "generated" / "capabilities.ts"


def test_public_server_allowlist_comes_from_the_table():
    """security.py decides nothing on its own; it asks the live mode."""

    for command in viewer_commands("live")["allowed"]:
        assert command_allowed_without_token(command)
    for prefix in viewer_commands("live")["allowed_prefixes"]:
        assert command_allowed_without_token(f"{prefix}example")
    for command in ("tools.run", "dataset.load", "extension.install", "jobs.cancel"):
        assert not command_allowed_without_token(command)
        assert not command_allowed_in_mode(command, "static")


def test_static_surface_is_a_subset_of_the_live_surface():
    """A Static Space may never run something a public Live Space refuses."""

    for command in viewer_commands("static")["allowed"]:
        assert command_allowed_in_mode(command, "live"), command
    assert viewer_commands("static")["allowed_prefixes"] == []


def test_static_mode_drops_what_needs_a_server():
    """D2: no text search, no new layouts, no Python tools in a bundle."""

    static = capability_flags("static")
    assert static["text_search"] is False
    assert static["new_layouts"] is False
    assert static["python_tools"] is False
    assert static["server_runtime"] is False
    assert static["panel_state"] == "ephemeral"
    assert "collection.search.create" not in viewer_commands("static")["allowed"]

    live = capability_flags("live")
    assert live["text_search"] is True
    assert live["python_tools"] is True
    assert live["panel_state"] == "durable"


def test_panel_target_commands_match_the_command_registry():
    """The commands whose target carries `panel_id` are not hand-listed twice."""

    registry = create_default_command_registry()
    from_registry = {
        metadata.id
        for metadata in registry.list_metadata()
        if metadata.target_schema.get("title") == "CollectionTarget"
    }
    assert set(viewer_commands("live")["panel_target"]) == from_registry


def test_every_mode_publishes_its_commands():
    for mode in HOSTING_MODES:
        payload = capabilities_payload(mode)
        assert payload["mode"] == mode
        assert set(payload["commands"]) == {"allowed", "allowed_prefixes", "panel_target"}


def test_overrides_narrow_but_do_not_rewrite_the_command_set():
    payload = capabilities_payload("static", layouts=False, sample_similarity=True)
    assert payload["layouts"] is False
    assert payload["sample_similarity"] is True
    assert payload["commands"] == viewer_commands("static")


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        capability_flags("public")  # type: ignore[arg-type]


def test_generated_frontend_table_is_not_stale():
    """frontend/src/generated/capabilities.ts is emitted, never edited."""

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "emit_capabilities_surface.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    emitted = GENERATED_TS.read_text(encoding="utf-8")
    marker = "export const CAPABILITY_MODES: Record<HostingMode, Capabilities> = "
    body = emitted.split(marker, 1)[1].rstrip().rstrip(";")
    assert json.loads(body) == capability_surface()["modes"]
