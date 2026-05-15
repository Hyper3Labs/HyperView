from __future__ import annotations

from pathlib import Path

from hyperview.runtime import HyperViewRuntime, LayoutViewState, WorkspaceRegistry


def test_runtime_persists_layout_views(tmp_path: Path, monkeypatch) -> None:
    workspace_registry_path = tmp_path / "workspaces.json"
    provider_registry_path = tmp_path / "providers.json"
    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    runtime = HyperViewRuntime()
    camera = {
        "yaw": 0.9,
        "pitch": 0.4,
        "distance": 3.2,
        "target_x": 0.0,
        "target_y": 0.0,
        "target_z": 0.0,
        "ortho_scale": 1.45,
    }
    version_before = runtime.version
    workspace = runtime.set_layout_view(
        "default",
        "demo__spherical__umap__3d",
        LayoutViewState(camera_3d=camera),
    )

    assert runtime.version == version_before
    assert workspace.ui.layout_views["demo__spherical__umap__3d"].camera_3d == camera

    reloaded = WorkspaceRegistry()
    restored = reloaded.get("default")
    assert restored is not None
    assert restored.ui.layout_views["demo__spherical__umap__3d"].camera_3d == camera


def test_runtime_clears_layout_views_when_dataset_changes(tmp_path: Path, monkeypatch) -> None:
    workspace_registry_path = tmp_path / "workspaces.json"
    provider_registry_path = tmp_path / "providers.json"
    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    runtime = HyperViewRuntime()
    runtime.set_workspace_dataset("default", "first")
    runtime.set_layout_view(
        "default",
        "demo__spherical__umap__3d",
        LayoutViewState(
            camera_3d={
                "yaw": 0.9,
                "pitch": 0.4,
                "distance": 3.2,
                "target_x": 0.0,
                "target_y": 0.0,
                "target_z": 0.0,
                "ortho_scale": 1.45,
            }
        ),
    )

    workspace = runtime.set_workspace_dataset("default", "second")
    assert workspace.ui.layout_views == {}
