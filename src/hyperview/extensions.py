"""HyperView extensions: folders containing tools and panels.

An extension is a folder in the user's repo (or under ``.hyperview/extensions``
in the cwd) with a small ``extension.toml`` manifest.

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
from typing import Any

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from hyperview.tools import ToolRecord, drain_pending_tools


EXTENSION_MANIFEST_NAME = "extension.toml"
DEFAULT_LOCAL_EXTENSIONS_DIR = ".hyperview/extensions"
VALID_PANEL_POSITIONS = {"center", "right", "bottom"}


@dataclass
class PanelSpecEntry:
    id: str
    title: str
    position: str = "right"
    file: str = "panel.jsx"


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
    def load(cls, folder: Path) -> "ExtensionManifest":
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
                    file=str(entry.get("file") or "panel.jsx"),
                )
            )

        return cls(
            name=name,
            folder=folder,
            description=data.get("description"),
            tools=tools,
            panels=panels,
        )


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
    """Return folders under ``<root>/.hyperview/extensions`` that look valid.

    ``root`` defaults to the process cwd. Returned paths are absolute.
    """

    base = (root or Path.cwd()) / DEFAULT_LOCAL_EXTENSIONS_DIR
    if not base.exists() or not base.is_dir():
        return []
    found: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if (entry / EXTENSION_MANIFEST_NAME).exists():
            found.append(entry.resolve())
    return found


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
    "DEFAULT_LOCAL_EXTENSIONS_DIR",
    "EXTENSION_MANIFEST_NAME",
    "ExtensionManifest",
    "LoadedExtension",
    "PanelSpecEntry",
    "ToolSpecEntry",
    "discover_local_extensions",
    "load_extension_tools",
    "resolve_panel_source",
    "unload_extension_modules",
]
