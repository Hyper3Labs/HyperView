"""Compatibility helpers for optional third-party runtime behavior."""

from __future__ import annotations

import sys


def disable_blocked_datasets_torch_shared_memory() -> None:
    """Keep HF streaming datasets usable when torch shared memory is sandboxed."""

    if "datasets" not in sys.modules:
        return
    try:
        from datasets import config as datasets_config
    except Exception:
        return
    if not getattr(datasets_config, "TORCH_AVAILABLE", False):
        return
    try:
        import torch

        torch.tensor(0).share_memory_()
    except RuntimeError as exc:
        if "torch_shm_manager" in str(exc) or "share" in str(exc).lower():
            datasets_config.TORCH_AVAILABLE = False
    except Exception:
        return
