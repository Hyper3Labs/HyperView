"""HyperView - Open-source dataset curation with hyperbolic embeddings visualization."""

from . import _version as _version
from ._compat import (
    disable_blocked_datasets_torch_shared_memory as _disable_blocked_datasets_torch_shared_memory,
)

# Aliased on import so it does not read as part of the 1.0 public surface. It is
# an internal startup workaround, not something callers should depend on.
_disable_blocked_datasets_torch_shared_memory()

from . import api as _api  # noqa: E402
from . import ui as ui  # noqa: E402
from .core import Sample as Sample  # noqa: E402

Dataset = _api.Dataset
Session = _api.Session
launch = _api.launch
export_workspace = _api.export_workspace
restore_workspace = _api.restore_workspace
register_provider = _api.register_provider
unregister_provider = _api.unregister_provider
__version__ = _version.__version__

__all__ = [
    "Dataset",
    "Session",
    "Sample",
    "launch",
    "export_workspace",
    "restore_workspace",
    "register_provider",
    "unregister_provider",
    "ui",
    "__version__",
]
