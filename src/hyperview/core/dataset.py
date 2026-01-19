"""Dataset class for managing collections of samples."""

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import numpy as np
from datasets import load_dataset
from PIL import Image

from hyperview.core.sample import Sample, SampleFromArray
from hyperview.storage.backend import StorageBackend
from hyperview.storage.schema import make_layout_key, make_space_key


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

        # Open an existing dataset
        dataset = hv.Dataset.open("my_dataset")

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
        self._embedding_computer = None
        self._projection_engine = None

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

        # Initialize label colors from storage
        self._sync_label_colors()

    def _sync_label_colors(self) -> None:
        """Sync label colors from storage and assign colors to new labels."""
        # Get existing colors from storage
        existing_colors = self._storage.label_colors

        # Get all unique labels
        all_labels = self._storage.get_unique_labels()

        # Assign colors to any labels without colors
        for label in all_labels:
            if label not in existing_colors:
                self._assign_label_color(label, existing_colors)

        # Save back if we added new colors
        if existing_colors != self._storage.label_colors:
            self._storage.label_colors = existing_colors

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
        """Add a sample to the dataset."""
        self._storage.add_sample(sample)

        # Assign color to label if needed
        if sample.label:
            colors = self._storage.label_colors
            if sample.label not in colors:
                self._assign_label_color(sample.label, colors)
                self._storage.label_colors = colors

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
    ) -> int:
        """Add all images from a directory.

        Args:
            directory: Path to the directory containing images.
            extensions: Tuple of valid file extensions.
            label_from_folder: If True, use parent folder name as label.
            recursive: If True, search subdirectories.

        Returns:
            Number of images added.
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

                # Track label colors
                if label:
                    colors = self._storage.label_colors
                    if label not in colors:
                        self._assign_label_color(label, colors)
                        self._storage.label_colors = colors

        # Batch add for efficiency
        self._storage.add_samples_batch(samples)
        return len(samples)

    def add_from_huggingface(
        self,
        dataset_name: str,
        split: str = "train",
        image_key: str = "img",
        label_key: str | None = "fine_label",
        label_names_key: str | None = None,
        max_samples: int | None = None,
        download_images: bool = True,
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
            download_images: If True (default), download images to local disk.
                            If False, use in-memory storage (won't persist).
            show_progress: Whether to show progress bar.
            skip_existing: If True (default), skip samples that already exist in storage.
                          If False, allow duplicate samples (not recommended).
            image_format: Image format to save: "auto" (detect from source, fallback PNG),
                         "png" (lossless), or "jpeg" (smaller files).

        Returns:
            Tuple of (num_added, num_skipped).
        """
        from hyperview.storage import StorageConfig

        try:
            from tqdm import tqdm
        except ImportError:
            tqdm = None

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
        colors = self._storage.label_colors

        # Setup progress bar
        if show_progress and tqdm is not None:
            iterator = tqdm(range(total), desc=f"Loading {dataset_name}")
        else:
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

            if download_images:
                # Save image to disk (FiftyOne pattern)
                image_path = media_dir / f"{sample_id}{ext}"
                if not image_path.exists():
                    # Convert to RGB if necessary (for JPEG or non-RGB images)
                    if save_format == "JPEG" or pil_image.mode in ("RGBA", "P", "L"):
                        pil_image = pil_image.convert("RGB")
                    pil_image.save(image_path, format=save_format)

                sample = Sample(
                    id=sample_id,
                    filepath=str(image_path),
                    label=label,
                    metadata=metadata,
                )
            else:
                # Use in-memory storage (legacy behavior, won't persist)
                image_array = np.array(pil_image)
                sample = SampleFromArray.from_array(
                    id=sample_id,
                    image_array=image_array,
                    label=label,
                    metadata=metadata,
                )

            samples.append(sample)

            # Track label colors
            if label and label not in colors:
                self._assign_label_color(label, colors)

        # Check for existing samples and skip duplicates
        skipped = 0
        if skip_existing and samples:
            all_ids = [s.id for s in samples]
            existing_ids = self._storage.get_existing_ids(all_ids)
            if existing_ids:
                samples = [s for s in samples if s.id not in existing_ids]
                skipped = len(all_ids) - len(samples)

        # Batch add for efficiency
        if samples:
            self._storage.add_samples_batch(samples)
        self._storage.label_colors = colors

        if download_images and show_progress:
            print(f"Images saved to: {media_dir}")
            if skipped > 0:
                print(f"Skipped {skipped} existing samples")

        return len(samples), skipped

    def compute_embeddings(
        self,
        model: str = "openai/clip-vit-base-patch32",
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> str:
        """Compute embeddings for samples that don't have them yet.

        Embeddings are stored in a dedicated space keyed by model_id.

        Args:
            model: EmbedAnything HuggingFace `model_id` to use.
            batch_size: Batch size for processing.
            show_progress: Whether to show progress bar.

        Returns:
            space_key for the embedding space.
        """
        from hyperview.embeddings.compute import EmbeddingComputer

        if self._embedding_computer is None or self._embedding_computer.model_id != model:
            self._embedding_computer = EmbeddingComputer(model=model)

        # Get embedding dimension from a test computation
        all_samples = self._storage.get_all_samples()
        if not all_samples:
            raise ValueError("No samples in dataset")

        # Compute one embedding to get dimension
        test_embedding = self._embedding_computer.compute_single(all_samples[0])
        dim = len(test_embedding)

        # Ensure space exists
        space_key = make_space_key(model)
        self._storage.ensure_space(model, dim)

        # Find samples needing embeddings
        missing_ids = self._storage.get_missing_embedding_ids(space_key)

        if not missing_ids:
            if show_progress:
                print(f"All {len(all_samples)} samples already have embeddings in space '{space_key}'")
            return space_key

        samples_needing_embeddings = self._storage.get_samples_by_ids(missing_ids)

        if show_progress:
            skipped = len(all_samples) - len(samples_needing_embeddings)
            if skipped > 0:
                print(f"Skipped {skipped} samples with existing embeddings")

        embeddings = self._embedding_computer.compute_batch(
            samples_needing_embeddings, batch_size=batch_size, show_progress=show_progress
        )

        # Store embeddings
        ids = [s.id for s in samples_needing_embeddings]
        vectors = np.array(embeddings, dtype=np.float32)
        self._storage.add_embeddings(space_key, ids, vectors)

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
            geometry: Geometry type ('euclidean' or 'poincare').
            n_neighbors: Number of neighbors for UMAP.
            min_dist: Minimum distance for UMAP.
            metric: Distance metric for UMAP.
            force: Force recomputation even if layout exists.

        Returns:
            layout_key for the computed layout.
        """
        from hyperview.embeddings.projection import ProjectionEngine

        if geometry not in ("euclidean", "poincare"):
            raise ValueError(f"Invalid geometry: {geometry}. Must be 'euclidean' or 'poincare'.")

        if self._projection_engine is None:
            self._projection_engine = ProjectionEngine()

        # Get space
        if space_key is None:
            spaces = self._storage.list_spaces()
            if not spaces:
                raise ValueError("No embedding spaces. Call compute_embeddings() first.")
            space_key = spaces[0].space_key

        space = self._storage.get_space(space_key)
        if space is None:
            raise ValueError(f"Space not found: {space_key}")

        # Get all embeddings from this space
        ids, vectors = self._storage.get_embeddings(space_key)
        if len(ids) == 0:
            raise ValueError(f"No embeddings in space '{space_key}'. Call compute_embeddings() first.")

        # Generate layout key (includes geometry)
        layout_key = make_layout_key(space_key, method, geometry)

        # Check if layout exists
        if not force and layout_key in self._storage.list_layouts():
            existing_ids, _ = self._storage.get_layout_coords(layout_key)
            if set(existing_ids) == set(ids):
                print(f"Layout '{layout_key}' already exists with {len(ids)} points")
                return layout_key
            else:
                print(f"Layout exists but has different samples, recomputing...")

        if len(ids) < 3:
            raise ValueError(f"Need at least 3 samples for visualization, have {len(ids)}")

        print(f"Computing {geometry} {method} layout for {len(ids)} samples...")

        # Compute projection based on geometry
        if geometry == "poincare":
            coords = self._projection_engine.project_to_poincare(
                vectors,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric=metric,
            )
        else:
            coords = self._projection_engine.project_umap(
                vectors,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric=metric,
            )

        # Store layout
        self._storage.add_layout_coords(layout_key, ids, coords)

        return layout_key

    def list_spaces(self) -> list[Any]:
        """List all embedding spaces in this dataset."""
        return self._storage.list_spaces()

    def list_layouts(self) -> list[str]:
        """List all layouts in this dataset."""
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

    def _assign_label_color(self, label: str, colors: dict[str, str]) -> None:
        """Assign a color to a label."""
        color_palette = [
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
            "#911eb4", "#46f0f0", "#f032e6", "#bcf60c", "#fabebe",
            "#008080", "#e6beff", "#9a6324", "#fffac8", "#800000",
            "#aaffc3", "#808000", "#ffd8b1", "#000075", "#808080",
        ]
        idx = len(colors) % len(color_palette)
        colors[label] = color_palette[idx]

    def get_label_colors(self) -> dict[str, str]:
        """Get the color mapping for labels."""
        return self._storage.label_colors.copy()

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
            self._storage.ensure_space(space_key, dim=2)

        layout_key = make_layout_key(space_key, method="precomputed", geometry=geometry)
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

    def to_dict(self) -> dict[str, Any]:
        """Convert dataset to dictionary for serialization."""
        return {
            "name": self.name,
            "num_samples": len(self),
            "labels": self.labels,
            "label_colors": self._storage.label_colors,
        }

    def save(self, filepath: str, include_thumbnails: bool = True) -> None:
        """Export dataset to a JSON file.

        Note: For persistent datasets (default), data is automatically saved.
        This method is for exporting to JSON format for sharing or backup.

        Args:
            filepath: Path to save the JSON file.
            include_thumbnails: Whether to include cached thumbnails.
        """
        samples = self._storage.get_all_samples()

        # Cache thumbnails before saving if requested
        if include_thumbnails:
            for s in samples:
                s.cache_thumbnail()

        data = {
            "name": self.name,
            "label_colors": self._storage.label_colors,
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

        # Set label colors
        label_colors = data.get("label_colors", {})
        dataset._storage.label_colors = label_colors

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

    @classmethod
    def open(cls, name: str) -> "Dataset":
        """Open an existing persistent dataset.

        Args:
            name: Name of the dataset to open.

        Returns:
            Dataset instance connected to existing data.

        Raises:
            ValueError: If dataset does not exist.
        """
        from hyperview.storage import LanceDBBackend

        if not LanceDBBackend.dataset_exists(name):
            raise ValueError(
                f"Dataset '{name}' does not exist. "
                f"Available datasets: {cls.list_datasets()}"
            )

        return cls(name=name, persist=True)

    @classmethod
    def list_datasets(cls) -> list[str]:
        """List all available persistent datasets.

        Returns:
            List of dataset names.
        """
        from hyperview.storage import LanceDBBackend

        return LanceDBBackend.list_datasets()

    @classmethod
    def delete(cls, name: str, delete_media: bool = False) -> bool:
        """Delete a persistent dataset.

        Args:
            name: Name of the dataset to delete.
            delete_media: If True, also delete associated media files from disk.
                         Default is False (safe, preserves media files).

        Returns:
            True if dataset was deleted, False if it didn't exist.
        """
        import os

        from hyperview.storage import LanceDBBackend

        if delete_media:
            try:
                dataset = cls.open(name)
            except Exception:
                dataset = None

            if dataset is not None:
                for fp in (s.filepath for s in dataset.samples):
                    if os.path.exists(fp):
                        try:
                            os.remove(fp)
                        except OSError:
                            continue

        return LanceDBBackend.delete_dataset(name)

    @classmethod
    def cleanup_orphaned_media(
        cls,
        delete: bool = False,
    ) -> tuple[int, list[str]]:
        """Find media files not referenced by any dataset.

        Scans the media directory for image files and checks if they are
        referenced by any existing dataset. Useful for cleaning up disk space
        after deleting datasets without the delete_media=True flag.

        Args:
            delete: If True, actually delete the orphaned files.
                   If False (default), just report them.

        Returns:
            Tuple of (count, list_of_orphaned_paths).
        """
        import os

        from hyperview.storage import StorageConfig

        config = StorageConfig.default()
        media_dir = config.media_dir

        if not media_dir.exists():
            return 0, []

        # Get all filepaths from all datasets
        referenced: set[str] = set()
        for dataset_name in cls.list_datasets():
            try:
                ds = cls.open(dataset_name)
                referenced.update(s.filepath for s in ds.samples)
            except Exception:
                continue

        # Find orphaned files (images not referenced by any dataset)
        orphaned: list[str] = []
        image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

        for img_path in media_dir.rglob("*"):
            if img_path.is_file() and img_path.suffix.lower() in image_extensions:
                if str(img_path) not in referenced:
                    orphaned.append(str(img_path))

        # Optionally delete orphaned files
        if delete:
            for path in orphaned:
                try:
                    os.remove(path)
                except OSError:
                    continue

        return len(orphaned), orphaned

    @classmethod
    def exists(cls, name: str) -> bool:
        """Check if a persistent dataset exists.

        Args:
            name: Name of the dataset to check.

        Returns:
            True if dataset exists.
        """
        from hyperview.storage import LanceDBBackend

        return LanceDBBackend.dataset_exists(name)
