"""Storage configuration for HyperView."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def get_default_database_dir() -> Path:
    """Get the default database directory.

    Uses HYPERVIEW_DATABASE_DIR env var if set, otherwise ~/.hyperview/datasets/
    """
    env_dir = os.environ.get("HYPERVIEW_DATABASE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".hyperview" / "datasets"


def get_default_media_dir() -> Path:
    """Get the default media directory for downloaded images.

    Uses HYPERVIEW_MEDIA_DIR env var if set, otherwise ~/.hyperview/media/
    Similar to FiftyOne's ~/fiftyone/huggingface/hub/ pattern.
    """
    env_dir = os.environ.get("HYPERVIEW_MEDIA_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".hyperview" / "media"


@dataclass
class StorageConfig:
    """Configuration for storage backend."""

    database_dir: Path = field(default_factory=get_default_database_dir)
    media_dir: Path = field(default_factory=get_default_media_dir)
    embedding_dim: int = 512  # Default CLIP dimension
    embedding_2d_dim: int = 2

    @classmethod
    def default(cls, embedding_dim: int = 512) -> "StorageConfig":
        """Create a default configuration with optional custom embedding dimension."""
        return cls(
            database_dir=get_default_database_dir(),
            media_dir=get_default_media_dir(),
            embedding_dim=embedding_dim,
        )

    def ensure_dir_exists(self) -> None:
        """Ensure the database directory exists."""
        self.database_dir.mkdir(parents=True, exist_ok=True)

    def ensure_media_dir_exists(self) -> None:
        """Ensure the media directory exists."""
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def get_huggingface_media_dir(self, dataset_name: str, split: str) -> Path:
        """Get the directory for storing HuggingFace dataset media.

        Creates: ~/.hyperview/media/huggingface/{dataset_name}/{split}/

        Args:
            dataset_name: Name of the HuggingFace dataset (e.g., "cifar100")
            split: Dataset split (e.g., "train", "test")

        Returns:
            Path to the media directory for this dataset/split.
        """
        # Sanitize dataset name for filesystem (replace / with _)
        safe_name = dataset_name.replace("/", "_")
        media_path = self.media_dir / "huggingface" / safe_name / split
        media_path.mkdir(parents=True, exist_ok=True)
        return media_path
