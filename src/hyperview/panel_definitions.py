"""Serializable panel definition metadata.

Panel definitions describe what a panel type is and what default runtime
metadata it declares. They intentionally exclude frontend implementation
bindings such as React components or Dockview adapter details.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _json_object_copy(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


@dataclass(frozen=True)
class PanelDefinition:
    panel_type: str
    label: str
    source: str
    title: str | None = None
    extension: str | None = None
    default_props: dict[str, Any] = field(default_factory=dict)
    default_state: dict[str, Any] = field(default_factory=dict)
    props_schema: dict[str, Any] | None = None
    state_schema: dict[str, Any] | None = None
    commands: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    default_layout: dict[str, Any] = field(default_factory=dict)
    allow_multiple: bool = True
    icon: str | None = None
    category: str | None = None
    static_compatible: bool = True
    static_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.panel_type.strip():
            raise ValueError("panel_type must be a non-empty string")
        if not self.label.strip():
            raise ValueError("panel definition label must be a non-empty string")
        if not self.source.strip():
            raise ValueError("panel definition source must be a non-empty string")

    def to_dict(self) -> dict[str, Any]:
        return {
            "panel_type": self.panel_type,
            "label": self.label,
            "title": self.title or self.label,
            "source": self.source,
            "extension": self.extension,
            "default_props": _json_object_copy(self.default_props),
            "default_state": _json_object_copy(self.default_state),
            "props_schema": (
                _json_object_copy(self.props_schema)
                if self.props_schema is not None
                else None
            ),
            "state_schema": (
                _json_object_copy(self.state_schema)
                if self.state_schema is not None
                else None
            ),
            "commands": list(self.commands),
            "queries": list(self.queries),
            "default_layout": _json_object_copy(self.default_layout),
            "allow_multiple": self.allow_multiple,
            "icon": self.icon,
            "category": self.category,
            "static_compatible": self.static_compatible,
            "static_reason": self.static_reason,
        }


BUILTIN_PANEL_DEFINITIONS = (
    PanelDefinition(
        panel_type="samples",
        label="Samples",
        title="Samples",
        source="builtin",
        default_layout={"id": "samples", "position": "center", "order": 10},
        commands=[
            "workspace.panel.state.get",
            "workspace.panel.state.patch",
            "panel.samples.retrieval.set-anchor",
            "panel.samples.retrieval.set-text-query",
            "panel.samples.retrieval.set-k",
            "panel.samples.retrieval.clear",
        ],
        queries=["samples.query", "samples.similar"],
        icon="grid",
        category="dataset",
    ),
    PanelDefinition(
        panel_type="scatter",
        label="Scatter",
        title="Embeddings",
        source="builtin",
        default_props={
            "preset": "euclidean-2d",
            "presets": {
                "euclidean-2d": {
                    "label": "Euclidean",
                    "geometry": "euclidean",
                    "layout_dimension": 2,
                },
                "poincare-2d": {
                    "label": "Hyperbolic",
                    "geometry": "poincare",
                    "layout_dimension": 2,
                },
                "spherical-2d": {
                    "label": "Spherical",
                    "geometry": "spherical",
                    "layout_dimension": 2,
                },
                "euclidean-3d": {
                    "label": "Euclidean 3D",
                    "geometry": "euclidean",
                    "layout_dimension": 3,
                },
                "spherical-3d": {
                    "label": "Sphere 3D",
                    "geometry": "spherical",
                    "layout_dimension": 3,
                },
            },
        },
        default_layout={
            "id": "scatter",
            "position": "center",
            "reference_panel_id": "samples",
            "direction": "right",
            "order": 20,
            "preset": "euclidean-2d",
        },
        commands=["workspace.panel.state.get", "workspace.panel.state.patch"],
        queries=["embeddings", "layouts"],
        icon="scatter",
        category="embedding",
    ),
    PanelDefinition(
        panel_type="explorer",
        label="Explorer",
        title="Labels",
        source="builtin",
        default_layout={
            "id": "explorer",
            "position": "right",
            "dock_zone": "left",
            "order": 0,
        },
        commands=["workspace.panel.state.get", "workspace.panel.state.patch"],
        icon="tags",
        category="dataset",
        allow_multiple=False,
    ),
)


def merge_default_props(
    definition: PanelDefinition | None,
    props: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _json_object_copy(definition.default_props) if definition is not None else {}
    merged.update(_json_object_copy(dict(props or {})))
    return merged
