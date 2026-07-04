"""FastAPI application for HyperView."""

import asyncio
import io
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from hyperview._version import __version__
from hyperview.control import (
    CommandEnvelope,
    ControlService,
    create_default_command_registry,
)
from hyperview.core.dataset import Dataset
from hyperview.core.selection import (
    OrbitViewState3D,
    points_in_polygon,
    select_ids_for_3d_lasso,
)
from hyperview.runtime import (
    HyperViewRuntime,
    LayoutViewState,
)
from hyperview.storage.metrics import distance_metric_for_space
from hyperview.storage.schema import parse_layout_dimension

# Extensions whose content is handed off to esbuild for JSX transformation.
_JSX_SUFFIXES = {".jsx"}
_PASSTHROUGH_JS_SUFFIXES = {".js", ".mjs"}

# Global runtime reference (set by launch()/serve)
_current_runtime: HyperViewRuntime | None = None
_current_session_id: str | None = None
MAX_SAMPLE_PAGE_SIZE = 500
MAX_SAMPLE_BATCH_SIZE = 1000
DEFAULT_THUMBNAIL_SIZE = 128


class SelectionRequest(BaseModel):
    """Request model for selection sync."""

    sample_ids: list[str]
    include_thumbnails: bool = False


class LassoSelectionRequest(BaseModel):
    """Request model for lasso selection queries."""

    layout_key: str  # e.g., "openai_clip-vit-base-patch32__umap"
    # Polygon vertices, interleaved: [x0, y0, x1, y1, ...]
    # - 2D layouts: data-space polygon (same coordinates as /api/embeddings)
    # - 3D layouts: screen-space polygon in CSS pixels
    polygon: list[float]
    # Required for 3D lasso requests.
    view_3d: dict[str, float] | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    label_filter: str | None = None
    missing_label_filter: bool = False
    offset: int = 0
    limit: int = 100
    include_thumbnails: bool = False


class ProviderRegisterRequest(BaseModel):
    alias: str
    import_path: str
    description: str | None = None
    defaults: dict[str, Any] | None = None
    overwrite: bool = False


class WorkspaceCreateRequest(BaseModel):
    workspace_id: str
    dataset_name: str | None = None
    activate: bool = False


class WorkspaceActivateRequest(BaseModel):
    workspace_id: str


class UiLayoutRequest(BaseModel):
    workspace_id: str
    layout_key: str | None


class UiSelectionRequest(BaseModel):
    workspace_id: str
    sample_ids: list[str]


class UiStatePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    client_id: str | None = None
    set_active_layout: bool = False
    active_layout_key: str | None = None
    set_selection: bool = False
    selected_ids: list[str] | None = None


class UiLayoutViewRequest(BaseModel):
    workspace_id: str
    layout_key: str
    camera_3d: OrbitViewState3D | None = None


class SamplesQueryRequest(BaseModel):
    workspace_id: str | None = None
    ids: list[str] | None = None
    labels: list[str | None] | None = None
    metadata: dict[str, Any] | None = None
    offset: int = 0
    limit: int = 100
    include_thumbnails: bool = False


class SamplesSelectionQueryRequest(BaseModel):
    workspace_id: str
    ids: list[str] | None = None
    labels: list[str | None] | None = None
    metadata: dict[str, Any] | None = None
    limit: int | None = None


class SamplesAggregateRequest(BaseModel):
    workspace_id: str | None = None
    group_by: str = "label"
    ids: list[str] | None = None
    labels: list[str | None] | None = None
    metadata: dict[str, Any] | None = None


class EmbeddingsComputeRequest(BaseModel):
    workspace_id: str
    dataset_name: str
    model: str
    provider: str | None = None
    checkpoint: str | None = None
    provider_kwargs: dict[str, Any] | None = None
    layouts: list[str] | None = None
    method: str = "umap"
    n_neighbors: int = 15
    min_dist: float = 0.1
    metric: str = "cosine"
    activate_layout: bool = True


class LayoutComputeRequest(BaseModel):
    workspace_id: str
    dataset_name: str
    space_key: str | None = None
    layouts: list[str]
    method: str = "umap"
    n_neighbors: int = 15
    min_dist: float = 0.1
    metric: str = "cosine"
    activate_layout: bool = True


class ToolRunRequest(BaseModel):
    tool: str
    workspace_id: str
    params: dict[str, Any] | None = None


class ExtensionInstallRequest(BaseModel):
    workspace_id: str
    folder: str
    add_panels: bool = False


class ExtensionRemoveRequest(BaseModel):
    name: str


def _control_service(runtime: HyperViewRuntime) -> ControlService:
    return ControlService(runtime, create_default_command_registry())


class SampleResponse(BaseModel):
    """Response model for a sample."""

    id: str
    filepath: str
    filename: str
    label: str | None
    text: str | None = None
    modality: str = "image"
    thumbnail: str | None
    media_url: str | None = None
    thumbnail_url: str | None = None
    metadata: dict
    width: int | None = None
    height: int | None = None


class LayoutInfoResponse(BaseModel):
    """Response model for layout info."""

    layout_key: str
    space_key: str
    method: str
    geometry: str
    count: int
    params: dict[str, Any] | None


class SpaceInfoResponse(BaseModel):
    """Response model for embedding space info."""

    space_key: str
    model_id: str
    dim: int
    count: int
    provider: str
    geometry: str
    config: dict[str, Any] | None


class DatasetResponse(BaseModel):
    """Response model for dataset info."""

    name: str
    num_samples: int
    labels: list[str]
    spaces: list[SpaceInfoResponse]
    layouts: list[LayoutInfoResponse]


class EmbeddingsResponse(BaseModel):
    """Response model for embeddings data (for scatter plot)."""

    layout_key: str
    geometry: str
    ids: list[str]
    labels: list[str | None]
    coords: list[list[float]]


class SimilarSampleResponse(SampleResponse):
    """Response model for a similar sample with distance."""

    distance: float


class SimilaritySearchResponse(BaseModel):
    """Response model for similarity search results."""

    query_id: str | None = None
    query_text: str | None = None
    query_sample: SampleResponse | None
    space_key: str | None
    metric: str
    k: int
    results: list[SimilarSampleResponse]


class TextSearchRequest(BaseModel):
    query_text: str
    k: int = 10
    space_key: str | None = None
    layout_key: str | None = None
    include_thumbnails: bool = False


def serialize_sample_for_response(
    sample: Any,
    include_thumbnail: bool = False,
    *,
    ensure_dimensions: bool = False,
) -> dict[str, Any]:
    thumbnail = None
    if include_thumbnail:
        try:
            thumbnail = sample.get_thumbnail_base64()
        except Exception:
            thumbnail = None

    payload = sample.to_api_dict(
        include_thumbnail=False,
        ensure_dimensions=ensure_dimensions,
    )
    payload["thumbnail"] = thumbnail
    payload["media_url"] = f"/api/samples/{sample.id}/content"
    payload["thumbnail_url"] = f"/api/samples/{sample.id}/thumbnail"
    return payload


def _resolve_sample_media_path(sample: Any) -> Path:
    file_path = Path(sample.filepath).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample media not found: {sample.filepath}")
    return file_path


def _media_cache_headers(file_path: Path, *, variant: str) -> dict[str, str]:
    stat = file_path.stat()
    etag = f'W/"{variant}-{stat.st_mtime_ns}-{stat.st_size}"'
    return {
        "Cache-Control": "public, max-age=3600",
        "ETag": etag,
    }


def _validate_page(offset: int, limit: int, *, max_limit: int = MAX_SAMPLE_PAGE_SIZE) -> tuple[int, int]:
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    if limit < 1 or limit > max_limit:
        raise HTTPException(status_code=400, detail=f"limit must be between 1 and {max_limit}")
    return offset, limit


def _metadata_value(metadata: dict[str, Any], path: str) -> Any:
    value: Any = metadata
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _query_samples(ds: Dataset, request: SamplesQueryRequest | SamplesAggregateRequest) -> list[Any]:
    samples = ds.get_samples_by_ids(request.ids) if request.ids is not None else ds.samples
    if request.labels is not None:
        wanted_labels = set(request.labels)
        samples = [sample for sample in samples if sample.label in wanted_labels]
    for key, expected in (request.metadata or {}).items():
        samples = [
            sample
            for sample in samples
            if _metadata_value(sample.metadata, key) == expected
        ]
    return samples


def _resolve_collection_items(
    ds: Dataset,
    collection: Any,
    *,
    offset: int,
    limit: int,
) -> tuple[list[tuple[Any, float | None]], int, bool]:
    """Materialize a page of a collection's members as (sample, score) pairs.

    Reuses the same retrieval/filtering methods the collection.* commands used
    to build the collection, rather than storing membership row-by-row, so a
    collection always reflects current data.
    """
    query = collection.query or {}

    if collection.kind == "neighbors":
        anchor = query.get("anchor") or {}
        sample_id = str(anchor.get("entityId") or "")
        if not sample_id:
            raise ValueError("Neighbors collection is missing an anchor entity id")
        k = int(query.get("k") or 18)
        results = ds.find_similar(sample_id, k=k, space_key=query.get("spaceKey"))
        total = len(results)
        page = results[offset : offset + limit]
        return (
            [(sample, float(distance)) for sample, distance in page],
            total,
            offset + limit < total,
        )

    if collection.kind == "search":
        query_text = str(query.get("queryText") or "")
        if not query_text:
            raise ValueError("Search collection is missing queryText")
        k = int(query.get("k") or 18)
        results = ds.find_similar_by_text(query_text, k=k, space_key=query.get("spaceKey"))
        total = len(results)
        page = results[offset : offset + limit]
        return (
            [(sample, float(distance)) for sample, distance in page],
            total,
            offset + limit < total,
        )

    if collection.kind == "filter":
        field = str(query.get("field") or "label")
        op = str(query.get("op") or "eq")
        value = query.get("value")
        if field == "label" and op == "eq":
            samples, total = ds.get_samples_paginated(offset=offset, limit=limit, label=value)
            return [(sample, None) for sample in samples], total, offset + limit < total
        # Less common field/op combinations: filter in memory. Every sample is
        # still loaded once per request in this path, unlike the label fast path.
        all_samples = ds.samples
        if field == "label":
            matches = [s for s in all_samples if s.label == value]
        else:
            matches = [s for s in all_samples if _metadata_value(s.metadata, field) == value]
        total = len(matches)
        page = matches[offset : offset + limit]
        return [(sample, None) for sample in page], total, offset + limit < total

    if collection.kind == "all":
        samples, total = ds.get_samples_paginated(offset=offset, limit=limit)
        return [(sample, None) for sample in samples], total, offset + limit < total

    raise ValueError(f"Collection kind '{collection.kind}' is not yet materializable")


def create_app(
    dataset: Dataset | None = None,
    runtime: HyperViewRuntime | None = None,
    session_id: str | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        dataset: Optional dataset to serve. If None, uses global dataset.

    Returns:
        FastAPI application instance.
    """
    global _current_runtime, _current_session_id
    if runtime is None:
        runtime = _current_runtime
    if runtime is None:
        runtime = HyperViewRuntime()
    if dataset is not None:
        runtime.attach_dataset_instance("default", dataset, activate_workspace=True)
    _current_runtime = runtime
    if session_id is not None:
        _current_session_id = session_id

    app = FastAPI(
        title="HyperView",
        description="Dataset visualization with hyperbolic embeddings",
        version=__version__,
    )

    def get_runtime() -> HyperViewRuntime:
        """Dependency that returns the current runtime or raises 404."""
        if _current_runtime is None:
            raise HTTPException(status_code=404, detail="No runtime loaded")
        return _current_runtime

    def get_dataset(
        workspace_id: str | None = Query(None),
        dataset_name: str | None = Query(None),
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ) -> Dataset:
        """Dependency that resolves the current dataset from the active workspace."""
        try:
            return runtime_dep.get_dataset(workspace_id=workspace_id, dataset_name=dataset_name)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # CORS middleware for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/__hyperview__/health")
    async def hyperview_health():
        snapshot = _current_runtime.snapshot() if _current_runtime is not None else None
        return {
            "name": "hyperview",
            "version": app.version,
            "session_id": _current_session_id,
            "workspace_id": snapshot["workspace"]["id"] if snapshot is not None else None,
            "dataset": snapshot["workspace"]["dataset_name"] if snapshot is not None else None,
            "pid": os.getpid(),
        }

    @app.get("/api/runtime")
    async def get_runtime_state(
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
        workspace_id: str | None = Query(None),
    ):
        return runtime_dep.snapshot(workspace_id)

    @app.get("/api/events")
    async def stream_runtime_events(
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
        workspace_id: str | None = Query(None),
        client_id: str | None = Query(None),
    ):
        async def event_stream():
            last_version = -1
            while True:
                snapshot = runtime_dep.snapshot(workspace_id)
                if snapshot["version"] != last_version:
                    last_version = snapshot["version"]
                    if (
                        client_id
                        and runtime_dep.version_source_client_id == client_id
                    ):
                        await asyncio.sleep(0.5)
                        continue
                    payload = json.dumps(snapshot)
                    yield f"data: {payload}\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/panels/content/{workspace_id}/{panel_id}/{asset_path:path}")
    async def get_panel_asset(
        workspace_id: str,
        panel_id: str,
        asset_path: str,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        def resolve_asset(root_dir: Path) -> tuple[Path | None, bool]:
            requested = (root_dir / asset_path).resolve()
            if requested != root_dir and root_dir not in requested.parents:
                return None, True
            if requested.exists() and requested.is_file():
                return requested, False
            return None, False

        panel_error: ValueError | None = None
        module_file: Path | None = None
        try:
            panel = runtime_dep.get_custom_panel(workspace_id, panel_id)
            module_file = panel.resolved_module_file()
        except ValueError as exc:
            panel_error = exc

        requested_asset: Path | None = None
        escaped = False
        if module_file is not None:
            requested_asset, escaped = resolve_asset(module_file.parent.resolve())
        if requested_asset is None:
            try:
                storage_dir = runtime_dep.extension_storage_dir(panel_id).resolve()
            except ValueError:
                storage_dir = None
            if storage_dir is not None:
                requested_asset, storage_escaped = resolve_asset(storage_dir)
                escaped = escaped or storage_escaped

        if requested_asset is None:
            if module_file is None and panel_error is not None and runtime_dep.get_extension(panel_id) is None:
                raise HTTPException(status_code=404, detail=str(panel_error))
            if module_file is None and panel_error is None:
                raise HTTPException(status_code=404, detail="Panel module file is not available")
            if escaped:
                raise HTTPException(status_code=404, detail="Panel asset path escapes panel root")
            raise HTTPException(status_code=404, detail=f"Panel asset not found: {asset_path}")

        suffix = requested_asset.suffix.lower()
        if suffix in _JSX_SUFFIXES:
            try:
                from esbuild_py import transform as _esbuild_transform
            except ImportError as exc:
                raise HTTPException(
                    status_code=500,
                    detail="esbuild_py is required to serve .jsx panel files",
                ) from exc
            try:
                source = requested_asset.read_text(encoding="utf-8")
                transformed = _esbuild_transform(source)
            except Exception as exc:  # pragma: no cover - transformation errors
                raise HTTPException(
                    status_code=500, detail=f"JSX transform failed: {exc}"
                ) from exc
            if transformed is None:
                raise HTTPException(status_code=500, detail="JSX transform produced no output")
            return Response(content=transformed, media_type="application/javascript")

        if suffix in _PASSTHROUGH_JS_SUFFIXES:
            return FileResponse(requested_asset, media_type="application/javascript")

        return FileResponse(requested_asset)

    @app.get("/api/jobs")
    async def list_jobs(runtime_dep: HyperViewRuntime = Depends(get_runtime)):
        return {"jobs": [job.to_dict() for job in runtime_dep.list_jobs()]}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, runtime_dep: HyperViewRuntime = Depends(get_runtime)):
        job = runtime_dep.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return job.to_dict()

    @app.post("/api/control/provider/register")
    async def register_provider(
        request: ProviderRegisterRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        try:
            registration = runtime_dep.provider_registry.register_python(
                request.alias,
                request.import_path,
                description=request.description,
                defaults=request.defaults,
                overwrite=request.overwrite,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        runtime_dep._bump_version()
        return {"provider": registration.to_dict()}

    @app.post("/api/control/workspaces/create")
    async def create_workspace_endpoint(
        request: WorkspaceCreateRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        try:
            workspace = runtime_dep.create_workspace(request.workspace_id, activate=request.activate)
            if request.dataset_name:
                workspace = runtime_dep.set_workspace_dataset(request.workspace_id, request.dataset_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"workspace": workspace.to_dict()}

    @app.post("/api/control/workspaces/set-active")
    async def set_active_workspace_endpoint(
        request: WorkspaceActivateRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        try:
            workspace = runtime_dep.set_active_workspace(request.workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"workspace": workspace.to_dict()}

    @app.post("/api/control/embeddings/compute")
    async def compute_embeddings_endpoint(
        request: EmbeddingsComputeRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        job = runtime_dep.submit_embedding_job(
            workspace_id=request.workspace_id,
            dataset_name=request.dataset_name,
            model=request.model,
            provider=request.provider,
            checkpoint=request.checkpoint,
            provider_kwargs=request.provider_kwargs,
            layouts=request.layouts,
            method=request.method,
            n_neighbors=request.n_neighbors,
            min_dist=request.min_dist,
            metric=request.metric,
            activate_layout=request.activate_layout,
        )
        return {"job": job.to_dict()}

    @app.post("/api/control/layouts/compute")
    async def compute_layouts_endpoint(
        request: LayoutComputeRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        job = runtime_dep.submit_layout_job(
            workspace_id=request.workspace_id,
            dataset_name=request.dataset_name,
            space_key=request.space_key,
            layouts=request.layouts,
            method=request.method,
            n_neighbors=request.n_neighbors,
            min_dist=request.min_dist,
            metric=request.metric,
            activate_layout=request.activate_layout,
        )
        return {"job": job.to_dict()}

    @app.post("/api/control/ui/layout")
    async def set_ui_layout_endpoint(
        request: UiLayoutRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        workspace = runtime_dep.set_active_layout(request.workspace_id, request.layout_key)
        return {"workspace": workspace.to_dict()}

    @app.post("/api/control/ui/selection")
    async def set_ui_selection_endpoint(
        request: UiSelectionRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        workspace = runtime_dep.set_selection(request.workspace_id, request.sample_ids)
        return {"workspace": workspace.to_dict()}

    @app.post("/api/control/ui/selection/query")
    async def set_ui_selection_query_endpoint(
        request: SamplesSelectionQueryRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        try:
            dataset = runtime_dep.get_dataset(workspace_id=request.workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        query = SamplesQueryRequest(
            workspace_id=request.workspace_id,
            ids=request.ids,
            labels=request.labels,
            metadata=request.metadata,
            offset=0,
            limit=request.limit or 1,
            include_thumbnails=False,
        )
        samples = _query_samples(dataset, query)
        if request.limit is not None:
            samples = samples[: max(0, request.limit)]
        workspace = runtime_dep.set_selection(request.workspace_id, [sample.id for sample in samples])
        return {"workspace": workspace.to_dict()}

    @app.patch("/api/control/ui/state")
    async def patch_ui_state_endpoint(
        request: UiStatePatchRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        try:
            workspace = runtime_dep.patch_ui_state(
                request.workspace_id,
                set_active_layout=request.set_active_layout,
                active_layout_key=request.active_layout_key,
                set_selection=request.set_selection,
                selected_ids=request.selected_ids,
                source_client_id=request.client_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"workspace": workspace.to_dict()}

    @app.post("/api/control/ui/layout-view")
    async def set_ui_layout_view_endpoint(
        request: UiLayoutViewRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        workspace = runtime_dep.set_layout_view(
            request.workspace_id,
            request.layout_key,
            LayoutViewState(
                camera_3d=request.camera_3d.model_dump() if request.camera_3d is not None else None
            ),
        )
        return {"workspace": workspace.to_dict()}

    @app.get("/api/control/commands")
    async def list_control_commands_endpoint(
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        return {"commands": _control_service(runtime_dep).list_commands()}

    @app.post("/api/control/commands/run")
    async def run_control_command_endpoint(
        request: CommandEnvelope,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        return _control_service(runtime_dep).run(request).to_dict()

    @app.get("/api/tools")
    async def list_tools_endpoint(
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        return {"tools": [record.to_dict() for record in runtime_dep.tools.list()]}

    @app.post("/api/tools/run")
    async def run_tool_endpoint(
        request: ToolRunRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        try:
            result = runtime_dep.run_tool(
                request.tool,
                workspace_id=request.workspace_id,
                params=request.params or {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - tool-defined errors
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {"ok": True, "result": result}

    @app.get("/api/extensions")
    async def list_extensions_endpoint(
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        return {
            "extensions": [item.to_dict() for item in runtime_dep.list_extensions()],
        }

    @app.get("/api/panel-definitions")
    async def list_panel_definitions_endpoint(
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        return {
            "panel_definitions": [
                definition.to_dict() for definition in runtime_dep.list_panel_definitions()
            ],
        }

    @app.post("/api/control/extensions/install")
    async def install_extension_endpoint(
        request: ExtensionInstallRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        folder = Path(request.folder).expanduser().resolve()
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail=f"Extension folder not found: {folder}")
        try:
            installation = runtime_dep.install_extension(
                request.workspace_id,
                folder,
                add_panels=request.add_panels,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"extension": installation.to_dict()}

    @app.delete("/api/control/extensions/remove")
    async def remove_extension_endpoint(
        request: ExtensionRemoveRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        installation = runtime_dep.uninstall_extension(request.name)
        if installation is None:
            raise HTTPException(status_code=404, detail=f"Unknown extension: {request.name}")
        return {"extension": installation.to_dict()}

    @app.get("/api/dataset", response_model=DatasetResponse)
    async def get_dataset_info(ds: Dataset = Depends(get_dataset)):
        """Get dataset metadata."""
        spaces = ds.list_spaces()
        space_dicts = [s.to_api_dict() for s in spaces]

        layouts = ds.list_layouts()
        layout_dicts = [layout.to_api_dict() for layout in layouts]

        return DatasetResponse(
            name=ds.name,
            num_samples=len(ds),
            labels=ds.labels,
            spaces=space_dicts,
            layouts=layout_dicts,
        )

    @app.get("/api/samples")
    async def get_samples(
        ds: Dataset = Depends(get_dataset),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=MAX_SAMPLE_PAGE_SIZE),
        label: str | None = None,
        missing_label: bool = Query(False),
        include_thumbnails: bool = Query(False),
    ):
        """Get paginated sample metadata."""
        samples, total = ds.get_samples_paginated(
            offset=offset,
            limit=limit,
            label=None if missing_label else label,
            missing_label=missing_label,
        )

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "samples": [
                serialize_sample_for_response(s, include_thumbnail=include_thumbnails)
                for s in samples
            ],
        }

    @app.get("/api/samples/{sample_id}", response_model=SampleResponse)
    async def get_sample(
        sample_id: str,
        ds: Dataset = Depends(get_dataset),
        include_thumbnails: bool = Query(False),
    ):
        """Get a single sample by ID."""
        try:
            sample = ds[sample_id]
            return SampleResponse(
                **serialize_sample_for_response(
                    sample,
                    include_thumbnail=include_thumbnails,
                    ensure_dimensions=True,
                )
            )
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

    @app.get("/api/samples/{sample_id}/content")
    async def get_sample_content(sample_id: str, ds: Dataset = Depends(get_dataset)):
        """Serve the source media file for a sample."""
        try:
            sample = ds[sample_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}") from exc

        file_path = _resolve_sample_media_path(sample)

        return FileResponse(file_path, headers=_media_cache_headers(file_path, variant="content"))

    @app.get("/api/samples/{sample_id}/thumbnail")
    async def get_sample_thumbnail(
        sample_id: str,
        ds: Dataset = Depends(get_dataset),
        size: int = Query(DEFAULT_THUMBNAIL_SIZE, ge=16, le=512),
    ):
        """Serve a generated thumbnail for a sample."""
        try:
            sample = ds[sample_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}") from exc

        file_path = _resolve_sample_media_path(sample)
        try:
            thumb = sample.get_thumbnail((size, size))
            if thumb.mode in ("RGBA", "P"):
                thumb = thumb.convert("RGB")
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=85)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=f"Sample thumbnail not available: {exc}") from exc

        headers = _media_cache_headers(file_path, variant=f"thumbnail-{size}")
        return Response(content=buffer.getvalue(), media_type="image/jpeg", headers=headers)

    @app.post("/api/samples/batch")
    async def get_samples_batch(request: SelectionRequest, ds: Dataset = Depends(get_dataset)):
        """Get multiple samples by their IDs."""
        if len(request.sample_ids) > MAX_SAMPLE_BATCH_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"sample_ids may contain at most {MAX_SAMPLE_BATCH_SIZE} ids",
            )
        samples = ds.get_samples_by_ids(request.sample_ids)
        return {
            "samples": [
                serialize_sample_for_response(
                    s,
                    include_thumbnail=request.include_thumbnails,
                )
                for s in samples
            ]
        }

    @app.post("/api/samples/query")
    async def query_samples(
        request: SamplesQueryRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        """Query samples with simple label, id, and metadata predicates."""
        try:
            ds = runtime_dep.get_dataset(workspace_id=request.workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        offset, limit = _validate_page(request.offset, request.limit)
        matches = _query_samples(ds, request)
        page = matches[offset : offset + limit]
        return {
            "total": len(matches),
            "offset": offset,
            "limit": limit,
            "samples": [
                serialize_sample_for_response(s, include_thumbnail=request.include_thumbnails)
                for s in page
            ],
        }

    @app.post("/api/samples/aggregate")
    async def aggregate_samples(
        request: SamplesAggregateRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        """Aggregate sample counts by label or metadata.<key>."""
        try:
            ds = runtime_dep.get_dataset(workspace_id=request.workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        samples = _query_samples(ds, request)
        counts: dict[str, int] = {}
        for sample in samples:
            if request.group_by == "label":
                raw_value = sample.label
            elif request.group_by.startswith("metadata."):
                raw_value = _metadata_value(sample.metadata, request.group_by.removeprefix("metadata."))
            else:
                raise HTTPException(status_code=400, detail="group_by must be 'label' or 'metadata.<key>'")
            key = "unlabeled" if raw_value is None else str(raw_value)
            counts[key] = counts.get(key, 0) + 1

        groups = [
            {"key": key, "count": count}
            for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return {"total": len(samples), "group_by": request.group_by, "groups": groups}

    @app.get("/api/collections/{collection_id}")
    async def get_collection(
        collection_id: str,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
        workspace_id: str | None = Query(None),
    ):
        """Get collection metadata (kind, query, dataset scope)."""
        try:
            workspace = runtime_dep.get_workspace(workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        collection = workspace.collections.get(collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail=f"Unknown collection: {collection_id}")
        return collection.to_dict()

    @app.get("/api/collections/{collection_id}/items")
    async def get_collection_items(
        collection_id: str,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
        workspace_id: str | None = Query(None),
        offset: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=MAX_SAMPLE_PAGE_SIZE),
        include_thumbnails: bool = Query(False),
    ):
        """Get a paged, materialized slice of a collection's member samples.

        This is the read path collections were introduced for: panels resolve
        `collection_id` to rows here instead of owning retrieval/filter logic
        themselves. Membership is (re)computed from the collection's stored
        `query`, not stored row-by-row, so it always reflects current data.
        """
        try:
            workspace = runtime_dep.get_workspace(workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        collection = workspace.collections.get(collection_id)
        if collection is None:
            raise HTTPException(status_code=404, detail=f"Unknown collection: {collection_id}")

        try:
            ds = runtime_dep.get_dataset(
                workspace_id=workspace.id, dataset_name=collection.dataset_id or None
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        try:
            items, total, has_more = _resolve_collection_items(
                ds, collection, offset=offset, limit=limit
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return {
            "collection_id": collection.id,
            "kind": collection.kind,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": has_more,
            "items": [
                {
                    **serialize_sample_for_response(sample, include_thumbnail=include_thumbnails),
                    "score": score,
                }
                for sample, score in items
            ],
        }

    @app.get("/api/embeddings", response_model=EmbeddingsResponse)
    async def get_embeddings(ds: Dataset = Depends(get_dataset), layout_key: str | None = None):
        """Get embedding coordinates for visualization."""
        layouts = ds.list_layouts()
        if not layouts:
            raise HTTPException(
                status_code=400, detail="No layouts computed. Call compute_visualization() first."
            )

        # Find the requested layout
        layout_info = None
        if layout_key is None:
            layout_info = next(
                (layout for layout in layouts if parse_layout_dimension(layout.layout_key) == 2),
                layouts[0],
            )
            layout_key = layout_info.layout_key
        else:
            layout_info = next((layout for layout in layouts if layout.layout_key == layout_key), None)
            if layout_info is None:
                raise HTTPException(status_code=404, detail=f"Layout not found: {layout_key}")

        ids, labels, coords = ds.get_visualization_data(layout_key)

        if not ids:
            raise HTTPException(status_code=400, detail=f"No data in layout '{layout_key}'.")

        return EmbeddingsResponse(
            layout_key=layout_key,
            geometry=layout_info.geometry,
            ids=ids,
            labels=labels,
            coords=coords.tolist(),
        )

    @app.post("/api/selection/lasso")
    async def lasso_selection(request: LassoSelectionRequest, ds: Dataset = Depends(get_dataset)):
        """Compute a lasso selection over the current embeddings.

        Returns a total selected count and a paginated page of selected samples.

                Selection modes:
                - 2D layouts: polygon in data space (same coordinates as /api/embeddings).
                - 3D layouts: polygon in screen space with explicit camera + viewport.
        """
        if request.offset < 0:
            raise HTTPException(status_code=400, detail="offset must be >= 0")
        if request.limit < 1 or request.limit > 2000:
            raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")

        if len(request.polygon) < 6 or len(request.polygon) % 2 != 0:
            raise HTTPException(
                status_code=400,
                detail="polygon must be an even-length list with at least 3 vertices",
            )

        layout_info = next(
            (layout for layout in ds.list_layouts() if layout.layout_key == request.layout_key),
            None,
        )
        if layout_info is None:
            raise HTTPException(status_code=404, detail=f"Layout not found: {request.layout_key}")
        layout_dimension = parse_layout_dimension(layout_info.layout_key)

        poly = np.asarray(request.polygon, dtype=np.float32).reshape((-1, 2))
        if not np.all(np.isfinite(poly)):
            raise HTTPException(status_code=400, detail="polygon must contain only finite numbers")

        selected_ids: list[str]

        if layout_dimension == 2:
            # Tight AABB prefilter in data space.
            x_min = float(np.min(poly[:, 0]))
            x_max = float(np.max(poly[:, 0]))
            y_min = float(np.min(poly[:, 1]))
            y_max = float(np.max(poly[:, 1]))

            candidate_ids, candidate_coords = ds.get_lasso_candidates_aabb(
                layout_key=request.layout_key,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                label_filter=None if request.missing_label_filter else request.label_filter,
                missing_label_filter=request.missing_label_filter,
            )

            if candidate_coords.size == 0:
                return {
                    "total": 0,
                    "offset": request.offset,
                    "limit": request.limit,
                    "sample_ids": [],
                    "samples": [],
                }

            inside_mask = points_in_polygon(candidate_coords, poly)
            if not np.any(inside_mask):
                return {
                    "total": 0,
                    "offset": request.offset,
                    "limit": request.limit,
                    "sample_ids": [],
                    "samples": [],
                }

            selected_ids = [candidate_ids[i] for i in np.flatnonzero(inside_mask)]
        elif layout_dimension == 3:
            if request.view_3d is None:
                raise HTTPException(
                    status_code=400,
                    detail="view_3d is required for 3D lasso selection",
                )
            if request.viewport_width is None or request.viewport_height is None:
                raise HTTPException(
                    status_code=400,
                    detail="viewport_width and viewport_height are required for 3D lasso selection",
                )
            if request.viewport_width <= 0 or request.viewport_height <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="viewport_width and viewport_height must be > 0",
                )

            try:
                view_3d = OrbitViewState3D(**request.view_3d)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid view_3d payload: {exc}")

            view_vals = np.array(
                [
                    view_3d.yaw,
                    view_3d.pitch,
                    view_3d.distance,
                    view_3d.target_x,
                    view_3d.target_y,
                    view_3d.target_z,
                    view_3d.ortho_scale,
                ],
                dtype=np.float64,
            )
            if not np.all(np.isfinite(view_vals)):
                raise HTTPException(status_code=400, detail="view_3d must contain only finite numbers")
            if view_3d.distance <= 0 or view_3d.ortho_scale <= 0:
                raise HTTPException(status_code=400, detail="view_3d.distance and view_3d.ortho_scale must be > 0")

            ids, labels, coords = ds.get_visualization_data(request.layout_key)
            if not ids:
                return {
                    "total": 0,
                    "offset": request.offset,
                    "limit": request.limit,
                    "sample_ids": [],
                    "samples": [],
                }
            if coords.ndim != 2 or coords.shape[1] != 3:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"3D lasso requires a 3D layout coordinate matrix; "
                        f"got shape {coords.shape} for layout '{request.layout_key}'."
                    ),
                )

            finite_mask = np.all(np.isfinite(coords), axis=1)
            if not np.all(finite_mask):
                finite_indices = np.flatnonzero(finite_mask)
                if finite_indices.size == 0:
                    return {
                        "total": 0,
                        "offset": request.offset,
                        "limit": request.limit,
                        "sample_ids": [],
                        "samples": [],
                    }
                ids = [ids[int(i)] for i in finite_indices]
                labels = [labels[int(i)] for i in finite_indices]
                coords = coords[finite_mask]

            selected_ids = select_ids_for_3d_lasso(
                ids=ids,
                labels=labels,
                coords=coords,
                geometry=layout_info.geometry,
                polygon=poly,
                view=view_3d,
                viewport_width=request.viewport_width,
                viewport_height=request.viewport_height,
                label_filter=None if request.missing_label_filter else request.label_filter,
                missing_label_filter=request.missing_label_filter,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported layout dimension for lasso: {layout_dimension}D",
            )

        total = len(selected_ids)

        start = int(request.offset)
        end = int(request.offset + request.limit)
        sample_ids = selected_ids[start:end]

        samples = ds.get_samples_by_ids(sample_ids)
        sample_dicts = [
            serialize_sample_for_response(s, include_thumbnail=request.include_thumbnails)
            for s in samples
        ]

        return {
            "total": total,
            "offset": request.offset,
            "limit": request.limit,
            "sample_ids": sample_ids,
            "samples": sample_dicts,
        }

    @app.get("/api/search/similar/{sample_id}", response_model=SimilaritySearchResponse)
    async def search_similar(
        sample_id: str,
        ds: Dataset = Depends(get_dataset),
        k: int = Query(10, ge=1, le=100),
        space_key: str | None = None,
        layout_key: str | None = None,
        include_thumbnails: bool = Query(False),
    ):
        """Return k nearest neighbors for a given sample."""
        resolved_space_key = space_key
        if layout_key is not None:
            layout = next((item for item in ds.list_layouts() if item.layout_key == layout_key), None)
            if layout is None:
                raise HTTPException(status_code=404, detail=f"Layout not found: {layout_key}")
            if resolved_space_key is not None and resolved_space_key != layout.space_key:
                raise HTTPException(
                    status_code=400,
                    detail="space_key does not match the requested layout_key",
                )
            resolved_space_key = layout.space_key

        spaces = ds.list_spaces()
        if resolved_space_key is None:
            if not spaces:
                raise HTTPException(status_code=400, detail="No embedding spaces available")
            resolved_space_key = spaces[0].space_key
        space = next((s for s in spaces if s.space_key == resolved_space_key), None)
        metric = distance_metric_for_space(space) if space is not None else "cosine"

        try:
            query_sample = ds[sample_id]
            similar = ds.find_similar(
                sample_id, k=k, space_key=resolved_space_key
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

        results = []
        for sample, distance in similar:
            results.append(
                SimilarSampleResponse(
                    **serialize_sample_for_response(
                        sample, include_thumbnail=include_thumbnails
                    ),
                    distance=distance,
                )
            )

        return SimilaritySearchResponse(
            query_id=sample_id,
            query_sample=SampleResponse(
                **serialize_sample_for_response(
                    query_sample, include_thumbnail=include_thumbnails
                )
            ),
            space_key=resolved_space_key,
            metric=metric,
            k=k,
            results=results,
        )

    @app.post("/api/search/text", response_model=SimilaritySearchResponse)
    async def search_by_text(
        request: TextSearchRequest,
        ds: Dataset = Depends(get_dataset),
    ):
        """Return k nearest neighbors for a natural-language text query."""
        query_text = request.query_text.strip()
        if not query_text:
            raise HTTPException(status_code=400, detail="query_text must be a non-empty string")

        resolved_space_key = request.space_key
        if request.layout_key is not None:
            layout = next(
                (item for item in ds.list_layouts() if item.layout_key == request.layout_key),
                None,
            )
            if layout is None:
                raise HTTPException(status_code=404, detail=f"Layout not found: {request.layout_key}")
            if resolved_space_key is not None and resolved_space_key != layout.space_key:
                raise HTTPException(
                    status_code=400,
                    detail="space_key does not match the requested layout_key",
                )
            resolved_space_key = layout.space_key

        spaces = ds.list_spaces()
        if resolved_space_key is None:
            if not spaces:
                raise HTTPException(status_code=400, detail="No embedding spaces available")
            resolved_space_key = spaces[0].space_key
        space = next((s for s in spaces if s.space_key == resolved_space_key), None)
        metric = distance_metric_for_space(space) if space is not None else "cosine"

        try:
            similar = ds.find_similar_by_text(
                query_text,
                k=request.k,
                space_key=resolved_space_key,
                layout_key=request.layout_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        results = []
        for sample, distance in similar:
            results.append(
                SimilarSampleResponse(
                    **serialize_sample_for_response(
                        sample, include_thumbnail=request.include_thumbnails
                    ),
                    distance=distance,
                )
            )

        return SimilaritySearchResponse(
            query_text=query_text,
            query_sample=None,
            space_key=resolved_space_key,
            metric=metric,
            k=request.k,
            results=results,
        )

    # Serve static frontend files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def set_runtime(runtime: HyperViewRuntime) -> None:
    """Set the global runtime for the server."""
    global _current_runtime
    _current_runtime = runtime
