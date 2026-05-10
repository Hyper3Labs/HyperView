"""FastAPI application for HyperView."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Literal

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hyperview.core.dataset import Dataset
from hyperview.core.selection import (
    OrbitViewState3D,
    points_in_polygon,
    select_ids_for_3d_lasso,
)
from hyperview.runtime import CustomPanelSpec, HyperViewRuntime
from hyperview.storage.schema import parse_layout_dimension

# Extensions whose content is handed off to esbuild for JSX transformation.
_JSX_SUFFIXES = {".jsx"}
_PASSTHROUGH_JS_SUFFIXES = {".js", ".mjs"}

# Global runtime reference (set by launch()/serve)
_current_runtime: HyperViewRuntime | None = None
_current_session_id: str | None = None


class SelectionRequest(BaseModel):
    """Request model for selection sync."""

    sample_ids: list[str]


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
    offset: int = 0
    limit: int = 100
    include_thumbnails: bool = True


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


class UiPanelRequest(BaseModel):
    workspace_id: str
    panel_id: str
    title: str
    kind: Literal["module", "scatter"] = "module"
    module_file: str | None = None
    layout_key: str | None = None
    position: str = "right"
    reference_panel_id: str | None = None
    direction: str | None = None


class UiPanelRemoveRequest(BaseModel):
    workspace_id: str
    panel_id: str


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


class ExtensionRemoveRequest(BaseModel):
    name: str


class SampleResponse(BaseModel):
    """Response model for a sample."""

    id: str
    filepath: str
    filename: str
    label: str | None
    thumbnail: str | None
    media_url: str | None = None
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

    query_id: str
    query_sample: SampleResponse | None
    space_key: str | None
    metric: str
    k: int
    results: list[SimilarSampleResponse]


def serialize_sample_for_response(sample: Any, include_thumbnail: bool = True) -> dict[str, Any]:
    payload = sample.to_api_dict(include_thumbnail=False)
    payload["thumbnail"] = None
    payload["media_url"] = f"/api/samples/{sample.id}/content"
    if include_thumbnail:
        try:
            payload["thumbnail"] = sample.get_thumbnail_base64()
        except Exception:
            payload["thumbnail"] = None
    return payload


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
        version="0.1.0",
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
    ):
        async def event_stream():
            last_version = -1
            while True:
                snapshot = runtime_dep.snapshot(workspace_id)
                if snapshot["version"] != last_version:
                    payload = json.dumps(snapshot)
                    yield f"data: {payload}\n\n"
                    last_version = snapshot["version"]
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

    @app.post("/api/control/ui/panels")
    async def add_ui_panel_endpoint(
        request: UiPanelRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        if request.position not in {"center", "right", "bottom"}:
            raise HTTPException(status_code=400, detail="position must be one of center, right, bottom")
        if request.direction is not None and request.direction not in {"right", "left", "above", "below", "within"}:
            raise HTTPException(status_code=400, detail="direction must be one of right, left, above, below, within")

        module_file: Path | None = None
        layout_key: str | None = None
        geometry: str | None = None
        layout_dimension: int | None = None

        if request.kind == "module":
            if not request.module_file:
                raise HTTPException(status_code=400, detail="module_file is required for module panels")
            module_file = Path(request.module_file).expanduser().resolve()
            if not module_file.exists() or not module_file.is_file():
                raise HTTPException(status_code=400, detail=f"Panel module file not found: {module_file}")
        else:
            if not request.layout_key:
                raise HTTPException(status_code=400, detail="layout_key is required for scatter panels")
            dataset = runtime_dep.get_dataset(request.workspace_id)
            layout_info = next(
                (layout for layout in dataset.list_layouts() if layout.layout_key == request.layout_key),
                None,
            )
            if layout_info is None:
                raise HTTPException(status_code=404, detail=f"Layout not found: {request.layout_key}")
            layout_key = layout_info.layout_key
            geometry = layout_info.geometry
            layout_dimension = parse_layout_dimension(layout_info.layout_key)

        panel = CustomPanelSpec(
            id=request.panel_id,
            title=request.title,
            kind=request.kind,
            module_file=str(module_file) if module_file is not None else None,
            position=request.position,  # type: ignore[arg-type]
            layout_key=layout_key,
            geometry=geometry,
            layout_dimension=layout_dimension,
            reference_panel_id=request.reference_panel_id,
            direction=request.direction,  # type: ignore[arg-type]
        )
        workspace = runtime_dep.add_custom_panel(request.workspace_id, panel)
        return {"workspace": workspace.to_dict()}

    @app.delete("/api/control/ui/panels")
    async def remove_ui_panel_endpoint(
        request: UiPanelRemoveRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        workspace = runtime_dep.remove_custom_panel(request.workspace_id, request.panel_id)
        return {"workspace": workspace.to_dict()}

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

    @app.post("/api/control/extensions/install")
    async def install_extension_endpoint(
        request: ExtensionInstallRequest,
        runtime_dep: HyperViewRuntime = Depends(get_runtime),
    ):
        folder = Path(request.folder).expanduser().resolve()
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail=f"Extension folder not found: {folder}")
        try:
            installation = runtime_dep.install_extension(request.workspace_id, folder)
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
        limit: int = Query(100, ge=1),
        label: str | None = None,
    ):
        """Get paginated samples with thumbnails."""
        samples, total = ds.get_samples_paginated(
            offset=offset, limit=limit, label=label
        )

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "samples": [serialize_sample_for_response(s, include_thumbnail=True) for s in samples],
        }

    @app.get("/api/samples/{sample_id}", response_model=SampleResponse)
    async def get_sample(sample_id: str, ds: Dataset = Depends(get_dataset)):
        """Get a single sample by ID."""
        try:
            sample = ds[sample_id]
            return SampleResponse(**serialize_sample_for_response(sample, include_thumbnail=True))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

    @app.get("/api/samples/{sample_id}/content")
    async def get_sample_content(sample_id: str, ds: Dataset = Depends(get_dataset)):
        """Serve the source media file for a sample."""
        try:
            sample = ds[sample_id]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}") from exc

        file_path = Path(sample.filepath).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"Sample media not found: {sample.filepath}")

        return FileResponse(file_path)

    @app.post("/api/samples/batch")
    async def get_samples_batch(request: SelectionRequest, ds: Dataset = Depends(get_dataset)):
        """Get multiple samples by their IDs."""
        samples = ds.get_samples_by_ids(request.sample_ids)
        return {
            "samples": [serialize_sample_for_response(s, include_thumbnail=True) for s in samples]
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
                label_filter=request.label_filter,
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
                label_filter=request.label_filter,
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
    ):
        """Return k nearest neighbors for a given sample."""
        resolved_space_key = space_key
        if resolved_space_key is None:
            spaces = ds.list_spaces()
            if not spaces:
                raise HTTPException(status_code=400, detail="No embedding spaces available")
            resolved_space_key = spaces[0].space_key

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
                    **serialize_sample_for_response(sample),
                    distance=distance,
                )
            )

        return SimilaritySearchResponse(
            query_id=sample_id,
            query_sample=SampleResponse(**serialize_sample_for_response(query_sample)),
            space_key=resolved_space_key,
            metric="cosine",
            k=k,
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
