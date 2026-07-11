"""Backend-owned panel control commands."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hyperview.control.models import CommandError
from hyperview.control.registry import CommandExecution, CommandRegistry, CommandSpec, EmptyArgs
from hyperview.runtime import HyperViewRuntime, SimilarityQueryState

PositivePanelDimension = Annotated[int, Field(gt=0)]


class PanelTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    panel_id: str


class PanelResizeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: PositivePanelDimension | None = None
    height: PositivePanelDimension | None = None
    min_width: PositivePanelDimension | None = None
    min_height: PositivePanelDimension | None = None
    max_width: PositivePanelDimension | None = None
    max_height: PositivePanelDimension | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> PanelResizeArgs:
        if not self.model_fields_set:
            raise ValueError("Panel resize requires at least one size or constraint field")
        return self


class PanelMoveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Literal["center", "right", "bottom"]
    reference_panel_id: str | None = None
    direction: Literal["right", "left", "above", "below", "within"] | None = None


class PanelAddArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel_id: str
    kind: Literal["extension", "scatter", "builtin"]
    title: str | None = None
    builtin_panel: str | None = None
    extension: str | None = None
    extension_panel: str | None = None
    layout_key: str | None = None
    position: Literal["center", "right", "bottom"] | None = None
    reference_panel_id: str | None = None
    direction: Literal["right", "left", "above", "below", "within"] | None = None
    width: PositivePanelDimension | None = None
    height: PositivePanelDimension | None = None
    min_width: PositivePanelDimension | None = None
    min_height: PositivePanelDimension | None = None
    max_width: PositivePanelDimension | None = None
    max_height: PositivePanelDimension | None = None
    visible: bool = True
    props: dict[str, Any] | None = None
    geometry: str | None = None
    layout_dimension: int | None = None
    require_resolved_layout: bool = True


class PanelUpdateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    position: Literal["center", "right", "bottom"] | None = None
    reference_panel_id: str | None = None
    direction: Literal["right", "left", "above", "below", "within"] | None = None
    width: PositivePanelDimension | None = None
    height: PositivePanelDimension | None = None
    min_width: PositivePanelDimension | None = None
    min_height: PositivePanelDimension | None = None
    max_width: PositivePanelDimension | None = None
    max_height: PositivePanelDimension | None = None
    visible: bool | None = None
    active: bool | None = None
    props: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> PanelUpdateArgs:
        if not self.model_fields_set:
            raise ValueError("Panel update requires at least one field")
        return self


class PanelPropsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    props: dict[str, Any]


class PanelStatePatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: dict[str, Any]
    replace_state: bool = False
    expected_revision: int | None = None
    client_id: str | None = None


class WorkspaceLayoutSetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: dict[str, Any] | None
    expected_revision: int | None = None
    client_id: str | None = None


class WorkspaceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str


class JobTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str


class SamplesRetrievalSetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: str
    layout_key: str | None = None
    index_id: str | None = None
    space_key: str | None = None
    k: int = 18
    source: str | None = None

    @model_validator(mode="after")
    def validate_limit(self) -> SamplesRetrievalSetArgs:
        if self.k < 1:
            raise ValueError("k must be a positive integer")
        return self


class SamplesRetrievalSetKArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    k: int

    @model_validator(mode="after")
    def validate_limit(self) -> SamplesRetrievalSetKArgs:
        if self.k < 1:
            raise ValueError("k must be a positive integer")
        return self


class SamplesRetrievalSetTextArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str
    layout_key: str | None = None
    index_id: str | None = None
    space_key: str | None = None
    k: int = 18
    source: str | None = None

    @model_validator(mode="after")
    def validate_query(self) -> SamplesRetrievalSetTextArgs:
        if not self.query_text.strip():
            raise ValueError("query_text must be a non-empty string")
        if self.k < 1:
            raise ValueError("k must be a positive integer")
        return self


class LabelsFilterArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = "label"
    value: Any = None
    clear: bool = False
    source: str | None = None

    @model_validator(mode="after")
    def require_value_unless_clear(self) -> LabelsFilterArgs:
        if not self.clear and "value" not in self.model_fields_set:
            raise ValueError("Labels filter requires value unless clear=true")
        return self


def _panel_target(target: BaseModel) -> PanelTarget:
    if not isinstance(target, PanelTarget):
        raise CommandError("validation_error", "Invalid panel target")
    return target


def _resize_args(args: BaseModel) -> PanelResizeArgs:
    if not isinstance(args, PanelResizeArgs):
        raise CommandError("validation_error", "Invalid panel resize args")
    return args


def _move_args(args: BaseModel) -> PanelMoveArgs:
    if not isinstance(args, PanelMoveArgs):
        raise CommandError("validation_error", "Invalid panel move args")
    return args


def _panel_add_args(args: BaseModel) -> PanelAddArgs:
    if not isinstance(args, PanelAddArgs):
        raise CommandError("validation_error", "Invalid panel add args")
    return args


def _panel_update_args(args: BaseModel) -> PanelUpdateArgs:
    if not isinstance(args, PanelUpdateArgs):
        raise CommandError("validation_error", "Invalid panel update args")
    return args


def _panel_props_args(args: BaseModel) -> PanelPropsArgs:
    if not isinstance(args, PanelPropsArgs):
        raise CommandError("validation_error", "Invalid panel props args")
    return args


def _panel_state_patch_args(args: BaseModel) -> PanelStatePatchArgs:
    if not isinstance(args, PanelStatePatchArgs):
        raise CommandError("validation_error", "Invalid panel state patch args")
    return args


def _workspace_target(target: BaseModel) -> WorkspaceTarget:
    if not isinstance(target, WorkspaceTarget):
        raise CommandError("validation_error", "Invalid workspace target")
    return target


def _cancel_job(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    if not isinstance(target, JobTarget):
        raise CommandError("validation_error", "Invalid job target")
    try:
        job = runtime.cancel_job(target.job_id)
    except ValueError as exc:
        raise CommandError("not_found", str(exc)) from exc
    return CommandExecution(result={"job": job.to_dict()})


def _samples_retrieval_set_args(args: BaseModel) -> SamplesRetrievalSetArgs:
    if not isinstance(args, SamplesRetrievalSetArgs):
        raise CommandError("validation_error", "Invalid samples retrieval set args")
    return args


def _samples_retrieval_set_k_args(args: BaseModel) -> SamplesRetrievalSetKArgs:
    if not isinstance(args, SamplesRetrievalSetKArgs):
        raise CommandError("validation_error", "Invalid samples retrieval k args")
    return args


def _samples_retrieval_set_text_args(args: BaseModel) -> SamplesRetrievalSetTextArgs:
    if not isinstance(args, SamplesRetrievalSetTextArgs):
        raise CommandError("validation_error", "Invalid samples text retrieval args")
    return args


def _labels_filter_args(args: BaseModel) -> LabelsFilterArgs:
    if not isinstance(args, LabelsFilterArgs):
        raise CommandError("validation_error", "Invalid labels filter args")
    return args


def _workspace_execution(workspace) -> CommandExecution:
    return CommandExecution(workspace=workspace, revision=workspace.ui.view_revision)


def _fields_set_payload(model: BaseModel) -> dict[str, Any]:
    return {field: getattr(model, field) for field in model.model_fields_set}


def _samples_panel_collection_result(workspace) -> dict[str, object]:
    state_entry = workspace.ui.panels.get("samples")
    state = state_entry.state if state_entry is not None else {}
    collection = state.get("collection")
    collection_id = state.get("collection_id")
    return {
        "panel_id": "samples",
        "collection_id": collection_id if isinstance(collection_id, str) else None,
        "collection": collection if isinstance(collection, dict) else None,
    }


def _space_key_deprecation_messages(args: BaseModel) -> tuple[str, ...]:
    if "space_key" not in args.model_fields_set:
        return ()
    return ("Deprecated argument 'space_key'; use 'index_id' instead.",)


def _add_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    add_args = _panel_add_args(args)
    workspace = runtime.add_runtime_panel(
        workspace_target.workspace_id,
        panel_id=add_args.panel_id,
        title=add_args.title,
        kind=add_args.kind,
        builtin_panel=add_args.builtin_panel,
        extension=add_args.extension,
        extension_panel=add_args.extension_panel,
        layout_key=add_args.layout_key,
        position=add_args.position,
        reference_panel_id=add_args.reference_panel_id,
        direction=add_args.direction,
        width=add_args.width,
        height=add_args.height,
        min_width=add_args.min_width,
        min_height=add_args.min_height,
        max_width=add_args.max_width,
        max_height=add_args.max_height,
        visible=add_args.visible,
        props=add_args.props,
        geometry=add_args.geometry,
        layout_dimension=add_args.layout_dimension,
        require_resolved_layout=add_args.require_resolved_layout,
    )
    return _workspace_execution(workspace)


def _update_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    update_args = _panel_update_args(args)
    patch = _fields_set_payload(update_args)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            **patch,
        )
    )


def _remove_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    return _workspace_execution(
        runtime.remove_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
        )
    )


def _resize_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    resize_args = _resize_args(args)
    patch = _fields_set_payload(resize_args)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            **patch,
        )
    )


def _move_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    move_args = _move_args(args)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            position=move_args.position,
            reference_panel_id=move_args.reference_panel_id,
            direction=move_args.direction,
        )
    )


def _focus_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            active=True,
            visible=True,
        )
    )


def _close_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            visible=False,
        )
    )


def _show_panel(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            visible=True,
        )
    )


def _update_panel_props(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    props_args = _panel_props_args(args)
    return _workspace_execution(
        runtime.update_custom_panel(
            panel_target.workspace_id,
            panel_target.panel_id,
            props=props_args.props,
        )
    )


def _get_panel_state(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    workspace = runtime.get_workspace(panel_target.workspace_id)
    state_payload = runtime.get_panel_state(
        panel_target.workspace_id,
        panel_target.panel_id,
    )
    return CommandExecution(
        workspace=workspace,
        result=state_payload,
        revision=int(state_payload.get("state_revision") or 0),
    )


def _patch_panel_state(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    panel_target = _panel_target(target)
    patch_args = _panel_state_patch_args(args)
    try:
        workspace = runtime.patch_panel_state(
            panel_target.workspace_id,
            panel_target.panel_id,
            patch_args.state,
            replace_state=patch_args.replace_state,
            expected_revision=patch_args.expected_revision,
            source_client_id=patch_args.client_id,
        )
    except ValueError as exc:
        if "revision conflict" in str(exc):
            raise CommandError("conflict", str(exc)) from exc
        raise
    state_payload = runtime.get_panel_state(panel_target.workspace_id, panel_target.panel_id)
    return CommandExecution(
        workspace=workspace,
        result=state_payload,
        revision=int(state_payload.get("state_revision") or 0),
    )


def _get_workspace_layout(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    workspace = runtime.get_workspace(workspace_target.workspace_id)
    payload = runtime.get_workspace_layout(workspace_target.workspace_id)
    return CommandExecution(
        workspace=workspace,
        result=payload,
        revision=int(payload["layout_revision"]),
    )


def _set_workspace_layout(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    layout_args = args if isinstance(args, WorkspaceLayoutSetArgs) else WorkspaceLayoutSetArgs()
    try:
        workspace = runtime.set_workspace_layout(
            workspace_target.workspace_id,
            layout_args.layout,
            expected_revision=layout_args.expected_revision,
            source_client_id=layout_args.client_id,
        )
    except ValueError as exc:
        if "revision conflict" in str(exc):
            raise CommandError("conflict", str(exc)) from exc
        raise
    payload = runtime.get_workspace_layout(workspace_target.workspace_id)
    return CommandExecution(
        workspace=workspace,
        result=payload,
        revision=int(payload["layout_revision"]),
    )


def _set_samples_retrieval_anchor(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    retrieval_args = _samples_retrieval_set_args(args)
    query = runtime.resolve_similarity_query(
        workspace_target.workspace_id,
        retrieval_args.sample_id,
        layout_key=retrieval_args.layout_key,
        index_id=retrieval_args.index_id,
        space_key=retrieval_args.space_key,
        k=retrieval_args.k,
        source=retrieval_args.source,
    )
    workspace = runtime.set_samples_retrieval(workspace_target.workspace_id, query)
    return CommandExecution(
        workspace=workspace,
        result=_samples_panel_collection_result(workspace),
        revision=workspace.ui.view_revision,
        messages=_space_key_deprecation_messages(retrieval_args),
    )


def _clear_samples_retrieval(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    workspace = runtime.clear_samples_retrieval(workspace_target.workspace_id)
    return CommandExecution(
        workspace=workspace,
        result=_samples_panel_collection_result(workspace),
        revision=workspace.ui.view_revision,
    )


def _set_samples_retrieval_k(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    k_args = _samples_retrieval_set_k_args(args)
    current_query = runtime.get_samples_retrieval_query(workspace_target.workspace_id)
    if current_query is None:
        raise CommandError("validation_error", "Samples retrieval has no active anchor")

    next_query = SimilarityQueryState(
        anchor_sample_id=current_query.anchor_sample_id,
        query_text=current_query.query_text,
        layout_key=current_query.layout_key,
        space_key=current_query.space_key,
        k=k_args.k,
        source=current_query.source,
    )
    workspace = runtime.set_samples_retrieval(workspace_target.workspace_id, next_query)
    return CommandExecution(
        workspace=workspace,
        result=_samples_panel_collection_result(workspace),
        revision=workspace.ui.view_revision,
    )


def _set_samples_text_retrieval(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    retrieval_args = _samples_retrieval_set_text_args(args)
    query = runtime.resolve_text_retrieval_query(
        workspace_target.workspace_id,
        retrieval_args.query_text,
        layout_key=retrieval_args.layout_key,
        index_id=retrieval_args.index_id,
        space_key=retrieval_args.space_key,
        k=retrieval_args.k,
        source=retrieval_args.source,
    )
    workspace = runtime.set_samples_retrieval(workspace_target.workspace_id, query)
    return CommandExecution(
        workspace=workspace,
        result=_samples_panel_collection_result(workspace),
        revision=workspace.ui.view_revision,
        messages=_space_key_deprecation_messages(retrieval_args),
    )


def _filter_labels(
    runtime: HyperViewRuntime,
    target: BaseModel,
    args: BaseModel,
) -> CommandExecution:
    workspace_target = _workspace_target(target)
    filter_args = _labels_filter_args(args)
    if filter_args.clear:
        workspace = runtime.clear_samples_filter(workspace_target.workspace_id)
    else:
        workspace = runtime.set_samples_filter(
            workspace_target.workspace_id,
            field=filter_args.field,
            value=filter_args.value,
            source=filter_args.source,
        )
    return CommandExecution(
        workspace=workspace,
        result=_samples_panel_collection_result(workspace),
        revision=workspace.ui.view_revision,
    )


def create_default_command_registry() -> CommandRegistry:
    registry = CommandRegistry()
    for spec in (
        CommandSpec(
            id="workspace.panel.add",
            owner="backend",
            summary="Add or replace a runtime-managed panel.",
            target_model=WorkspaceTarget,
            args_model=PanelAddArgs,
            handler=_add_panel,
        ),
        CommandSpec(
            id="workspace.panel.update",
            owner="backend",
            summary="Update durable runtime panel fields.",
            target_model=PanelTarget,
            args_model=PanelUpdateArgs,
            handler=_update_panel,
        ),
        CommandSpec(
            id="workspace.panel.remove",
            owner="backend",
            summary="Remove a runtime-managed panel from the workspace view.",
            target_model=PanelTarget,
            args_model=EmptyArgs,
            handler=_remove_panel,
        ),
        CommandSpec(
            id="workspace.panel.resize",
            owner="backend",
            summary="Resize a runtime-managed panel.",
            target_model=PanelTarget,
            args_model=PanelResizeArgs,
            handler=_resize_panel,
        ),
        CommandSpec(
            id="workspace.panel.move",
            owner="backend",
            summary="Move a runtime-managed panel.",
            target_model=PanelTarget,
            args_model=PanelMoveArgs,
            handler=_move_panel,
        ),
        CommandSpec(
            id="workspace.panel.focus",
            owner="backend",
            summary="Focus a runtime-managed panel.",
            target_model=PanelTarget,
            args_model=EmptyArgs,
            handler=_focus_panel,
        ),
        CommandSpec(
            id="workspace.panel.close",
            owner="backend",
            summary="Hide a runtime-managed panel without removing it.",
            target_model=PanelTarget,
            args_model=EmptyArgs,
            handler=_close_panel,
        ),
        CommandSpec(
            id="workspace.panel.show",
            owner="backend",
            summary="Show a hidden runtime-managed panel.",
            target_model=PanelTarget,
            args_model=EmptyArgs,
            handler=_show_panel,
        ),
        CommandSpec(
            id="workspace.panel.update-props",
            owner="backend",
            summary="Replace documented props for a runtime-managed panel.",
            target_model=PanelTarget,
            args_model=PanelPropsArgs,
            handler=_update_panel_props,
        ),
        CommandSpec(
            id="workspace.panel.state.get",
            owner="backend",
            summary="Read durable runtime-managed state for a panel.",
            target_model=PanelTarget,
            args_model=EmptyArgs,
            handler=_get_panel_state,
        ),
        CommandSpec(
            id="workspace.panel.state.patch",
            owner="backend",
            summary="Patch durable runtime-managed state for a panel.",
            target_model=PanelTarget,
            args_model=PanelStatePatchArgs,
            handler=_patch_panel_state,
        ),
        CommandSpec(
            id="workspace.layout.get",
            owner="backend",
            summary="Read the persisted Dockview workspace layout.",
            target_model=WorkspaceTarget,
            args_model=EmptyArgs,
            handler=_get_workspace_layout,
        ),
        CommandSpec(
            id="workspace.layout.set",
            owner="backend",
            summary="Replace the persisted Dockview workspace layout.",
            target_model=WorkspaceTarget,
            args_model=WorkspaceLayoutSetArgs,
            handler=_set_workspace_layout,
        ),
        CommandSpec(
            id="panel.samples.retrieval.set-anchor",
            owner="backend",
            summary="Set Samples panel retrieval anchor state.",
            target_model=WorkspaceTarget,
            args_model=SamplesRetrievalSetArgs,
            handler=_set_samples_retrieval_anchor,
        ),
        CommandSpec(
            id="panel.samples.retrieval.clear",
            owner="backend",
            summary="Clear Samples panel retrieval state.",
            target_model=WorkspaceTarget,
            args_model=EmptyArgs,
            handler=_clear_samples_retrieval,
        ),
        CommandSpec(
            id="panel.samples.retrieval.set-k",
            owner="backend",
            summary="Set Samples panel retrieval result count.",
            target_model=WorkspaceTarget,
            args_model=SamplesRetrievalSetKArgs,
            handler=_set_samples_retrieval_k,
        ),
        CommandSpec(
            id="panel.samples.retrieval.set-text-query",
            owner="backend",
            summary="Set Samples panel text retrieval query state.",
            target_model=WorkspaceTarget,
            args_model=SamplesRetrievalSetTextArgs,
            handler=_set_samples_text_retrieval,
        ),
        CommandSpec(
            id="collection.neighbors.create",
            owner="backend",
            summary="Create a nearest-neighbor collection for the Samples panel.",
            target_model=WorkspaceTarget,
            args_model=SamplesRetrievalSetArgs,
            handler=_set_samples_retrieval_anchor,
        ),
        CommandSpec(
            id="collection.search.create",
            owner="backend",
            summary="Create a text-search collection for the Samples panel.",
            target_model=WorkspaceTarget,
            args_model=SamplesRetrievalSetTextArgs,
            handler=_set_samples_text_retrieval,
        ),
        CommandSpec(
            id="collection.filter.set",
            owner="backend",
            summary="Create or clear a label filter collection for the Samples panel.",
            target_model=WorkspaceTarget,
            args_model=LabelsFilterArgs,
            handler=_filter_labels,
        ),
        CommandSpec(
            id="jobs.cancel",
            owner="backend",
            summary="Request cooperative cancellation of a queued or running job.",
            target_model=JobTarget,
            args_model=EmptyArgs,
            handler=_cancel_job,
        ),
    ):
        registry.register(spec)
    return registry
