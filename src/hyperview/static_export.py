"""Static workspace export for read-only HyperView demos."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from hyperview._version import __version__
from hyperview.core.dataset import Dataset
from hyperview.runtime import CollectionState, CustomPanelSpec, HyperViewRuntime
from hyperview.server.app import (
    DEFAULT_THUMBNAIL_SIZE,
    serialize_sample_for_response,
)
from hyperview.storage.metrics import distance_metric_for_space
from hyperview.storage.schema import parse_layout_dimension, space_key_from_index_ref

SAMPLE_SHARD_SIZE = 500
SIMILARITY_SHARD_SIZE = 100
DEFAULT_SIMILARITY_EXPORT_K = 50
MAX_COLLECTION_EXPORT_K = 100
STATIC_BUNDLE_SCHEMA_VERSION = 1


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
    num_similarity_queries: int
    similarity_k: int
    num_files: int
    bundle_bytes: int

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
            "num_similarity_queries": self.num_similarity_queries,
            "similarity_k": self.similarity_k,
            "num_files": self.num_files,
            "bundle_bytes": self.bundle_bytes,
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
    spaces = dataset.list_spaces()
    return {
        "name": dataset.name,
        "num_samples": len(dataset),
        "labels": dataset.labels,
        "fields": dataset.fields,
        "spaces": [space.to_api_dict() for space in spaces],
        "representations": [space.to_representation_dict() for space in spaces],
        "indexes": [space.to_index_dict() for space in spaces],
        "layouts": [layout.to_api_dict() for layout in dataset.list_layouts()],
    }


def _workspace_fingerprint(dataset: Dataset, snapshot: dict[str, Any]) -> str:
    payload = {
        "dataset": _dataset_payload(dataset),
        "samples": [
            {
                "id": sample.id,
                "label": sample.label,
                "text": getattr(sample, "text", None),
                "metadata": sample.metadata,
            }
            for sample in dataset.samples
        ],
        "workspace": snapshot.get("workspace", {}),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


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
    if not sample.filepath or not sample.is_image:
        return media_count
    source = Path(sample.filepath).expanduser()
    if source.exists() and source.is_file():
        sample_dir = out_dir / "api" / "samples" / _sample_path_segment(sample.id)
        sample_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, sample_dir / "content")
        media_count += 1

        try:
            thumb = sample.get_thumbnail((DEFAULT_THUMBNAIL_SIZE, DEFAULT_THUMBNAIL_SIZE))
            if thumb is None:
                return media_count
            if thumb.mode in ("RGBA", "P"):
                thumb = thumb.convert("RGB")
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=85)
            thumb_bytes = buffer.getvalue()
            (sample_dir / "thumbnail").write_bytes(thumb_bytes)
            media_count += 1
        except Exception:
            pass
    return media_count


def _write_samples(out_dir: Path, dataset: Dataset) -> tuple[list[dict[str, Any]], int, int]:
    samples = [
        serialize_sample_for_response(sample, include_thumbnail=False, ensure_dimensions=True)
        for sample in dataset.samples
    ]
    shards: list[dict[str, Any]] = []
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
        label_counts: dict[str | None, int] = {}
        for sample in shard_samples:
            label = sample.get("label")
            label_counts[label] = label_counts.get(label, 0) + 1
        shards.append(
            {
                "path": shard_path,
                "offset": offset,
                "count": len(shard_samples),
                "sample_ids": [sample["id"] for sample in shard_samples],
                "label_counts": [
                    {"value": label, "count": count}
                    for label, count in sorted(
                        label_counts.items(), key=lambda item: (item[0] is not None, str(item[0]))
                    )
                ],
            }
        )

    _write_json(
        out_dir / "api" / "samples" / "index.json",
        {
            "schema_version": STATIC_BUNDLE_SCHEMA_VERSION,
            "total": len(samples),
            "shard_size": SAMPLE_SHARD_SIZE,
            "shards": shards,
        },
    )

    media_count = 0
    for sample in dataset.samples:
        media_count += _write_sample_media(out_dir, sample)

    return samples, len(shards), media_count


def _resolve_collection_ids(
    dataset: Dataset,
    collection: CollectionState,
    *,
    provider_registry: Any | None = None,
) -> tuple[list[str], dict[str, float] | None]:
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
        query_text = str(query.get("queryText") or "").strip()
        k = int(query.get("k") or DEFAULT_SIMILARITY_EXPORT_K)
        space_key = query.get("spaceKey") or space_key_from_index_ref(query.get("indexId"))
        layout_key = query.get("layoutId")
        if isinstance(anchor, dict):
            sample_id = str(anchor.get("entityId") or anchor.get("entity_id") or "")
            try:
                results = dataset.find_similar(
                    sample_id,
                    k=max(1, min(k, MAX_COLLECTION_EXPORT_K)),
                    space_key=space_key if isinstance(space_key, str) else None,
                    layout_key=layout_key if isinstance(layout_key, str) else None,
                )
            except Exception:
                return [], None
            scores = {sample.id: float(distance) for sample, distance in results}
            return [sample.id for sample, _distance in results], scores
        if query_text:
            results = dataset.find_similar_by_text(
                query_text,
                k=max(1, min(k, MAX_COLLECTION_EXPORT_K)),
                space_key=space_key if isinstance(space_key, str) else None,
                layout_key=layout_key if isinstance(layout_key, str) else None,
                _provider_registry=provider_registry,
            )
            scores = {sample.id: float(distance) for sample, distance in results}
            return [sample.id for sample, _distance in results], scores
    return [], collection.scores


def _write_collections(
    out_dir: Path,
    dataset: Dataset,
    snapshot: dict[str, Any],
    *,
    provider_registry: Any | None = None,
) -> int:
    collections = [
        CollectionState.from_dict(item)
        for item in snapshot.get("workspace", {}).get("collections", [])
        if isinstance(item, dict)
    ]
    for collection in collections:
        ids, scores = _resolve_collection_ids(
            dataset,
            collection,
            provider_registry=provider_registry,
        )
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


def _write_similarity(out_dir: Path, dataset: Dataset, *, k: int) -> int:
    spaces = dataset.list_spaces()
    if not spaces or k <= 0:
        return 0
    samples = dataset.samples

    root_dir = out_dir / "api" / "search" / "similar"
    index: dict[str, Any] = {
        "schema_version": STATIC_BUNDLE_SCHEMA_VERSION,
        "k": k,
        "default_space_key": None,
        "spaces": {},
    }
    query_count = 0
    for space in spaces:
        metric = distance_metric_for_space(space)
        encoded_space = quote(space.space_key, safe="")
        space_shards: list[dict[str, Any]] = []
        for offset in range(0, len(samples), SIMILARITY_SHARD_SIZE):
            shard_samples = samples[offset : offset + SIMILARITY_SHARD_SIZE]
            queries: dict[str, Any] = {}
            for sample in shard_samples:
                try:
                    similar = dataset.find_similar(sample.id, k=k, space_key=space.space_key)
                except Exception:
                    continue
                queries[sample.id] = {
                    "results": [
                        {"sample_id": result.id, "distance": float(distance)}
                        for result, distance in similar
                    ]
                }
                query_count += 1

            if not queries:
                continue
            shard_number = len(space_shards)
            shard_path = f"{encoded_space}/shards/{shard_number:06d}.json"
            _write_json(
                root_dir / shard_path,
                {
                    "space_key": space.space_key,
                    "metric": metric,
                    "k": k,
                    "queries": queries,
                },
            )
            space_shards.append(
                {
                    "path": shard_path,
                    "sample_ids": list(queries),
                }
            )

        if not space_shards:
            continue
        if index["default_space_key"] is None:
            index["default_space_key"] = space.space_key
        index["spaces"][space.space_key] = {
            "metric": metric,
            "shards": space_shards,
        }

    if query_count == 0:
        return 0
    _write_json(root_dir / "index.json", index)
    return query_count


def _annotate_static_panels(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    definitions = {
        item.get("panel_type"): item
        for item in snapshot.get("panel_definitions", [])
        if isinstance(item, dict) and item.get("panel_type")
    }
    statuses: list[dict[str, Any]] = []
    compatible_ids: set[str] = set()
    panels = snapshot.get("workspace", {}).get("ui", {}).get("custom_panels", [])
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        definition = definitions.get(panel.get("panel_type"), {})
        compatible = bool(definition.get("static_compatible", True))
        reason = definition.get("static_reason")
        data = panel.setdefault("data", {})
        if isinstance(data, dict):
            data["static_compatible"] = compatible
            data["static_reason"] = reason
        panel_id = str(panel.get("id") or "")
        if compatible:
            compatible_ids.add(panel_id)
        statuses.append(
            {
                "panel_id": panel_id,
                "panel_type": panel.get("panel_type"),
                "static_compatible": compatible,
                "reason": reason,
            }
        )
    return statuses, compatible_ids


def _copy_panel_modules(
    out_dir: Path,
    runtime: HyperViewRuntime,
    workspace_id: str,
    compatible_ids: set[str],
) -> None:
    workspace = runtime.get_workspace(workspace_id)
    excluded_modules = {
        module_file
        for panel in workspace.ui.custom_panels
        if panel.id not in compatible_ids
        for module_file in [panel.resolved_module_file()]
        if module_file is not None
    }
    for panel in workspace.ui.custom_panels:
        if panel.kind != "module" or panel.id not in compatible_ids:
            continue
        _copy_panel_module(out_dir, panel, workspace_id, excluded_modules)


def _copy_panel_module(
    out_dir: Path,
    panel: CustomPanelSpec,
    workspace_id: str,
    excluded_modules: set[Path],
) -> None:
    module_file = panel.resolved_module_file()
    if module_file is None or not module_file.exists():
        return
    target_dir = out_dir / "api" / "panels" / "content" / quote(workspace_id, safe="") / quote(panel.id, safe="")
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in module_file.parent.iterdir():
        if item.resolve() in excluded_modules or item.suffix.lower() in {".py", ".pyc", ".toml"}:
            continue
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


def _cloudflare_worker_name(workspace_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", workspace_id.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug) or "space"
    return f"hyperview-{slug}"[:63].rstrip("-")


def _write_cloudflare_config(out_dir: Path, workspace_id: str) -> str:
    worker_name = _cloudflare_worker_name(workspace_id)
    _write_json(
        out_dir / "wrangler.jsonc",
        {
            "name": worker_name,
            "compatibility_date": datetime.now(timezone.utc).date().isoformat(),
            "assets": {
                "directory": ".",
                "not_found_handling": "single-page-application",
            },
        },
    )
    (out_dir / ".assetsignore").write_text("wrangler.jsonc\n.assetsignore\n", encoding="utf-8")
    return worker_name


def _prepare_output_dir(out_dir: Path) -> None:
    if out_dir.exists() and not out_dir.is_dir():
        raise RuntimeError(f"Export path is not a directory: {out_dir}")
    if out_dir.exists() and any(out_dir.iterdir()):
        if not (out_dir / "hyperview-static.json").is_file():
            raise RuntimeError(
                f"Export directory is not empty and is not a HyperView bundle: {out_dir}"
            )
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)


def _bundle_stats(out_dir: Path) -> tuple[int, int]:
    files = [path for path in out_dir.rglob("*") if path.is_file()]
    return len(files), sum(path.stat().st_size for path in files)


def export_runtime_workspace(
    runtime: HyperViewRuntime,
    workspace_id: str,
    out: str | Path,
    *,
    similarity_k: int = DEFAULT_SIMILARITY_EXPORT_K,
) -> StaticExportResult:
    if similarity_k < 0:
        raise ValueError("similarity_k must be zero or greater")
    out_dir = Path(out).expanduser().resolve()
    _prepare_output_dir(out_dir)

    workspace = runtime.get_workspace(workspace_id)
    if not workspace.dataset_name:
        raise RuntimeError(f"Workspace '{workspace_id}' has no dataset")
    dataset = runtime.get_dataset(workspace_id, workspace.dataset_name)

    _copy_static_frontend(out_dir)
    _inject_static_flag(out_dir / "index.html")

    snapshot = runtime.snapshot(workspace_id)
    panel_statuses, compatible_panel_ids = _annotate_static_panels(snapshot)
    _write_json(out_dir / "api" / "runtime.json", snapshot)
    _write_json(out_dir / "api" / "dataset.json", _dataset_payload(dataset))
    _write_json(
        out_dir / "api" / "panel-definitions.json",
        {"panel_definitions": snapshot.get("panel_definitions", [])},
    )

    _samples, num_shards, num_media_files = _write_samples(out_dir, dataset)
    num_layouts = _write_embeddings(out_dir, dataset)
    num_collections = _write_collections(
        out_dir,
        dataset,
        snapshot,
        provider_registry=runtime.provider_registry,
    )
    num_similarity_queries = _write_similarity(out_dir, dataset, k=similarity_k)
    _copy_panel_modules(out_dir, runtime, workspace_id, compatible_panel_ids)
    worker_name = _write_cloudflare_config(out_dir, workspace_id)

    manifest = {
        "schema_version": STATIC_BUNDLE_SCHEMA_VERSION,
        "kind": "hyperview-static-space",
        "static": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hyperview_version": __version__,
        "workspace": {
            "id": workspace_id,
            "dataset_name": workspace.dataset_name,
            "fingerprint": _workspace_fingerprint(dataset, snapshot),
        },
        "capabilities": {
            "browse_samples": True,
            "layouts": True,
            "selection": True,
            "lasso_2d": True,
            "lasso_3d": False,
            "sample_similarity": num_similarity_queries > 0,
            "similarity_k": similarity_k if num_similarity_queries > 0 else 0,
            "text_search": False,
            "python_tools": False,
            "runtime_mutations": False,
            "panel_state": "ephemeral",
            "panels": panel_statuses,
        },
        "artifacts": {
            "runtime": "api/runtime.json",
            "dataset": "api/dataset.json",
            "samples": "api/samples/index.json",
            "embeddings": "api/embeddings/default.json",
            "similarity": (
                "api/search/similar/index.json" if num_similarity_queries > 0 else None
            ),
        },
        "deployment": {
            "cloudflare": {
                "worker_name": worker_name,
                "config": "wrangler.jsonc",
                "command": "npx wrangler deploy --config wrangler.jsonc",
                "mode": "static-assets-only",
            }
        },
    }
    _write_json(out_dir / "hyperview-static.json", manifest)
    num_files, bundle_bytes = _bundle_stats(out_dir)

    return StaticExportResult(
        workspace_id=workspace_id,
        dataset_name=workspace.dataset_name,
        output_dir=out_dir,
        num_samples=len(dataset),
        num_sample_shards=num_shards,
        num_layouts=num_layouts,
        num_collections=num_collections,
        num_media_files=num_media_files,
        num_similarity_queries=num_similarity_queries,
        similarity_k=similarity_k,
        num_files=num_files,
        bundle_bytes=bundle_bytes,
    )


def export_workspace(
    workspace_id: str,
    out: str | Path,
    *,
    similarity_k: int = DEFAULT_SIMILARITY_EXPORT_K,
) -> StaticExportResult:
    runtime = HyperViewRuntime()
    try:
        runtime.get_workspace(workspace_id)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        return export_runtime_workspace(runtime, workspace_id, out, similarity_k=similarity_k)
    except HTTPException as exc:
        raise RuntimeError(str(exc.detail)) from exc
