"""HyCoCLIP ONNX embedding provider - torch-free runtime.

This provider runs an ONNX-exported HyCoCLIP/MERU image encoder with
`onnxruntime` to compute *hyperboloid (Lorentz)* embeddings.

Outputs:
- Embeddings are returned in hyperboloid format with shape (N, D+1), where the
  first coordinate is the time component.

Requirements:
- onnxruntime (already included via embed-anything)
- An exported ONNX model (and its external weights .data file) produced by
    `hyperbolic_model_zoo/hycoclip_onnx/export_onnx.py`.

Why this exists:
- Torch is required to *export* HyCoCLIP to ONNX.
- Torch is NOT required at runtime once you have the ONNX artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from hyperview.core.sample import Sample
from hyperview.embeddings.providers import (
    BaseEmbeddingProvider,
    ModelSpec,
    register_provider,
)

__all__ = ["HyCoCLIPOnnxProvider"]


# ---------------------------------------------------------------------------
# Dependency checking
# ---------------------------------------------------------------------------


def _check_onnxruntime() -> bool:
    try:
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def _require_dependencies() -> None:
    if not _check_onnxruntime():
        raise ImportError(
            "HyCoCLIP ONNX provider requires onnxruntime.\n\n"
            "It should already be installed via embed-anything.\n"
            "If not, install with: uv add onnxruntime"
        )


# ---------------------------------------------------------------------------
# Preprocessing (pure PIL+numpy)
# ---------------------------------------------------------------------------


def _preprocess_rgb_image_to_bchw_float01(img: Any, size: int = 224) -> np.ndarray:
    """Resize shortest side to 224, center crop, return (1,3,H,W) float32 in [0,1]."""
    from PIL import Image

    if not isinstance(img, Image.Image):
        raise TypeError(f"Expected PIL.Image.Image, got {type(img)}")

    w, h = img.size
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid image size: {w}x{h}")

    # Resize shortest side to `size`.
    scale = float(size) / float(min(w, h))
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    img = img.resize((new_w, new_h), resample=Image.Resampling.BICUBIC)

    # Center crop.
    left = int(round((new_w - size) / 2.0))
    top = int(round((new_h - size) / 2.0))
    img = img.crop((left, top, left + size, top + size))

    arr = np.asarray(img, dtype=np.float32) / 255.0  # HWC in [0,1]
    arr = np.transpose(arr, (2, 0, 1))  # CHW
    return arr[None, ...]  # BCHW


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class HyCoCLIPOnnxProvider(BaseEmbeddingProvider):
    """ONNX HyCoCLIP provider - torch-free runtime.

    Uses onnxruntime for inference. No PyTorch required at runtime.
    """

    def __init__(self) -> None:
        self._session: Any = None
        self._model_spec: ModelSpec | None = None
        self._input_name: str | None = None
        self._output_names: list[str] | None = None
        self._curvature: float | None = None

    @property
    def provider_id(self) -> str:
        return "hycoclip_onnx"

    def _resolve_onnx_path(self, model_spec: ModelSpec) -> Path:
        if not model_spec.checkpoint:
            raise ValueError(
                "HyCoCLIP ONNX provider requires 'checkpoint' to be a path/URL to a .onnx file."
            )

        checkpoint = model_spec.checkpoint

        # Handle HuggingFace Hub URLs (hf://repo_id#filename)
        if checkpoint.startswith("hf://"):
            raise NotImplementedError(
                "WIP: hf:// checkpoints are disabled until ONNX external weights are published. "
                "Use a local .onnx path with its .onnx.data file present."
            )

        path = Path(checkpoint).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"ONNX model not found: {path}")
        if path.suffix.lower() != ".onnx":
            raise ValueError(f"Expected a .onnx file, got: {path}")
        return path

    def _ensure_session(self, model_spec: ModelSpec) -> None:
        _require_dependencies()

        if self._session is not None and self._model_spec == model_spec:
            return

        import onnxruntime as ort

        onnx_path = self._resolve_onnx_path(model_spec)

        # Default to CPU for maximum compatibility.
        get_available = getattr(ort, "get_available_providers", None)
        available = get_available() if callable(get_available) else ["CPUExecutionProvider"]
        providers = ["CPUExecutionProvider"] if "CPUExecutionProvider" in available else list(available)

        self._session = ort.InferenceSession(str(onnx_path), providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self._output_names = [o.name for o in self._session.get_outputs()]
        self._curvature = None
        self._model_spec = model_spec

    def compute_embeddings(
        self,
        samples: list[Sample],
        model_spec: ModelSpec,
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Compute hyperboloid embeddings (t, x) with shape (N, D+1)."""
        self._ensure_session(model_spec)

        assert self._session is not None
        assert self._input_name is not None

        output_names = self._output_names or []
        if not output_names:
            raise RuntimeError("ONNX session has no outputs")

        # Prefer named outputs if present.
        emb_name = "embedding_hyperboloid" if "embedding_hyperboloid" in output_names else output_names[0]
        curv_name = "curvature" if "curvature" in output_names else None

        # NOTE: Current torch.onnx export is only reliable for batch_size=1.
        if batch_size != 1 and show_progress:
            print("HyCoCLIP-ONNX export currently runs with batch_size=1; overriding")
        batch_size = 1

        all_embeddings: list[np.ndarray] = []

        if show_progress:
            print(f"Computing HyCoCLIP-ONNX embeddings for {len(samples)} samples...")

        for i in range(0, len(samples), batch_size):
            batch_samples = samples[i : i + batch_size]

            images = []
            for sample in batch_samples:
                with sample.load_image() as img:
                    img.load()
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    bchw = _preprocess_rgb_image_to_bchw_float01(img.copy(), size=224)
                    images.append(bchw[0])  # CHW

            batch_np = np.stack(images, axis=0).astype(np.float32)

            outputs = self._session.run(
                [name for name in (emb_name, curv_name) if name is not None],
                {self._input_name: batch_np},
            )

            hyper = np.asarray(outputs[0], dtype=np.float32)
            if hyper.ndim != 2:
                raise RuntimeError(f"Expected (B,D) embeddings, got shape={hyper.shape}")

            # Capture curvature once.
            if curv_name is not None and self._curvature is None and len(outputs) > 1:
                curv_arr = np.asarray(outputs[1]).reshape(-1)
                if curv_arr.size > 0:
                    self._curvature = float(curv_arr[0])

            all_embeddings.append(hyper)

        return np.vstack(all_embeddings)

    def get_space_config(self, model_spec: ModelSpec, dim: int) -> dict[str, Any]:
        config = super().get_space_config(model_spec, dim)
        config["geometry"] = "hyperboloid"
        if self._curvature is not None:
            config["curvature"] = self._curvature
        config["spatial_dim"] = dim - 1
        return config


# Auto-register on import
register_provider("hycoclip_onnx", HyCoCLIPOnnxProvider)
