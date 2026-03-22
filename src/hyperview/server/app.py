"""FastAPI application for HyperView."""

import os
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hyperview.core.dataset import Dataset
from hyperview.core.selection import (
    OrbitViewState3D,
    points_in_polygon,
    select_ids_for_3d_lasso,
)
from hyperview.storage.schema import parse_layout_dimension

# Global dataset reference (set by launch())
_current_dataset: Dataset | None = None
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


class SampleResponse(BaseModel):
    """Response model for a sample."""

    id: str
    filepath: str
    filename: str
    label: str | None
    thumbnail: str | None
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


class SimilarSampleResponse(BaseModel):
    """Response model for a similar sample with distance."""

    id: str
    filepath: str
    filename: str
    label: str | None
    thumbnail: str | None
    distance: float
    metadata: dict


class SimilaritySearchResponse(BaseModel):
    """Response model for similarity search results."""

    query_id: str
    k: int
    results: list[SimilarSampleResponse]


def create_app(dataset: Dataset | None = None, session_id: str | None = None) -> FastAPI:
    """Create the FastAPI application.

    Args:
        dataset: Optional dataset to serve. If None, uses global dataset.

    Returns:
        FastAPI application instance.
    """
    global _current_dataset, _current_session_id
    if dataset is not None:
        _current_dataset = dataset
    if session_id is not None:
        _current_session_id = session_id

    app = FastAPI(
        title="HyperView",
        description="Dataset visualization with hyperbolic embeddings",
        version="0.1.0",
    )

    def get_dataset() -> Dataset:
        """Dependency that returns the current dataset or raises 404."""
        if _current_dataset is None:
            raise HTTPException(status_code=404, detail="No dataset loaded")
        return _current_dataset

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
        return {
            "name": "hyperview",
            "version": app.version,
            "session_id": _current_session_id,
            "dataset": _current_dataset.name if _current_dataset is not None else None,
            "pid": os.getpid(),
        }

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
        limit: int = Query(100, ge=1, le=1000),
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
            "samples": [s.to_api_dict(include_thumbnail=True) for s in samples],
        }

    @app.get("/api/samples/{sample_id}", response_model=SampleResponse)
    async def get_sample(sample_id: str, ds: Dataset = Depends(get_dataset)):
        """Get a single sample by ID."""
        try:
            sample = ds[sample_id]
            return SampleResponse(**sample.to_api_dict())
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

    @app.post("/api/samples/batch")
    async def get_samples_batch(request: SelectionRequest, ds: Dataset = Depends(get_dataset)):
        """Get multiple samples by their IDs."""
        samples = ds.get_samples_by_ids(request.sample_ids)
        return {"samples": [s.to_api_dict(include_thumbnail=True) for s in samples]}

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

    @app.get("/api/spaces")
    async def get_spaces(ds: Dataset = Depends(get_dataset)):
        """Get all embedding spaces."""
        spaces = ds.list_spaces()
        return {"spaces": [s.to_api_dict() for s in spaces]}

    @app.get("/api/layouts")
    async def get_layouts(ds: Dataset = Depends(get_dataset)):
        """Get all available layouts."""
        layouts = ds.list_layouts()
        return {"layouts": [layout.to_api_dict() for layout in layouts]}

    @app.post("/api/selection")
    async def sync_selection(request: SelectionRequest):
        """Sync selection state (for future use)."""
        return {"status": "ok", "selected": request.sample_ids}

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
        sample_dicts = [s.to_api_dict(include_thumbnail=request.include_thumbnails) for s in samples]

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
        try:
            similar = ds.find_similar(
                sample_id, k=k, space_key=space_key
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

        results = []
        for sample, distance in similar:
            try:
                thumbnail = sample.get_thumbnail_base64()
            except Exception:
                thumbnail = None

            results.append(
                SimilarSampleResponse(
                    id=sample.id,
                    filepath=sample.filepath,
                    filename=sample.filename,
                    label=sample.label,
                    thumbnail=thumbnail,
                    distance=distance,
                    metadata=sample.metadata,
                )
            )

        return SimilaritySearchResponse(
            query_id=sample_id,
            k=k,
            results=results,
        )

    @app.get("/api/thumbnail/{sample_id}")
    async def get_thumbnail(sample_id: str, ds: Dataset = Depends(get_dataset)):
        """Get thumbnail image for a sample."""
        try:
            sample = ds[sample_id]
            thumbnail_b64 = sample.get_thumbnail_base64()
            return JSONResponse({"thumbnail": thumbnail_b64})
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Sample not found: {sample_id}")

    # Serve static frontend files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    else:
        # Fallback: serve a simple HTML page
        @app.get("/")
        async def root():
            return {"message": "HyperView API", "docs": "/docs"}

    return app


def set_dataset(dataset: Dataset) -> None:
    """Set the global dataset for the server."""
    global _current_dataset
    _current_dataset = dataset
