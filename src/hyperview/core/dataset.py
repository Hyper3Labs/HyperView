"""Dataset class for managing collections of samples."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
from datasets import DownloadConfig, load_dataset
from PIL import Image

from hyperview.core.sample import Sample
from hyperview.storage.backend import StorageBackend
from hyperview.storage.schema import make_layout_key


class Dataset:
    """A collection of samples with support for embeddings and visualization.

    Datasets are automatically persisted to LanceDB by default, providing:
    - Automatic persistence (no need to call save())
    - Vector similarity search
    - Efficient storage and retrieval

    Embeddings are stored separately from samples, keyed by model_id.
    Layouts (2D projections) are stored per layout_key (space + method).

    Examples:
        # Create a new dataset (auto-persisted)
        dataset = hv.Dataset("my_dataset")
        dataset.add_images_dir("/path/to/images")

        # Create an in-memory dataset (for testing)
        dataset = hv.Dataset("temp", persist=False)
    """

    def __init__(
        self,
        name: str | None = None,
        persist: bool = True,
        storage: StorageBackend | None = None,
    ):
        """Initialize a new dataset.

        Args:
            name: Optional name for the dataset.
            persist: If True (default), use LanceDB for persistence.
                    If False, use in-memory storage.
            storage: Optional custom storage backend. If provided, persist is ignored.
        """
        self.name = name or f"dataset_{uuid.uuid4().hex[:8]}"

        # Initialize storage backend
        if storage is not None:
            self._storage = storage
        elif persist:
            from hyperview.storage import LanceDBBackend, StorageConfig

            config = StorageConfig.default()
            self._storage = LanceDBBackend(self.name, config)
        else:
            from hyperview.storage import MemoryBackend
            self._storage = MemoryBackend(self.name)

    # Color palette for deterministic label color assignment
    _COLOR_PALETTE = [
        "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
        "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
        "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000",
        "#aaffc3", "#808000", "#ffd8b1", "#000075", "#808080",
    ]

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
        """Add a sample to the dataset (idempotent)."""
        self._storage.add_sample(sample)

    def _ingest_samples(
        self,
        samples: list[Sample],
        *,
        skip_existing: bool = True,
    ) -> tuple[int, int]:
        """Shared ingestion helper for batch sample insertion.

        Handles deduplication uniformly.

        Args:
            samples: List of samples to ingest.
            skip_existing: If True, skip samples that already exist in storage.

        Returns:
            Tuple of (num_added, num_skipped).
        """
        if not samples:
            return 0, 0

        skipped = 0
        if skip_existing:
            all_ids = [s.id for s in samples]
            existing_ids = self._storage.get_existing_ids(all_ids)
            if existing_ids:
                samples = [s for s in samples if s.id not in existing_ids]
                skipped = len(all_ids) - len(samples)

        if not samples:
            return 0, skipped

        self._storage.add_samples_batch(samples)

        return len(samples), skipped

    def add_image(
        self,
        filepath: str,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
        sample_id: str | None = None,
    ) -> Sample:
        """Add a single image to the dataset.

        Args:
            filepath: Path to the image file.
            label: Optional label for the image.
            metadata: Optional metadata dictionary.
            sample_id: Optional custom ID. If not provided, one will be generated.

        Returns:
            The created Sample.
        """
        if sample_id is None:
            sample_id = hashlib.md5(filepath.encode()).hexdigest()[:12]

        sample = Sample(
            id=sample_id,
            filepath=filepath,
            label=label,
            metadata=metadata or {},
        )
        self.add_sample(sample)
        return sample

    def add_images_dir(
        self,
        directory: str,
        extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp"),
        label_from_folder: bool = False,
        recursive: bool = True,
        skip_existing: bool = True,
    ) -> tuple[int, int]:
        """Add all images from a directory.

        Args:
            directory: Path to the directory containing images.
            extensions: Tuple of valid file extensions.
            label_from_folder: If True, use parent folder name as label.
            recursive: If True, search subdirectories.
            skip_existing: If True (default), skip samples that already exist.

        Returns:
            Tuple of (num_added, num_skipped).
        """
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
                )
                samples.append(sample)

        # Use shared ingestion helper
        return self._ingest_samples(samples, skip_existing=skip_existing)

    def add_from_huggingface(
        self,
        dataset_name: str,
        split: str = "train",
        image_key: str = "img",
        label_key: str | None = "fine_label",
        label_names_key: str | None = None,
        max_samples: int | None = None,
        show_progress: bool = True,
        skip_existing: bool = True,
        image_format: str = "auto",
    ) -> tuple[int, int]:
        """Load samples from a HuggingFace dataset.

        Images are downloaded to disk at ~/.hyperview/media/huggingface/{dataset}/{split}/
        This ensures images persist across sessions and embeddings can be computed
        at any time, similar to FiftyOne's approach.

        Args:
            dataset_name: Name of the HuggingFace dataset.
            split: Dataset split to use.
            image_key: Key for the image column.
            label_key: Key for the label column (can be None).
            label_names_key: Key for label names in dataset info.
            max_samples: Maximum number of samples to load.
            show_progress: Whether to print progress.
            skip_existing: If True (default), skip samples that already exist in storage.
            image_format: Image format to save: "auto" (detect from source, fallback PNG),
                         "png" (lossless), or "jpeg" (smaller files).

        Returns:
            Tuple of (num_added, num_skipped).
        """
        from hyperview.storage import StorageConfig

        # HuggingFace `load_dataset()` can be surprisingly slow even when the dataset
        # is already cached, due to Hub reachability checks in some environments.
        # For a fast path, first try loading in "offline" mode (cache-only), and
        # fall back to an online load if the dataset isn't cached yet.
        try:
            ds = cast(
                Any,
                load_dataset(
                    dataset_name,
                    split=split,
                    download_config=DownloadConfig(local_files_only=True),
                ),
            )
        except Exception:
            ds = cast(Any, load_dataset(dataset_name, split=split))

        # Get label names if available
        label_names = None
        if label_key and label_names_key:
            if label_names_key in ds.features:
                label_names = ds.features[label_names_key].names
        elif label_key:
            if hasattr(ds.features[label_key], "names"):
                label_names = ds.features[label_key].names

        # Extract dataset metadata for robust sample IDs
        config_name = getattr(ds.info, "config_name", None) or "default"
        fingerprint = ds._fingerprint[:8] if hasattr(ds, "_fingerprint") and ds._fingerprint else "unknown"
        version = str(ds.info.version) if ds.info.version else None

        # Get media directory for this dataset
        config = StorageConfig.default()
        media_dir = config.get_huggingface_media_dir(dataset_name, split)

        samples = []
        total = len(ds) if max_samples is None else min(len(ds), max_samples)

        if show_progress:
            print(f"Loading {total} samples from {dataset_name}...")

        iterator = range(total)

        for i in iterator:
            item = ds[i]
            image = item[image_key]

            # Handle PIL Image or numpy array
            if isinstance(image, Image.Image):
                pil_image = image
            else:
                pil_image = Image.fromarray(np.asarray(image))

            # Get label
            label = None
            if label_key and label_key in item:
                label_idx = item[label_key]
                if label_names and isinstance(label_idx, int):
                    label = label_names[label_idx]
                else:
                    label = str(label_idx)

            # Generate robust sample ID with config and fingerprint
            safe_name = dataset_name.replace("/", "_")
            sample_id = f"{safe_name}_{config_name}_{fingerprint}_{split}_{i}"

            # Determine image format and extension
            if image_format == "auto":
                # Try to preserve original format, fallback to PNG
                original_format = getattr(pil_image, "format", None)
                if original_format in ("JPEG", "JPG"):
                    save_format = "JPEG"
                    ext = ".jpg"
                else:
                    save_format = "PNG"
                    ext = ".png"
            elif image_format == "jpeg":
                save_format = "JPEG"
                ext = ".jpg"
            else:
                save_format = "PNG"
                ext = ".png"

            # Enhanced metadata with dataset info
            metadata = {
                "source": dataset_name,
                "config": config_name,
                "split": split,
                "index": i,
                "fingerprint": ds._fingerprint if hasattr(ds, "_fingerprint") else None,
                "version": version,
            }

            image_path = media_dir / f"{sample_id}{ext}"
            if not image_path.exists():
                if save_format == "JPEG" or pil_image.mode in ("RGBA", "P", "L"):
                    pil_image = pil_image.convert("RGB")
                pil_image.save(image_path, format=save_format)

            sample = Sample(
                id=sample_id,
                filepath=str(image_path),
                label=label,
                metadata=metadata,
            )

            samples.append(sample)

        # Use shared ingestion helper
        num_added, skipped = self._ingest_samples(samples, skip_existing=skip_existing)

        if show_progress:
            print(f"Images saved to: {media_dir}")
            if skipped > 0:
                print(f"Skipped {skipped} existing samples")

        return num_added, skipped

    def compute_embeddings(
        self,
        model: str,
        *,
        provider: str | None = None,
        checkpoint: str | None = None,
        batch_size: int = 32,
        show_progress: bool = True,
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
        spec = EmbeddingSpec(
            provider=provider,
            model_id=model,
            checkpoint=checkpoint,
            provider_kwargs=provider_kwargs,
        )

        space_key, _num_computed, _num_skipped = compute_embeddings(
            storage=self._storage,
            spec=spec,
            batch_size=batch_size,
            show_progress=show_progress,
        )
        return space_key

    def compute_visualization(
        self,
        space_key: str | None = None,
        method: str = "umap",
        geometry: str = "euclidean",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        force: bool = False,
    ) -> str:
        """Compute 2D projections for visualization.

        Args:
            space_key: Embedding space to project. If None, uses the first available.
            method: Projection method ('umap' supported).
            geometry: Output geometry type ('euclidean' or 'poincare').
            n_neighbors: Number of neighbors for UMAP.
            min_dist: Minimum distance for UMAP.
            metric: Distance metric for UMAP.
            force: Force recomputation even if layout exists.

        Returns:
            layout_key for the computed layout.
        """
        from hyperview.embeddings.pipelines import compute_layout

        return compute_layout(
            storage=self._storage,
            space_key=space_key,
            method=method,
            geometry=geometry,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric=metric,
            force=force,
            show_progress=True,
        )

    def list_spaces(self) -> list[Any]:
        """List all embedding spaces in this dataset."""
        return self._storage.list_spaces()

    def list_layouts(self) -> list[Any]:
        """List all layouts in this dataset (returns LayoutInfo objects)."""
        return self._storage.list_layouts()

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k most similar samples to a given sample.

        Args:
            sample_id: ID of the query sample.
            k: Number of neighbors to return.
            space_key: Embedding space to search in. If None, uses first available.

        Returns:
            List of (sample, distance) tuples, sorted by distance ascending.
        """
        return self._storage.find_similar(sample_id, k, space_key)

    def find_similar_by_vector(
        self,
        vector: list[float],
        k: int = 10,
        space_key: str | None = None,
    ) -> list[tuple[Sample, float]]:
        """Find k most similar samples to a given vector.

        Args:
            vector: Query vector.
            k: Number of neighbors to return.
            space_key: Embedding space to search in. If None, uses first available.

        Returns:
            List of (sample, distance) tuples, sorted by distance ascending.
        """
        return self._storage.find_similar_by_vector(vector, k, space_key)

    @staticmethod
    def _compute_label_color(label: str, palette: list[str]) -> str:
        """Compute a deterministic color for a label."""
        digest = hashlib.md5(label.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % len(palette)
        return palette[idx]

    def get_label_colors(self) -> dict[str, str]:
        """Get the color mapping for labels (computed deterministically)."""
        labels = self._storage.get_unique_labels()
        return {label: self._compute_label_color(label, self._COLOR_PALETTE) for label in labels}

    def set_coords(
        self,
        geometry: str,
        ids: list[str],
        coords: np.ndarray | list[list[float]],
    ) -> str:
        """Set precomputed 2D coordinates for visualization.

        Use this when you have precomputed 2D projections and want to skip
        embedding computation. Useful for smoke tests or external projections.

        Args:
            geometry: "euclidean" or "poincare".
            ids: List of sample IDs.
            coords: (N, 2) array of coordinates.

        Returns:
            The layout_key for the stored coordinates.

        Example:
            >>> dataset.set_coords("euclidean", ["s0", "s1"], [[0.1, 0.2], [0.3, 0.4]])
            >>> dataset.set_coords("poincare", ["s0", "s1"], [[0.1, 0.2], [0.3, 0.4]])
            >>> hv.launch(dataset)
        """
        if geometry not in ("euclidean", "poincare"):
            raise ValueError(f"geometry must be 'euclidean' or 'poincare', got '{geometry}'")

        coords_arr = np.asarray(coords, dtype=np.float32)
        if coords_arr.ndim != 2 or coords_arr.shape[1] != 2:
            raise ValueError(f"coords must be (N, 2), got shape {coords_arr.shape}")

        # Ensure a synthetic space exists (required by launch())
        space_key = "precomputed"
        if not any(s.space_key == space_key for s in self._storage.list_spaces()):
            precomputed_config = {
                "provider": "precomputed",
                "geometry": "unknown",  # Precomputed coords don't have a source embedding geometry
            }
            self._storage.ensure_space(space_key, dim=2, config=precomputed_config)

        layout_key = make_layout_key(space_key, method="precomputed", geometry=geometry)

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
    ) -> tuple[list[Sample], int]:
        """Get paginated samples.

        This avoids loading all samples into memory and is used by the server
        API for efficient pagination.
        """
        return self._storage.get_samples_paginated(offset=offset, limit=limit, label=label)

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
        layout_ids, layout_coords = self._storage.get_layout_coords(layout_key)
        if not layout_ids:
            return [], [], np.empty((0, 2), dtype=np.float32)

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
            return [], [], np.empty((0, 2), dtype=np.float32)

        return ids, labels, np.asarray(coords, dtype=np.float32)


    def get_lasso_candidates_aabb(
        self,
        *,
        layout_key: str,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> tuple[list[str], np.ndarray]:
        """Return candidate (id, xy) rows within an AABB for a layout."""
        return self._storage.get_lasso_candidates_aabb(
            layout_key=layout_key,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
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
                    "metadata": s.metadata,
                    "thumbnail_base64": s.thumbnail_base64 if include_thumbnails else None,
                }
                for s in samples
            ],
        }
        with open(filepath, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, filepath: str, persist: bool = False) -> "Dataset":
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
                filepath=s_data["filepath"],
                label=s_data.get("label"),
                metadata=s_data.get("metadata", {}),
                thumbnail_base64=s_data.get("thumbnail_base64"),
            )
            samples.append(sample)

        dataset._storage.add_samples_batch(samples)
        return dataset
