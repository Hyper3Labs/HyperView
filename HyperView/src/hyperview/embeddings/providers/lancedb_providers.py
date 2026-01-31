"""LanceDB-registered embedding providers for HyperView.

This module registers HyperView's embedding providers into the LanceDB embedding
registry using the @register decorator.

Providers:
- embed-anything: CLIP-based image embeddings (torch-free, default)
- hyper-models: Non-Euclidean model zoo via `hyper-models` (torch-free ONNX; downloads from HF Hub)
"""

from __future__ import annotations

from typing import Any

import numpy as np
from lancedb.embeddings import EmbeddingFunction, register
from pydantic import PrivateAttr

__all__ = [
    "EmbedAnythingEmbeddings",
    "HyperModelsEmbeddings",
]


@register("embed-anything")
class EmbedAnythingEmbeddings(EmbeddingFunction):
    """CLIP-based image embeddings via embed-anything.

    This is the default provider for HyperView - lightweight and torch-free.

    Args:
        name: HuggingFace model ID for CLIP (default: openai/clip-vit-base-patch32)
        batch_size: Batch size for processing
    """

    name: str = "openai/clip-vit-base-patch32"
    batch_size: int = 32

    _computer: Any = PrivateAttr(default=None)
    _ndims: int | None = PrivateAttr(default=None)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._computer = None
        self._ndims = None

    def _get_computer(self) -> Any:
        if self._computer is None:
            from hyperview.embeddings.compute import EmbeddingComputer

            self._computer = EmbeddingComputer(model=self.name)
        return self._computer

    def ndims(self) -> int:
        if self._ndims is None:
            if "large" in self.name.lower():
                self._ndims = 768
            elif "clip" in self.name.lower():
                self._ndims = 512
            else:
                self._ndims = 512
        return self._ndims

    def compute_source_embeddings(
        self, inputs: Any, *args: Any, **kwargs: Any
    ) -> list[np.ndarray | None]:
        from hyperview.core.sample import Sample

        computer = self._get_computer()

        samples: list[Any] = []
        for inp in self.sanitize_input(inputs):
            if isinstance(inp, Sample):
                samples.append(inp)
            elif isinstance(inp, str):
                samples.append(Sample(id=inp, filepath=inp))
            else:
                raise TypeError(f"Unsupported input type: {type(inp)}")

        embeddings = computer.compute_batch(samples, batch_size=self.batch_size, show_progress=False)
        return list(embeddings)

    def compute_query_embeddings(
        self, query: Any, *args: Any, **kwargs: Any
    ) -> list[np.ndarray | None]:
        return self.compute_source_embeddings([query], *args, **kwargs)


@register("hyper-models")
class HyperModelsEmbeddings(EmbeddingFunction):
    """Non-Euclidean embeddings via the `hyper-models` package.

    This provider is a thin wrapper around `hyper_models.load(...)`.
    Models are downloaded from the Hugging Face Hub on first use.

    Args:
        name: Model name in the hyper-models registry (e.g. 'hycoclip-vit-s').
        checkpoint: Optional local path to an ONNX file (skips hub download).
        batch_size: Batch size hint. Current HyCoCLIP/MERU ONNX exports may only
            support batch_size=1; HyperView encodes one image at a time for
            maximum compatibility.
    """

    name: str = "hycoclip-vit-s"
    checkpoint: str | None = None
    batch_size: int = 1

    _model: Any = PrivateAttr(default=None)
    _model_info: Any = PrivateAttr(default=None)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model = None
        self._model_info = None

    def _ensure_model_info(self) -> None:
        if self._model_info is not None:
            return

        try:
            import hyper_models
        except ImportError as e:
            raise ImportError(
                "Provider 'hyper-models' requires the 'hyper-models' package. "
                "Install it with: `uv pip install hyper-models`"
            ) from e

        try:
            self._model_info = hyper_models.get_model_info(self.name)
        except KeyError:
            available = ", ".join(sorted(hyper_models.list_models()))
            raise ValueError(
                f"Unknown hyper-models model: '{self.name}'. Available: {available}"
            ) from None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return

        self._ensure_model_info()
        import hyper_models

        self._model = hyper_models.load(self.name, local_path=self.checkpoint)

    def ndims(self) -> int:
        self._ensure_model_info()
        assert self._model_info is not None
        return int(getattr(self._model_info, "dim"))

    @property
    def geometry(self) -> str:
        self._ensure_model_info()
        assert self._model_info is not None
        return str(getattr(self._model_info, "geometry"))

    def compute_source_embeddings(
        self, inputs: Any, *args: Any, **kwargs: Any
    ) -> list[np.ndarray | None]:
        from hyperview.core.sample import Sample

        self._ensure_model()
        assert self._model is not None

        inputs = self.sanitize_input(inputs)
        all_embeddings: list[np.ndarray | None] = []

        from PIL import Image

        for inp in inputs:
            if isinstance(inp, Sample):
                with inp.load_image() as img:
                    img.load()
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    pil_img = img.copy()
            elif isinstance(inp, str):
                with Image.open(inp) as img:
                    img.load()
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    pil_img = img.copy()
            elif isinstance(inp, Image.Image):
                pil_img = inp.convert("RGB") if inp.mode != "RGB" else inp
            else:
                raise TypeError(f"Unsupported input type: {type(inp)}")

            emb = self._model.encode_images([pil_img])
            vec = np.asarray(emb[0], dtype=np.float32)
            all_embeddings.append(vec)

        return all_embeddings

    def compute_query_embeddings(
        self, query: Any, *args: Any, **kwargs: Any
    ) -> list[np.ndarray | None]:
        return self.compute_source_embeddings([query], *args, **kwargs)
