"""Dataset class for managing collections of samples."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import mimetypes
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
from PIL import Image

from hyperview._compat import disable_blocked_datasets_torch_shared_memory
from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.fields import FieldCatalog, FieldDefinition
from hyperview.storage.schema import (
    LayoutInfo,
    SpaceInfo,
    make_layout_key,
    normalize_layout_dimension,
    parse_layout_dimension,
)

DEFAULT_VISUALIZATION_LAYOUT = "euclidean"
VALID_VISUALIZATION_GEOMETRIES = ("euclidean", "poincare", "spherical")

# Persisted provider spellings from before provider-registry unification.
# Add future read-compatible slug migrations here.
LEGACY_PROVIDER_ALIASES = {
    "embed_anything": "embed-anything",
}

# These are the multimodal model-id families HyperView's legacy
# embed-anything examples and defaults produced before provider metadata was
# persisted. They are intentionally bounded: an unknown provider must not be
# guessed for an arbitrary model.
LEGACY_EMBED_ANYTHING_MODEL_PREFIXES = (
    "openai/clip-",
    "google/siglip-",
    "jinaai/jina-clip-",
)


def _normalize_provider_slug(provider: str) -> str:
    return LEGACY_PROVIDER_ALIASES.get(provider, provider)


def _is_legacy_embed_anything_model(model_id: str) -> bool:
    normalized_model_id = model_id.strip().lower()
    return normalized_model_id.startswith(LEGACY_EMBED_ANYTHING_MODEL_PREFIXES)


def load_dataset(*args: Any, **kwargs: Any) -> Any:
    """Lazy wrapper for Hugging Face dataset loading."""
    from datasets import load_dataset as hf_load_dataset

    return hf_load_dataset(*args, **kwargs)


def _download_config(**kwargs: Any) -> Any:
    from datasets import DownloadConfig

    return DownloadConfig(**kwargs)


def _hash_huggingface_dataset(dataset: Any) -> str:
    from datasets.fingerprint import Hasher

    return str(Hasher.hash(dataset))


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    total_seconds = int(round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s"


def _format_eta(seconds: float) -> str:
    if not math.isfinite(seconds) or seconds < 0:
        return "unknown"
    return _format_elapsed(seconds)


def _normalize_local_filepath(filepath: str) -> str:
    """Resolve local relative paths at ingestion time."""
    if "://" in filepath:
        return filepath

    path = Path(filepath).expanduser()
    if path.is_absolute():
        return str(path)
    return str(path.resolve())


def _normalize_sample_filepath(sample: Sample) -> Sample:
    if sample.filepath is None:
        return sample
    normalized = _normalize_local_filepath(sample.filepath)
    if normalized == sample.filepath:
        return sample
    return sample.model_copy(update={"filepath": normalized})


def _dedupe_samples_by_id(samples: list[Sample]) -> list[Sample]:
    """Return samples unique by id, keeping the last occurrence."""

    deduped: dict[str, Sample] = {}
    for sample in samples:
        if sample.id in deduped:
            del deduped[sample.id]
        deduped[sample.id] = sample
    return list(deduped.values())


def _media_type_for_path(path: str | Path) -> str | None:
    """Infer a MIME-ish media type from a source filename."""
    media_type, _ = mimetypes.guess_type(str(path))
    return media_type


def _field_catalog_for_samples(samples: list[Sample]) -> FieldCatalog:
    """Build the discoverable field catalog for ingested sample records."""
    fields: FieldCatalog = {
        "id": FieldDefinition(type="scalar", nullable=False, source="builtin"),
        "filepath": FieldDefinition(type="media", nullable=True, source="builtin"),
        "media_type": FieldDefinition(type="scalar", nullable=True, source="builtin"),
        "duration_s": FieldDefinition(type="scalar", nullable=True, source="builtin"),
        "label": FieldDefinition(type="label", nullable=True, source="builtin"),
        "text": FieldDefinition(type="text", nullable=True, source="builtin"),
        "modality": FieldDefinition(type="scalar", nullable=False, source="builtin"),
    }
    for sample in samples:
        for key in sample.metadata:
            fields.setdefault(
                f"metadata.{key}",
                FieldDefinition(type="scalar", nullable=True, source="metadata"),
            )
    return fields


def parse_visualization_layout(layout: str) -> tuple[str, int]:
    """Parse a public visualization layout spec like ``euclidean:3d``.

    Omitting the suffix defaults to 2D for Euclidean and Poincare layouts,
    and to 3D for spherical layouts.
    """
    layout_spec = layout.strip().lower()
    if not layout_spec:
        raise ValueError("layout must be a non-empty string")

    if ":" in layout_spec:
        geometry, dimension_spec = layout_spec.rsplit(":", 1)
    else:
        geometry = layout_spec
        dimension_spec = "3d" if geometry.strip() == "spherical" else "2d"

    geometry = geometry.strip()
    dimension_spec = dimension_spec.strip()

    if geometry not in VALID_VISUALIZATION_GEOMETRIES:
        raise ValueError(
            f"layout geometry must be one of {VALID_VISUALIZATION_GEOMETRIES}, got '{geometry}'"
        )

    if dimension_spec not in ("2d", "3d"):
        raise ValueError(
            f"layout must use the form '<geometry>:2d' or '<geometry>:3d', got '{layout}'"
        )

    layout_dimension = normalize_layout_dimension(int(dimension_spec[0]))
    if geometry == "poincare" and layout_dimension != 2:
        raise ValueError("Poincare layouts currently require 2D output.")

    return geometry, layout_dimension


class LayoutRecord(LayoutInfo):
    """One visualization layout, described by what produced it.

    Layout keys carry a content hash, so they are only knowable after the
    layout is computed. This record exposes the properties a caller actually
    reasons about — which model and provider produced the embedding space, and
    which geometry, dimension, and projection method produced the layout — so
    scripts can look a layout up instead of pinning its key as a constant.
    """

    def __init__(self, layout: LayoutInfo, space: SpaceInfo | None) -> None:
        super().__init__(
            layout_key=layout.layout_key,
            space_key=layout.space_key,
            method=layout.method,
            geometry=layout.geometry,
            count=layout.count,
            created_at=layout.created_at,
            params=layout.params,
        )
        self.model_id = space.model_id if space is not None else None
        self.provider = space.provider if space is not None else None

    @property
    def key(self) -> str:
        """The layout key, as passed to ``hv.ui.Scatter(layout_key=...)``."""

        return self.layout_key

    @property
    def space_id(self) -> str:
        """The embedding space this layout projects."""

        return self.space_key

    @property
    def dimension(self) -> int:
        """2 or 3, parsed from the layout key."""

        return self.layout_dimension

    @property
    def sample_count(self) -> int:
        """How many samples have coordinates in this layout."""

        return self.count

    def to_api_dict(self) -> dict[str, Any]:
        return {
            **super().to_api_dict(),
            "model_id": self.model_id,
            "provider": self.provider,
            "layout_dimension": self.layout_dimension,
        }

    def describe(self) -> str:
        """One line naming this layout, for error messages and logs."""

        return (
            f"{self.layout_key} (model={self.model_id}, provider={self.provider}, "
            f"geometry={self.geometry}, dimension={self.dimension}, "
            f"method={self.method}, samples={self.sample_count})"
        )


class Dataset:
    """A collection of samples with support for embeddings and visualization.

    Datasets are automatically persisted to LanceDB by default, providing:
    - Automatic persistence (no need to call save())
    - Vector similarity search
    - Efficient storage and retrieval

    Embeddings are stored separately from samples, keyed by model_id.
    Layouts (2D/3D projections) are stored per layout_key (space + method).
    """

    def __init__(
        self,
        name: str | None = None,
        persist: bool = True,
        storage: StorageBackend | None = None,
    ):
        disable_blocked_datasets_torch_shared_memory()
        self.name = name or f"dataset_{uuid.uuid4().hex[:8]}"

        if storage is not None:
            self._storage = storage
        elif persist:
            from hyperview.storage import LanceDBBackend, StorageConfig

            config = StorageConfig.default()
            self._storage = LanceDBBackend(self.name, config)
        else:
            from hyperview.storage import MemoryBackend

            self._storage = MemoryBackend(self.name)

        self.last_requested_sample_ids: list[str] = []

    def __len__(self) -> int:
        return len(self._storage)

    def __iter__(self) -> Iterator[Sample]:
        return iter(self._storage)

    def __getitem__(self, sample_id: str) -> Sample:
        sample = self._storage.get_sample(sample_id)
        if sample is None:
            raise KeyError(sample_id)
        return sample

    def add_sample(self, sample: Sample) -> None:
        """Add or update a single sample."""
        self.add_samples([sample], skip_existing=False)

    def add_samples(
        self,
        samples: Iterable[Sample],
        *,
        skip_existing: bool = False,
    ) -> tuple[int, int]:
        """Add or update samples in a single batch.

        Returns ``(num_added_or_upserted, num_skipped_existing)``.
        """
        sample_list = list(samples)
        self.last_requested_sample_ids = [sample.id for sample in sample_list]
        sample_list = [_normalize_sample_filepath(sample) for sample in sample_list]

        if not sample_list:
            return 0, 0

        sample_list = _dedupe_samples_by_id(sample_list)

        skipped = 0
        if skip_existing:
            all_ids = [sample.id for sample in sample_list]
            existing_ids = self._storage.get_existing_ids(all_ids)
            if existing_ids:
                sample_list = [sample for sample in sample_list if sample.id not in existing_ids]
                skipped = len(all_ids) - len(sample_list)

        if not sample_list:
            return 0, skipped

        self._storage.add_samples_batch(sample_list)
        self._storage.register_fields(_field_catalog_for_samples(sample_list))

        return len(sample_list), skipped

    def add_images_dir(
        self,
        directory: str,
        extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp"),
        label_from_folder: bool = False,
        recursive: bool = True,
        skip_existing: bool = True,
    ) -> tuple[int, int]:
        """Add all images from a directory."""
        directory_path = Path(directory)
        if not directory_path.exists():
            raise ValueError(f"Directory does not exist: {directory_path}")

        samples = []
        pattern = "**/*" if recursive else "*"

        for path in directory_path.glob(pattern):
            if path.is_file() and path.suffix.lower() in extensions:
                label = path.parent.name if label_from_folder else None
                sample_id = hashlib.md5(str(path).encode()).hexdigest()[:12]
                sample = Sample(
                    id=sample_id,
                    filepath=str(path),
                    label=label,
                    metadata={},
                    media_type=_media_type_for_path(path),
                )
                samples.append(sample)

        return self.add_samples(samples, skip_existing=skip_existing)

    def add_texts(
        self,
        records: Iterable[dict[str, Any]] | str | Path,
        *,
        text_field: str = "text",
        label_field: str | None = "label",
        id_field: str | None = "id",
        skip_existing: bool = True,
    ) -> tuple[int, int]:
        """Add text records from dictionaries, JSONL, or CSV.

        Input fields are mapped onto HyperView's canonical ``text``, ``label``,
        and ``id`` fields. Any remaining values are retained under ``metadata``.
        """
        if not text_field:
            raise ValueError("text_field must be a non-empty string")

        source_records: Iterable[dict[str, Any]]
        if isinstance(records, (str, Path)):
            path = Path(records).expanduser()
            if not path.exists() or not path.is_file():
                raise ValueError(f"Text records file does not exist: {path}")
            suffix = path.suffix.lower()
            if suffix == ".jsonl":

                def iter_jsonl() -> Iterator[dict[str, Any]]:
                    with path.open(encoding="utf-8") as handle:
                        for line_number, line in enumerate(handle, start=1):
                            if not line.strip():
                                continue
                            value = json.loads(line)
                            if not isinstance(value, dict):
                                raise ValueError(
                                    f"JSONL record {line_number} must be an object"
                                )
                            yield value

                source_records = iter_jsonl()
            elif suffix == ".csv":

                def iter_csv() -> Iterator[dict[str, Any]]:
                    with path.open(encoding="utf-8", newline="") as handle:
                        yield from csv.DictReader(handle)

                source_records = iter_csv()
            else:
                raise ValueError("Text records path must use a .jsonl or .csv extension")
        else:
            source_records = records

        samples: list[Sample] = []
        for index, record in enumerate(source_records):
            if not isinstance(record, dict):
                raise TypeError(f"Text record {index} must be a dictionary")
            if text_field not in record:
                raise ValueError(f"Text record {index} is missing field '{text_field}'")

            text = str(record[text_field] or "").strip()
            if not text:
                raise ValueError(f"Text record {index} has an empty '{text_field}' value")

            label: str | None = None
            if label_field and record.get(label_field) is not None:
                label = str(record[label_field])

            if id_field and record.get(id_field) is not None:
                sample_id = str(record[id_field]).strip()
                if not sample_id:
                    raise ValueError(f"Text record {index} has an empty '{id_field}' value")
            else:
                identity = json.dumps(record, sort_keys=True, default=str)
                sample_id = f"text_{hashlib.sha256(f'{index}:{identity}'.encode()).hexdigest()[:12]}"

            metadata_value = record.get("metadata")
            metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
            mapped_fields = {text_field, "metadata"}
            if label_field:
                mapped_fields.add(label_field)
            if id_field:
                mapped_fields.add(id_field)
            metadata.update(
                {key: value for key, value in record.items() if key not in mapped_fields}
            )

            samples.append(
                Sample(
                    id=sample_id,
                    filepath=None,
                    label=label,
                    text=text,
                    modality="text",
                    media_type="text/plain",
                    metadata=metadata,
                )
            )

        added, skipped = self.add_samples(samples, skip_existing=skip_existing)
        if samples:
            mapped_catalog: FieldCatalog = {
                "id": FieldDefinition(
                    type="scalar", nullable=False, source=id_field or "generated"
                ),
                "text": FieldDefinition(type="text", nullable=False, source=text_field),
                "label": FieldDefinition(
                    type="label", nullable=True, source=label_field or "unmapped"
                ),
            }
            self._storage.register_fields(mapped_catalog)
        return added, skipped

    def add_from_huggingface(
        self,
        dataset_name: str,
        config: str | None = None,
        split: str = "train",
        image_key: str | None = "img",
        label_key: str | None = "fine_label",
        label_names_key: str | None = None,
        text_key: str | None = None,
        max_samples: int | None = None,
        shuffle: bool = False,
        seed: int = 42,
        streaming: bool = False,
        shuffle_buffer_size: int = 1000,
        show_progress: bool = True,
        skip_existing: bool = True,
        image_format: str = "auto",
    ) -> tuple[int, int]:
        """Load image, text, or paired samples from a Hugging Face dataset."""
        from hyperview.storage import StorageConfig

        if not image_key and not text_key:
            raise ValueError("At least one of image_key or text_key is required")

        source_index_key = "__hyperview_source_index"

        def attach_huggingface_source_index(
            example: dict[str, Any],
            index: int,
        ) -> dict[str, Any]:
            augmented = dict(example)
            augmented[source_index_key] = index
            return augmented

        if shuffle_buffer_size < 1:
            raise ValueError("shuffle_buffer_size must be >= 1")

        if streaming:
            ds = cast(
                Any,
                load_dataset(
                    dataset_name,
                    name=config,
                    split=split,
                    streaming=True,
                ),
            )
        else:
            try:
                ds = cast(
                    Any,
                    load_dataset(
                        dataset_name,
                        name=config,
                        split=split,
                        download_config=_download_config(local_files_only=True),
                    ),
                )
            except Exception:
                ds = cast(Any, load_dataset(dataset_name, name=config, split=split))

        source_fingerprint = getattr(ds, "_fingerprint", None)
        if source_fingerprint is None:
            source_fingerprint = _hash_huggingface_dataset(ds)
        source_fingerprint = str(source_fingerprint)

        label_names = None
        if label_key and label_names_key:
            if label_names_key in ds.features:
                label_names = ds.features[label_names_key].names
        elif label_key:
            if hasattr(ds.features[label_key], "names"):
                label_names = ds.features[label_key].names

        config_name = getattr(ds.info, "config_name", None) or "default"
        version = str(ds.info.version) if ds.info.version else None
        fingerprint = source_fingerprint[:8]

        total: int | None
        selected_indices: list[int] | None = None
        iterator: Iterator[Any]
        if streaming:
            stream = ds
            if hasattr(stream, "select_columns"):
                columns = [key for key in (image_key,) if key]
                if label_key:
                    columns.append(label_key)
                if text_key:
                    columns.append(text_key)
                stream = stream.select_columns(list(dict.fromkeys(columns)))
            stream = stream.map(attach_huggingface_source_index, with_indices=True)
            if shuffle:
                if hasattr(stream, "reshard"):
                    stream = stream.reshard()
                stream = stream.shuffle(seed=seed, buffer_size=shuffle_buffer_size)
            if max_samples is not None:
                total = max_samples
                iterator = iter(stream.take(max_samples))
            else:
                total = None
                iterator = iter(stream)
        else:
            dataset_size = len(ds)
            total = dataset_size if max_samples is None else min(dataset_size, max_samples)

            if shuffle:
                rng = np.random.default_rng(seed)
                selected_indices = rng.permutation(dataset_size)[:total].tolist()
                ds = ds.select(selected_indices)
            elif max_samples is not None:
                selected_indices = list(range(total))
                ds = ds.select(selected_indices)

            iterator = (ds[i] for i in range(total))

        storage_config = StorageConfig.default()
        media_dir = storage_config.get_huggingface_media_dir(dataset_name, split)

        samples: list[Sample] = []

        if show_progress:
            if total is None:
                print(f"Loading samples from {dataset_name} via streaming...", flush=True)
            else:
                mode_suffix = " via streaming" if streaming else ""
                print(
                    f"Loading {total} samples from {dataset_name}{mode_suffix}...",
                    flush=True,
                )

        started_at = time.perf_counter()
        last_report_at = started_at
        report_every = 50 if total is None else max(25, min(200, total // 20 or 25))
        loaded = 0
        progress_stop = threading.Event()

        def emit_progress(now: float, *, waiting_for_first_sample: bool = False) -> None:
            elapsed = max(now - started_at, 1e-9)
            if waiting_for_first_sample:
                if total is None:
                    print(
                        "Still waiting for the first streamed sample "
                        f"(elapsed {_format_elapsed(elapsed)})",
                        flush=True,
                    )
                else:
                    print(
                        "Still waiting for the first streamed sample "
                        f"(0/{total}, elapsed {_format_elapsed(elapsed)})",
                        flush=True,
                    )
                return

            rate = loaded / elapsed
            if total is None:
                print(
                    f"Loaded {loaded} samples ({rate:.1f}/s, elapsed {_format_elapsed(elapsed)})",
                    flush=True,
                )
                return

            remaining = total - loaded
            eta_seconds = remaining / rate if rate > 0 else float("inf")
            print(
                f"Loaded {loaded}/{total} samples "
                f"({loaded / total:.0%}, {rate:.1f}/s, "
                f"elapsed {_format_elapsed(elapsed)}, ETA {_format_eta(eta_seconds)})",
                flush=True,
            )

        heartbeat: threading.Thread | None = None
        if show_progress and streaming:

            def heartbeat_reporter() -> None:
                while not progress_stop.wait(10.0):
                    now = time.perf_counter()
                    if loaded == 0:
                        emit_progress(now, waiting_for_first_sample=True)
                    elif now - last_report_at >= 10.0:
                        emit_progress(now)

            heartbeat = threading.Thread(
                target=heartbeat_reporter,
                name="hyperview-hf-progress",
                daemon=True,
            )
            heartbeat.start()

        try:
            for i, item in enumerate(iterator):
                if streaming:
                    source_index = int(item.pop(source_index_key, i))
                else:
                    source_index = selected_indices[i] if selected_indices is not None else i
                pil_image: Image.Image | None = None
                if image_key:
                    image = item[image_key]
                    if isinstance(image, Image.Image):
                        pil_image = image
                    else:
                        pil_image = Image.fromarray(np.asarray(image))

                label = None
                if label_key and label_key in item:
                    label_idx = item[label_key]
                    if label_names and isinstance(label_idx, int):
                        label = label_names[label_idx]
                    else:
                        label = str(label_idx)

                text: str | None = None
                if text_key and text_key in item:
                    raw_text = item[text_key]
                    if isinstance(raw_text, list):
                        text = " ".join(str(part).strip() for part in raw_text if str(part).strip()) or None
                    elif raw_text is not None:
                        text = str(raw_text).strip() or None
                if pil_image is None and text is None:
                    raise ValueError(
                        f"Hugging Face sample {source_index} has no non-empty "
                        f"'{text_key}' value"
                    )

                modality = "multimodal" if pil_image is not None and text else (
                    "image" if pil_image is not None else "text"
                )

                safe_name = dataset_name.replace("/", "_")
                sample_id = f"{safe_name}_{config_name}_{fingerprint}_{split}_{source_index}"

                image_path: Path | None = None
                if pil_image is not None and image_format == "auto":
                    original_format = getattr(pil_image, "format", None)
                    if original_format in ("JPEG", "JPG"):
                        save_format = "JPEG"
                        ext = ".jpg"
                    else:
                        save_format = "PNG"
                        ext = ".png"
                elif pil_image is not None and image_format == "jpeg":
                    save_format = "JPEG"
                    ext = ".jpg"
                elif pil_image is not None:
                    save_format = "PNG"
                    ext = ".png"

                metadata = {
                    "source": dataset_name,
                    "config": config_name,
                    "split": split,
                    "index": source_index,
                    "fingerprint": source_fingerprint,
                    "version": version,
                }

                if pil_image is not None:
                    image_path = media_dir / f"{sample_id}{ext}"
                if image_path is not None and not image_path.exists():
                    if save_format == "JPEG" or pil_image.mode in ("RGBA", "P", "L"):
                        pil_image = pil_image.convert("RGB")
                    pil_image.save(image_path, format=save_format)

                sample = Sample(
                    id=sample_id,
                    filepath=str(image_path) if image_path is not None else None,
                    label=label,
                    text=text,
                    modality=modality,
                    metadata=metadata,
                    media_type=(
                        _media_type_for_path(image_path)
                        if image_path is not None
                        else "text/plain"
                    ),
                )

                samples.append(sample)
                loaded += 1

                if not show_progress:
                    continue

                now = time.perf_counter()
                should_report = loaded == 1
                if total is not None and loaded == total:
                    should_report = True
                if loaded % report_every == 0:
                    should_report = True
                if now - last_report_at >= 5.0:
                    should_report = True
                if not should_report:
                    continue

                emit_progress(now)
                last_report_at = now
        finally:
            progress_stop.set()
            if heartbeat is not None:
                heartbeat.join(timeout=0.1)

        if total is None:
            total = loaded

        num_added, skipped = self.add_samples(samples, skip_existing=skip_existing)
        mapped_fields: FieldCatalog = {}
        if image_key:
            mapped_fields["filepath"] = FieldDefinition(
                type="media", nullable=not bool(image_key), source=image_key
            )
        if text_key:
            mapped_fields["text"] = FieldDefinition(
                type="text", nullable=bool(image_key), source=text_key
            )
        if label_key:
            mapped_fields["label"] = FieldDefinition(
                type="label", nullable=True, source=label_key
            )
        if mapped_fields:
            self._storage.register_fields(mapped_fields)

        if show_progress:
            print(
                f"Prepared {loaded} samples in {_format_elapsed(time.perf_counter() - started_at)}",
                flush=True,
            )
            if image_key:
                print(f"Images saved to: {media_dir}", flush=True)
            if skipped > 0:
                print(f"Skipped {skipped} existing samples", flush=True)

        return num_added, skipped

    def compute_embeddings(
        self,
        model: str,
        *,
        provider: str | None = None,
        checkpoint: str | None = None,
        batch_size: int = 32,
        sample_ids: list[str] | None = None,
        show_progress: bool = True,
        _provider_registry: Any | None = None,
        **provider_kwargs: Any,
    ) -> str:
        """Compute embeddings for samples that don't have them yet.

        Embeddings are stored in a dedicated space keyed by the embedding spec.

        Args:
            model: Model identifier (required). Use a HuggingFace model_id
                (e.g. 'openai/clip-vit-base-patch32') for embed-anything, or a
                hyper-models name (e.g. 'hycoclip-vit-s') for hyperbolic embeddings.
            provider: Explicit provider identifier. If not specified, auto-detected:
                'hyper-models' if model matches a hyper-models name, else 'embed-anything'.
                Available providers: `hyperview.embeddings.list_embedding_providers()`.
            checkpoint: Checkpoint path/URL (hf://... or local path) for weight-only models.
            batch_size: Batch size for processing.
            sample_ids: Optional subset of sample IDs to ensure embeddings for.
                If omitted, computes embeddings for all samples missing them.
            show_progress: Whether to show progress bar.
            **provider_kwargs: Additional kwargs passed to the embedding function.

        Returns:
            space_key for the embedding space.

        Raises:
            ValueError: If model is not provided.
        """
        if not model:
            raise ValueError(
                "model is required. Examples: 'openai/clip-vit-base-patch32' (CLIP), "
                "'hycoclip-vit-s' (hyperbolic). See hyperview.embeddings.list_embedding_providers()."
            )

        from hyperview.embeddings.engine import EmbeddingSpec
        from hyperview.embeddings.pipelines import compute_embeddings

        if provider is None:
            provider = "embed-anything"
            try:
                import hyper_models

                if model in hyper_models.list_models():
                    provider = "hyper-models"
            except ImportError:
                pass
        provider = _normalize_provider_slug(provider)
        spec = EmbeddingSpec(
            provider=provider,
            model_id=model,
            checkpoint=checkpoint,
            provider_kwargs=provider_kwargs,
            modality=(
                "multimodal"
                if provider in {"embed-anything", "hyper-models"}
                else "image"
            ),
        )

        space_key, _num_computed, _num_skipped = compute_embeddings(
            storage=self._storage,
            spec=spec,
            batch_size=batch_size,
            sample_ids=sample_ids,
            show_progress=show_progress,
            provider_registry=_provider_registry,
        )
        return space_key

    def compute_visualization(
        self,
        space_key: str | None = None,
        method: str = "umap",
        layout: str = DEFAULT_VISUALIZATION_LAYOUT,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        force: bool = False,
    ) -> str:
        """Compute projections for visualization.

        Args:
            space_key: Embedding space to project. If None, uses the first available.
            method: Projection method ('umap' or 'pca').
            layout: Layout spec like 'euclidean', 'euclidean:3d', or 'spherical'.
                Omitting the suffix defaults to 2D for Euclidean/Poincare and 3D for spherical.
            n_neighbors: Number of neighbors for UMAP (ignored for PCA).
            min_dist: Minimum distance for UMAP (ignored for PCA).
            metric: Distance metric for UMAP (ignored for PCA).
            force: Force recomputation even if layout exists.

        Returns:
            layout_key for the computed layout.
        """
        from hyperview.embeddings.pipelines import compute_layout

        geometry, layout_dimension = parse_visualization_layout(layout)

        return compute_layout(
            storage=self._storage,
            space_key=space_key,
            method=method,
            geometry=geometry,
            layout_dimension=layout_dimension,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric=metric,
            force=force,
            show_progress=True,
        )

    def list_spaces(self) -> list[Any]:
        """List all embedding spaces in this dataset."""
        return self._storage.list_spaces()

    @property
    def fields(self) -> FieldCatalog:
        """Typed catalog of fields available on this dataset."""
        return self._storage.get_fields()

    def list_layouts(self) -> list[LayoutRecord]:
        """List every layout in this dataset as a structured record.

        Each record carries the layout key plus the space, model, provider,
        geometry, dimension, method, params, and sample count behind it.
        """

        spaces = {space.space_key: space for space in self._storage.list_spaces()}
        return [
            LayoutRecord(layout, spaces.get(layout.space_key))
            for layout in self._storage.list_layouts()
        ]

    def find_layout(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        geometry: str | None = None,
        dimension: int | None = None,
        method: str | None = None,
    ) -> str | None:
        """Return the layout key matching every criterion given, or None.

        Layout keys carry a content hash of the embedding and projection
        parameters, so they cannot be written down ahead of time. Describe the
        layout you want instead::

            layout_key = dataset.find_layout(model="hycoclip-vit-s", geometry="poincare")

        Args:
            model: Model id the embedding space was computed with.
            provider: Embedding provider alias, e.g. ``"hyper-models"``.
            geometry: Layout geometry: ``euclidean``, ``poincare``, or ``spherical``.
            dimension: Layout dimension, 2 or 3.
            method: Projection method, e.g. ``"umap"`` or ``"pca"``.

        Returns:
            The single matching layout key, or None when nothing matches.

        Raises:
            ValueError: When more than one layout matches. The message lists
                the candidates so the caller can narrow the query.
        """

        criteria: dict[str, Any] = {
            "model": model,
            "provider": provider,
            "geometry": geometry,
            "dimension": dimension,
            "method": method,
        }
        matches = [
            record
            for record in self.list_layouts()
            if (model is None or record.model_id == model)
            and (provider is None or record.provider == provider)
            and (geometry is None or record.geometry == geometry)
            and (dimension is None or record.dimension == dimension)
            and (method is None or record.method == method)
        ]

        if not matches:
            return None
        if len(matches) == 1:
            return matches[0].key

        query = ", ".join(
            f"{name}={value!r}" for name, value in criteria.items() if value is not None
        )
        candidates = "\n  ".join(record.describe() for record in matches)
        raise ValueError(
            f"find_layout({query or 'no criteria'}) matched {len(matches)} layouts. "
            "Add criteria until one layout is left. Candidates:\n  " + candidates
        )

    def _resolve_similarity_space_key(
        self,
        *,
        space_key: str | None = None,
        layout_key: str | None = None,
    ) -> str | None:
        if layout_key is None:
            return space_key

        layout = next(
            (item for item in self.list_layouts() if item.layout_key == layout_key),
            None,
        )
        if layout is None:
            raise ValueError(f"Layout not found: {layout_key}")
        if space_key is not None and space_key != layout.space_key:
            raise ValueError("space_key does not match the requested layout_key")
        return layout.space_key

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        space_key: str | None = None,
        *,
        layout_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k most similar samples to a given sample.

        Args:
            sample_id: ID of the query sample.
            k: Number of neighbors to return.
            space_key: Embedding space to search in. If None, uses first available.
            layout_key: Visualization layout whose embedding space should be searched.

        Returns:
            List of (sample, distance) tuples, sorted by distance ascending.
        """
        resolved_space_key = self._resolve_similarity_space_key(
            space_key=space_key,
            layout_key=layout_key,
        )
        return self._storage.find_similar(sample_id, k, resolved_space_key)

    def find_similar_by_vector(
        self,
        vector: list[float],
        k: int = 10,
        space_key: str | None = None,
        *,
        layout_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k most similar samples to a given vector.

        Args:
            vector: Query vector.
            k: Number of neighbors to return.
            space_key: Embedding space to search in. If None, uses first available.
            layout_key: Visualization layout whose embedding space should be searched.

        Returns:
            List of (sample, distance) tuples, sorted by distance ascending.
        """
        resolved_space_key = self._resolve_similarity_space_key(
            space_key=space_key,
            layout_key=layout_key,
        )
        return self._storage.find_similar_by_vector(vector, k, resolved_space_key)

    def _embedding_spec_for_space(self, space_key: str) -> Any:
        from hyperview.embeddings.engine import EmbeddingSpec

        space = next(
            (item for item in self.list_spaces() if item.space_key == space_key),
            None,
        )
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        config = dict(space.config or {})
        stored_provider = str(config.get("provider") or space.provider or "unknown")
        model_id = str(space.model_id)
        if stored_provider == "unknown":
            if _is_legacy_embed_anything_model(model_id):
                provider = "embed-anything"
            else:
                raise ValueError(
                    f"Embedding space '{space_key}' has stored provider "
                    f"'{stored_provider}', and model '{model_id}' is not a recognized "
                    "legacy CLIP signature. Migrate the space metadata to set an "
                    "explicit provider before using text search."
                )
        else:
            provider = _normalize_provider_slug(stored_provider)
        checkpoint = config.get("checkpoint")
        provider_kwargs = {
            key: value
            for key, value in config.items()
            if key not in {"provider", "model_id", "checkpoint", "dim", "geometry", "modality", "params", "params_source", "spatial_dim"}
        }
        modality = config.get("modality") or ("multimodal" if provider == "embed-anything" else "image")
        return EmbeddingSpec(
            provider=provider,
            model_id=model_id,
            checkpoint=checkpoint if isinstance(checkpoint, str) else None,
            provider_kwargs=provider_kwargs,
            modality=modality,  # type: ignore[arg-type]
        )

    def find_similar_by_text(
        self,
        text: str,
        k: int = 10,
        space_key: str | None = None,
        *,
        layout_key: str | None = None,
        hybrid: bool = False,
        _provider_registry: Any | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find samples by text-vector similarity, optionally fused with FTS."""
        query = str(text or "").strip()
        if not query:
            raise ValueError("text query must be a non-empty string")

        resolved_space_key = self._resolve_similarity_space_key(
            space_key=space_key,
            layout_key=layout_key,
        )
        if resolved_space_key is None:
            raise ValueError("No embedding spaces available")

        from hyperview.embeddings.engine import get_engine

        spec = self._embedding_spec_for_space(resolved_space_key)
        vector = get_engine(provider_registry=_provider_registry).embed_texts(
            [query], spec
        )[0]
        candidate_k = max(k * 4, 20) if hybrid else k
        vector_results = self._storage.find_similar_by_text(
            query,
            candidate_k,
            resolved_space_key,
            query_vector=vector,
        )
        if not hybrid:
            return vector_results

        fts_results = self._find_text_matches(query, candidate_k)
        reciprocal_rank_constant = 60
        scores: dict[str, float] = {}
        samples_by_id: dict[str, Sample] = {}
        for ranked_results in (vector_results, fts_results):
            for rank, result in enumerate(ranked_results, start=1):
                sample = result[0] if isinstance(result, tuple) else result
                samples_by_id[sample.id] = sample
                scores[sample.id] = scores.get(sample.id, 0.0) + 1.0 / (
                    reciprocal_rank_constant + rank
                )

        ranked_ids = sorted(scores, key=lambda sample_id: (-scores[sample_id], sample_id))
        return [
            (samples_by_id[sample_id], 1.0 / scores[sample_id])
            for sample_id in ranked_ids[:k]
        ]

    def _find_text_matches(self, query: str, k: int) -> list[Sample]:
        """Rank text matches using LanceDB FTS, with a memory-backend fallback."""
        samples_table = getattr(self._storage, "_samples_table", None)
        if samples_table is not None:
            try:
                rows = (
                    samples_table.search(query, query_type="fts")
                    .select(["id"])
                    .limit(k)
                    .to_list()
                )
                samples_by_id = {
                    sample.id: sample
                    for sample in self._storage.get_samples_by_ids(
                        [str(row["id"]) for row in rows]
                    )
                }
                return [
                    samples_by_id[str(row["id"])]
                    for row in rows
                    if str(row["id"]) in samples_by_id
                ]
            except (RuntimeError, TypeError, ValueError):
                # Tiny/in-memory datasets and older LanceDB builds may not have
                # a usable FTS index yet; preserve deterministic search behavior.
                pass

        terms = [term for term in query.casefold().split() if term]
        ranked: list[tuple[Sample, int]] = []
        for sample in self.samples:
            haystack = (sample.text or "").casefold()
            score = sum(haystack.count(term) for term in terms)
            if score:
                ranked.append((sample, score))
        ranked.sort(key=lambda item: (-item[1], item[0].id))
        return [sample for sample, _score in ranked[:k]]

    def set_coords(
        self,
        geometry: str,
        ids: list[str],
        coords: np.ndarray | list[list[float]],
    ) -> str:
        """Set precomputed coordinates for visualization.

        Use this when you have precomputed projections and want to skip
        embedding computation. Useful for smoke tests or external projections.

        Args:
            geometry: "euclidean", "poincare", or "spherical".
            ids: List of sample IDs.
            coords: (N, D) array of coordinates.

        Returns:
            The layout_key for the stored coordinates.

        Example:
            >>> dataset.set_coords("euclidean", ["s0", "s1"], [[0.1, 0.2], [0.3, 0.4]])
            >>> dataset.set_coords("spherical", ["s0", "s1"], [[0.1, 0.2, 0.3], [0.3, 0.4, 0.5]])
            >>> hv.launch(dataset)
        """
        if geometry not in ("euclidean", "poincare", "spherical"):
            raise ValueError(
                f"geometry must be 'euclidean', 'poincare', or 'spherical', got '{geometry}'"
            )

        coords_arr = np.asarray(coords, dtype=np.float32)
        if coords_arr.ndim != 2 or coords_arr.shape[1] < 2:
            raise ValueError(f"coords must be (N, D) with D>=2, got shape {coords_arr.shape}")

        layout_dimension = normalize_layout_dimension(int(coords_arr.shape[1]))
        if geometry == "poincare" and layout_dimension != 2:
            raise ValueError("poincare precomputed layouts must be 2D")

        # Ensure a synthetic space exists (required by launch())
        space_key = f"precomputed_{layout_dimension}d"
        if not any(s.space_key == space_key for s in self._storage.list_spaces()):
            precomputed_config = {
                "provider": "precomputed",
                "geometry": "unknown",  # Precomputed coords don't have a source embedding geometry
            }
            self._storage.ensure_space(space_key, dim=layout_dimension, config=precomputed_config)

        layout_key = make_layout_key(
            space_key,
            method="precomputed",
            geometry=geometry,
            layout_dimension=layout_dimension,
        )

        # Ensure layout registry entry exists
        self._storage.ensure_layout(
            layout_key=layout_key,
            space_key=space_key,
            method="precomputed",
            geometry=geometry,
            params=None,
        )

        self._storage.add_layout_coords(layout_key, list(ids), coords_arr)
        return layout_key

    @property
    def samples(self) -> list[Sample]:
        """Get all samples as a list."""
        return self._storage.get_all_samples()

    @property
    def labels(self) -> list[str]:
        """Get unique labels in the dataset."""
        return self._storage.get_unique_labels()

    def filter(self, predicate: Callable[[Sample], bool]) -> list[Sample]:
        """Filter samples based on a predicate function."""
        return self._storage.filter(predicate)

    def get_samples_paginated(
        self,
        offset: int = 0,
        limit: int = 100,
        label: str | None = None,
        missing_label: bool = False,
    ) -> tuple[list[Sample], int]:
        """Get paginated samples.

        This avoids loading all samples into memory and is used by the server
        API for efficient pagination.
        """
        return self._storage.get_samples_paginated(
            offset=offset,
            limit=limit,
            label=label,
            missing_label=missing_label,
        )

    def get_samples_by_ids(self, sample_ids: list[str]) -> list[Sample]:
        """Retrieve multiple samples by ID.

        The returned list is aligned to the input order and skips missing IDs.
        """
        return self._storage.get_samples_by_ids(sample_ids)

    def get_visualization_data(
        self,
        layout_key: str,
    ) -> tuple[list[str], list[str | None], np.ndarray]:
        """Get visualization data (ids, labels, coords) for a layout."""
        layout_dimension = parse_layout_dimension(layout_key)

        layout_ids, layout_coords = self._storage.get_layout_coords(layout_key)
        if not layout_ids:
            return [], [], np.empty((0, layout_dimension), dtype=np.float32)

        labels_by_id = self._storage.get_labels_by_ids(layout_ids)

        ids: list[str] = []
        labels: list[str | None] = []
        coords: list[np.ndarray] = []

        for i, sample_id in enumerate(layout_ids):
            if sample_id in labels_by_id:
                ids.append(sample_id)
                labels.append(labels_by_id[sample_id])
                coords.append(layout_coords[i])

        if not coords:
            return [], [], np.empty((0, layout_dimension), dtype=np.float32)

        return ids, labels, np.asarray(coords, dtype=np.float32)

    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
        label_filter: str | None = None,
        missing_label_filter: bool = False,
    ) -> tuple[list[str], np.ndarray]:
        """Return candidate (id, xy) rows within an AABB for a layout."""
        return self._storage.get_lasso_candidates_aabb(
            layout_key=layout_key,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            label_filter=label_filter,
            missing_label_filter=missing_label_filter,
        )

    def save(self, filepath: str, include_thumbnails: bool = True) -> None:
        """Export dataset to a JSON file.

        Args:
            filepath: Path to save the JSON file.
            include_thumbnails: Whether to include cached thumbnails.
        """
        samples = self._storage.get_all_samples()
        if include_thumbnails:
            for s in samples:
                s.cache_thumbnail()

        data = {
            "name": self.name,
            "samples": [
                {
                    "id": s.id,
                    "filepath": s.filepath,
                    "label": s.label,
                    "text": s.text,
                    "modality": s.modality,
                    "media_type": s.media_type,
                    "duration_s": s.duration_s,
                    "metadata": s.metadata,
                    "thumbnail_base64": s.thumbnail_base64 if include_thumbnails else None,
                }
                for s in samples
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, filepath: str, persist: bool = False) -> Dataset:
        """Load dataset from a JSON file.

        Args:
            filepath: Path to the JSON file.
            persist: If True, persist the loaded data to LanceDB.
                    If False (default), keep in memory only.

        Returns:
            Dataset instance.
        """
        with open(filepath) as f:
            data = json.load(f)

        dataset = cls(name=data["name"], persist=persist)

        # Add samples
        samples = []
        for s_data in data["samples"]:
            sample = Sample(
                id=s_data["id"],
                filepath=s_data.get("filepath"),
                label=s_data.get("label"),
                text=s_data.get("text"),
                modality=s_data.get("modality", "image"),
                media_type=s_data.get("media_type"),
                duration_s=s_data.get("duration_s"),
                metadata=s_data.get("metadata", {}),
                thumbnail_base64=s_data.get("thumbnail_base64"),
            )
            samples.append(sample)

        dataset._storage.add_samples_batch(samples)
        return dataset
