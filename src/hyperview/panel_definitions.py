"""Serializable panel definition metadata.

Panel definitions describe what a panel type is, which renderer implements it,
and what default runtime metadata it declares. Renderer references are stable
transport identifiers, not frontend component imports or Dockview details.
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
    renderer: str
    title: str | None = None
    extension: str | None = None
    extension_panel: str | None = None
    default_props: dict[str, Any] = field(default_factory=dict)
    default_state: dict[str, Any] = field(default_factory=dict)
    props_schema: dict[str, Any] | None = None
    state_schema: dict[str, Any] | None = None
    commands: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    data_capabilities: list[str] = field(default_factory=list)
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
        if not self.renderer.strip():
            raise ValueError("panel definition renderer must be a non-empty string")
        validate_json_contract(self.default_props, self.props_schema, label="default props")
        validate_json_contract(self.default_state, self.state_schema, label="default state")

    def to_dict(self) -> dict[str, Any]:
        return {
            "panel_type": self.panel_type,
            "label": self.label,
            "title": self.title or self.label,
            "source": self.source,
            "renderer": self.renderer,
            "extension": self.extension,
            "extension_panel": self.extension_panel,
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
            "data_capabilities": list(self.data_capabilities),
            "default_layout": _json_object_copy(self.default_layout),
            "allow_multiple": self.allow_multiple,
            "icon": self.icon,
            "category": self.category,
            "static_compatible": self.static_compatible,
            "static_reason": self.static_reason,
        }


def validate_json_contract(
    value: Any,
    schema: dict[str, Any] | None,
    *,
    label: str,
) -> None:
    """Validate the small JSON-schema subset supported by panel manifests."""

    if schema is None:
        return
    expected_type = schema.get("type")
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if isinstance(expected_type, list):
        valid_type = any(type_checks.get(item, lambda _value: False)(value) for item in expected_type)
    elif expected_type is None:
        valid_type = True
    else:
        valid_type = type_checks.get(expected_type, lambda _value: False)(value)
    if not valid_type:
        raise ValueError(f"{label} must match schema type {expected_type!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} must be one of {schema['enum']!r}")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for required in schema.get("required") or []:
            if required not in value:
                raise ValueError(f"{label}.{required} is required")
        if schema.get("additionalProperties") is False:
            unexpected = sorted(set(value) - set(properties))
            if unexpected:
                raise ValueError(f"{label} has unsupported fields: {', '.join(unexpected)}")
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                validate_json_contract(item, child_schema, label=f"{label}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            validate_json_contract(item, schema["items"], label=f"{label}[{index}]")


def merge_default_props(
    definition: PanelDefinition | None,
    props: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = _json_object_copy(definition.default_props) if definition is not None else {}
    merged.update(_json_object_copy(dict(props or {})))
    return merged
