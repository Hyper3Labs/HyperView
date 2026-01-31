from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def add_repo_to_syspath(repo_root: Path) -> None:
    """Add a local clone's repo root to sys.path so `import hycoclip` works."""
    import sys

    repo_root = repo_root.expanduser().resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f"hycoclip repo root does not exist: {repo_root}")
    sys.path.insert(0, str(repo_root))


def load_image_as_chw_float01(image_path: Path, size: int = 224) -> np.ndarray:
    """Load an image and return float32 array shaped (1,3,H,W) with values in [0,1].

    Preprocessing matches the common CLIP-like pipeline:
    - Resize shortest side to `size` with bicubic
    - Center crop to (size, size)
    - Convert to float32 in [0,1]

    HyCoCLIP normalizes internally in `encode_image` using ImageNet mean/std.
    """
    image_path = image_path.expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"image does not exist: {image_path}")

    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid image size: {w}x{h} ({image_path})")

    # Resize so that shortest side == size.
    scale = float(size) / float(min(w, h))
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    img = img.resize((new_w, new_h), resample=Image.BICUBIC)

    # Center crop.
    left = int(round((new_w - size) / 2.0))
    top = int(round((new_h - size) / 2.0))
    img = img.crop((left, top, left + size, top + size))

    arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC in [0,1]
    arr = np.transpose(arr, (2, 0, 1))  # CHW
    arr = arr[None, ...]  # BCHW
    return arr


def hyperboloid_lift(space: np.ndarray, curvature: float) -> np.ndarray:
    """Lift Lorentz-model space components to full (time, space) hyperboloid vector.

    Upstream HyCoCLIP uses the convention:
      t = sqrt(1/curv + ||x||^2)
      hyper = concat([t, x])

    Args:
      space: (B, D) float array
      curvature: positive scalar (curv > 0)

    Returns:
      (B, D+1)
    """
    if curvature <= 0:
        raise ValueError(f"curvature must be > 0, got {curvature}")
    if space.ndim != 2:
        raise ValueError(f"space must be rank-2 (B,D), got shape={space.shape}")

    x2 = np.sum(space * space, axis=-1, keepdims=True)
    t = np.sqrt((1.0 / curvature) + x2)
    return np.concatenate([t, space], axis=-1)


def cosine_similarity(a: np.ndarray, b: np.ndarray, eps: float = 1e-12) -> float:
    """Cosine similarity between two 1D vectors."""
    a = np.asarray(a).reshape(-1)
    b = np.asarray(b).reshape(-1)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + eps
    return float(np.dot(a, b) / denom)

