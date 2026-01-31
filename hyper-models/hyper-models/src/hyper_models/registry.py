"""Model registry - maps model names to hub locations and metadata."""

from __future__ import annotations

from dataclasses import dataclass, field

from hyper_models.preprocessing import ImageConfig

__all__ = ["ModelInfo", "list_models", "get_model_info"]


@dataclass
class ModelInfo:
    """Metadata for a registered model."""

    name: str
    geometry: str  # 'hyperboloid', 'poincare', 'sphere', 'euclidean'
    dim: int
    hub_id: str
    license: str
    description: str = ""
    input_name: str = "image"
    output_name: str | None = None
    image_config: ImageConfig = field(default_factory=ImageConfig)


_MODELS: dict[str, ModelInfo] = {
    "hycoclip-vit-s": ModelInfo(
        name="hycoclip-vit-s",
        geometry="hyperboloid",
        dim=513,
        hub_id="mnm-matin/hyperbolic-clip",
        license="CC-BY-NC",
        description="HyCoCLIP ViT-Small (512D hyperboloid)",
        output_name="embedding_hyperboloid",
    ),
    "hycoclip-vit-b": ModelInfo(
        name="hycoclip-vit-b",
        geometry="hyperboloid",
        dim=513,
        hub_id="mnm-matin/hyperbolic-clip",
        license="CC-BY-NC",
        description="HyCoCLIP ViT-Base (512D hyperboloid)",
        output_name="embedding_hyperboloid",
    ),
    "meru-vit-s": ModelInfo(
        name="meru-vit-s",
        geometry="hyperboloid",
        dim=513,
        hub_id="mnm-matin/hyperbolic-clip",
        license="CC-BY-NC",
        description="MERU ViT-Small (512D hyperboloid)",
        output_name="embedding_hyperboloid",
    ),
    "meru-vit-b": ModelInfo(
        name="meru-vit-b",
        geometry="hyperboloid",
        dim=513,
        hub_id="mnm-matin/hyperbolic-clip",
        license="CC-BY-NC",
        description="MERU ViT-Base (512D hyperboloid)",
        output_name="embedding_hyperboloid",
    ),
}


def list_models(geometry: str | None = None) -> list[str]:
    """List available model names, optionally filtered by geometry."""
    if geometry is None:
        return list(_MODELS.keys())
    return [name for name, info in _MODELS.items() if info.geometry == geometry]


def get_model_info(name: str) -> ModelInfo:
    """Get metadata for a model. Raises KeyError if not found."""
    if name not in _MODELS:
        raise KeyError(f"Model '{name}' not found. Available: {', '.join(_MODELS.keys())}")
    return _MODELS[name]
