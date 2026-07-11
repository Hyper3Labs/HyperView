"""Per-dataset typed field catalog persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, TypedDict

FieldType = Literal["scalar", "text", "media", "label", "vector_ref"]


class FieldDefinition(TypedDict):
    type: FieldType
    nullable: bool
    source: str


FieldCatalog = dict[str, FieldDefinition]


class FieldRegistry:
    """Small JSON registry stored alongside a dataset's Lance tables."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> FieldCatalog:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        fields = data.get("fields", {}) if isinstance(data, dict) else {}
        return {str(name): definition for name, definition in fields.items()}

    def update(self, fields: FieldCatalog) -> FieldCatalog:
        catalog = self.load()
        catalog.update(fields)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload: dict[str, Any] = {"fields": dict(sorted(catalog.items()))}
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return catalog
