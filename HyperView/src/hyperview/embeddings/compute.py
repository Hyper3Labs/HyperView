"""Image embedding computation via EmbedAnything."""

import os
import tempfile
from pathlib import Path

import numpy as np
from embed_anything import EmbeddingModel
from PIL import Image

from hyperview.core.sample import Sample


class EmbeddingComputer:
    """Compute embeddings for image samples using EmbedAnything."""

    def __init__(self, model: str):
        """Initialize the embedding computer.

        Args:
            model: HuggingFace model ID to load via EmbedAnything.
        """
        if not model or not model.strip():
            raise ValueError("model must be a non-empty HuggingFace model_id")

        self.model_id = model
        self._model: EmbeddingModel | None = None

    def _get_model(self) -> EmbeddingModel:
        """Lazily initialize the EmbedAnything model."""
        if self._model is None:
            self._model = EmbeddingModel.from_pretrained_hf(model_id=self.model_id)
        return self._model

    def _load_rgb_image(self, sample: Sample) -> Image.Image:
        """Load an image and normalize it to RGB.

        For file-backed samples, returns an in-memory copy and closes the file
        handle immediately to avoid leaking descriptors during batch processing.
        """
        with sample.load_image() as img:
            img.load()
            if img.mode != "RGB":
                return img.convert("RGB")
            return img.copy()

    def _embed_file(self, file_path: str) -> np.ndarray:
        model = self._get_model()
        result = model.embed_file(file_path)

        if not result:
            raise RuntimeError(f"EmbedAnything returned no embeddings for: {file_path}")
        if len(result) != 1:
            raise RuntimeError(
                f"Expected 1 embedding for an image file, got {len(result)}: {file_path}"
            )

        return np.asarray(result[0].embedding, dtype=np.float32)

    def _embed_pil_image(self, image: Image.Image) -> np.ndarray:
        temp_fd, temp_path = tempfile.mkstemp(suffix=".png")
        os.close(temp_fd)
        try:
            image.save(temp_path, format="PNG")
            return self._embed_file(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def compute_single(self, sample: Sample) -> np.ndarray:
        """Compute embedding for a single sample."""
        image = self._load_rgb_image(sample)
        return self._embed_pil_image(image)

    def compute_batch(
        self,
        samples: list[Sample],
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> list[np.ndarray]:
        """Compute embeddings for a list of samples."""
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        self._get_model()

        if show_progress:
            print(f"Computing embeddings for {len(samples)} samples...")

        return [self.compute_single(sample) for sample in samples]

