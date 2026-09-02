from __future__ import annotations

import re
from pathlib import Path

import pytest

from hyperview.extensions import ExtensionManifest
from hyperview.runtime import CustomPanelSpec, PanelStateEntry, WorkspaceUiState

ROOT = Path(__file__).resolve().parents[1]
PANEL_SDK_SOURCE = ROOT / "frontend" / "src" / "panel-sdk" / "index.tsx"
REFERENCE_PANEL_SOURCE = ROOT / "src" / "hyperview" / "shipped_extensions" / "reference" / "panel.jsx"


def test_v2_sdk_exposes_generic_similarity_hook_to_extensions() -> None:
    sdk_source = PANEL_SDK_SOURCE.read_text(encoding="utf-8")

    assert "useSimilarSamples: typeof useSimilarSamples;" in sdk_source
    assert re.search(r"hooks:\s*\{[\s\S]*?useSimilarSamples,", sdk_source)


def test_custom_panel_snapshot_carries_state_only_in_panel_state_map() -> None:
    ui = WorkspaceUiState(
        custom_panels=[CustomPanelSpec(id="summary", title="Summary")],
        panels={
            "summary": PanelStateEntry(
                state={"collapsed": True},
                state_revision=3,
            )
        },
    )

    payload = ui.to_dict()

    assert payload["custom_panels"][0]["state_revision"] == 3
    assert "state" not in payload["custom_panels"][0]
    assert payload["panels"]["summary"] == {
        "state": {"collapsed": True},
        "state_revision": 3,
    }


def test_custom_panel_kind_is_normalized_and_unknown_values_fail_clearly() -> None:
    scatter = CustomPanelSpec.from_dict(
        {"id": "map", "title": "Map", "kind": "scatter"}
    )
    extension = CustomPanelSpec.from_dict(
        {"id": "summary", "title": "Summary", "kind": "extension"}
    )

    assert scatter.kind == "builtin"
    assert scatter.builtin_panel == "scatter"
    assert scatter.source == "shipped"
    assert scatter.renderer == "native:scatter"
    assert extension.kind == "module"

    with pytest.raises(
        ValueError,
        match="Unsupported panel kind 'iframe'; expected 'builtin' or 'module'",
    ):
        CustomPanelSpec.from_dict(
            {"id": "legacy", "title": "Legacy", "kind": "iframe"}
        )


def test_extension_panel_definitions_do_not_publish_lifecycle(tmp_path: Path) -> None:
    extension_dir = tmp_path / "lifecycle-free"
    extension_dir.mkdir()
    (extension_dir / "extension.toml").write_text(
        """
name = "lifecycle-free"

[[panels]]
id = "summary"
title = "Summary"
file = "panel.jsx"

[panels.lifecycle]
mount = "unused"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = ExtensionManifest.load(extension_dir)
    definition = manifest.panels[0].to_definition(manifest.name).to_dict()

    assert "lifecycle" not in definition


def test_shipped_reference_panel_uses_only_hooks_exported_by_v2_sdk() -> None:
    panel_source = REFERENCE_PANEL_SOURCE.read_text(encoding="utf-8")
    sdk_source = PANEL_SDK_SOURCE.read_text(encoding="utf-8")

    assert 'sdk.version !== "2"' in panel_source
    assert "usePanelSelection" not in panel_source
    assert "usePanelRuntimeState" not in panel_source

    hook_match = re.search(r"const \{ ([^}]+) \} = hooks;", panel_source)
    assert hook_match is not None
    used_hooks = {hook.strip() for hook in hook_match.group(1).split(",")}
    for hook in used_hooks:
        assert f"export function {hook}(" in sdk_source


def test_v2_sdk_publishes_the_panel_chrome_the_builtins_use() -> None:
    sdk_source = PANEL_SDK_SOURCE.read_text(encoding="utf-8")

    shared_components = (
        "Panel",
        "PanelHeader",
        "PanelToolbar",
        "PanelToolbarButton",
        "PanelToolbarIconButton",
    )
    declaration = re.search(r"components:\s*\{([\s\S]*?)\};", sdk_source)
    installed = re.search(r"components:\s*\{([\s\S]*?)\},\n    hooks:", sdk_source)

    assert declaration is not None, "HyperViewPanelSdkGlobal must declare components"
    assert installed is not None, "installHyperViewPanelSdkGlobal must install components"
    for component in shared_components:
        assert f"{component}: typeof {component};" in declaration.group(1)
        assert re.search(rf"(?m)^\s*{component},\s*$", installed.group(1))


def test_shipped_reference_panel_uses_only_components_exported_by_v2_sdk() -> None:
    panel_source = REFERENCE_PANEL_SOURCE.read_text(encoding="utf-8")
    sdk_source = PANEL_SDK_SOURCE.read_text(encoding="utf-8")

    component_match = re.search(r"const \{ ([^}]+) \} = components;", panel_source)
    assert component_match is not None, "the reference panel should demonstrate the component kit"

    declaration = re.search(r"components:\s*\{([\s\S]*?)\};", sdk_source)
    assert declaration is not None
    for component in (name.strip() for name in component_match.group(1).split(",")):
        assert f"{component}: typeof {component};" in declaration.group(1)
