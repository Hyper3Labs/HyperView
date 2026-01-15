"""Embedding computation using EmbedAnything."""

import os
import tempfile

import embed_anything
import numpy as np
from embed_anything import EmbeddingModel, WhichModel
from PIL import Image

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from hyperview.core.sample import Sample


class EmbeddingComputer:
    """Compute embeddings for images using EmbedAnything."""

    def __init__(self, model: str = "clip"):
        """Initialize the embedding computer.

        Args:
            model: Model to use for embeddings.
        """
        self.model_name = model
        self._model = None
        self._initialized = False

    def _init_model(self) -> None:
        """Lazily initialize the model."""
        if self._initialized:
            return
        # Use CLIP model by default
        self._model = EmbeddingModel.from_pretrained_hf(
            WhichModel.Clip,
            model_id="openai/clip-vit-base-patch32",
        )
        self._embed_anything = embed_anything
        self._initialized = True

    def _load_rgb_image(self, sample: Sample) -> Image.Image:
        """Load an image and ensure it is in RGB mode."""
        image = sample.load_image()
        if image.mode != "RGB":
            image = image.convert("RGB")
        return image

    def _embed_with_model(
        self,
        sample: Sample,
        image: Image.Image | None = None,
    ) -> np.ndarray | None:
        """Attempt to embed a sample via embed_anything, handling memory-backed files."""
        path = sample.filepath
        temp_path: str | None = None

        try:
            if path.startswith("memory://"):
                if image is None:
                    image = self._load_rgb_image(sample)
                temp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                image.save(temp_file, format="PNG")
                temp_file.close()
                temp_path = temp_file.name
                path = temp_path

            result = self._embed_anything.embed_file(path, embedder=self._model)
            if result:
                return np.array(result[0].embedding, dtype=np.float32)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        return None

    def compute_single(self, sample: Sample) -> np.ndarray:
        """Compute embedding for a single sample.

        Args:
            sample: Sample to compute embedding for.

        Returns:
            Embedding as numpy array.
        """
        self._init_model()

        pil_image = None
        if sample.filepath.startswith("memory://"):
            pil_image = self._load_rgb_image(sample)

        embedding = self._embed_with_model(sample, image=pil_image)
        if embedding is None:
            raise RuntimeError(f"Failed to compute embedding for sample {sample.id}")

        return embedding

    def compute_batch(
        self,
        samples: list[Sample],
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> list[np.ndarray]:
        """Compute embeddings for a batch of samples.

        Args:
            samples: List of samples to compute embeddings for.
            batch_size: Number of samples to process at once.
            show_progress: Whether to show a progress bar.

        Returns:
            List of embeddings as numpy arrays.
        """
        self._init_model()

        embeddings = []
        total = len(samples)

        if show_progress and tqdm is not None:
            iterator = tqdm(range(0, total, batch_size), desc="Computing embeddings")
        else:
            if show_progress and tqdm is None:
                print(f"Computing embeddings for {total} samples...")
            iterator = range(0, total, batch_size)

        for i in iterator:
            batch = samples[i : i + batch_size]
            batch_embeddings = []

            for sample in batch:
                pil_image = None
                if sample.filepath.startswith("memory://"):
                    pil_image = self._load_rgb_image(sample)

                embedding = self._embed_with_model(sample, image=pil_image)
                if embedding is None:
                    raise RuntimeError(
                        f"Failed to compute embedding for sample {sample.id}"
                    )

                batch_embeddings.append(embedding)

            embeddings.extend(batch_embeddings)

        return embeddings

