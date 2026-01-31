"""Model loading - download from Hub and instantiate."""

from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download

from hyper_models.models import ONNXModel
from hyper_models.registry import get_model_info

__all__ = ["load"]


def load(name: str, *, local_path: str | Path | None = None) -> ONNXModel:
    """Load a model by name.

    Args:
        name: Model name (e.g., 'hycoclip-vit-s').
        local_path: Optional local ONNX path (skips Hub download).

    Returns:
        Model instance ready for inference.

    Example:
        >>> model = hyper_models.load("hycoclip-vit-s")
        >>> embeddings = model.encode_images([Image.open("photo.jpg")])
    """
    info = get_model_info(name)

    if local_path is None:
        hub_path = f"{info.name}/model.onnx"
        local_dir = snapshot_download(info.hub_id, allow_patterns=[f"{hub_path}*"])
        local_path = Path(local_dir) / hub_path
    else:
        local_path = Path(local_path)

    return ONNXModel(
        path=Path(local_path),
        geometry=info.geometry,
        dim=info.dim,
        input_name=info.input_name,
        output_name=info.output_name,
        image_config=info.image_config,
    )
