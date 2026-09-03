"""Bundle export for HyperView workspaces.

One export produces one bundle. The same folder hosts two ways: as a **Static
Space** (files on a static host, read-only, no Python) and as a **Live Space**
(``hyperview serve --from <bundle>`` in a container, backed by a real runtime).
The artifacts under ``api/`` serve the Static Space; the artifacts under
``restore/`` plus ``extensions/`` carry what a Live Space needs and a browser
does not -- embedding vectors and full extension folders.
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
from fastapi import HTTPException

from hyperview._version import __version__
from hyperview.core.dataset import Dataset
from hyperview.extensions import EXTENSION_MANIFEST_NAME, ExtensionManifest
from hyperview.runtime import CollectionState, CustomPanelSpec, HyperViewRuntime
from hyperview.server.app import (
    DEFAULT_THUMBNAIL_SIZE,
    serialize_sample_for_response,
)
from hyperview.storage.metrics import distance_metric_for_space
from hyperview.storage.schema import parse_layout_dimension, space_key_from_index_ref

SAMPLE_SHARD_SIZE = 500
SIMILARITY_SHARD_SIZE = 100
DEFAULT_SIMILARITY_EXPORT_K = 0
MAX_COLLECTION_EXPORT_K = 100
STATIC_BUNDLE_SCHEMA_VERSION = 1
NO_LAYOUTS_STATIC_REASON = "No layouts in this dataset"
# Versions the restore contract, independently of the Static Space schema.
# `schema_version` stays at 1 because restore only adds manifest keys and
# bundle paths; every field a Static Space consumer already reads is unchanged,
# and `_read_static_bundle_manifest` rejects any other `schema_version`.
RESTORE_SCHEMA_VERSION = 1
RESTORE_DIR = "restore"
BUNDLE_EXTENSIONS_DIR = "extensions"
SAMPLE_MEDIA_FILENAME = "content"


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
    warnings: tuple[str, ...] = ()

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
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class StaticBundleCopyResult:
    source_dir: Path
    output_dir: Path
    num_files: int
    bundle_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_dir": str(self.source_dir),
            "output_dir": str(self.output_dir),
            "num_files": self.num_files,
            "bundle_bytes": self.bundle_bytes,
        }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _public_static_payload(value: Any) -> Any:
    """Remove host-only filesystem details from JSON written to a static bundle."""

    if isinstance(value, dict):
        return {
            key: _public_static_payload(item)
            for key, item in value.items()
            if key not in {"filepath", "folder", "module_file"}
        }
    if isinstance(value, list):
        return [_public_static_payload(item) for item in value]
    return value


def _copy_static_frontend(out_dir: Path) -> None:
    static_dir = Path(__file__).parent / "server" / "static"
    if not static_dir.exists():
        raise RuntimeError(f"Packaged frontend assets are missing: {static_dir}")
    # A reviewed bundle may carry a previous hashed frontend build. Replace
    # every frontend-owned top-level artifact before copying the current shell
    # so repeated rebases do not retain unreachable chunks. Exported API,
    # media, panel modules, and deployment metadata live outside this set.
    for item in static_dir.iterdir():
        target = out_dir / item.name
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
    shutil.copytree(static_dir, out_dir, dirs_exist_ok=True)


def _inject_static_config(index_path: Path) -> None:
    script_body = "window.__HYPERVIEW_STATIC__ = true;"
    script = f"<script>{script_body}</script>"
    if not index_path.exists():
        raise RuntimeError(f"Frontend index.html is missing from export: {index_path}")
    html = index_path.read_text(encoding="utf-8")
    config_pattern = re.compile(
        r"window\.__HYPERVIEW_STATIC__\s*=\s*true;\s*"
        r"(?:window\.__HYPERVIEW_MOUNT_PATH__\s*=\s*[^;]+;\s*)?"
    )
    if config_pattern.search(html):
        html = config_pattern.sub(script_body, html, count=1)
    elif "<head>" in html:
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


def _write_samples(
    out_dir: Path, dataset: Dataset
) -> tuple[list[dict[str, Any]], int, int, list[str]]:
    samples = [
        _public_static_payload(
            serialize_sample_for_response(sample, include_thumbnail=False, ensure_dimensions=True)
        )
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
    missing_media: list[str] = []
    for sample in dataset.samples:
        media_count += _write_sample_media(out_dir, sample)
        if sample.filepath and sample.is_image:
            source = Path(sample.filepath).expanduser()
            if not source.is_file():
                missing_media.append(sample.id)

    warnings: list[str] = []
    if missing_media:
        preview = ", ".join(missing_media[:5])
        suffix = "" if len(missing_media) <= 5 else f", and {len(missing_media) - 5} more"
        warnings.append(
            f"{len(missing_media)} image samples reference missing local media files "
            f"({preview}{suffix}); their content and thumbnails were not exported."
        )

    return samples, len(shards), media_count, warnings


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
    if collection.kind == "selection":
        raw_ids = query.get("ids") or []
        if not isinstance(raw_ids, list):
            return [], None
        return [str(sample_id) for sample_id in raw_ids], None
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
                "sample": _public_static_payload(
                    serialize_sample_for_response(sample, include_thumbnail=False)
                ),
            }
            for rank, (sample_id, sample) in enumerate(
                (item.id, item) for item in dataset.get_samples_by_ids(ids)
            )
        ]
        # Keep the colon in collection directory names. Static asset servers
        # decode `%3A` before mapping a URL to the filesystem, so writing an
        # actually percent-encoded directory makes the browser-visible
        # `/api/collections/<id>/items.json` path 404.
        collection_dir = out_dir / "api" / "collections" / quote(collection.id, safe=":")
        _write_json(
            collection_dir / "items.json",
            {
                "collection_id": collection.id,
                "total": len(rows),
                "offset": 0,
                "limit": len(rows),
                "items": rows,
            },
        )
        _write_json(
            collection_dir / "index.json",
            {"collection": collection.to_dict(), "total": len(rows), "shards": ["items.json"]},
        )
    return len(collections)


def _prune_unreferenced_collections(snapshot: dict[str, Any]) -> None:
    """Keep only collections reachable by the exported workspace UI.

    Live workspaces retain prior searches for history and reuse. A static
    bundle cannot (and should not) recompute every historical query. Prepared
    collections referenced by panel props/state remain available, as does the
    dataset's all-items collection.
    """

    workspace = snapshot.get("workspace")
    if not isinstance(workspace, dict):
        return
    raw_collections = workspace.get("collections")
    if not isinstance(raw_collections, list):
        return
    collection_ids = {
        str(collection.get("id"))
        for collection in raw_collections
        if isinstance(collection, dict) and collection.get("id")
    }
    referenced: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, str):
            if value in collection_ids:
                referenced.add(value)
            return
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
            return
        if isinstance(value, list):
            for nested in value:
                collect(nested)

    collect(workspace.get("ui"))
    collect(snapshot.get("panel_definitions"))
    workspace["collections"] = [
        collection
        for collection in raw_collections
        if isinstance(collection, dict)
        and (
            collection.get("kind") == "all"
            or str(collection.get("id")) in referenced
        )
    ]


def _write_embeddings(out_dir: Path, dataset: Dataset) -> int:
    layouts = dataset.list_layouts()
    if not layouts:
        return 0
    default_layout = next(
        (layout for layout in layouts if parse_layout_dimension(layout.layout_key) == 2),
        layouts[0],
    )
    _write_json(
        out_dir / "api" / "embeddings" / "default.json",
        _embedding_payload(dataset, default_layout.layout_key),
    )
    for layout in layouts:
        _write_json(
            out_dir / "api" / "embeddings" / f"{quote(layout.layout_key, safe='')}.json",
            _embedding_payload(dataset, layout.layout_key),
        )
    return len(layouts)


def _producer_payload() -> dict[str, Any]:
    """Record what produced the vectors in this bundle.

    A restored Live Space answers typed text queries by encoding the query with
    the same model that produced the stored sample vectors. When that model
    lives in `hyper-models`, the version that wrote the vectors is the only
    thing that says whether a given container can reproduce them.
    """

    try:
        hyper_models_version: str | None = importlib_metadata.version("hyper-models")
    except importlib_metadata.PackageNotFoundError:
        hyper_models_version = None
    return {
        "hyperview": __version__,
        "hyper_models": hyper_models_version,
        "python": platform.python_version(),
    }


def _write_restore_embeddings(out_dir: Path, dataset: Dataset) -> list[dict[str, Any]]:
    """Write per-space sample vectors and describe them for restore.

    A Static Space never reads these: the browser only needs layout coordinates
    and, optionally, a precomputed neighbor index. A Live Space does, because
    answering a typed text query means encoding the query and searching the
    sample vectors in the model's own space -- which cannot be reconstructed
    from a 2D projection.

    Vectors go to compressed ``.npz`` rather than JSON: a float32 array of
    100k x 512 is roughly 200MB packed and about five times that as decimal
    text, and the values round-trip exactly either way.
    """

    entries: list[dict[str, Any]] = []
    for space in dataset.list_spaces():
        ids, vectors = dataset._storage.get_embeddings(space.space_key)
        vector_array = np.asarray(vectors, dtype=np.float32)
        if len(ids) == 0:
            vector_array = np.empty((0, space.dim), dtype=np.float32)

        relative = f"{RESTORE_DIR}/spaces/{quote(space.space_key, safe='')}/vectors.npz"
        target = out_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            np.savez_compressed(
                handle,
                ids=np.asarray(list(ids), dtype=np.str_),
                vectors=vector_array,
            )

        entries.append(
            {
                "space_key": space.space_key,
                "model_id": space.model_id,
                "dim": space.dim,
                "count": len(ids),
                "provider": space.provider,
                "geometry": space.geometry,
                "modality": space.modality,
                "index_id": space.index_id,
                "representation_id": space.representation_id,
                "config": space.config,
                "vectors": relative,
            }
        )
    return entries


def _restore_layout_payload(dataset: Dataset) -> list[dict[str, Any]]:
    """Describe layouts against the coordinate files the export already wrote."""

    return [
        {
            "layout_key": layout.layout_key,
            "space_key": layout.space_key,
            "method": layout.method,
            "geometry": layout.geometry,
            "params": layout.params,
            "count": layout.count,
            "coords": f"api/embeddings/{quote(layout.layout_key, safe='')}.json",
        }
        for layout in dataset.list_layouts()
    ]


def _extension_folders_to_copy(
    runtime: HyperViewRuntime,
    workspace_id: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Resolve every extension folder the bundle should carry.

    Two sources, because the exporting process may not be the one that
    installed anything. ``hyperview export`` builds a bare runtime and reads
    the persisted workspace, so ``list_extensions()`` is empty there while the
    view still renders extension panels. Those panels persist the path to their
    module source, whose parent directory is the extension folder.

    Every installed extension is copied, not only the ones the view renders:
    the runtime snapshot lists all of their tools and panel definitions, so
    restoring fewer would not reproduce the snapshot.
    """

    folders: dict[str, dict[str, Any]] = {}
    for installation in runtime.list_extensions():
        folder = installation.manifest.folder
        if not folder.is_dir():
            continue
        folders[installation.manifest.name] = {
            "folder": folder,
            "source": installation.source,
            "workspace_id": installation.workspace_id,
            "add_panels": installation.add_panels,
            "panels": list(installation.panel_ids),
        }

    warnings: list[str] = []
    for panel in runtime.get_workspace(workspace_id).ui.custom_panels:
        if not panel.extension or panel.extension in folders:
            continue
        module_file = panel.resolved_module_file()
        folder = module_file.parent if module_file is not None else None
        manifest = None
        if folder is not None and (folder / EXTENSION_MANIFEST_NAME).is_file():
            try:
                manifest = ExtensionManifest.load(folder)
            except (OSError, ValueError) as exc:
                warnings.append(
                    f"Extension '{panel.extension}' has an unreadable manifest at {folder}: "
                    f"{exc}. Panel '{panel.id}' will be missing when the bundle runs as a "
                    "Live Space."
                )
                continue
        if manifest is None or manifest.name != panel.extension:
            warnings.append(
                f"Extension '{panel.extension}' was not found on this host, so its folder "
                f"is not in the bundle. Panel '{panel.id}' will be missing when the bundle "
                "runs as a Live Space."
            )
            continue
        folders[manifest.name] = {
            "folder": manifest.folder,
            "source": panel.resolved_source(),
            "workspace_id": workspace_id,
            "add_panels": False,
            "panels": [],
        }
    return folders, warnings


def _copy_extension_folders(
    out_dir: Path,
    runtime: HyperViewRuntime,
    workspace_id: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Copy each referenced extension's full folder into the bundle.

    ``_copy_panel_modules`` publishes only the browser-loadable panel source a
    Static Space can execute, and deliberately drops ``.py`` and ``.toml``. A
    Live Space runs the extension for real, so it needs the manifest, the
    Python tools, and any assets -- the whole folder, installed through the
    normal ``install_extension`` path on restore.
    """

    folders, warnings = _extension_folders_to_copy(runtime, workspace_id)
    entries: list[dict[str, Any]] = []
    for name, info in sorted(folders.items()):
        relative = f"{BUNDLE_EXTENSIONS_DIR}/{name}"
        target = out_dir / relative
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(
            info["folder"],
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "artifacts"),
        )
        entries.append(
            {
                "name": name,
                "path": relative,
                "source": info["source"],
                "workspace_id": info["workspace_id"],
                "add_panels": info["add_panels"],
                "panels": info["panels"],
            }
        )
    return entries, warnings


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


def _annotate_static_panels(
    snapshot: dict[str, Any], runtime: HyperViewRuntime, workspace_id: str
) -> tuple[list[dict[str, Any]], set[str], list[str]]:
    definitions = {
        item.get("panel_type"): item
        for item in snapshot.get("panel_definitions", [])
        if isinstance(item, dict) and item.get("panel_type")
    }
    statuses: list[dict[str, Any]] = []
    compatible_ids: set[str] = set()
    warnings: list[str] = []
    runtime_panels = {
        panel.id: panel for panel in runtime.get_workspace(workspace_id).ui.custom_panels
    }
    panels = snapshot.get("workspace", {}).get("ui", {}).get("custom_panels", [])
    for panel in panels:
        if not isinstance(panel, dict):
            continue
        definition = definitions.get(panel.get("panel_type"), {})
        compatible = bool(definition.get("static_compatible", True))
        reason = definition.get("static_reason")
        panel_id = str(panel.get("id") or "")
        runtime_panel = runtime_panels.get(panel_id)
        if compatible and runtime_panel is not None and runtime_panel.kind == "module":
            module_file = runtime_panel.resolved_module_file()
            if module_file is None or not module_file.is_file():
                compatible = False
                reason = "Panel module source is missing from the workspace host."
                warnings.append(f"Panel '{panel_id}' was omitted: {reason}")
        data = panel.setdefault("data", {})
        if isinstance(data, dict):
            data["static_compatible"] = compatible
            data["static_reason"] = reason
            if compatible and runtime_panel is not None and runtime_panel.kind == "module":
                module_file = runtime_panel.resolved_module_file()
                if module_file is not None:
                    module_name = (
                        f"{module_file.stem}.js"
                        if module_file.suffix.lower() == ".jsx"
                        else module_file.name
                    )
                    data["module_src"] = (
                        "/api/panels/content/"
                        f"{quote(workspace_id, safe='')}/"
                        f"{quote(panel_id, safe='')}/"
                        f"{quote(module_name, safe='')}"
                    )
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
    return statuses, compatible_ids, warnings


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
    target_dir = (
        out_dir
        / "api"
        / "panels"
        / "content"
        / quote(workspace_id, safe="")
        / quote(panel.id, safe="")
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in module_file.parent.iterdir():
        if item.resolve() in excluded_modules or item.suffix.lower() in {".py", ".pyc", ".toml"}:
            continue
        target_name = f"{item.stem}.js" if item.suffix.lower() == ".jsx" else item.name
        target = target_dir / target_name
        if item.is_file():
            if item.suffix.lower() == ".jsx":
                try:
                    from esbuild_py import transform as esbuild_transform

                    transformed = esbuild_transform(item.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to transform JSX panel module {item}: {exc}"
                    ) from exc
                if transformed is not None:
                    # JSX siblings are emitted as .js as well so static hosts
                    # serve a browser-module MIME type. Keep relative imports
                    # aligned with those emitted filenames.
                    transformed = re.sub(
                        r'(["\'])(\.{1,2}/[^"\']+)\.jsx\1',
                        lambda match: (
                            f"{match.group(1)}{match.group(2)}.js{match.group(1)}"
                        ),
                        transformed,
                    )
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


def _deployment_payload(out_dir: Path, workspace_id: str) -> dict[str, Any]:
    """Describe how to host the bundle.

    Bundles reference their assets relatively, so one description covers being
    served at a domain root and being dropped inside a containing site.
    """

    worker_name = _write_cloudflare_config(out_dir, workspace_id)
    return {
        "hosting": {"mode": "static-assets"},
        "cloudflare": {
            "worker_name": worker_name,
            "config": "wrangler.jsonc",
            "command": "npx wrangler deploy --config wrangler.jsonc",
            "mode": "static-assets-only",
        },
        # Where this bundle can be published, and under which hosting model.
        # A Static Space serves these files; a Live Space runs the HyperView
        # server over the same bundle so visitors also get queries and compute.
        "targets": {
            "static": {
                "space": "Static Space",
                "commands": [
                    "hyperview publish <bundle> --to hf:<owner>/<name> --mode static",
                    "hyperview publish <bundle> --to cloudflare",
                    "hyperview publish <bundle> --to dir:<path>",
                ],
            },
            "live": {
                "space": "Live Space",
                "commands": [
                    "hyperview publish <bundle> --to hf:<owner>/<name> --mode live",
                ],
            },
        },
    }


def _resolved(path: str | Path) -> Path | None:
    try:
        return Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _sources_inside_output_dir(
    runtime: HyperViewRuntime,
    workspace_id: str,
    dataset: Dataset,
    out_dir: Path,
) -> list[str]:
    """Name every file the export would copy out of its own output directory."""

    offenders: list[str] = []

    for sample in dataset.samples:
        if not sample.filepath:
            continue
        source = _resolved(sample.filepath)
        if source is not None and source.is_relative_to(out_dir):
            offenders.append(f"sample '{sample.id}' media at {source}")

    folders, _warnings = _extension_folders_to_copy(runtime, workspace_id)
    for name, info in sorted(folders.items()):
        source = _resolved(info["folder"])
        if source is not None and source.is_relative_to(out_dir):
            offenders.append(f"extension '{name}' folder at {source}")

    for panel in runtime.get_workspace(workspace_id).ui.custom_panels:
        module_file = panel.resolved_module_file()
        if module_file is None:
            continue
        source = _resolved(module_file)
        if source is not None and source.is_relative_to(out_dir):
            offenders.append(f"panel '{panel.id}' module at {source}")

    return offenders


def _refuse_export_that_reads_its_own_output(
    runtime: HyperViewRuntime,
    workspace_id: str,
    dataset: Dataset,
    out_dir: Path,
) -> None:
    """Refuse before anything is cleared, not after.

    Exporting a workspace whose media or extension folders live inside the
    output directory would delete the files it is about to copy: the bundle
    comes out missing exactly what it was reading. A workspace restored from a
    bundle with ``--link-media`` is the way this happens.
    """

    offenders = _sources_inside_output_dir(runtime, workspace_id, dataset, out_dir)
    if not offenders:
        return
    preview = "; ".join(offenders[:3])
    more = "" if len(offenders) <= 3 else f"; and {len(offenders) - 3} more"
    raise RuntimeError(
        f"Export would read from its own output directory and was refused before "
        f"anything was written: {len(offenders)} source files of workspace "
        f"'{workspace_id}' are inside {out_dir} ({preview}{more}). Export to a "
        "different directory, or restore the bundle without --link-media so the "
        "dataset owns its media and extensions outside the bundle."
    )


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


def read_bundle_manifest(bundle_dir: str | Path) -> dict[str, Any]:
    """Read and validate a bundle's ``hyperview-static.json`` manifest."""

    return _read_static_bundle_manifest(Path(bundle_dir).expanduser().resolve())


def _read_static_bundle_manifest(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = bundle_dir / "hyperview-static.json"
    if not bundle_dir.is_dir() or not manifest_path.is_file():
        raise RuntimeError(f"Not a HyperView static bundle: {bundle_dir}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Invalid HyperView static manifest: {manifest_path}") from exc
    if (
        manifest.get("schema_version") != STATIC_BUNDLE_SCHEMA_VERSION
        or manifest.get("kind") != "hyperview-static-space"
        or manifest.get("static") is not True
    ):
        raise RuntimeError(f"Unsupported HyperView static bundle: {bundle_dir}")
    workspace = manifest.get("workspace")
    if not isinstance(workspace, dict) or not workspace.get("id"):
        raise RuntimeError(f"Static bundle manifest has no workspace id: {manifest_path}")
    return manifest


def copy_static_bundle(source: str | Path, out: str | Path) -> StaticBundleCopyResult:
    """Copy an existing static bundle onto the packaged frontend."""

    source_dir = Path(source).expanduser().resolve()
    out_dir = Path(out).expanduser().resolve()
    manifest = _read_static_bundle_manifest(source_dir)
    if (
        source_dir == out_dir
        or source_dir in out_dir.parents
        or out_dir in source_dir.parents
    ):
        raise RuntimeError("Source and output bundle directories must not overlap")

    _prepare_output_dir(out_dir)
    shutil.copytree(source_dir, out_dir, dirs_exist_ok=True)
    # Keep reviewed workspace data and custom panel modules, but serve them
    # through the current packaged frontend.
    _copy_static_frontend(out_dir)
    _inject_static_config(out_dir / "index.html")

    manifest.pop("mount_path", None)
    manifest["deployment"] = _deployment_payload(
        out_dir,
        str(manifest["workspace"]["id"]),
    )
    _write_json(out_dir / "hyperview-static.json", manifest)
    num_files, bundle_bytes = _bundle_stats(out_dir)
    return StaticBundleCopyResult(
        source_dir=source_dir,
        output_dir=out_dir,
        num_files=num_files,
        bundle_bytes=bundle_bytes,
    )


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

    workspace = runtime.get_workspace(workspace_id)
    if not workspace.dataset_name:
        raise RuntimeError(f"Workspace '{workspace_id}' has no dataset")
    dataset = runtime.get_dataset(workspace_id, workspace.dataset_name)

    # Every check that can refuse the export runs before the output directory
    # is cleared, so a refusal leaves an existing bundle intact.
    _refuse_export_that_reads_its_own_output(runtime, workspace_id, dataset, out_dir)
    _prepare_output_dir(out_dir)

    _copy_static_frontend(out_dir)
    _inject_static_config(out_dir / "index.html")

    snapshot = runtime.snapshot(workspace_id)
    # The bundle is scoped to the requested workspace even when the runtime
    # process has another workspace active globally.
    snapshot["active_workspace_id"] = workspace_id
    snapshot["workspaces"] = [
        {"id": workspace.id, "dataset_name": workspace.dataset_name}
    ]
    layouts = dataset.list_layouts()
    has_layouts = bool(layouts)
    has_2d_layout = any(parse_layout_dimension(layout.layout_key) == 2 for layout in layouts)
    if not has_layouts:
        # Keep the definition and let the declarative static contract carry the
        # reason: dropping it by name leaves an exported scatter panel pointing
        # at a definition the bundle no longer describes.
        for definition in snapshot.get("panel_definitions", []):
            if definition.get("panel_type") == "scatter":
                definition["static_compatible"] = False
                definition["static_reason"] = NO_LAYOUTS_STATIC_REASON
    panel_statuses, compatible_panel_ids, panel_warnings = _annotate_static_panels(
        snapshot, runtime, workspace_id
    )
    snapshot = _public_static_payload(snapshot)
    _prune_unreferenced_collections(snapshot)
    _write_json(out_dir / "api" / "runtime.json", snapshot)
    _write_json(out_dir / "api" / "dataset.json", _dataset_payload(dataset))
    _write_json(
        out_dir / "api" / "panel-definitions.json",
        {"panel_definitions": snapshot.get("panel_definitions", [])},
    )

    _samples, num_shards, num_media_files, media_warnings = _write_samples(out_dir, dataset)
    warnings = panel_warnings + media_warnings
    num_layouts = _write_embeddings(out_dir, dataset)
    num_collections = _write_collections(
        out_dir,
        dataset,
        snapshot,
        provider_registry=runtime.provider_registry,
    )
    num_similarity_queries = _write_similarity(out_dir, dataset, k=similarity_k)
    _copy_panel_modules(out_dir, runtime, workspace_id, compatible_panel_ids)

    restore_spaces = _write_restore_embeddings(out_dir, dataset)
    restore_extensions, extension_warnings = _copy_extension_folders(
        out_dir, runtime, workspace_id
    )
    warnings = warnings + extension_warnings

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
            "layouts": has_layouts,
            "selection": True,
            "lasso_2d": has_2d_layout,
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
            "embeddings": "api/embeddings/default.json" if num_layouts > 0 else None,
            "similarity": ("api/search/similar/index.json" if num_similarity_queries > 0 else None),
        },
        "deployment": _deployment_payload(
            out_dir,
            workspace_id,
        ),
        "producer": _producer_payload(),
        "restore": {
            "schema_version": RESTORE_SCHEMA_VERSION,
            "supported": True,
            "workspace_id": workspace_id,
            "dataset": {
                "name": workspace.dataset_name,
                "num_samples": len(dataset),
                "samples": "api/samples/index.json",
                "fields": "api/dataset.json",
            },
            "media": {
                "root": "api/samples",
                "filename": SAMPLE_MEDIA_FILENAME,
            },
            "spaces": restore_spaces,
            "layouts": _restore_layout_payload(dataset),
            "collections": [
                str(collection.get("id"))
                for collection in snapshot.get("workspace", {}).get("collections", [])
                if isinstance(collection, dict) and collection.get("id")
            ],
            "extensions": restore_extensions,
        },
        "warnings": warnings,
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
        warnings=tuple(warnings),
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
        return export_runtime_workspace(
            runtime,
            workspace_id,
            out,
            similarity_k=similarity_k,
        )
    except HTTPException as exc:
        raise RuntimeError(str(exc.detail)) from exc
