"""HyperView extensions: folders containing tools and panels.

An extension is a folder in the user's repo, usually under
``.hyperview/extensions`` in the project root, with a small ``extension.toml``
manifest.

Minimal shape::

    name = "lrp"
    description = "LRP explainability"

    [[tools]]
    file = "tools.py"

    [[panels]]
    id = "lrp"
    title = "LRP"
    position = "right"
    file = "panel.jsx"

One folder can declare multiple ``[[tools]]`` and ``[[panels]]``. Tools and
panels are registered against a single workspace when the extension is
added; removal unregisters them.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from hyperview.panel_definitions import PanelDefinition
from hyperview.tools import ToolRecord, drain_pending_tools

EXTENSION_MANIFEST_NAME = "extension.toml"
DEFAULT_LOCAL_EXTENSIONS_DIR = ".hyperview/extensions"
SHIPPED_EXTENSIONS_DIR = Path(__file__).with_name("shipped_extensions")
CORE_EXTENSION_NAME = "core"
VALID_PANEL_POSITIONS = {"center", "right", "bottom"}
VALID_PANEL_DIRECTIONS = {"right", "left", "above", "below", "within"}
PANEL_LAYOUT_FIELDS = (
    "reference_panel_id",
    "direction",
    "width",
    "height",
    "min_width",
    "min_height",
    "max_width",
    "max_height",
)


@dataclass
class PanelSpecEntry:
    id: str
    title: str
    position: str = "right"
    file: str | None = "panel.jsx"
    renderer: str | None = None
    panel_type: str | None = None
    label: str | None = None
    default_props: dict[str, object] = field(default_factory=dict)
    default_state: dict[str, object] = field(default_factory=dict)
    props_schema: dict[str, object] | None = None
    state_schema: dict[str, object] | None = None
    commands: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    data_capabilities: list[str] = field(default_factory=list)
    default_layout: dict[str, object] = field(default_factory=dict)
    allow_multiple: bool = True
    icon: str | None = None
    category: str | None = None
    static_compatible: bool = True
    static_reason: str | None = None

    def resolved_panel_type(self, extension_name: str) -> str:
        panel_type = (self.panel_type or "").strip()
        return panel_type or f"{extension_name}.{self.id}"

    def to_definition(
        self,
        extension_name: str,
        *,
        source: str = "extension",
    ) -> PanelDefinition:
        return PanelDefinition(
            panel_type=self.resolved_panel_type(extension_name),
            label=self.label or self.title,
            title=self.title,
            source=source,
            renderer=self.resolved_renderer(),
            extension=extension_name,
            default_props=dict(self.default_props),
            default_state=dict(self.default_state),
            props_schema=dict(self.props_schema) if self.props_schema is not None else None,
            state_schema=dict(self.state_schema) if self.state_schema is not None else None,
            commands=list(self.commands),
            queries=list(self.queries),
            data_capabilities=list(self.data_capabilities),
            default_layout=dict(self.default_layout),
            allow_multiple=self.allow_multiple,
            icon=self.icon,
            category=self.category,
            static_compatible=self.static_compatible,
            static_reason=self.static_reason,
        )

    def resolved_renderer(self) -> str:
        renderer = (self.renderer or "").strip()
        if renderer:
            return renderer
        if not self.file:
            raise ValueError(f"Panel '{self.id}' needs either renderer or file")
        return f"module:{self.file}"

    def module_file(self) -> str | None:
        renderer = self.resolved_renderer()
        if not renderer.startswith("module:"):
            return None
        return self.file or renderer.removeprefix("module:").strip() or None


@dataclass
class ToolSpecEntry:
    file: str


@dataclass
class ExtensionManifest:
    name: str
    folder: Path
    description: str | None = None
    tools: list[ToolSpecEntry] = field(default_factory=list)
    panels: list[PanelSpecEntry] = field(default_factory=list)

    @classmethod
    def load(cls, folder: Path) -> ExtensionManifest:
        folder = folder.expanduser().resolve()
        manifest_path = folder / EXTENSION_MANIFEST_NAME
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"No {EXTENSION_MANIFEST_NAME} found in {folder}"
            )

        data = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        name = str(data.get("name") or "").strip()
        if not name:
            raise ValueError(f"{manifest_path}: top-level 'name' is required")

        tools = [
            ToolSpecEntry(file=str(entry["file"]))
            for entry in list(data.get("tools") or [])
            if entry.get("file")
        ]
        panels: list[PanelSpecEntry] = []
        for entry in list(data.get("panels") or []):
            panel_id = str(entry.get("id") or "").strip()
            if not panel_id:
                raise ValueError(f"{manifest_path}: panel 'id' is required")

            position = str(entry.get("position") or "right")
            if position not in VALID_PANEL_POSITIONS:
                raise ValueError(
                    f"{manifest_path}: unsupported panel position '{position}'"
                )

            panels.append(
                PanelSpecEntry(
                    id=panel_id,
                    title=str(entry.get("title") or panel_id),
                    position=position,
                    file=(
                        _optional_str(entry.get("file"))
                        or (None if _optional_str(entry.get("renderer")) else "panel.jsx")
                    ),
                    renderer=_optional_str(entry.get("renderer")),
                    panel_type=_optional_str(entry.get("panel_type")),
                    label=_optional_str(entry.get("label")),
                    default_props=_dict_or_empty(entry.get("default_props")),
                    default_state=_dict_or_empty(entry.get("default_state")),
                    props_schema=_optional_dict(entry.get("props_schema")),
                    state_schema=_optional_dict(entry.get("state_schema")),
                    commands=_string_list(entry.get("commands")),
                    queries=_string_list(entry.get("queries")),
                    data_capabilities=_string_list(entry.get("data_capabilities")),
                    default_layout=_panel_default_layout(entry, position),
                    allow_multiple=bool(entry.get("allow_multiple", True)),
                    icon=_optional_str(entry.get("icon")),
                    category=_optional_str(entry.get("category")),
                    static_compatible=bool(entry.get("static_compatible", True)),
                    static_reason=_optional_str(entry.get("static_reason")),
                )
            )

        return cls(
            name=name,
            folder=folder,
            description=data.get("description"),
            tools=tools,
            panels=panels,
        )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dict_or_empty(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_dict(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _panel_default_layout(entry: dict[str, object], position: str) -> dict[str, object]:
    layout = _dict_or_empty(entry.get("default_layout"))
    layout.setdefault("position", position)
    for field_name in PANEL_LAYOUT_FIELDS:
        value = entry.get(field_name)
        if value is not None:
            layout[field_name] = value
    layout_position = str(layout.get("position") or position)
    if layout_position not in VALID_PANEL_POSITIONS:
        raise ValueError(
            f"unsupported panel default_layout position '{layout_position}'"
        )
    layout["position"] = layout_position
    layout_direction = layout.get("direction")
    if layout_direction is not None:
        layout_direction = str(layout_direction)
        if layout_direction not in VALID_PANEL_DIRECTIONS:
            raise ValueError(
                f"unsupported panel default_layout direction '{layout_direction}'"
            )
        layout["direction"] = layout_direction
    return layout


@dataclass
class LoadedExtension:
    """Result of loading an extension's Python tool modules."""

    manifest: ExtensionManifest
    module_names: list[str] = field(default_factory=list)
    tools: list[ToolRecord] = field(default_factory=list)


def _make_module_name(extension_name: str, source_file: Path) -> str:
    stem = source_file.stem.replace("-", "_")
    unique = uuid.uuid4().hex[:8]
    safe_name = extension_name.replace("-", "_")
    return f"hyperview_ext_{safe_name}_{stem}_{unique}"


def load_extension_tools(manifest: ExtensionManifest) -> LoadedExtension:
    """Import every ``tools.file`` referenced by the manifest.

    Each import fires the ``@tool`` decorator which pushes onto the pending
    queue. We drain that queue here and tag records with the extension
    name so they can be unregistered as a group.
    """

    # Flush any stale pending tools before we start.
    drain_pending_tools()

    module_names: list[str] = []
    collected: list[ToolRecord] = []
    for spec in manifest.tools:
        source_file = (manifest.folder / spec.file).resolve()
        if not source_file.exists():
            raise FileNotFoundError(
                f"Extension '{manifest.name}': tools file not found: {source_file}"
            )

        module_name = _make_module_name(manifest.name, source_file)
        module_spec = importlib.util.spec_from_file_location(module_name, source_file)
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"Cannot build import spec for {source_file}")
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_name] = module
        try:
            module_spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        module_names.append(module_name)

        for record in drain_pending_tools():
            record.extension = manifest.name
            collected.append(record)

    return LoadedExtension(
        manifest=manifest,
        module_names=module_names,
        tools=collected,
    )


def unload_extension_modules(loaded: LoadedExtension) -> None:
    for module_name in loaded.module_names:
        sys.modules.pop(module_name, None)


def discover_local_extensions(root: Path | None = None) -> list[Path]:
    """Return folders under the nearest ``.hyperview/extensions`` that look valid.

    ``root`` defaults to the process cwd. Discovery walks upward so launching
    HyperView from a nested directory still attaches project-local extensions.
    Returned paths are absolute.
    """

    start = (root or Path.cwd()).resolve()
    for project_root in [start, *start.parents]:
        base = project_root / DEFAULT_LOCAL_EXTENSIONS_DIR
        if not base.exists() or not base.is_dir():
            continue

        found: list[Path] = []
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and (entry / EXTENSION_MANIFEST_NAME).exists():
                found.append(entry.resolve())
        return found

    return []


def discover_shipped_extensions() -> list[Path]:
    """Return extension packages distributed with HyperView."""

    if not SHIPPED_EXTENSIONS_DIR.is_dir():
        return []
    return [
        entry.resolve()
        for entry in sorted(SHIPPED_EXTENSIONS_DIR.iterdir())
        if entry.name != CORE_EXTENSION_NAME
        and entry.is_dir()
        and (entry / EXTENSION_MANIFEST_NAME).is_file()
    ]


def load_core_panel_definitions() -> list[PanelDefinition]:
    """Load native panel definitions from HyperView's packaged core manifest."""

    manifest = ExtensionManifest.load(SHIPPED_EXTENSIONS_DIR / CORE_EXTENSION_NAME)
    if manifest.name != CORE_EXTENSION_NAME:
        raise ValueError("The packaged core extension manifest must be named 'core'")
    definitions = [
        panel.to_definition(manifest.name, source="shipped")
        for panel in manifest.panels
    ]
    invalid = [item.panel_type for item in definitions if not item.renderer.startswith("native:")]
    if invalid:
        raise ValueError(
            "Core panel renderers must use native: references: " + ", ".join(invalid)
        )
    return definitions


def resolve_shipped_extension(name: str) -> Path:
    """Resolve one shipped extension by its manifest name."""

    requested = name.strip()
    if not requested:
        raise ValueError("shipped extension name must be a non-empty string")
    for folder in discover_shipped_extensions():
        manifest = ExtensionManifest.load(folder)
        if manifest.name == requested:
            return folder
    available = [ExtensionManifest.load(folder).name for folder in discover_shipped_extensions()]
    suffix = f" Available: {', '.join(available)}" if available else ""
    raise ValueError(f"Unknown shipped extension: {requested}.{suffix}")


def resolve_panel_source(
    folder: Path, file_name: str
) -> Path:
    """Resolve a panel's source file under an extension folder."""

    folder_resolved = folder.resolve()
    candidate = (folder_resolved / file_name).resolve()
    if folder_resolved not in candidate.parents and candidate != folder_resolved:
        raise ValueError(f"Panel file path escapes extension folder: {file_name}")
    if not candidate.exists():
        raise FileNotFoundError(f"Panel file not found: {candidate}")
    return candidate


__all__ = [
    "CORE_EXTENSION_NAME",
    "DEFAULT_LOCAL_EXTENSIONS_DIR",
    "EXTENSION_MANIFEST_NAME",
    "ExtensionManifest",
    "LoadedExtension",
    "PanelSpecEntry",
    "ToolSpecEntry",
    "discover_local_extensions",
    "discover_shipped_extensions",
    "load_extension_tools",
    "load_core_panel_definitions",
    "resolve_panel_source",
    "resolve_shipped_extension",
    "unload_extension_modules",
]
