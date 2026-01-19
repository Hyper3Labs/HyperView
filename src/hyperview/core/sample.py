"""Sample class representing a single data point in a dataset."""

import base64
import io
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field


class Sample(BaseModel):
    """A single sample in a HyperView dataset.

    Samples are pure metadata containers. Embeddings and layouts are stored
    separately in dedicated tables (per embedding space / per layout).
    """

    id: str = Field(..., description="Unique identifier for the sample")
    filepath: str = Field(..., description="Path to the image file")
    label: str | None = Field(default=None, description="Label for the sample")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    thumbnail_base64: str | None = Field(default=None, description="Cached thumbnail as base64")

    model_config = {"arbitrary_types_allowed": True}

    @property
    def filename(self) -> str:
        """Get the filename from the filepath."""
        return Path(self.filepath).name

    def load_image(self) -> Image.Image:
        """Load the image from disk."""
        return Image.open(self.filepath)

    def get_thumbnail(self, size: tuple[int, int] = (128, 128)) -> Image.Image:
        """Get a thumbnail of the image."""
        img = self.load_image()
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return img

    def get_thumbnail_base64(self, size: tuple[int, int] = (128, 128)) -> str:
        """Get thumbnail as base64 encoded string."""
        # Return cached thumbnail if available
        if self.thumbnail_base64:
            return self.thumbnail_base64

        thumb = self.get_thumbnail(size)
        # Convert to RGB if necessary (for PNG with alpha)
        if thumb.mode in ("RGBA", "P"):
            thumb = thumb.convert("RGB")
        buffer = io.BytesIO()
        thumb.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def cache_thumbnail(self, size: tuple[int, int] = (128, 128)) -> None:
        """Cache the thumbnail as base64 for persistence."""
        if self.thumbnail_base64 is None:
            thumb = self.get_thumbnail(size)
            if thumb.mode in ("RGBA", "P"):
                thumb = thumb.convert("RGB")
            buffer = io.BytesIO()
            thumb.save(buffer, format="JPEG", quality=85)
            self.thumbnail_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    def to_api_dict(self, include_thumbnail: bool = True) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        data = {
            "id": self.id,
            "filepath": self.filepath,
            "filename": self.filename,
            "label": self.label,
            "metadata": self.metadata,
        }
        if include_thumbnail:
            data["thumbnail"] = self.get_thumbnail_base64()
        return data


class SampleFromArray(Sample):
    """A sample created from a numpy array (e.g., from HuggingFace datasets)."""

    _image_array: np.ndarray | None = None

    @classmethod
    def from_array(
        cls,
        id: str,
        image_array: np.ndarray,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "SampleFromArray":
        """Create a sample from a numpy array."""
        sample = cls(
            id=id,
            filepath=f"memory://{id}",
            label=label,
            metadata=metadata or {},
        )
        sample._image_array = image_array
        return sample

    def load_image(self) -> Image.Image:
        """Load the image from the array."""
        if self._image_array is not None:
            return Image.fromarray(self._image_array)
        return super().load_image()
