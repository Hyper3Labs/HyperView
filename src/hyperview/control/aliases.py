"""Control command names and deprecated aliases."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger(__name__)

DEPRECATED_COMMAND_ALIASES: dict[str, str] = {
    "ui.panel.add": "workspace.panel.add",
    "ui.panel.update": "workspace.panel.update",
    "ui.panel.remove": "workspace.panel.remove",
    "ui.panel.resize": "workspace.panel.resize",
    "ui.panel.move": "workspace.panel.move",
    "ui.panel.focus": "workspace.panel.focus",
    "ui.panel.close": "workspace.panel.close",
    "ui.panel.show": "workspace.panel.show",
    "ui.panel.update-props": "workspace.panel.update-props",
    "ui.panel.state.get": "workspace.panel.state.get",
    "ui.panel.state.patch": "workspace.panel.state.patch",
    "samples.retrieval.set-anchor": "panel.samples.retrieval.set-anchor",
    "samples.retrieval.set-text-query": "panel.samples.retrieval.set-text-query",
    "samples.retrieval.set-k": "panel.samples.retrieval.set-k",
    "samples.retrieval.clear": "panel.samples.retrieval.clear",
    "panel.samples.show-neighbors": "collection.neighbors.create",
    "panel.labels.filter": "collection.filter.set",
}


def resolve_command_alias(command_id: str) -> str:
    """Return the canonical command id, warning when a deprecated alias is used."""

    canonical_id = DEPRECATED_COMMAND_ALIASES.get(command_id)
    if canonical_id is None:
        return command_id
    LOGGER.warning(
        "Deprecated HyperView command '%s' used; use '%s' instead.",
        command_id,
        canonical_id,
    )
    return canonical_id
