"""hyper-models: A model zoo for non-Euclidean embedding models.

Hyperbolic, spherical, and product manifold models with torch-free ONNX inference.

Example:
    >>> import hyper_models
    >>> model = hyper_models.load("hycoclip-vit-s")
    >>> embeddings = model.encode_images([Image.open("photo.jpg")])
    >>> model.geometry  # 'hyperboloid'
    >>> model.dim       # 513
"""

from hyper_models.loader import load
from hyper_models.registry import ModelInfo, get_model_info, list_models
from hyper_models.models import ONNXModel
from hyper_models.preprocessing import ImageConfig, preprocess_images

__all__ = [
    "load",
    "list_models",
    "get_model_info",
    "ModelInfo",
    "ONNXModel",
    "ImageConfig",
    "preprocess_images",
]
__version__ = "0.1.0"

