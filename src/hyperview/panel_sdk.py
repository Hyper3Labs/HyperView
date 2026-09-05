"""The panel SDK contract the shipped HyperView shell exposes to extension panels."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SURFACE_PATH = Path(__file__).with_name("panel_sdk_surface.json")


@lru_cache(maxsize=1)
def _surface() -> dict[str, Any]:
    try:
        payload = json.loads(SURFACE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:  # pragma: no cover - packaging failure
        raise RuntimeError(
            "This HyperView installation is missing panel_sdk_surface.json; "
            "the wheel was built without the panel SDK contract."
        ) from exc
    return payload


def panel_sdk_surface() -> dict[str, Any]:
    """What `window.HyperViewPanelSDK` offers a panel module in this release.

    Returns ``{"version": str, "keys": [str], "hooks": [str],
    "components": [str], "constants": [str]}``: the SDK major version a panel
    must assert, the top-level keys of the global, the hook names available
    under ``sdk.hooks``, the React components available under
    ``sdk.components``, and the shared literals under ``sdk.constants``. Panel
    linters should read this rather than keep their own copy, which is how a
    checker ends up rejecting a hook the shell has shipped for two releases.
    """

    surface = _surface()
    return {
        "version": str(surface["version"]),
        "keys": list(surface["keys"]),
        "hooks": list(surface["hooks"]),
        "components": list(surface.get("components", [])),
        "constants": list(surface.get("constants", [])),
    }
