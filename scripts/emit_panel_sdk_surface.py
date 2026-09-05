#!/usr/bin/env python3
"""Emit the panel SDK surface the frontend installs, for packaging.

`installHyperViewPanelSdkGlobal` in frontend/src/panel-sdk/index.tsx is the only
authority on what an extension panel may reach through `window.HyperViewPanelSDK`.
Anything that validates panels against that contract -- the hyperview-spaces
conformance checker, most of all -- used to hand-copy the hook list and drift
from it silently. This script writes the list into the Python package so
`hyperview.panel_sdk_surface()` can serve it to those checkers.

Run it after changing the SDK global:

    python scripts/emit_panel_sdk_surface.py

tests/test_panel_sdk_surface.py fails when the committed JSON is stale.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SDK_SOURCE = ROOT / "frontend" / "src" / "panel-sdk" / "index.tsx"
SURFACE_PATH = ROOT / "src" / "hyperview" / "panel_sdk_surface.json"

_INSTALL_BLOCK = re.compile(
    r"window\.HyperViewPanelSDK\s*=\s*\{(?P<body>.*?)\n\s*\};",
    re.DOTALL,
)
_HOOKS_BLOCK = re.compile(r"\n(?P<indent>\s*)hooks:\s*\{(?P<body>.*?)\n(?P=indent)\},", re.DOTALL)
_COMPONENTS_BLOCK = re.compile(
    r"\n(?P<indent>\s*)components:\s*\{(?P<body>.*?)\n(?P=indent)\},", re.DOTALL
)
_CONSTANTS_BLOCK = re.compile(
    r"\n(?P<indent>\s*)constants:\s*\{(?P<body>.*?)\n(?P=indent)\},", re.DOTALL
)
_VERSION = re.compile(r"""version:\s*["'](?P<version>[^"']+)["']""")


def _entry_names(body: str) -> list[str]:
    """The property names of one object literal, ignoring nested objects."""

    names: list[str] = []
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth == 0:
            match = re.match(r"([A-Za-z_$][\w$]*)\s*[:,]", stripped)
            if match:
                names.append(match.group(1))
        depth += stripped.count("{") - stripped.count("}")
    return names


def read_panel_sdk_surface(source: Path = SDK_SOURCE) -> dict[str, Any]:
    """Parse the SDK global the frontend installs into a JSON-ready payload."""

    text = source.read_text(encoding="utf-8")
    install = _INSTALL_BLOCK.search(text)
    if install is None:
        raise SystemExit(f"{source}: could not find the window.HyperViewPanelSDK assignment")
    body = install.group("body")

    version = _VERSION.search(body)
    if version is None:
        raise SystemExit(f"{source}: the SDK global does not declare a version")

    hooks = _HOOKS_BLOCK.search(body)
    if hooks is None:
        raise SystemExit(f"{source}: the SDK global does not declare a hooks object")

    hook_names = sorted(set(_entry_names(hooks.group("body"))))
    if not hook_names:
        raise SystemExit(f"{source}: the SDK global exposes no hooks")

    components = _COMPONENTS_BLOCK.search(body)
    component_names = sorted(set(_entry_names(components.group("body")))) if components else []

    constants = _CONSTANTS_BLOCK.search(body)
    constant_names = sorted(set(_entry_names(constants.group("body")))) if constants else []

    remainder = body.replace(hooks.group(0), "\n")
    if components is not None:
        remainder = remainder.replace(components.group(0), "\n")
    if constants is not None:
        remainder = remainder.replace(constants.group(0), "\n")
    keys = sorted(
        set(_entry_names(remainder))
        | {"hooks"}
        | ({"components"} if components else set())
        | ({"constants"} if constants else set())
    )
    return {
        "version": version.group("version"),
        "keys": keys,
        "hooks": hook_names,
        "components": component_names,
        "constants": constant_names,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail instead of writing when the committed surface is stale",
    )
    args = parser.parse_args(argv)

    surface = read_panel_sdk_surface()
    payload = json.dumps(surface, indent=2, sort_keys=True) + "\n"
    if args.check:
        current = SURFACE_PATH.read_text(encoding="utf-8") if SURFACE_PATH.is_file() else ""
        if current != payload:
            print(f"{SURFACE_PATH} is stale; run python scripts/emit_panel_sdk_surface.py")
            return 1
        print(f"{SURFACE_PATH} is up to date")
        return 0

    SURFACE_PATH.write_text(payload, encoding="utf-8")
    print(f"wrote {SURFACE_PATH} (SDK v{surface['version']}, {len(surface['hooks'])} hooks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
