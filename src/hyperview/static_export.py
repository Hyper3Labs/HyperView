"""Static workspace export for read-only HyperView demos."""

from __future__ import annotations

import io
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from hyperview.core.dataset import Dataset
from hyperview.runtime import CollectionState, CustomPanelSpec, HyperViewRuntime
from hyperview.server.app import (
    DEFAULT_THUMBNAIL_SIZE,
    MAX_SAMPLE_PAGE_SIZE,
    serialize_sample_for_response,
)
from hyperview.storage.metrics import distance_metric_for_space
from hyperview.storage.schema import parse_layout_dimension, space_key_from_index_ref

SAMPLE_SHARD_SIZE = 500
SIMILARITY_EXPORT_K = 100


@dataclass(frozen=True)
class StaticExportResult:
    workspace_id: str
    dataset_name: str
    output_dir: Path
    num_samples: int
    num_sample_shards: int
    num_layouts: int
    num_collections: int
    num_media_files: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "dataset_name": self.dataset_name,
            "output_dir": str(self.output_dir),
            "num_samples": self.num_samples,
            "num_sample_shards": self.num_sample_shards,
            "num_layouts": self.num_layouts,
            "num_collections": self.num_collections,
            "num_media_files": self.num_media_files,
        }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _copy_static_frontend(out_dir: Path) -> None:
    static_dir = Path(__file__).parent / "server" / "static"
    if not static_dir.exists():
        raise RuntimeError(f"Packaged frontend assets are missing: {static_dir}")
    shutil.copytree(static_dir, out_dir, dirs_exist_ok=True)


def _inject_static_flag(index_path: Path) -> None:
    marker = "window.__HYPERVIEW_STATIC__ = true;"
    script = f"<script>{marker}</script>"
    if not index_path.exists():
        raise RuntimeError(f"Frontend index.html is missing from export: {index_path}")
    html = index_path.read_text(encoding="utf-8")
    if marker in html:
        return
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{script}", 1)
    else:
        html = f"{script}\n{html}"
    index_path.write_text(html, encoding="utf-8")


def _dataset_payload(dataset: Dataset) -> dict[str, Any]:
    return {
        "name": dataset.name,
        "num_samples": len(dataset),
        "labels": dataset.labels,
        "spaces": [space.to_api_dict() for space in dataset.list_spaces()],
        "layouts": [layout.to_api_dict() for layout in dataset.list_layouts()],
    }


def _embedding_payload(dataset: Dataset, layout_key: str) -> dict[str, Any]:
    layout = next((item for item in dataset.list_layouts() if item.layout_key == layout_key), None)
    if layout is None:
        raise ValueError(f"Layout not found: {layout_key}")
    ids, labels, coords = dataset.get_visualization_data(layout_key)
    return {
        "layout_key": layout_key,
        "geometry": layout.geometry,
        "ids": ids,
        "labels": labels,
        "coords": coords.tolist(),
    }


def _sample_path_segment(sample_id: str) -> str:
    return quote(sample_id, safe="")


def _write_sample_media(out_dir: Path, sample: Any) -> int:
    media_count = 0
    source = Path(sample.filepath).expanduser()
    if source.exists() and source.is_file():
        sample_dir = out_dir / "api" / "samples" / _sample_path_segment(sample.id)
        sample_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, sample_dir / "content")

        media_dir = out_dir / "media" / "samples" / _sample_path_segment(sample.id)
        media_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, media_dir / source.name)
        media_count += 2

        try:
            thumb = sample.get_thumbnail((DEFAULT_THUMBNAIL_SIZE, DEFAULT_THUMBNAIL_SIZE))
            if thumb.mode in ("RGBA", "P"):
                thumb = thumb.convert("RGB")
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=85)
            thumb_bytes = buffer.getvalue()
            (sample_dir / "thumbnail").write_bytes(thumb_bytes)
            thumb_dir = out_dir / "media" / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            (thumb_dir / f"{_sample_path_segment(sample.id)}.jpg").write_bytes(thumb_bytes)
            media_count += 2
        except Exception:
            pass
    return media_count


def _write_samples(out_dir: Path, dataset: Dataset) -> tuple[list[dict[str, Any]], int, int]:
    samples = [serialize_sample_for_response(sample, include_thumbnail=False) for sample in dataset.samples]
    shards: list[str] = []
    for offset in range(0, len(samples), SAMPLE_SHARD_SIZE):
        shard_index = len(shards)
        shard_path = f"shards/{shard_index:06d}.json"
        shard_samples = samples[offset : offset + SAMPLE_SHARD_SIZE]
        _write_json(
            out_dir / "api" / "samples" / shard_path,
            {
                "total": len(samples),
                "offset": offset,
                "limit": SAMPLE_SHARD_SIZE,
                "samples": shard_samples,
            },
        )
        shards.append(shard_path)

    _write_json(
        out_dir / "api" / "samples" / "index.json",
        {
            "total": len(samples),
            "shard_size": SAMPLE_SHARD_SIZE,
            "shards": shards,
        },
    )

    media_count = 0
    for sample in dataset.samples:
        payload = serialize_sample_for_response(sample, include_thumbnail=False, ensure_dimensions=True)
        _write_json(out_dir / "api" / "samples" / f"{_sample_path_segment(sample.id)}.json", payload)
        media_count += _write_sample_media(out_dir, sample)

    return samples, len(shards), media_count


def _resolve_collection_ids(dataset: Dataset, collection: CollectionState) -> tuple[list[str], dict[str, float] | None]:
    query = collection.query or {}
    if collection.kind == "all":
        return [sample.id for sample in dataset.samples], None
    if collection.kind == "filter":
        field = query.get("field")
        op = query.get("op")
        value = query.get("value")
        if field == "label" and op == "eq":
            return [sample.id for sample in dataset.samples if sample.label == value], None
        return [], None
    if collection.kind in {"neighbors", "search"}:
        anchor = query.get("anchor")
        k = int(query.get("k") or SIMILARITY_EXPORT_K)
        space_key = query.get("spaceKey") or space_key_from_index_ref(query.get("indexId"))
        layout_key = query.get("layoutId")
        if isinstance(anchor, dict):
            sample_id = str(anchor.get("entityId") or anchor.get("entity_id") or "")
            try:
                results = dataset.find_similar(
                    sample_id,
                    k=max(1, min(k, SIMILARITY_EXPORT_K)),
                    space_key=space_key if isinstance(space_key, str) else None,
                    layout_key=layout_key if isinstance(layout_key, str) else None,
                )
            except Exception:
                return [], None
            scores = {sample.id: float(distance) for sample, distance in results}
            return [sample.id for sample, _distance in results], scores
    return [], collection.scores


def _write_collections(out_dir: Path, dataset: Dataset, snapshot: dict[str, Any]) -> int:
    collections = [
        CollectionState.from_dict(item)
        for item in snapshot.get("workspace", {}).get("collections", [])
        if isinstance(item, dict)
    ]
    for collection in collections:
        ids, scores = _resolve_collection_ids(dataset, collection)
        rows = [
            {
                "sample_id": sample_id,
                "rank": rank,
                "score": scores.get(sample_id) if scores is not None else None,
                "sample": serialize_sample_for_response(sample, include_thumbnail=False),
            }
            for rank, (sample_id, sample) in enumerate(
                (item.id, item) for item in dataset.get_samples_by_ids(ids)
            )
        ]
        collection_dir = out_dir / "api" / "collections" / quote(collection.id, safe="")
        _write_json(
            collection_dir / "items.json",
            {"collection_id": collection.id, "total": len(rows), "offset": 0, "limit": len(rows), "items": rows},
        )
        _write_json(
            collection_dir / "index.json",
            {"collection": collection.to_dict(), "total": len(rows), "shards": ["items.json"]},
        )
    return len(collections)


def _write_embeddings(out_dir: Path, dataset: Dataset) -> int:
    layouts = dataset.list_layouts()
    if not layouts:
        return 0
    default_layout = next(
        (layout for layout in layouts if parse_layout_dimension(layout.layout_key) == 2),
        layouts[0],
    )
    _write_json(out_dir / "api" / "embeddings" / "default.json", _embedding_payload(dataset, default_layout.layout_key))
    for layout in layouts:
        _write_json(
            out_dir / "api" / "embeddings" / f"{quote(layout.layout_key, safe='')}.json",
            _embedding_payload(dataset, layout.layout_key),
        )
    return len(layouts)


def _similarity_payload(
    dataset: Dataset,
    sample_id: str,
    *,
    space_key: str | None,
    layout_key: str | None = None,
) -> dict[str, Any] | None:
    spaces = dataset.list_spaces()
    resolved_space_key = space_key
    if layout_key is not None:
        layout = next((item for item in dataset.list_layouts() if item.layout_key == layout_key), None)
        if layout is not None:
            resolved_space_key = layout.space_key
    if resolved_space_key is None and spaces:
        resolved_space_key = spaces[0].space_key
    space = next((item for item in spaces if item.space_key == resolved_space_key), None)
    metric = distance_metric_for_space(space) if space is not None else "cosine"
    try:
        query_sample = dataset[sample_id]
        similar = dataset.find_similar(sample_id, k=SIMILARITY_EXPORT_K, space_key=resolved_space_key)
    except Exception:
        return None
    return {
        "query_id": sample_id,
        "query_sample": serialize_sample_for_response(query_sample, include_thumbnail=False),
        "space_key": resolved_space_key,
        "metric": metric,
        "k": SIMILARITY_EXPORT_K,
        "results": [
            {
                **serialize_sample_for_response(sample, include_thumbnail=False),
                "distance": float(distance),
            }
            for sample, distance in similar
        ],
    }


def _write_similarity(out_dir: Path, dataset: Dataset) -> None:
    spaces = dataset.list_spaces()
    if not spaces:
        return
    for sample in dataset.samples:
        sample_dir = out_dir / "api" / "search" / "similar" / _sample_path_segment(sample.id)
        for space in spaces:
            payload = _similarity_payload(dataset, sample.id, space_key=space.space_key)
            if payload is not None:
                _write_json(sample_dir / f"{quote(space.space_key, safe='')}.json", payload)
        default_payload = _similarity_payload(dataset, sample.id, space_key=None)
        if default_payload is not None:
            _write_json(sample_dir / "default.json", default_payload)


def _copy_panel_modules(out_dir: Path, runtime: HyperViewRuntime, workspace_id: str) -> None:
    workspace = runtime.get_workspace(workspace_id)
    for panel in workspace.ui.custom_panels:
        if panel.kind != "module":
            continue
        _copy_panel_module(out_dir, panel, workspace_id)


def _copy_panel_module(out_dir: Path, panel: CustomPanelSpec, workspace_id: str) -> None:
    module_file = panel.resolved_module_file()
    if module_file is None or not module_file.exists():
        return
    target_dir = out_dir / "api" / "panels" / "content" / quote(workspace_id, safe="") / quote(panel.id, safe="")
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in module_file.parent.iterdir():
        target = target_dir / item.name
        if item.is_file():
            if item.suffix.lower() == ".jsx":
                try:
                    from esbuild_py import transform as esbuild_transform

                    transformed = esbuild_transform(item.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise RuntimeError(f"Failed to transform JSX panel module {item}: {exc}") from exc
                if transformed is not None:
                    target.write_text(transformed, encoding="utf-8")
            else:
                shutil.copy2(item, target)


def export_runtime_workspace(
    runtime: HyperViewRuntime,
    workspace_id: str,
    out: str | Path,
) -> StaticExportResult:
    out_dir = Path(out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    workspace = runtime.get_workspace(workspace_id)
    if not workspace.dataset_name:
        raise RuntimeError(f"Workspace '{workspace_id}' has no dataset")
    dataset = runtime.get_dataset(workspace_id, workspace.dataset_name)

    _copy_static_frontend(out_dir)
    _inject_static_flag(out_dir / "index.html")

    snapshot = runtime.snapshot(workspace_id)
    _write_json(out_dir / "api" / "runtime.json", snapshot)
    _write_json(out_dir / "api" / "dataset.json", _dataset_payload(dataset))
    _write_json(
        out_dir / "api" / "panel-definitions.json",
        {"panel_definitions": snapshot.get("panel_definitions", [])},
    )

    _samples, num_shards, num_media_files = _write_samples(out_dir, dataset)
    num_layouts = _write_embeddings(out_dir, dataset)
    num_collections = _write_collections(out_dir, dataset, snapshot)
    _write_similarity(out_dir, dataset)
    _copy_panel_modules(out_dir, runtime, workspace_id)

    manifest = {
        "static": True,
        "workspace_id": workspace_id,
        "dataset_name": workspace.dataset_name,
        "api": {
            "runtime": "api/runtime.json",
            "dataset": "api/dataset.json",
            "samples": "api/samples/index.json",
            "embeddings": "api/embeddings/default.json",
        },
    }
    _write_json(out_dir / "hyperview-static.json", manifest)

    return StaticExportResult(
        workspace_id=workspace_id,
        dataset_name=workspace.dataset_name,
        output_dir=out_dir,
        num_samples=len(dataset),
        num_sample_shards=num_shards,
        num_layouts=num_layouts,
        num_collections=num_collections,
        num_media_files=num_media_files,
    )


def export_workspace(workspace_id: str, out: str | Path) -> StaticExportResult:
    runtime = HyperViewRuntime()
    try:
        runtime.get_workspace(workspace_id)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        return export_runtime_workspace(runtime, workspace_id, out)
    except HTTPException as exc:
        raise RuntimeError(str(exc.detail)) from exc
