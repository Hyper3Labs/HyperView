from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import hyperview

ROOT = Path(__file__).resolve().parents[1]
SDK_SOURCE = ROOT / "frontend" / "src" / "panel-sdk" / "index.tsx"
EMITTER = ROOT / "scripts" / "emit_panel_sdk_surface.py"


def _emitter():
    spec = importlib.util.spec_from_file_location("emit_panel_sdk_surface", EMITTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_packaged_surface_matches_the_installed_sdk_global() -> None:
    """The packaged contract is what the shell actually installs, not a copy of it.

    Panel linters read `hyperview.panel_sdk_surface()`; a stale file makes them
    reject hooks the shell ships or bless hooks it dropped.
    """

    assert hyperview.panel_sdk_surface() == _emitter().read_panel_sdk_surface(SDK_SOURCE)


def test_surface_lists_every_hook_the_sdk_global_installs() -> None:
    source = SDK_SOURCE.read_text(encoding="utf-8")
    hooks_block = re.search(r"\n  hooks: \{(.*?)\n  \};", source, re.DOTALL)
    assert hooks_block is not None, "the SDK global's hook type declarations moved"
    declared = set(re.findall(r"^\s{4}(\w+): typeof \w+;", hooks_block.group(1), re.MULTILINE))
    components_block = re.search(r"\n  components: \{(.*?)\n  \};", source, re.DOTALL)
    assert components_block is not None, "the SDK global's component declarations moved"
    declared_components = set(
        re.findall(r"^\s{4}(\w+): typeof \w+;", components_block.group(1), re.MULTILINE)
    )

    surface = hyperview.panel_sdk_surface()

    assert surface["version"] == "2"
    assert declared, "the SDK global's hook type declarations moved"
    assert declared <= set(surface["hooks"])
    assert "useSupportsSampleSimilarity" in surface["hooks"]
    assert declared_components == set(surface["components"])
    assert "Panel" in surface["components"]
    assert set(surface["keys"]) == {"React", "components", "createClient", "hooks", "version"}
