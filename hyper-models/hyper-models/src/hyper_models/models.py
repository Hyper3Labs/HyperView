"""ONNX model wrapper for hyper-models."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from hyper_models.preprocessing import ImageConfig, preprocess_images

__all__ = ["ONNXModel"]


class ONNXModel:
    """ONNX Runtime model wrapper for embedding inference."""

    def __init__(
        self,
        path: Path,
        geometry: str,
        dim: int,
        *,
        input_name: str = "image",
        output_name: str | None = None,
        image_config: ImageConfig | None = None,
    ) -> None:
        self._path = path
        self.geometry = geometry
        self.dim = dim
        self._input_name = input_name
        self._output_name = output_name
        self._image_config = image_config or ImageConfig()
        self._session = None

    def _ensure_session(self) -> None:
        if self._session is None:
            import onnxruntime as ort

            self._session = ort.InferenceSession(str(self._path), providers=["CPUExecutionProvider"])

    def encode(self, inputs: np.ndarray) -> np.ndarray:
        """Encode preprocessed inputs (B, C, H, W) to embeddings (B, D)."""
        self._ensure_session()
        outputs = self._session.run(None, {self._input_name: inputs})

        if self._output_name:
            output_names = [o.name for o in self._session.get_outputs()]
            return np.asarray(outputs[output_names.index(self._output_name)], dtype=np.float32)

        return np.asarray(outputs[0], dtype=np.float32)

    def encode_images(self, images: list[Image.Image]) -> np.ndarray:
        """Encode PIL images to embeddings (B, D)."""
        return self.encode(preprocess_images(images, self._image_config))
