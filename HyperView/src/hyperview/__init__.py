"""HyperView - Open-source dataset curation with hyperbolic embeddings visualization."""

from . import _version as _version
from . import api as _api

Dataset = _api.Dataset
launch = _api.launch
__version__ = _version.__version__

__all__ = [
    "Dataset",
    "launch",
    "__version__",
]
