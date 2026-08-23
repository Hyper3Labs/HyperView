"""Backend-owned commands for runtime, workspace, and extension mutations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hyperview.control.models import CommandError
from hyperview.control.registry import CommandExecution, CommandSpec, EmptyArgs
from hyperview.runtime import HyperViewRuntime, LayoutViewState


class WorkspaceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str


class ProviderTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str


class ExtensionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class WorkspaceCreateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str | None = None
    activate: bool = False


class WorkspaceDatasetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str


class WorkspaceActiveLayoutArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_key: str | None
    client_id: str | None = None


class WorkspaceSelectionArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_ids: list[str] = Field(default_factory=list, max_length=2000)
    client_id: str | None = None


class WorkspaceStatePatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_active_layout: bool = False
    active_layout_key: str | None = None
    set_selection: bool = False
    selected_ids: list[str] | None = Field(default=None, max_length=2000)
    client_id: str | None = None

    @model_validator(mode="after")
    def require_a_mutation(self) -> WorkspaceStatePatchArgs:
        if not self.set_active_layout and not self.set_selection:
            raise ValueError("Workspace state patch requires at least one mutation")
        return self


class OrbitViewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    yaw: float
    pitch: float
    distance: float
    target_x: float
    target_y: float
    target_z: float
    ortho_scale: float


class WorkspaceLayoutViewArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_key: str
    camera_3d: OrbitViewArgs | None = None


class ProviderRegisterArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    import_path: str
    description: str | None = None
    defaults: dict[str, Any] | None = None
    overwrite: bool = False


class EmbeddingsComputeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    model: str
    provider: str | None = None
    checkpoint: str | None = None
    provider_kwargs: dict[str, Any] | None = None
    layouts: list[str] | None = None
    method: str = "umap"
    n_neighbors: int = Field(default=15, gt=0)
    min_dist: float = Field(default=0.1, ge=0)
    metric: str = "cosine"
    activate_layout: bool = True


class LayoutsComputeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str
    space_key: str | None = None
    layouts: list[str]
    method: str = "umap"
    n_neighbors: int = Field(default=15, gt=0)
    min_dist: float = Field(default=0.1, ge=0)
    metric: str = "cosine"
    activate_layout: bool = True


class ExtensionInstallArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: str | None = None
    shipped: str | None = None
    add_panels: bool = False

    @model_validator(mode="after")
    def require_one_source(self) -> ExtensionInstallArgs:
        if bool(self.folder) == bool(self.shipped):
            raise ValueError("Provide exactly one of folder or shipped")
        return self


def _workspace_target(target: BaseModel) -> WorkspaceTarget:
    if not isinstance(target, WorkspaceTarget):
        raise CommandError("validation_error", "Invalid workspace target")
    return target


def _provider_target(target: BaseModel) -> ProviderTarget:
    if not isinstance(target, ProviderTarget):
        raise CommandError("validation_error", "Invalid provider target")
    return target


def _extension_target(target: BaseModel) -> ExtensionTarget:
    if not isinstance(target, ExtensionTarget):
        raise CommandError("validation_error", "Invalid extension target")
    return target


def _create_workspace(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    create_args = args if isinstance(args, WorkspaceCreateArgs) else WorkspaceCreateArgs()
    workspace = runtime.create_workspace(workspace_target.workspace_id, activate=create_args.activate)
    if create_args.dataset_name:
        workspace = runtime.set_workspace_dataset(workspace.id, create_args.dataset_name)
    return CommandExecution(workspace=workspace, result={"workspace_id": workspace.id})


def _delete_workspace(runtime: HyperViewRuntime, target: BaseModel, _args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    workspace = runtime.delete_workspace(workspace_target.workspace_id)
    return CommandExecution(
        workspace=workspace,
        result={
            "deleted_workspace_id": workspace_target.workspace_id,
            "active_workspace_id": runtime.workspace_registry.active_workspace_id,
        },
    )


def _activate_workspace(runtime: HyperViewRuntime, target: BaseModel, _args: BaseModel) -> CommandExecution:
    workspace = runtime.set_active_workspace(_workspace_target(target).workspace_id)
    return CommandExecution(workspace=workspace, result={"workspace_id": workspace.id})


def _set_workspace_dataset(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    dataset_args = args if isinstance(args, WorkspaceDatasetArgs) else None
    if dataset_args is None:
        raise CommandError("validation_error", "Invalid workspace dataset arguments")
    workspace = runtime.set_workspace_dataset(workspace_target.workspace_id, dataset_args.dataset_name)
    return CommandExecution(workspace=workspace, result={"dataset_name": dataset_args.dataset_name})


def _set_active_layout(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    layout_args = args if isinstance(args, WorkspaceActiveLayoutArgs) else None
    if layout_args is None:
        raise CommandError("validation_error", "Invalid active-layout arguments")
    workspace = runtime.patch_ui_state(
        workspace_target.workspace_id,
        set_active_layout=True,
        active_layout_key=layout_args.layout_key,
        source_client_id=layout_args.client_id,
    )
    return CommandExecution(workspace=workspace, result={"layout_key": layout_args.layout_key})


def _set_selection(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    selection_args = args if isinstance(args, WorkspaceSelectionArgs) else None
    if selection_args is None:
        raise CommandError("validation_error", "Invalid selection arguments")
    workspace = runtime.set_selection(workspace_target.workspace_id, selection_args.sample_ids)
    return CommandExecution(
        workspace=workspace,
        result={"selected_ids": list(workspace.ui.selected_ids)},
    )


def _patch_workspace_state(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    patch_args = args if isinstance(args, WorkspaceStatePatchArgs) else None
    if patch_args is None:
        raise CommandError("validation_error", "Invalid workspace state arguments")
    workspace = runtime.patch_ui_state(
        workspace_target.workspace_id,
        set_active_layout=patch_args.set_active_layout,
        active_layout_key=patch_args.active_layout_key,
        set_selection=patch_args.set_selection,
        selected_ids=patch_args.selected_ids,
        source_client_id=patch_args.client_id,
    )
    return CommandExecution(workspace=workspace)


def _set_layout_view(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    view_args = args if isinstance(args, WorkspaceLayoutViewArgs) else None
    if view_args is None:
        raise CommandError("validation_error", "Invalid layout-view arguments")
    workspace = runtime.set_layout_view(
        workspace_target.workspace_id,
        view_args.layout_key,
        LayoutViewState(
            camera_3d=view_args.camera_3d.model_dump() if view_args.camera_3d is not None else None
        ),
    )
    return CommandExecution(
        workspace=workspace,
        result={"layout_key": view_args.layout_key, "view": workspace.ui.layout_views[view_args.layout_key].to_dict()},
    )


def _register_provider(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    provider_target = _provider_target(target)
    register_args = args if isinstance(args, ProviderRegisterArgs) else None
    if register_args is None:
        raise CommandError("validation_error", "Invalid provider arguments")
    registration = runtime.provider_registry.register_python(
        provider_target.alias,
        register_args.import_path,
        description=register_args.description,
        defaults=register_args.defaults,
        overwrite=register_args.overwrite,
    )
    runtime._bump_version()
    return CommandExecution(result={"provider": registration.to_dict()})


def _unregister_provider(runtime: HyperViewRuntime, target: BaseModel, _args: BaseModel) -> CommandExecution:
    provider_target = _provider_target(target)
    if not runtime.provider_registry.unregister(provider_target.alias):
        raise CommandError("not_found", f"Unknown provider: {provider_target.alias}")
    runtime._bump_version()
    return CommandExecution(result={"alias": provider_target.alias})


def _compute_embeddings(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    compute_args = args if isinstance(args, EmbeddingsComputeArgs) else None
    if compute_args is None:
        raise CommandError("validation_error", "Invalid embedding arguments")
    job = runtime.submit_embedding_job(
        workspace_id=workspace_target.workspace_id,
        **compute_args.model_dump(),
    )
    return CommandExecution(
        workspace=runtime.get_workspace(workspace_target.workspace_id),
        result={"job": job.to_dict()},
    )


def _compute_layouts(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    compute_args = args if isinstance(args, LayoutsComputeArgs) else None
    if compute_args is None:
        raise CommandError("validation_error", "Invalid layout arguments")
    job = runtime.submit_layout_job(
        workspace_id=workspace_target.workspace_id,
        **compute_args.model_dump(),
    )
    return CommandExecution(
        workspace=runtime.get_workspace(workspace_target.workspace_id),
        result={"job": job.to_dict()},
    )


def _install_extension(runtime: HyperViewRuntime, target: BaseModel, args: BaseModel) -> CommandExecution:
    workspace_target = _workspace_target(target)
    install_args = args if isinstance(args, ExtensionInstallArgs) else None
    if install_args is None:
        raise CommandError("validation_error", "Invalid extension arguments")
    if install_args.shipped:
        installation = runtime.install_shipped_extension(
            workspace_target.workspace_id,
            install_args.shipped,
            add_panels=install_args.add_panels,
        )
    else:
        folder = Path(install_args.folder or "").expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"Extension folder not found: {folder}")
        installation = runtime.install_extension(
            workspace_target.workspace_id,
            folder,
            add_panels=install_args.add_panels,
        )
    return CommandExecution(
        workspace=runtime.get_workspace(workspace_target.workspace_id),
        result={"extension": installation.to_dict()},
    )


def _remove_extension(runtime: HyperViewRuntime, target: BaseModel, _args: BaseModel) -> CommandExecution:
    extension_target = _extension_target(target)
    installation = runtime.get_extension(extension_target.name)
    if installation is None:
        raise CommandError("not_found", f"Unknown extension: {extension_target.name}")
    workspace_id = installation.workspace_id
    removed = runtime.uninstall_extension(extension_target.name)
    if removed is None:
        raise CommandError("not_found", f"Unknown extension: {extension_target.name}")
    return CommandExecution(
        workspace=runtime.get_workspace(workspace_id),
        result={"extension": removed.to_dict()},
    )


def runtime_command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("workspace.create", "backend", "Create a workspace.", WorkspaceTarget, WorkspaceCreateArgs, _create_workspace),
        CommandSpec("workspace.delete", "backend", "Delete a workspace.", WorkspaceTarget, EmptyArgs, _delete_workspace),
        CommandSpec("workspace.activate", "backend", "Activate a workspace.", WorkspaceTarget, EmptyArgs, _activate_workspace),
        CommandSpec("workspace.dataset.set", "backend", "Bind a dataset to a workspace.", WorkspaceTarget, WorkspaceDatasetArgs, _set_workspace_dataset),
        CommandSpec("workspace.active-layout.set", "backend", "Set the active visualization layout.", WorkspaceTarget, WorkspaceActiveLayoutArgs, _set_active_layout),
        CommandSpec("workspace.selection.set", "backend", "Replace the workspace sample selection.", WorkspaceTarget, WorkspaceSelectionArgs, _set_selection),
        CommandSpec("workspace.state.patch", "backend", "Atomically patch workspace UI state.", WorkspaceTarget, WorkspaceStatePatchArgs, _patch_workspace_state),
        CommandSpec("workspace.layout-view.set", "backend", "Persist a layout camera view.", WorkspaceTarget, WorkspaceLayoutViewArgs, _set_layout_view),
        CommandSpec("provider.register", "backend", "Register a Python embedding provider.", ProviderTarget, ProviderRegisterArgs, _register_provider),
        CommandSpec("provider.unregister", "backend", "Remove a custom embedding provider.", ProviderTarget, EmptyArgs, _unregister_provider),
        CommandSpec("embeddings.compute", "backend", "Submit an embedding computation job.", WorkspaceTarget, EmbeddingsComputeArgs, _compute_embeddings),
        CommandSpec("layouts.compute", "backend", "Submit a layout computation job.", WorkspaceTarget, LayoutsComputeArgs, _compute_layouts),
        CommandSpec("extension.install", "backend", "Install a local or shipped extension.", WorkspaceTarget, ExtensionInstallArgs, _install_extension),
        CommandSpec("extension.remove", "backend", "Remove an installed extension.", ExtensionTarget, EmptyArgs, _remove_extension),
    )


__all__ = ["runtime_command_specs"]
