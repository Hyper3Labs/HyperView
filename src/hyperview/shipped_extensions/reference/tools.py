from __future__ import annotations

from typing import Any

from hyperview.tools import RunContext, tool


@tool("reference.describe")
def describe(ctx: RunContext) -> dict[str, Any]:
    """Return a compact, machine-readable description of the active workspace."""

    return {
        "workspace_id": ctx.workspace_id,
        "dataset": ctx.dataset.name if ctx.dataset is not None else None,
        "sample_count": len(ctx.dataset) if ctx.dataset is not None else 0,
        "selected_ids": list(ctx.workspace.ui.selected_ids),
    }
