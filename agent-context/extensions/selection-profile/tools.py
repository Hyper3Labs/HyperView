from __future__ import annotations

from collections import Counter
from typing import Any

from hyperview.tools import RunContext, tool


@tool("selection_profile.summarize")
def summarize_selection(ctx: RunContext, *, sample_ids: list[str] | None = None) -> dict[str, Any]:
    if ctx.dataset is None:
        raise ValueError("No active dataset")

    ids = sample_ids or ctx.workspace.ui.selected_ids
    selected_samples = ctx.dataset.get_samples_by_ids(ids) if ids else []
    label_counts = Counter(sample.label or "unlabeled" for sample in selected_samples)
    width_values = [sample.width for sample in selected_samples if sample.width]
    height_values = [sample.height for sample in selected_samples if sample.height]

    return {
        "dataset": ctx.dataset.name,
        "workspace": ctx.workspace_id,
        "selection_count": len(selected_samples),
        "requested_count": len(ids),
        "total_samples": len(ctx.dataset),
        "labels": [
            {"label": label, "count": count}
            for label, count in label_counts.most_common(8)
        ],
        "mean_width": round(sum(width_values) / len(width_values), 1) if width_values else None,
        "mean_height": round(sum(height_values) / len(height_values), 1) if height_values else None,
        "samples": [
            {
                "id": sample.id,
                "label": sample.label,
                "filename": sample.filename,
                "width": sample.width,
                "height": sample.height,
            }
            for sample in selected_samples[:12]
        ],
    }
