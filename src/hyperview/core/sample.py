"""Sample class representing a single data point in a dataset."""

import base64
import io
from pathlib import Path
from typing import Any

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
    width: int | None = Field(default=None, description="Image width in pixels")
    height: int | None = Field(default=None, description="Image height in pixels")

    model_config = {"arbitrary_types_allowed": True}

    @property
    def filename(self) -> str:
        """Get the filename from the filepath."""
        return Path(self.filepath).name

    def load_image(self) -> Image.Image:
        """Load the image from disk."""
        return Image.open(self.filepath)

    def get_thumbnail(self, size: tuple[int, int] = (128, 128)) -> Image.Image:
        """Get a thumbnail of the image. Also captures original dimensions."""
        img = self.load_image()
        # Capture original dimensions while we have the image loaded
        if self.width is None or self.height is None:
            self.width, self.height = img.size
        img.thumbnail(size, Image.Resampling.LANCZOS)
        return img

    def _encode_thumbnail(self, size: tuple[int, int] = (128, 128)) -> str:
        """Encode thumbnail as base64 JPEG."""
        thumb = self.get_thumbnail(size)
        if thumb.mode in ("RGBA", "P"):
            thumb = thumb.convert("RGB")
        buffer = io.BytesIO()
        thumb.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def get_thumbnail_base64(self, size: tuple[int, int] = (128, 128)) -> str:
        """Get thumbnail as base64 encoded string."""
        return self.thumbnail_base64 or self._encode_thumbnail(size)

    def cache_thumbnail(self, size: tuple[int, int] = (128, 128)) -> None:
        """Cache the thumbnail as base64 for persistence."""
        if self.thumbnail_base64 is None:
            self.thumbnail_base64 = self._encode_thumbnail(size)

    def to_api_dict(self, include_thumbnail: bool = True) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        # Ensure dimensions are populated (loads image if needed but not cached)
        if self.width is None or self.height is None:
            self.ensure_dimensions()

        data = {
            "id": self.id,
            "filepath": self.filepath,
            "filename": self.filename,
            "label": self.label,
            "metadata": self.metadata,
            "width": self.width,
            "height": self.height,
        }
        if include_thumbnail:
            data["thumbnail"] = self.get_thumbnail_base64()
        return data

    def ensure_dimensions(self) -> None:
        """Load image dimensions if not already set."""
        if self.width is None or self.height is None:
            try:
                img = self.load_image()
                self.width, self.height = img.size
            except Exception:
                # If image can't be loaded, leave as None
                pass



