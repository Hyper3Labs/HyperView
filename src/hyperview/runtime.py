"""Runtime, provider registry, and workspace state for HyperView."""

from __future__ import annotations

import importlib
import inspect
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from hyperview.core.dataset import Dataset
from hyperview.extensions import (
    ExtensionManifest,
    LoadedExtension,
    load_extension_tools,
    resolve_panel_source,
    unload_extension_modules,
)
from hyperview.storage.config import StorageConfig
from hyperview.tools import RunContext, ToolRegistry


def _now_ts() -> int:
    return int(time.time())


def get_runtime_config_dir() -> Path:
    datasets_dir = StorageConfig.default().datasets_dir
    config_dir = datasets_dir.parent
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_provider_registry_path() -> Path:
    return get_runtime_config_dir() / "providers.json"


def get_workspace_registry_path() -> Path:
    return get_runtime_config_dir() / "workspaces.json"


def _import_from_path(import_path: str) -> Any:
    if ":" not in import_path:
        raise ValueError(
            "import_path must use the form '<module>:<object>', "
            f"got '{import_path}'"
        )

    module_name, object_name = import_path.split(":", 1)
    module = importlib.import_module(module_name)

    try:
        return getattr(module, object_name)
    except AttributeError as exc:
        raise ValueError(
            f"Object '{object_name}' not found in module '{module_name}'"
        ) from exc


@dataclass
class ProviderRegistration:
    alias: str
    kind: Literal["python"]
    import_path: str
    description: str | None = None
    defaults: dict[str, Any] = field(default_factory=dict)
    created_at: int = field(default_factory=_now_ts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderRegistration:
        return cls(
            alias=str(data["alias"]),
            kind="python",
            import_path=str(data["import_path"]),
            description=data.get("description"),
            defaults=dict(data.get("defaults") or {}),
            created_at=int(data.get("created_at") or _now_ts()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderRegistry:
    """Persistent registry for user-defined embedding providers."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_provider_registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._providers: dict[str, ProviderRegistration] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._providers = {}
            return

        data = json.loads(self.path.read_text())
        providers = data.get("providers") or []
        self._providers = {
            entry["alias"]: ProviderRegistration.from_dict(entry) for entry in providers
        }

    def _save(self) -> None:
        payload = {
            "providers": [
                provider.to_dict() for provider in sorted(self._providers.values(), key=lambda item: item.alias)
            ]
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def list(self) -> list[ProviderRegistration]:
        return [self._providers[key] for key in sorted(self._providers)]

    def get(self, alias: str) -> ProviderRegistration | None:
        return self._providers.get(alias)

    def register_python(
        self,
        alias: str,
        import_path: str,
        *,
        description: str | None = None,
        defaults: dict[str, Any] | None = None,
        overwrite: bool = False,
    ) -> ProviderRegistration:
        alias = alias.strip()
        if not alias:
            raise ValueError("alias must be a non-empty string")

        existing = self._providers.get(alias)
        if existing is not None and not overwrite:
            raise ValueError(f"Provider alias already registered: {alias}")

        _import_from_path(import_path)

        registration = ProviderRegistration(
            alias=alias,
            kind="python",
            import_path=import_path,
            description=description,
            defaults=dict(defaults or {}),
        )
        self._providers[alias] = registration
        self._save()
        return registration

    def unregister(self, alias: str) -> bool:
        removed = self._providers.pop(alias, None)
        if removed is None:
            return False
        self._save()
        return True

    def is_available(self, alias: str) -> bool:
        registration = self.get(alias)
        if registration is None:
            return False
        try:
            _import_from_path(registration.import_path)
        except Exception:
            return False
        return True

    def instantiate(self, alias: str, **kwargs: Any) -> Any:
        registration = self.get(alias)
        if registration is None:
            raise ValueError(f"Unknown custom provider alias: {alias}")

        target = _import_from_path(registration.import_path)
        resolved_kwargs = {**registration.defaults, **kwargs}

        if inspect.isclass(target):
            return target(**resolved_kwargs)

        if callable(target):
            created = target(**resolved_kwargs)
            return created

        if resolved_kwargs:
            raise ValueError(
                f"Custom provider '{alias}' resolved to a non-callable object and cannot accept kwargs"
            )
        return target


@dataclass
class CustomPanelSpec:
    id: str
    title: str
    module_file: str | None = None
    kind: Literal["module", "scatter"] = "module"
    position: Literal["center", "right", "bottom"] = "right"
    layout_key: str | None = None
    geometry: str | None = None
    layout_dimension: int | None = None
    reference_panel_id: str | None = None
    direction: Literal["right", "left", "above", "below", "within"] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomPanelSpec:
        kind = str(data.get("kind") or "module")
        if kind not in {"module", "scatter"}:
            kind = "module"

        position = str(data.get("position") or "right")
        if position not in {"center", "right", "bottom"}:
            position = "right"

        direction = data.get("direction")
        if direction is not None:
            direction = str(direction)
            if direction not in {"right", "left", "above", "below", "within"}:
                direction = None

        layout_dimension = data.get("layout_dimension")
        if layout_dimension is not None:
            try:
                layout_dimension = int(layout_dimension)
            except (TypeError, ValueError):
                layout_dimension = None

        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            module_file=data.get("module_file"),
            kind=kind,  # type: ignore[arg-type]
            position=position,  # type: ignore[arg-type]
            layout_key=data.get("layout_key"),
            geometry=data.get("geometry"),
            layout_dimension=layout_dimension,
            reference_panel_id=data.get("reference_panel_id"),
            direction=direction,  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def resolved_module_file(self) -> Path | None:
        if not self.module_file:
            return None
        return Path(self.module_file).expanduser().resolve()


@dataclass
class LayoutViewState:
    camera_3d: dict[str, float] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutViewState:
        camera_raw = data.get("camera_3d")
        camera_3d: dict[str, float] | None = None
        if isinstance(camera_raw, dict):
            parsed: dict[str, float] = {}
            required_keys = (
                "yaw",
                "pitch",
                "distance",
                "target_x",
                "target_y",
                "target_z",
                "ortho_scale",
            )
            for key in required_keys:
                value = camera_raw.get(key)
                if value is None:
                    parsed = {}
                    break
                try:
                    parsed[key] = float(value)
                except (TypeError, ValueError):
                    parsed = {}
                    break
            if len(parsed) == len(required_keys):
                camera_3d = parsed
        return cls(camera_3d=camera_3d)

    def to_dict(self) -> dict[str, Any]:
        return {"camera_3d": dict(self.camera_3d) if self.camera_3d is not None else None}


@dataclass
class WorkspaceUiState:
    active_layout_key: str | None = None
    selected_ids: list[str] = field(default_factory=list)
    custom_panels: list[CustomPanelSpec] = field(default_factory=list)
    layout_views: dict[str, LayoutViewState] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceUiState:
        custom_panels: list[CustomPanelSpec] = []
        for entry in list(data.get("custom_panels") or []):
            panel = CustomPanelSpec.from_dict(entry)
            if panel.kind == "scatter" or panel.module_file:
                custom_panels.append(panel)

        layout_views: dict[str, LayoutViewState] = {}
        raw_layout_views = data.get("layout_views") or {}
        if isinstance(raw_layout_views, dict):
            for layout_key, view_data in raw_layout_views.items():
                if isinstance(layout_key, str) and isinstance(view_data, dict):
                    layout_views[layout_key] = LayoutViewState.from_dict(view_data)

        return cls(
            active_layout_key=data.get("active_layout_key"),
            selected_ids=list(data.get("selected_ids") or []),
            custom_panels=custom_panels,
            layout_views=layout_views,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_layout_key": self.active_layout_key,
            "selected_ids": list(self.selected_ids),
            "custom_panels": [panel.to_dict() for panel in self.custom_panels],
            "layout_views": {
                layout_key: view.to_dict()
                for layout_key, view in sorted(self.layout_views.items())
            },
        }


@dataclass
class WorkspaceState:
    id: str
    dataset_name: str | None = None
    ui: WorkspaceUiState = field(default_factory=WorkspaceUiState)
    created_at: int = field(default_factory=_now_ts)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceState:
        return cls(
            id=str(data["id"]),
            dataset_name=data.get("dataset_name"),
            ui=WorkspaceUiState.from_dict(data.get("ui") or {}),
            created_at=int(data.get("created_at") or _now_ts()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "dataset_name": self.dataset_name,
            "ui": self.ui.to_dict(),
            "created_at": self.created_at,
        }


class WorkspaceRegistry:
    """Persistent registry for HyperView workspaces."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_workspace_registry_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.active_workspace_id: str | None = None
        self._workspaces: dict[str, WorkspaceState] = {}
        self._load()
        if not self._workspaces:
            self.create_workspace("default", activate=True)

    def _load(self) -> None:
        if not self.path.exists():
            self.active_workspace_id = None
            self._workspaces = {}
            return

        data = json.loads(self.path.read_text())
        self.active_workspace_id = data.get("active_workspace_id")
        self._workspaces = {
            entry["id"]: WorkspaceState.from_dict(entry)
            for entry in list(data.get("workspaces") or [])
        }

    def _save(self) -> None:
        payload = {
            "active_workspace_id": self.active_workspace_id,
            "workspaces": [
                workspace.to_dict()
                for workspace in sorted(self._workspaces.values(), key=lambda item: item.id)
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def list(self) -> list[WorkspaceState]:
        return [self._workspaces[key] for key in sorted(self._workspaces)]

    def get(self, workspace_id: str) -> WorkspaceState | None:
        return self._workspaces.get(workspace_id)

    def create_workspace(self, workspace_id: str, *, activate: bool = False) -> WorkspaceState:
        workspace_id = workspace_id.strip()
        if not workspace_id:
            raise ValueError("workspace_id must be a non-empty string")
        if workspace_id in self._workspaces:
            raise ValueError(f"Workspace already exists: {workspace_id}")

        workspace = WorkspaceState(id=workspace_id)
        self._workspaces[workspace_id] = workspace
        if activate or self.active_workspace_id is None:
            self.active_workspace_id = workspace_id
        self._save()
        return workspace

    def ensure_workspace(self, workspace_id: str, *, activate: bool = False) -> WorkspaceState:
        workspace = self.get(workspace_id)
        if workspace is not None:
            if activate:
                self.active_workspace_id = workspace_id
                self._save()
            return workspace
        return self.create_workspace(workspace_id, activate=activate)

    def set_active_workspace(self, workspace_id: str) -> WorkspaceState:
        workspace = self.get(workspace_id)
        if workspace is None:
            raise ValueError(f"Unknown workspace: {workspace_id}")
        self.active_workspace_id = workspace_id
        self._save()
        return workspace

    def delete_workspace(self, workspace_id: str) -> WorkspaceState | None:
        workspace = self.get(workspace_id)
        if workspace is None:
            raise ValueError(f"Unknown workspace: {workspace_id}")
        if len(self._workspaces) <= 1:
            raise ValueError("Cannot delete the last remaining workspace")

        del self._workspaces[workspace_id]

        if self.active_workspace_id == workspace_id:
            remaining_ids = sorted(self._workspaces)
            self.active_workspace_id = remaining_ids[0] if remaining_ids else None

        self._save()
        if self.active_workspace_id is None:
            return None
        return self._workspaces[self.active_workspace_id]

    def set_dataset(self, workspace_id: str, dataset_name: str) -> WorkspaceState:
        workspace = self.ensure_workspace(workspace_id)
        workspace.dataset_name = dataset_name
        self._save()
        return workspace

    def update_workspace(self, workspace: WorkspaceState) -> None:
        self._workspaces[workspace.id] = workspace
        self._save()


@dataclass
class JobState:
    id: str
    kind: str
    workspace_id: str
    dataset_name: str | None
    status: Literal["queued", "running", "completed", "failed"] = "queued"
    created_at: int = field(default_factory=_now_ts)
    started_at: int | None = None
    finished_at: int | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtensionInstallation:
    """Bookkeeping for an installed extension (in-memory, per-process)."""

    manifest: ExtensionManifest
    loaded: LoadedExtension
    workspace_id: str
    panel_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.manifest.name,
            "folder": str(self.manifest.folder),
            "description": self.manifest.description,
            "workspace_id": self.workspace_id,
            "panels": list(self.panel_ids),
            "tools": [record.to_dict() for record in self.loaded.tools],
        }


class HyperViewRuntime:
    """Mutable application runtime for multi-workspace HyperView sessions."""

    def __init__(
        self,
        *,
        provider_registry: ProviderRegistry | None = None,
        workspace_registry: WorkspaceRegistry | None = None,
    ):
        self.runtime_id = uuid.uuid4().hex
        self.provider_registry = provider_registry or ProviderRegistry()
        self.workspace_registry = workspace_registry or WorkspaceRegistry()
        self.tools = ToolRegistry()
        self._extensions: dict[str, ExtensionInstallation] = {}
        self._dataset_cache: dict[str, Dataset] = {}
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.RLock()
        self._version = 1

    @property
    def version(self) -> int:
        return self._version

    def _bump_version(self) -> None:
        with self._lock:
            self._version += 1

    def list_available_datasets(self) -> list[str]:
        datasets_dir = StorageConfig.default().datasets_dir
        datasets_dir.mkdir(parents=True, exist_ok=True)
        return sorted([path.name for path in datasets_dir.iterdir() if path.is_dir()])

    def attach_dataset_instance(
        self,
        workspace_id: str,
        dataset: Dataset,
        *,
        activate_workspace: bool = True,
    ) -> None:
        with self._lock:
            self._dataset_cache[dataset.name] = dataset
            self.workspace_registry.set_dataset(workspace_id, dataset.name)
            if activate_workspace:
                self.workspace_registry.set_active_workspace(workspace_id)
            self._bump_version()

    def create_workspace(self, workspace_id: str, *, activate: bool = False) -> WorkspaceState:
        with self._lock:
            workspace = self.workspace_registry.create_workspace(workspace_id, activate=activate)
            self._bump_version()
            return workspace

    def set_active_workspace(self, workspace_id: str) -> WorkspaceState:
        with self._lock:
            workspace = self.workspace_registry.set_active_workspace(workspace_id)
            self._bump_version()
            return workspace

    def set_workspace_dataset(
        self,
        workspace_id: str,
        dataset_name: str,
    ) -> WorkspaceState:
        with self._lock:
            previous_workspace = self.workspace_registry.get(workspace_id)
            previous_dataset_name = (
                previous_workspace.dataset_name if previous_workspace is not None else None
            )
            workspace = self.workspace_registry.set_dataset(workspace_id, dataset_name)
            if previous_dataset_name != dataset_name:
                workspace.ui.active_layout_key = None
                workspace.ui.selected_ids = []
                workspace.ui.layout_views = {}
                self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def get_workspace(self, workspace_id: str | None = None) -> WorkspaceState:
        resolved_workspace_id = workspace_id or self.workspace_registry.active_workspace_id
        if resolved_workspace_id is None:
            raise ValueError("No active workspace")
        workspace = self.workspace_registry.get(resolved_workspace_id)
        if workspace is None:
            raise ValueError(f"Unknown workspace: {resolved_workspace_id}")
        return workspace

    def get_dataset(self, workspace_id: str | None = None, dataset_name: str | None = None) -> Dataset:
        workspace = self.get_workspace(workspace_id)
        resolved_dataset_name = dataset_name or workspace.dataset_name
        if not resolved_dataset_name:
            raise ValueError(f"Workspace '{workspace.id}' has no active dataset")

        cached = self._dataset_cache.get(resolved_dataset_name)
        if cached is not None:
            return cached

        dataset = Dataset(resolved_dataset_name)
        self._dataset_cache[resolved_dataset_name] = dataset
        return dataset

    def set_active_layout(self, workspace_id: str, layout_key: str | None) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            workspace.ui.active_layout_key = layout_key
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def set_selection(self, workspace_id: str, sample_ids: list[str]) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            workspace.ui.selected_ids = list(dict.fromkeys(sample_ids))
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def set_layout_view(
        self,
        workspace_id: str,
        layout_key: str,
        view: LayoutViewState,
    ) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            current = workspace.ui.layout_views.get(layout_key)
            if current is not None and current.to_dict() == view.to_dict():
                return workspace
            workspace.ui.layout_views[layout_key] = view
            self.workspace_registry.update_workspace(workspace)
            # Camera saves are high-frequency local UI state; avoid forcing
            # runtime snapshots that can overwrite in-progress selection state.
            return workspace

    def add_custom_panel(self, workspace_id: str, panel: CustomPanelSpec) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            panels = [existing for existing in workspace.ui.custom_panels if existing.id != panel.id]
            panels.append(panel)
            workspace.ui.custom_panels = panels
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def remove_custom_panel(self, workspace_id: str, panel_id: str) -> WorkspaceState:
        with self._lock:
            workspace = self.get_workspace(workspace_id)
            workspace.ui.custom_panels = [
                panel for panel in workspace.ui.custom_panels if panel.id != panel_id
            ]
            self.workspace_registry.update_workspace(workspace)
            self._bump_version()
            return workspace

    def get_custom_panel(self, workspace_id: str, panel_id: str) -> CustomPanelSpec:
        workspace = self.get_workspace(workspace_id)
        for panel in workspace.ui.custom_panels:
            if panel.id == panel_id:
                return panel
        raise ValueError(f"Unknown panel '{panel_id}' for workspace '{workspace.id}'")

    def register_job(
        self,
        *,
        kind: str,
        workspace_id: str,
        dataset_name: str | None,
        params: dict[str, Any],
    ) -> JobState:
        job = JobState(
            id=uuid.uuid4().hex,
            kind=kind,
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            params=params,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._bump_version()
        return job

    def list_jobs(self) -> list[JobState]:
        with self._lock:
            return [self._jobs[key] for key in sorted(self._jobs)]

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit_job(
        self,
        *,
        kind: str,
        workspace_id: str,
        dataset_name: str | None,
        params: dict[str, Any],
        target: Any,
    ) -> JobState:
        job = self.register_job(kind=kind, workspace_id=workspace_id, dataset_name=dataset_name, params=params)

        def runner() -> None:
            with self._lock:
                current = self._jobs[job.id]
                current.status = "running"
                current.started_at = _now_ts()
                self._bump_version()

            try:
                result = target()
            except Exception as exc:  # pragma: no cover - error path depends on runtime failures
                with self._lock:
                    current = self._jobs[job.id]
                    current.status = "failed"
                    current.error = f"{type(exc).__name__}: {exc}"
                    current.finished_at = _now_ts()
                    self._bump_version()
                return

            with self._lock:
                current = self._jobs[job.id]
                current.status = "completed"
                current.result = result
                current.finished_at = _now_ts()
                self._bump_version()

        thread = threading.Thread(target=runner, name=f"hyperview-job-{job.id[:8]}", daemon=True)
        thread.start()
        return job

    def submit_embedding_job(
        self,
        *,
        workspace_id: str,
        dataset_name: str,
        model: str,
        provider: str | None = None,
        checkpoint: str | None = None,
        provider_kwargs: dict[str, Any] | None = None,
        layouts: list[str] | None = None,
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        activate_layout: bool = True,
    ) -> JobState:
        provider_kwargs = dict(provider_kwargs or {})

        def run() -> dict[str, Any]:
            dataset = self.get_dataset(workspace_id, dataset_name)
            space_key = dataset.compute_embeddings(
                model=model,
                provider=provider,
                checkpoint=checkpoint,
                show_progress=True,
                **provider_kwargs,
            )

            layout_keys: list[str] = []
            for layout in layouts or []:
                layout_key = dataset.compute_visualization(
                    space_key=space_key,
                    method=method,
                    layout=layout,
                    n_neighbors=n_neighbors,
                    min_dist=min_dist,
                    metric=metric,
                )
                layout_keys.append(layout_key)

            self.set_workspace_dataset(workspace_id, dataset_name)
            if activate_layout and layout_keys:
                self.set_active_layout(workspace_id, layout_keys[0])

            return {
                "space_key": space_key,
                "layout_keys": layout_keys,
            }

        return self.submit_job(
            kind="embeddings.compute",
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            params={
                "model": model,
                "provider": provider,
                "checkpoint": checkpoint,
                "layouts": list(layouts or []),
            },
            target=run,
        )

    def submit_layout_job(
        self,
        *,
        workspace_id: str,
        dataset_name: str,
        space_key: str | None,
        layouts: list[str],
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        activate_layout: bool = True,
    ) -> JobState:
        def run() -> dict[str, Any]:
            dataset = self.get_dataset(workspace_id, dataset_name)
            layout_keys: list[str] = []
            for layout in layouts:
                layout_key = dataset.compute_visualization(
                    space_key=space_key,
                    method=method,
                    layout=layout,
                    n_neighbors=n_neighbors,
                    min_dist=min_dist,
                    metric=metric,
                )
                layout_keys.append(layout_key)
            if activate_layout and layout_keys:
                self.set_active_layout(workspace_id, layout_keys[0])
            return {"layout_keys": layout_keys}

        return self.submit_job(
            kind="layouts.compute",
            workspace_id=workspace_id,
            dataset_name=dataset_name,
            params={"space_key": space_key, "layouts": layouts},
            target=run,
        )

    def get_panel_payload(self, workspace_id: str, panel: CustomPanelSpec) -> dict[str, Any]:
        module_file = panel.resolved_module_file()
        if module_file is None:
            return {"module_src": None}

        return {
            "module_src": "/api/panels/content/"
            f"{quote(workspace_id, safe='')}/"
            f"{quote(panel.id, safe='')}/"
            f"{quote(module_file.name, safe='')}"
            f"?v={self.version}",
        }

    # ------------------------------------------------------------------
    # Extensions and tools
    # ------------------------------------------------------------------

    def list_extensions(self) -> list[ExtensionInstallation]:
        with self._lock:
            return [self._extensions[key] for key in sorted(self._extensions)]

    def get_extension(self, name: str) -> ExtensionInstallation | None:
        with self._lock:
            return self._extensions.get(name)

    def install_extension(self, workspace_id: str, folder: Path) -> ExtensionInstallation:
        """Load an extension folder and register its tools + panels."""

        manifest = ExtensionManifest.load(folder)
        loaded = load_extension_tools(manifest)
        prepared_panels: list[CustomPanelSpec] = []
        for panel_entry in manifest.panels:
            panel_file = resolve_panel_source(manifest.folder, panel_entry.file)
            prepared_panels.append(
                CustomPanelSpec(
                    id=panel_entry.id,
                    title=panel_entry.title,
                    module_file=str(panel_file),
                    position=panel_entry.position,  # type: ignore[arg-type]
                )
            )

        with self._lock:
            self.get_workspace(workspace_id)

            previous_installation = self._extensions.get(manifest.name)
            previous_workspace_panels: list[CustomPanelSpec] | None = None
            if previous_installation is not None:
                try:
                    previous_workspace = self.get_workspace(previous_installation.workspace_id)
                except ValueError:
                    previous_workspace = None
                if previous_workspace is not None:
                    previous_workspace_panels = list(previous_workspace.ui.custom_panels)

            installed_panel_ids: list[str] = []
            try:
                if previous_installation is not None:
                    self._uninstall_extension_locked(manifest.name)

                for record in loaded.tools:
                    self.tools.register(record)

                for panel in prepared_panels:
                    self._add_custom_panel_locked(workspace_id, panel)
                    installed_panel_ids.append(panel.id)

                installation = ExtensionInstallation(
                    manifest=manifest,
                    loaded=loaded,
                    workspace_id=workspace_id,
                    panel_ids=list(installed_panel_ids),
                )
                self._extensions[manifest.name] = installation
                self._bump_version()
                return installation
            except Exception:
                if installed_panel_ids:
                    workspace = self.get_workspace(workspace_id)
                    workspace.ui.custom_panels = [
                        panel
                        for panel in workspace.ui.custom_panels
                        if panel.id not in installed_panel_ids
                    ]
                    self.workspace_registry.update_workspace(workspace)

                self.tools.unregister_by_extension(manifest.name)
                unload_extension_modules(loaded)

                if previous_installation is not None:
                    self._extensions[manifest.name] = previous_installation
                    for record in previous_installation.loaded.tools:
                        self.tools.register(record)

                    if previous_workspace_panels is not None:
                        workspace = self.get_workspace(previous_installation.workspace_id)
                        workspace.ui.custom_panels = previous_workspace_panels
                        self.workspace_registry.update_workspace(workspace)

                raise

    def uninstall_extension(self, name: str) -> ExtensionInstallation | None:
        with self._lock:
            return self._uninstall_extension_locked(name)

    def _uninstall_extension_locked(self, name: str) -> ExtensionInstallation | None:
        installation = self._extensions.pop(name, None)
        if installation is None:
            return None

        try:
            workspace = self.get_workspace(installation.workspace_id)
        except ValueError:
            workspace = None

        if workspace is not None:
            workspace.ui.custom_panels = [
                panel
                for panel in workspace.ui.custom_panels
                if panel.id not in installation.panel_ids
            ]
            self.workspace_registry.update_workspace(workspace)

        self.tools.unregister_by_extension(name)
        unload_extension_modules(installation.loaded)
        self._bump_version()
        return installation

    def reload_extension(self, name: str) -> ExtensionInstallation | None:
        with self._lock:
            installation = self._extensions.get(name)
            if installation is None:
                return None
            folder = installation.manifest.folder
            workspace_id = installation.workspace_id
        return self.install_extension(workspace_id, folder)

    def _add_custom_panel_locked(self, workspace_id: str, panel: CustomPanelSpec) -> None:
        workspace = self.get_workspace(workspace_id)
        panels = [existing for existing in workspace.ui.custom_panels if existing.id != panel.id]
        panels.append(panel)
        workspace.ui.custom_panels = panels
        self.workspace_registry.update_workspace(workspace)

    def extension_storage_dir(self, extension_name: str) -> Path:
        installation = self.get_extension(extension_name)
        if installation is None:
            raise ValueError(f"Unknown extension: {extension_name}")
        storage = installation.manifest.folder / "artifacts"
        storage.mkdir(parents=True, exist_ok=True)
        return storage

    def run_tool(
        self,
        uri: str,
        *,
        workspace_id: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        record = self.tools.get(uri)
        if record is None:
            raise ValueError(f"Unknown tool: {uri}")

        extension_name = record.extension or "default"
        try:
            storage = self.extension_storage_dir(extension_name)
        except ValueError:
            storage = Path.cwd()

        try:
            dataset = self.get_dataset(workspace_id)
        except ValueError:
            dataset = None

        call_params = dict(params or {})
        ctx = RunContext(
            runtime=self,
            workspace_id=workspace_id,
            dataset=dataset,
            params=call_params,
            extension_storage=storage,
            extension_name=extension_name,
        )
        return record.func(ctx, **call_params)

    def snapshot(self, workspace_id: str | None = None) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_id)
        return {
            "runtime_id": self.runtime_id,
            "version": self.version,
            "active_workspace_id": self.workspace_registry.active_workspace_id,
            "extensions": [installation.to_dict() for installation in self.list_extensions()],
            "tools": [record.to_dict() for record in self.tools.list()],
            "workspaces": [
                {
                    "id": item.id,
                    "dataset_name": item.dataset_name,
                }
                for item in self.workspace_registry.list()
            ],
            "workspace": {
                "id": workspace.id,
                "dataset_name": workspace.dataset_name,
                "ui": {
                    "active_layout_key": workspace.ui.active_layout_key,
                    "selected_ids": list(workspace.ui.selected_ids),
                    "layout_views": {
                        layout_key: view.to_dict()
                        for layout_key, view in sorted(workspace.ui.layout_views.items())
                    },
                    "custom_panels": [
                        {
                            **panel.to_dict(),
                            "data": self.get_panel_payload(workspace.id, panel),
                        }
                        for panel in workspace.ui.custom_panels
                    ],
                },
            },
        }
