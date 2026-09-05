"""The one table that says what a HyperView host lets a viewer do.

Read-only HyperView used to be specified four times: the Static Space export
manifest, the ``isStaticBundle()`` branches in the frontend, the static command
allowlist in the frontend's emulator, and the public-server allowlist in
``hyperview.server.security``. This module is the single definition all four
now derive from (D6 in ``docs/architecture-plan-2026-09.md``):

* :func:`command_allowed_in_mode` backs
  ``hyperview.server.security.command_allowed_without_token``.
* :func:`capabilities_payload` writes the ``capabilities`` block of the export
  manifest, so a Static Space ships its own contract.
* ``GET /api/capabilities`` serves the same payload for a Live Space.
* ``scripts/emit_capabilities_surface.py`` writes
  ``frontend/src/generated/capabilities.ts`` from it, so the frontend never
  keeps a hand-maintained copy of any of it.

Two hosting modes exist, and the difference between them is encoded here rather
than in a second list:

``live``
    ``hyperview serve``, including ``--public`` (a Live Space). A Python
    runtime answers, so everything the viewer surface names is executable.

``static``
    An exported bundle on a static host (a Static Space). The browser emulates
    the control plane, so only the commands it can carry out locally are in the
    set, and the flags that need a server -- text search, new layouts, Python
    tools, durable state -- are off (D2).

Mode flags say what the *host* permits. Facts that depend on the exported data
-- whether a 2-D layout exists, whether similarity was precomputed, which
panels survived the export -- narrow them further and are passed to
:func:`capabilities_payload` as overrides by the exporter.
"""

from __future__ import annotations

from typing import Any, Literal

__all__ = [
    "HOSTING_MODES",
    "HostingMode",
    "capabilities_payload",
    "capability_flags",
    "capability_surface",
    "command_allowed_in_mode",
    "viewer_commands",
]

HostingMode = Literal["live", "static"]

HOSTING_MODES: tuple[HostingMode, ...] = ("live", "static")

# Commands a visitor may run on a server that has no session token. They change
# what the viewer sees -- panels, selection, retrieval, collections -- and
# nothing else. Everything outside this set stays closed even under
# HYPERVIEW_NO_AUTH=1, because the rest of the command surface imports
# arbitrary modules, installs extension code, or starts unbounded compute.
_LIVE_COMMAND_PREFIXES: tuple[str, ...] = ("workspace.panel.", "panel.", "collection.")
_LIVE_COMMANDS: frozenset[str] = frozenset(
    {
        "workspace.active-layout.set",
        "workspace.selection.set",
        "workspace.state.patch",
        "workspace.layout-view.set",
        "workspace.layout.get",
        "workspace.layout.set",
    }
)

# The subset a Static Space can carry out with no server: the browser rewrites
# its own copy of the runtime snapshot. There are no prefixes here because the
# emulator implements named commands, not families -- an extension panel's own
# `panel.*` command has no handler in a bundle and must be refused, not
# silently accepted. `collection.search.create` is absent for the same reason
# text_search is False: a text query needs a model.
_STATIC_COMMANDS: frozenset[str] = frozenset(
    {
        "collection.filter.set",
        "collection.neighbors.create",
        "collection.selection.set",
        "panel.samples.retrieval.set-anchor",
        "workspace.panel.focus",
        "workspace.panel.state.patch",
        "workspace.panel.update",
        "workspace.panel.update-props",
    }
)

# The commands whose target carries an optional `panel_id`. These are exactly
# the CommandSpecs declaring `CollectionTarget` in
# src/hyperview/control/ui_panel.py; tests/test_capabilities_contract.py fails
# when the two drift.
_PANEL_TARGET_COMMANDS: frozenset[str] = frozenset(
    {
        "collection.filter.set",
        "collection.neighbors.create",
        "collection.search.create",
        "collection.selection.set",
        "panel.samples.retrieval.set-anchor",
    }
)

_COMMANDS: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    "live": (_LIVE_COMMANDS, _LIVE_COMMAND_PREFIXES),
    "static": (_STATIC_COMMANDS, ()),
}

# What each hosting mode permits, before the exported data narrows it.
_FLAGS: dict[str, dict[str, Any]] = {
    "live": {
        "browse_samples": True,
        "layouts": True,
        "selection": True,
        "lasso_2d": True,
        "lasso_3d": True,
        "sample_similarity": True,
        "similarity_k": 0,
        "text_search": True,
        "new_layouts": True,
        "python_tools": True,
        "runtime_mutations": True,
        "server_runtime": True,
        "panel_state": "durable",
    },
    "static": {
        "browse_samples": True,
        "layouts": True,
        "selection": True,
        "lasso_2d": True,
        "lasso_3d": False,
        # Precomputed similarity is only present when the export wrote it, so
        # the mode default is off and `capabilities_payload` turns it on.
        "sample_similarity": False,
        "similarity_k": 0,
        "text_search": False,
        "new_layouts": False,
        "python_tools": False,
        "runtime_mutations": False,
        "server_runtime": False,
        "panel_state": "ephemeral",
    },
}


def _resolve(mode: str) -> HostingMode:
    if mode not in _FLAGS:
        raise ValueError(f"Unknown hosting mode: {mode!r}; expected one of {HOSTING_MODES}")
    return mode  # type: ignore[return-value]


def viewer_commands(mode: HostingMode = "live") -> dict[str, list[str]]:
    """Return the command surface a viewer may drive in ``mode``."""

    commands, prefixes = _COMMANDS[_resolve(mode)]
    return {
        "allowed": sorted(commands),
        "allowed_prefixes": list(prefixes),
        "panel_target": sorted(_PANEL_TARGET_COMMANDS),
    }


def command_allowed_in_mode(command: str, mode: HostingMode = "live") -> bool:
    """Return whether ``command`` is inside the viewer surface of ``mode``."""

    commands, prefixes = _COMMANDS[_resolve(mode)]
    return command in commands or (bool(prefixes) and command.startswith(prefixes))


def capability_flags(mode: HostingMode) -> dict[str, Any]:
    """Return the capability flags ``mode`` permits, before data narrows them."""

    return dict(_FLAGS[_resolve(mode)])


def capabilities_payload(mode: HostingMode, **overrides: Any) -> dict[str, Any]:
    """Return the ``capabilities`` block a host of ``mode`` publishes.

    ``overrides`` carry the facts only the caller knows: whether the export has
    layouts, whether similarity was precomputed, which panels survived.
    """

    payload: dict[str, Any] = {"mode": _resolve(mode)}
    payload.update(capability_flags(mode))
    payload.update(overrides)
    payload["commands"] = viewer_commands(mode)
    return payload


def capability_surface() -> dict[str, Any]:
    """Return every mode's contract, for emitting into the frontend."""

    return {
        "modes": {mode: capabilities_payload(mode) for mode in HOSTING_MODES},
    }
