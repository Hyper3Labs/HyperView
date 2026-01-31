"""Image preprocessing for ONNX inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from PIL import Image

__all__ = ["preprocess_images", "ImageConfig"]

_RESAMPLE = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


@dataclass(frozen=True)
class ImageConfig:
    """Image preprocessing configuration (CLIP-style defaults)."""

    size: int = 224
    interpolation: Literal["nearest", "bilinear", "bicubic", "lanczos"] = "bicubic"
    rescale: float = 1.0 / 255.0
    mean: tuple[float, float, float] | None = None
    std: tuple[float, float, float] | None = None


def preprocess_images(images: list[Image.Image], config: ImageConfig | None = None) -> np.ndarray:
    """Preprocess PIL images for ONNX inference.

    Args:
        images: List of PIL Images.
        config: Preprocessing config. Uses CLIP defaults if None.

    Returns:
        (B, 3, H, H) float32 array.
    """
    config = config or ImageConfig()
    resample = _RESAMPLE[config.interpolation]

    batch = []
    for img in images:
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize shortest side, then center crop
        w, h = img.size
        scale = config.size / min(w, h)
        img = img.resize((int(round(w * scale)), int(round(h * scale))), resample=resample)

        w, h = img.size
        left, top = (w - config.size) // 2, (h - config.size) // 2
        img = img.crop((left, top, left + config.size, top + config.size))

        # To float32 CHW
        arr = np.asarray(img, dtype=np.float32) * config.rescale
        arr = np.transpose(arr, (2, 0, 1))

        if config.mean is not None and config.std is not None:
            mean = np.array(config.mean, dtype=np.float32).reshape(3, 1, 1)
            std = np.array(config.std, dtype=np.float32).reshape(3, 1, 1)
            arr = (arr - mean) / std

        batch.append(arr)

    return np.stack(batch, axis=0)
