"""Load an exported HyperView bundle back into a live runtime.

``hyperview export`` writes a bundle: one folder that is the unit of delivery.
Hosting it as files on a static host makes it a **Static Space**. Loading it
here and serving it with ``hyperview serve --from <bundle>`` makes the same
folder a **Live Space** -- a real runtime with a dataset, embedding spaces,
layouts, collections, extensions, and the exported view already applied.

Restore is idempotent. Running it twice against the same
``HYPERVIEW_DATASETS_DIR`` reuses the dataset it finds instead of rebuilding
it, so a container that restarts comes back to the same Space rather than
re-ingesting on every boot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np

from hyperview.core.dataset import Dataset
from hyperview.core.sample import Sample
from hyperview.extensions import EXTENSION_MANIFEST_NAME, resolve_panel_source
from hyperview.runtime import HyperViewRuntime
from hyperview.static_export import (
    RESTORE_SCHEMA_VERSION,
    SAMPLE_MEDIA_FILENAME,
    read_bundle_manifest,
)


@dataclass(frozen=True)
class BundleRestoreResult:
    """What a restore put into the runtime."""

    bundle_dir: Path
    workspace_id: str
    dataset_name: str
    num_samples: int
    num_spaces: int
    num_layouts: int
    num_collections: int
    num_extensions: int
    num_panels: int
    reused_dataset: bool
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_dir": str(self.bundle_dir),
            "workspace_id": self.workspace_id,
            "dataset_name": self.dataset_name,
            "num_samples": self.num_samples,
            "num_spaces": self.num_spaces,
            "num_layouts": self.num_layouts,
            "num_collections": self.num_collections,
            "num_extensions": self.num_extensions,
            "num_panels": self.num_panels,
            "reused_dataset": self.reused_dataset,
            "warnings": list(self.warnings),
        }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"Bundle is missing {path.name}: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Bundle has invalid JSON at {path}: {exc}") from exc


def read_restore_manifest(bundle_dir: Path) -> dict[str, Any]:
    """Return the ``restore`` section of a bundle manifest.

    Bundles exported before restore existed are still valid Static Spaces, so
    the failure names what is missing rather than calling the folder invalid.
    """

    manifest = read_bundle_manifest(bundle_dir)
    restore = manifest.get("restore")
    if not isinstance(restore, dict) or restore.get("supported") is not True:
        raise RuntimeError(
            f"Bundle at {bundle_dir} carries no restore data and can only be hosted as a "
            "Static Space. Re-export it with this version of HyperView to run it as a "
            "Live Space."
        )
    schema_version = restore.get("schema_version")
    if schema_version != RESTORE_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported bundle restore schema_version {schema_version!r} "
            f"(this HyperView reads {RESTORE_SCHEMA_VERSION})"
        )
    return manifest


def _bundle_sample_payloads(bundle_dir: Path) -> list[dict[str, Any]]:
    """Read every sample record out of the bundle's sharded sample JSON."""

    samples_dir = bundle_dir / "api" / "samples"
    index = _read_json(samples_dir / "index.json")
    payloads: list[dict[str, Any]] = []
    for shard in index.get("shards") or []:
        if not isinstance(shard, dict) or not shard.get("path"):
            continue
        shard_payload = _read_json(samples_dir / str(shard["path"]))
        payloads.extend(
            item for item in (shard_payload.get("samples") or []) if isinstance(item, dict)
        )
    return payloads


def _sample_media_path(bundle_dir: Path, sample_id: str) -> Path:
    return bundle_dir / "api" / "samples" / quote(sample_id, safe="") / SAMPLE_MEDIA_FILENAME


def _sample_from_payload(bundle_dir: Path, payload: dict[str, Any]) -> tuple[Sample, bool]:
    """Rebuild one Sample, pointing its filepath at the bundle's own media copy.

    The bundle already holds a byte-for-byte copy of every exported media file,
    and the storage layer only ever needs ``filepath`` to be a readable path on
    this host -- the server reads media straight off disk. Copying those files
    a second time into ``HYPERVIEW_MEDIA_DIR`` would double a container's disk
    for no gain, and would have to invent filenames, because the bundle stores
    media extensionless under the sample id. Pointing at the bundle keeps one
    copy and keeps the folder self-contained; a bundle that moves is handled by
    restoring again, which re-points every filepath.
    """

    sample_id = str(payload["id"])
    media_path = _sample_media_path(bundle_dir, sample_id)
    has_media = media_path.is_file()
    media_missing = bool(payload.get("media_url")) and not has_media

    metadata = payload.get("metadata")
    return (
        Sample(
            id=sample_id,
            filepath=str(media_path) if has_media else None,
            label=payload.get("label"),
            text=payload.get("text"),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            width=payload.get("width"),
            height=payload.get("height"),
            media_type=payload.get("media_type"),
            duration_s=payload.get("duration_s"),
            modality=str(payload.get("modality") or "image"),
        ),
        media_missing,
    )


def _restore_dataset(
    bundle_dir: Path,
    dataset_name: str,
    dataset_payload: dict[str, Any],
) -> tuple[Dataset, int, bool, list[str]]:
    payloads = _bundle_sample_payloads(bundle_dir)
    samples: list[Sample] = []
    missing_media: list[str] = []
    for payload in payloads:
        sample, media_missing = _sample_from_payload(bundle_dir, payload)
        samples.append(sample)
        if media_missing:
            missing_media.append(sample.id)

    dataset = Dataset(dataset_name)
    existing = dataset.samples
    media_root = (bundle_dir / "api" / "samples").resolve()
    # Reuse only when the dataset already holds exactly these samples *and*
    # already points at this bundle. An id-only match would leave a restarted
    # container reading media out of a bundle path that no longer exists.
    already_restored = bool(existing) and {item.id for item in existing} == {
        item.id for item in samples
    }
    if already_restored:
        already_restored = all(
            item.filepath is None or Path(item.filepath).resolve().is_relative_to(media_root)
            for item in existing
        )

    if not already_restored:
        dataset.add_samples(samples, skip_existing=False)

    fields = dataset_payload.get("fields")
    if isinstance(fields, dict) and fields:
        dataset._storage.register_fields(fields)

    warnings: list[str] = []
    if missing_media:
        preview = ", ".join(missing_media[:5])
        suffix = "" if len(missing_media) <= 5 else f", and {len(missing_media) - 5} more"
        warnings.append(
            f"{len(missing_media)} samples reference media the bundle does not carry "
            f"({preview}{suffix}); they were restored without a media file."
        )

    return dataset, len(samples), already_restored, warnings


def _restore_spaces(bundle_dir: Path, dataset: Dataset, restore: dict[str, Any]) -> int:
    """Recreate embedding spaces under their source space ids.

    The space id is not cosmetic: index ids (``space:<space_key>``), layout
    rows, collection queries, and panel props all address it, so a restored
    space that picked a fresh key would leave the exported view pointing at
    nothing.
    """

    entries = [item for item in (restore.get("spaces") or []) if isinstance(item, dict)]
    for entry in entries:
        vectors_ref = entry.get("vectors")
        if not vectors_ref:
            continue
        with np.load(bundle_dir / str(vectors_ref), allow_pickle=False) as payload:
            ids = [str(item) for item in payload["ids"].tolist()]
            vectors = np.asarray(payload["vectors"], dtype=np.float32)
        dataset.register_embeddings(
            str(entry["space_key"]),
            str(entry.get("model_id") or entry["space_key"]),
            ids,
            vectors,
            config=entry.get("config"),
        )
    return len(entries)


def _restore_layouts(bundle_dir: Path, dataset: Dataset, restore: dict[str, Any]) -> int:
    """Recreate layouts under their source layout keys."""

    entries = [item for item in (restore.get("layouts") or []) if isinstance(item, dict)]
    for entry in entries:
        coords_ref = entry.get("coords")
        if not coords_ref:
            continue
        payload = _read_json(bundle_dir / str(coords_ref))
        ids = [str(item) for item in (payload.get("ids") or [])]
        coords = np.asarray(payload.get("coords") or [], dtype=np.float32)
        if not ids:
            continue
        dataset.register_layout(
            str(entry["layout_key"]),
            str(entry["space_key"]),
            ids,
            coords,
            method=str(entry.get("method") or "precomputed"),
            geometry=str(entry.get("geometry") or "euclidean"),
            params=entry.get("params"),
        )
    return len(entries)


def _install_bundle_extensions(
    bundle_dir: Path,
    runtime: HyperViewRuntime,
    workspace_id: str,
    restore: dict[str, Any],
) -> tuple[int, list[str]]:
    """Install each extension the bundle carries through the normal path.

    ``add_panels`` is off: the exported workspace snapshot already describes
    every panel instance with its position, props, and state, and is applied
    afterwards. Letting the installer add its manifest defaults first would
    place panels the snapshot then has to overwrite.
    """

    installed = 0
    warnings: list[str] = []
    for entry in restore.get("extensions") or []:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        name = str(entry.get("name") or entry["path"])
        folder = bundle_dir / str(entry["path"])
        if not (folder / EXTENSION_MANIFEST_NAME).is_file():
            warnings.append(
                f"Extension '{name}' is listed in the bundle manifest but its folder is "
                f"missing {EXTENSION_MANIFEST_NAME}; its panels and tools were not restored."
            )
            continue
        source = entry.get("source")
        try:
            runtime.install_extension(
                workspace_id,
                folder,
                add_panels=False,
                source="shipped" if source == "shipped" else "extension",
            )
        except Exception as exc:  # noqa: BLE001 - one bad extension must not sink the Space
            warnings.append(f"Extension '{name}' failed to install from the bundle: {exc}")
            continue
        installed += 1
    return installed, warnings


def _repair_panel_module_file(
    panel: dict[str, Any],
    runtime: HyperViewRuntime,
) -> str | None:
    """Re-point a panel at its module source on this host.

    The export strips ``module_file`` from the snapshot because it is a path on
    the machine that did the exporting. After the extensions are installed the
    real path is knowable again, and it has to be filled in before the payload
    is parsed: ``WorkspaceUiState.from_dict`` drops a module panel that has no
    module file, which would silently delete the panel from the restored view.
    """

    if panel.get("module_file"):
        return None
    kind = str(panel.get("kind") or "module")
    if kind == "builtin":
        return None

    panel_id = str(panel.get("id") or "?")
    extension = panel.get("extension")
    extension_panel = panel.get("extension_panel")
    if not extension or not extension_panel:
        return (
            f"Panel '{panel_id}' has no extension reference and no module source; "
            "it was dropped from the restored view."
        )

    installation = runtime.get_extension(str(extension))
    if installation is None:
        return (
            f"Panel '{panel_id}' needs extension '{extension}', which the bundle did not "
            "install; it was dropped from the restored view."
        )

    entry = next(
        (item for item in installation.manifest.panels if item.id == str(extension_panel)),
        None,
    )
    module_name = entry.module_file() if entry is not None else None
    if module_name is None:
        return (
            f"Panel '{panel_id}' is not declared by extension '{extension}'; "
            "it was dropped from the restored view."
        )

    try:
        panel["module_file"] = str(resolve_panel_source(installation.manifest.folder, module_name))
    except (FileNotFoundError, ValueError) as exc:
        return f"Panel '{panel_id}' module source could not be resolved: {exc}"
    return None


def _workspace_payload(
    snapshot: dict[str, Any],
    runtime: HyperViewRuntime,
    *,
    workspace_id: str,
    dataset_name: str,
) -> tuple[dict[str, Any], list[str]]:
    raw = snapshot.get("workspace")
    if not isinstance(raw, dict):
        raise RuntimeError("Bundle runtime snapshot has no workspace section")

    payload = json.loads(json.dumps(raw))
    payload["id"] = workspace_id
    payload["dataset_name"] = dataset_name

    warnings: list[str] = []
    ui = payload.get("ui")
    if isinstance(ui, dict):
        for panel in ui.get("custom_panels") or []:
            if not isinstance(panel, dict):
                continue
            # Static-hosting annotations (`static_compatible`, `module_src`)
            # describe the browser-only bundle and mean nothing to a runtime.
            panel.pop("data", None)
            warning = _repair_panel_module_file(panel, runtime)
            if warning is not None:
                warnings.append(warning)
    return payload, warnings


def restore_bundle(
    bundle: str | Path,
    *,
    runtime: HyperViewRuntime | None = None,
    workspace_id: str | None = None,
) -> tuple[HyperViewRuntime, BundleRestoreResult]:
    """Restore a bundle into a runtime and return both.

    Args:
        bundle: Path to a folder written by ``hyperview export``.
        runtime: Runtime to restore into. A new one is created when omitted.
        workspace_id: Workspace id to restore under. Defaults to the id the
            bundle was exported from, which is what panel props and pinned
            layout keys expect.

    Returns:
        ``(runtime, result)``.
    """

    bundle_dir = Path(bundle).expanduser().resolve()
    manifest = read_restore_manifest(bundle_dir)
    restore = manifest["restore"]

    dataset_name = str(manifest["workspace"].get("dataset_name") or "").strip()
    if not dataset_name:
        raise RuntimeError(f"Bundle manifest names no dataset: {bundle_dir}")

    target_workspace_id = str(workspace_id or manifest["workspace"]["id"]).strip()
    if not target_workspace_id:
        raise ValueError("workspace_id must be a non-empty string")

    snapshot = _read_json(bundle_dir / "api" / "runtime.json")
    dataset_payload = _read_json(bundle_dir / "api" / "dataset.json")

    runtime = runtime or HyperViewRuntime()
    runtime.workspace_registry.ensure_workspace(target_workspace_id, activate=True)

    dataset, num_samples, reused_dataset, warnings = _restore_dataset(
        bundle_dir, dataset_name, dataset_payload
    )
    num_spaces = _restore_spaces(bundle_dir, dataset, restore)
    num_layouts = _restore_layouts(bundle_dir, dataset, restore)

    # Attach before applying the view: attaching a different dataset name
    # resets the workspace's collections, panel state, and active layout.
    runtime.attach_dataset_instance(target_workspace_id, dataset, activate_workspace=True)

    num_extensions, extension_warnings = _install_bundle_extensions(
        bundle_dir, runtime, target_workspace_id, restore
    )
    warnings.extend(extension_warnings)

    payload, panel_warnings = _workspace_payload(
        snapshot,
        runtime,
        workspace_id=target_workspace_id,
        dataset_name=dataset_name,
    )
    warnings.extend(panel_warnings)
    workspace = runtime.restore_workspace_state(target_workspace_id, payload)

    return runtime, BundleRestoreResult(
        bundle_dir=bundle_dir,
        workspace_id=target_workspace_id,
        dataset_name=dataset_name,
        num_samples=num_samples,
        num_spaces=num_spaces,
        num_layouts=num_layouts,
        num_collections=len(workspace.collections),
        num_extensions=num_extensions,
        num_panels=len(workspace.ui.custom_panels),
        reused_dataset=reused_dataset,
        warnings=tuple(warnings),
    )


__all__ = [
    "BundleRestoreResult",
    "read_restore_manifest",
    "restore_bundle",
]
