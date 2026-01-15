"""Dataset class for managing collections of samples."""

import hashlib
import json
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
from datasets import load_dataset
from PIL import Image

from hyperview.core.sample import Sample, SampleFromArray
from hyperview.storage.backend import StorageBackend


class Dataset:
    """A collection of samples with support for embeddings and visualization.

    Datasets are automatically persisted to LanceDB by default, providing:
    - Automatic persistence (no need to call save())
    - Vector similarity search
    - Efficient storage and retrieval

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
        embedding_dim: int = 512,
    ):
        """Initialize a new dataset.

        Args:
            name: Optional name for the dataset.
            persist: If True (default), use LanceDB for persistence.
                    If False, use in-memory storage.
            storage: Optional custom storage backend. If provided, persist is ignored.
            embedding_dim: Dimension of embeddings (default 512 for CLIP).
        """
        self.name = name or f"dataset_{uuid.uuid4().hex[:8]}"
        self._embedding_dim = embedding_dim
        self._embedding_computer = None
        self._projection_engine = None

        # Initialize storage backend
        if storage is not None:
            self._storage = storage
        elif persist:
            from hyperview.storage import LanceDBBackend, StorageConfig

            config = StorageConfig.default(embedding_dim=embedding_dim)
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
        directory = Path(directory)
        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        samples = []
        pattern = "**/*" if recursive else "*"

        for path in directory.glob(pattern):
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

        ds = load_dataset(dataset_name, split=split)

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
                pil_image = Image.fromarray(image)

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
        model: str = "clip",
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> None:
        """Compute embeddings for samples that don't have them yet.

        Args:
            model: Embedding model to use.
            batch_size: Batch size for processing.
            show_progress: Whether to show progress bar.
        """
        from hyperview.embeddings.compute import EmbeddingComputer

        if self._embedding_computer is None:
            self._embedding_computer = EmbeddingComputer(model=model)

        all_samples = self._storage.get_all_samples()
        # Only compute for samples without embeddings
        samples_needing_embeddings = [s for s in all_samples if s.embedding is None]

        if not samples_needing_embeddings:
            if show_progress:
                print(f"All {len(all_samples)} samples already have embeddings")
            return

        if show_progress:
            skipped = len(all_samples) - len(samples_needing_embeddings)
            if skipped > 0:
                print(f"Skipped {skipped} samples with existing embeddings")

        embeddings = self._embedding_computer.compute_batch(
            samples_needing_embeddings, batch_size=batch_size, show_progress=show_progress
        )

        # Update samples with embeddings
        for sample, embedding in zip(samples_needing_embeddings, embeddings):
            sample.embedding = embedding.tolist()

        # Batch update in storage
        self._storage.update_samples_batch(samples_needing_embeddings)

    def compute_visualization(
        self,
        method: str = "umap",
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        metric: str = "cosine",
        force: bool = False,
    ) -> None:
        """Compute 2D projections for visualization.

        Args:
            method: Projection method ('umap' supported).
            n_neighbors: Number of neighbors for UMAP.
            min_dist: Minimum distance for UMAP.
            metric: Distance metric for UMAP.
            force: Force recomputation even if projections exist.
        """
        from hyperview.embeddings.projection import ProjectionEngine

        if self._projection_engine is None:
            self._projection_engine = ProjectionEngine()

        samples_with_embeddings = [s for s in self._storage if s.embedding is not None]
        if not samples_with_embeddings:
            raise ValueError("No embeddings computed. Call compute_embeddings() first.")

        # Check if projections already exist (unless forced)
        if not force:
            samples_needing_projection = [
                s for s in samples_with_embeddings if s.embedding_2d is None
            ]
            if not samples_needing_projection:
                print(f"All {len(samples_with_embeddings)} samples already have projections")
                return
            # UMAP needs consistent projections, so if any samples need it, recompute all
            # (can't mix old and new UMAP projections)
            if len(samples_needing_projection) < len(samples_with_embeddings):
                print(
                    f"Some samples missing projections - recomputing all "
                    f"({len(samples_needing_projection)} new, "
                    f"{len(samples_with_embeddings) - len(samples_needing_projection)} existing)"
                )

        samples = samples_with_embeddings
        embeddings = np.array([s.embedding for s in samples])

        # Compute Euclidean 2D projection
        coords_euclidean = self._projection_engine.project_umap(
            embeddings,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            metric=metric,
        )

        # Compute Hyperbolic (Poincaré) 2D projection
        coords_hyperbolic = self._projection_engine.project_to_poincare(
            embeddings,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
        )

        for sample, coord_e, coord_h in zip(samples, coords_euclidean, coords_hyperbolic):
            sample.embedding_2d = coord_e.tolist()
            sample.embedding_2d_hyperbolic = coord_h.tolist()

        # Batch update in storage
        self._storage.update_samples_batch(samples)

    def find_similar(
        self,
        sample_id: str,
        k: int = 10,
        use_hyperbolic: bool = False,
    ) -> list[tuple[Sample, float]]:
        """Find k most similar samples to a given sample.

        Args:
            sample_id: ID of the query sample.
            k: Number of neighbors to return.
            use_hyperbolic: If True, search in hyperbolic embedding space.
                           If False (default), search in high-dimensional embedding space.

        Returns:
            List of (sample, distance) tuples, sorted by distance ascending.
        """
        vector_column = "embedding_2d_hyperbolic" if use_hyperbolic else "embedding"
        return self._storage.find_similar(sample_id, k, vector_column)

    def find_similar_by_vector(
        self,
        vector: list[float],
        k: int = 10,
        use_hyperbolic: bool = False,
    ) -> list[tuple[Sample, float]]:
        """Find k most similar samples to a given vector.

        Args:
            vector: Query vector.
            k: Number of neighbors to return.
            use_hyperbolic: If True, search in hyperbolic embedding space.

        Returns:
            List of (sample, distance) tuples, sorted by distance ascending.
        """
        vector_column = "embedding_2d_hyperbolic" if use_hyperbolic else "embedding"
        return self._storage.find_similar_by_vector(vector, k, vector_column)

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
                    "embedding": s.embedding,
                    "embedding_2d": s.embedding_2d,
                    "embedding_2d_hyperbolic": s.embedding_2d_hyperbolic,
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
                embedding=s_data.get("embedding"),
                embedding_2d=s_data.get("embedding_2d"),
                embedding_2d_hyperbolic=s_data.get("embedding_2d_hyperbolic"),
                thumbnail_base64=s_data.get("thumbnail_base64"),
            )
            samples.append(sample)

        dataset._storage.add_samples_batch(samples)
        return dataset

    @classmethod
    def open(cls, name: str, embedding_dim: int = 512) -> "Dataset":
        """Open an existing persistent dataset.

        Args:
            name: Name of the dataset to open.
            embedding_dim: Embedding dimension (must match original).

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

        return cls(name=name, persist=True, embedding_dim=embedding_dim)

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
