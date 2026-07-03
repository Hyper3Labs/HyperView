from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from hyperview import Dataset
from hyperview.cli import main
from hyperview.core.sample import Sample
from hyperview.figures import FigureExportResult, FigureRenderOptions
from hyperview.runtime import LayoutViewState, WorkspaceState


class LocalProviderFixture:
    pass


class FigureRuntimeFixture:
    def __init__(self, dataset: Dataset):
        self.dataset = dataset
        self.workspace = WorkspaceState(id="default", dataset_name=dataset.name)
        self.workspace.ui.active_layout_key = dataset.list_layouts()[0].layout_key
        self.workspace.ui.selected_ids = ["sample-a"]
        self.workspace.ui.layout_views[self.workspace.ui.active_layout_key] = LayoutViewState(
            camera_3d={
                "yaw": 0.9,
                "pitch": 0.4,
                "distance": 3.2,
                "target_x": 0.0,
                "target_y": 0.0,
                "target_z": 0.0,
                "ortho_scale": 1.45,
            }
        )

    def get_workspace(self, workspace_id: str | None = None) -> WorkspaceState:
        return self.workspace

    def get_dataset(
        self, workspace_id: str | None = None, dataset_name: str | None = None
    ) -> Dataset:
        return self.dataset


def test_cli_rejects_legacy_top_level_flags(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["--dataset", "cifar10_demo"])

    assert "invalid choice" in capsys.readouterr().err


def test_cli_provider_and_workspace_commands_use_persistent_registries(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    provider_registry_path = tmp_path / "providers.json"
    workspace_registry_path = tmp_path / "workspaces.json"

    monkeypatch.setattr(
        "hyperview.runtime.get_provider_registry_path",
        lambda: provider_registry_path,
    )
    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    main(
        [
            "provider",
            "register",
            "test-provider",
            "--import-path",
            "tests.test_cli_control:LocalProviderFixture",
            "--json",
        ]
    )
    provider_payload = json.loads(capsys.readouterr().out)
    assert provider_payload["provider"]["alias"] == "test-provider"
    assert provider_registry_path.exists()

    main(["workspace", "create", "research", "--activate", "--json"])
    workspace_payload = json.loads(capsys.readouterr().out)
    assert workspace_payload["workspace"]["id"] == "research"

    main(["workspace", "set-dataset", "research", "birds", "--json"])
    add_dataset_payload = json.loads(capsys.readouterr().out)
    assert add_dataset_payload["workspace"]["dataset_name"] == "birds"
    assert workspace_registry_path.exists()

    main(["workspace", "set-dataset", "research", "flowers", "--json"])
    replace_dataset_payload = json.loads(capsys.readouterr().out)
    assert replace_dataset_payload["workspace"]["dataset_name"] == "flowers"

    main(["workspace", "create", "one-shot", "--dataset", "cars", "--json"])
    create_with_dataset_payload = json.loads(capsys.readouterr().out)
    assert create_with_dataset_payload["workspace"]["dataset_name"] == "cars"


def test_cli_embeddings_compute_posts_runtime_job(monkeypatch, capsys) -> None:
    recorded: dict[str, object] = {}

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded["url"] = url
        recorded["payload"] = payload
        recorded["method"] = method
        return {"job": {"id": "job-123"}}

    def fake_wait(base_url: str, job_id: str) -> dict[str, object]:
        return {"id": job_id, "status": "completed", "result": {"space_key": "space-a"}}

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)
    monkeypatch.setattr("hyperview.cli._wait_for_job", fake_wait)

    main(
        [
            "embeddings",
            "compute",
            "--workspace",
            "default",
            "--dataset",
            "birds",
            "--model-id",
            "experiment-a",
            "--provider",
            "custom-provider",
            "--checkpoint",
            "/tmp/checkpoint.json",
            "--provider-arg",
            "dim=4",
            "--layout",
            "euclidean:2d",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["job"]["status"] == "completed"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/embeddings/compute"
    assert recorded["payload"] == {
        "workspace_id": "default",
        "dataset_name": "birds",
        "model": "experiment-a",
        "provider": "custom-provider",
        "checkpoint": "/tmp/checkpoint.json",
        "provider_kwargs": {"dim": 4},
        "layouts": ["euclidean:2d"],
        "method": "umap",
        "n_neighbors": 15,
        "min_dist": 0.1,
        "metric": "cosine",
    }


def test_cli_figure_export_uses_active_workspace_layout(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    dataset = Dataset("figure_cli", persist=False)
    dataset.add_sample(Sample(id="sample-a", filepath="/virtual/a.png", label="cat"))
    layout_key = dataset.set_coords("spherical", ["sample-a"], [[1.0, 0.0, 0.0]])
    output = tmp_path / "figure.png"
    recorded: dict[str, object] = {}

    def fake_runtime() -> FigureRuntimeFixture:
        return FigureRuntimeFixture(dataset)

    def fake_render_layout_figure(**kwargs: object) -> FigureExportResult:
        recorded.update(kwargs)
        return FigureExportResult(
            output_path=output,
            layout_key=str(kwargs["layout_key"]),
            geometry="spherical",
            width=2400,
            height=1800,
            num_points=1,
        )

    monkeypatch.setattr("hyperview.cli.HyperViewRuntime", fake_runtime)
    monkeypatch.setattr("hyperview.cli.render_layout_figure", fake_render_layout_figure)

    main(["figure", "export", str(output), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["figure"]["layout_key"] == layout_key
    assert recorded["dataset"] is dataset
    assert recorded["layout_key"] == layout_key
    assert recorded["output_path"] == str(output)
    assert recorded["view"] is not None
    options = recorded["options"]
    assert isinstance(options, FigureRenderOptions)
    assert options.theme == "light"
    assert options.point_radius == 4.0
    assert options.guide_style == "paper"
    assert options.legend == "auto"
    assert options.selected_ids == set()


def test_cli_figure_export_reports_validation_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dataset = Dataset("figure_cli_error", persist=False)
    dataset.add_sample(Sample(id="sample-a", filepath="/virtual/a.png", label="cat"))
    dataset.set_coords("euclidean", ["sample-a"], [[0.0, 0.0]])
    output = tmp_path / "figure.png"

    def fake_runtime() -> FigureRuntimeFixture:
        return FigureRuntimeFixture(dataset)

    monkeypatch.setattr("hyperview.cli.HyperViewRuntime", fake_runtime)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "figure",
                "export",
                str(output),
                "--layout",
                "precomputed_2d__euclidean_precomputed__2d",
            ]
        )

    assert "3D layouts only" in str(exc_info.value)


def test_cli_panel_add_posts_extension_panel_instance(
    monkeypatch,
    capsys,
) -> None:
    recorded: dict[str, object] = {}

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded["url"] = url
        recorded["payload"] = payload
        recorded["method"] = method
        return {"workspace": {"id": "default"}}

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "add",
            "--workspace",
            "default",
            "--panel-id",
            "agent-panel",
            "--extension",
            "agent-tools",
            "--extension-panel",
            "agent-panel",
            "--position",
            "right",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["workspace"]["id"] == "default"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/commands/run"
    assert recorded["payload"] == {
        "command": "ui.panel.add",
        "target": {"workspace_id": "default"},
        "args": {
            "panel_id": "agent-panel",
            "title": None,
            "kind": "extension",
            "builtin_panel": None,
            "extension": "agent-tools",
            "extension_panel": "agent-panel",
            "layout_key": None,
            "position": "right",
            "reference_panel_id": None,
            "direction": None,
            "visible": True,
            "props": None,
        },
    }


def test_cli_panel_add_posts_scatter_panel_layout_binding(monkeypatch, capsys) -> None:
    recorded: dict[str, object] = {}

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded["url"] = url
        recorded["payload"] = payload
        recorded["method"] = method
        return {"workspace": {"id": "default"}}

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "add",
            "--workspace",
            "default",
            "--panel-id",
            "uncha-poincare",
            "--title",
            "UNCHA",
            "--kind",
            "scatter",
            "--layout-key",
            "uncha__poincare_umap__2d",
            "--position",
            "center",
            "--reference-panel-id",
            "hycoclip-poincare",
            "--direction",
            "right",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["workspace"]["id"] == "default"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/commands/run"
    assert recorded["payload"] == {
        "command": "ui.panel.add",
        "target": {"workspace_id": "default"},
        "args": {
            "panel_id": "uncha-poincare",
            "title": "UNCHA",
            "kind": "scatter",
            "builtin_panel": None,
            "extension": None,
            "extension_panel": None,
            "layout_key": "uncha__poincare_umap__2d",
            "position": "center",
            "reference_panel_id": "hycoclip-poincare",
            "direction": "right",
            "visible": True,
            "props": None,
        },
    }


def test_cli_panel_add_posts_builtin_samples_panel(monkeypatch, capsys) -> None:
    recorded: dict[str, object] = {}

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded["url"] = url
        recorded["payload"] = payload
        recorded["method"] = method
        return {"workspace": {"id": "default"}}

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "add",
            "--workspace",
            "default",
            "--panel-id",
            "samples",
            "--kind",
            "builtin",
            "--builtin-panel",
            "samples",
            "--position",
            "right",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["workspace"]["id"] == "default"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/commands/run"
    assert recorded["payload"] == {
        "command": "ui.panel.add",
        "target": {"workspace_id": "default"},
        "args": {
            "panel_id": "samples",
            "title": None,
            "kind": "builtin",
            "builtin_panel": "samples",
            "extension": None,
            "extension_panel": None,
            "layout_key": None,
            "position": "right",
            "reference_panel_id": None,
            "direction": None,
            "visible": True,
            "props": None,
        },
    }


def test_cli_panel_definitions_lists_runtime_panel_contracts(monkeypatch, capsys) -> None:
    recorded: dict[str, str] = {}

    def fake_get(url: str) -> dict[str, object]:
        recorded["url"] = url
        return {
            "panel_definitions": [
                {
                    "panel_type": "samples",
                    "label": "Samples",
                    "title": "Samples",
                    "source": "builtin",
                }
            ]
        }

    monkeypatch.setattr("hyperview.cli._http_get_json", fake_get)

    main(["ui", "panel", "definitions", "--json"])

    output = json.loads(capsys.readouterr().out)
    assert recorded["url"] == "http://127.0.0.1:6262/api/panel-definitions"
    assert output["panel_definitions"][0]["panel_type"] == "samples"


def test_cli_panel_update_posts_runtime_panel_props(monkeypatch, capsys) -> None:
    recorded: dict[str, object] = {}

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded["url"] = url
        recorded["payload"] = payload
        recorded["method"] = method
        return {"workspace": {"id": "default"}}

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "update",
            "--workspace",
            "default",
            "--panel-id",
            "ranked-clip",
            "--props-json",
            '{"mode":"ranked","rank":{"anchorSampleId":"sample-1","k":24}}',
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["workspace"]["id"] == "default"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/commands/run"
    assert recorded["payload"] == {
        "command": "ui.panel.update",
        "target": {"workspace_id": "default", "panel_id": "ranked-clip"},
        "args": {
            "props": {
                "mode": "ranked",
                "rank": {
                    "anchorSampleId": "sample-1",
                    "k": 24,
                },
            },
        },
    }


def test_cli_panel_layout_commands_patch_runtime_panel_state(monkeypatch, capsys) -> None:
    recorded: list[dict[str, object]] = []

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded.append({"url": url, "payload": payload, "method": method})
        return {"ok": True, "workspace": {"id": "default"}}

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "resize",
            "--workspace",
            "default",
            "--panel-id",
            "readout",
            "--width",
            "360",
            "--min-width",
            "280",
            "--json",
        ]
    )
    main(
        [
            "ui",
            "panel",
            "move",
            "--workspace",
            "default",
            "--panel-id",
            "readout",
            "--position",
            "right",
            "--reference-panel-id",
            "samples",
            "--direction",
            "right",
            "--json",
        ]
    )
    main(
        [
            "ui",
            "panel",
            "focus",
            "--workspace",
            "default",
            "--panel-id",
            "readout",
            "--json",
        ]
    )
    main(
        [
            "ui",
            "panel",
            "close",
            "--workspace",
            "default",
            "--panel-id",
            "readout",
            "--json",
        ]
    )
    main(
        [
            "ui",
            "panel",
            "show",
            "--workspace",
            "default",
            "--panel-id",
            "readout",
            "--json",
        ]
    )

    _ = capsys.readouterr()
    assert [entry["method"] for entry in recorded] == ["POST", "POST", "POST", "POST", "POST"]
    assert {entry["url"] for entry in recorded} == {
        "http://127.0.0.1:6262/api/control/commands/run"
    }
    assert recorded[0]["payload"] == {
        "command": "ui.panel.resize",
        "target": {"workspace_id": "default", "panel_id": "readout"},
        "args": {"width": 360, "min_width": 280},
    }
    assert recorded[1]["payload"] == {
        "command": "ui.panel.move",
        "target": {"workspace_id": "default", "panel_id": "readout"},
        "args": {
            "position": "right",
            "reference_panel_id": "samples",
            "direction": "right",
        },
    }
    assert recorded[2]["payload"] == {
        "command": "ui.panel.focus",
        "target": {"workspace_id": "default", "panel_id": "readout"},
        "args": {},
    }
    assert recorded[3]["payload"] == {
        "command": "ui.panel.close",
        "target": {"workspace_id": "default", "panel_id": "readout"},
        "args": {},
    }
    assert recorded[4]["payload"] == {
        "command": "ui.panel.show",
        "target": {"workspace_id": "default", "panel_id": "readout"},
        "args": {},
    }


def test_cli_generic_command_runner_posts_command_envelope(monkeypatch, capsys) -> None:
    recorded: dict[str, object] = {}

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded["url"] = url
        recorded["payload"] = payload
        recorded["method"] = method
        return {
            "ok": True,
            "command": "ui.panel.resize",
            "workspace": {"id": "default"},
            "revision": 2,
        }

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "commands",
            "run",
            "ui.panel.resize",
            "--target",
            "workspace_id=default",
            "--target",
            "panel_id=readout",
            "--arg",
            "width=360",
            "--arg",
            "min_width=null",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/commands/run"
    assert recorded["payload"] == {
        "command": "ui.panel.resize",
        "target": {"workspace_id": "default", "panel_id": "readout"},
        "args": {"width": 360, "min_width": None},
    }


def test_cli_generic_command_runner_prints_error_envelope(monkeypatch, capsys) -> None:
    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        return {
            "ok": False,
            "command": "ui.panel.resize",
            "error": {
                "code": "not_found",
                "message": "Panel not found: missing",
            },
        }

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "commands",
            "run",
            "ui.panel.resize",
            "--target",
            "workspace_id=default",
            "--target",
            "panel_id=missing",
            "--arg",
            "width=360",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "ok": False,
        "command": "ui.panel.resize",
        "error": {
            "code": "not_found",
            "message": "Panel not found: missing",
        },
    }


def test_cli_panel_state_and_samples_retrieval_commands_post_command_envelopes(
    monkeypatch,
    capsys,
) -> None:
    recorded: list[dict[str, object]] = []

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded.append({"url": url, "payload": payload, "method": method})
        return {
            "ok": True,
            "command": payload["command"],
            "result": {"panel_id": "samples", "state_revision": 1},
            "workspace": {"id": "default"},
        }

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "state",
            "get",
            "--workspace",
            "default",
            "--panel-id",
            "samples",
            "--json",
        ]
    )
    panel_state_get = json.loads(capsys.readouterr().out)
    assert panel_state_get["command"] == "ui.panel.state.get"

    main(
        [
            "ui",
            "panel",
            "state",
            "patch",
            "--workspace",
            "default",
            "--panel-id",
            "samples",
            "--state-json",
            '{"settings":{"density":"compact"}}',
            "--expected-revision",
            "0",
            "--replace",
            "--json",
        ]
    )
    panel_state_patch = json.loads(capsys.readouterr().out)
    assert panel_state_patch["command"] == "ui.panel.state.patch"

    main(
        [
            "ui",
            "samples",
            "retrieval",
            "set-anchor",
            "--workspace",
            "default",
            "--sample-id",
            "sample-2",
            "--space-key",
            "clip",
            "--k",
            "12",
            "--json",
        ]
    )
    retrieval_set = json.loads(capsys.readouterr().out)
    assert retrieval_set["workspace"]["id"] == "default"

    main(
        [
            "ui",
            "samples",
            "retrieval",
            "set-k",
            "--workspace",
            "default",
            "--k",
            "24",
            "--json",
        ]
    )
    retrieval_k = json.loads(capsys.readouterr().out)
    assert retrieval_k["workspace"]["id"] == "default"

    main(
        [
            "ui",
            "samples",
            "retrieval",
            "clear",
            "--workspace",
            "default",
            "--json",
        ]
    )
    retrieval_clear = json.loads(capsys.readouterr().out)
    assert retrieval_clear["workspace"]["id"] == "default"

    assert [entry["method"] for entry in recorded] == ["POST", "POST", "POST", "POST", "POST"]
    assert {entry["url"] for entry in recorded} == {
        "http://127.0.0.1:6262/api/control/commands/run"
    }
    assert recorded[0]["payload"] == {
        "command": "ui.panel.state.get",
        "target": {"workspace_id": "default", "panel_id": "samples"},
        "args": {},
    }
    assert recorded[1]["payload"] == {
        "command": "ui.panel.state.patch",
        "target": {"workspace_id": "default", "panel_id": "samples"},
        "args": {
            "state": {"settings": {"density": "compact"}},
            "replace_state": True,
            "expected_revision": 0,
        },
    }
    assert recorded[2]["payload"] == {
        "command": "samples.retrieval.set-anchor",
        "target": {"workspace_id": "default"},
        "args": {
            "sample_id": "sample-2",
            "layout_key": None,
            "space_key": "clip",
            "k": 12,
            "source": "cli",
        },
    }
    assert recorded[3]["payload"] == {
        "command": "samples.retrieval.set-k",
        "target": {"workspace_id": "default"},
        "args": {"k": 24},
    }
    assert recorded[4]["payload"] == {
        "command": "samples.retrieval.clear",
        "target": {"workspace_id": "default"},
        "args": {},
    }


def test_cli_panel_state_patch_prints_error_envelope(monkeypatch, capsys) -> None:
    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        return {
            "ok": False,
            "command": payload["command"],
            "error": {
                "code": "conflict",
                "message": "panel state revision conflict: expected 1, got 2",
            },
        }

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "ui",
            "panel",
            "state",
            "patch",
            "--workspace",
            "default",
            "--panel-id",
            "samples",
            "--state-json",
            '{"settings":{"density":"loose"}}',
            "--expected-revision",
            "1",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output == {
        "ok": False,
        "command": "ui.panel.state.patch",
        "error": {
            "code": "conflict",
            "message": "panel state revision conflict: expected 1, got 2",
        },
    }


def test_cli_panel_collection_shortcuts_post_command_envelopes(monkeypatch, capsys) -> None:
    recorded: list[dict[str, object]] = []

    def fake_send(url: str, payload: dict[str, object], method: str = "POST") -> dict[str, object]:
        recorded.append({"url": url, "payload": payload, "method": method})
        return {
            "ok": True,
            "command": payload["command"],
            "result": {"collection_id": "collection-1"},
            "workspace": {"id": "default"},
        }

    monkeypatch.setattr("hyperview.cli._http_send_json", fake_send)

    main(
        [
            "panel",
            "samples",
            "show-neighbors",
            "--workspace",
            "default",
            "--sample-id",
            "sample-2",
            "--space-key",
            "clip",
            "--k",
            "12",
            "--json",
        ]
    )
    neighbors_output = json.loads(capsys.readouterr().out)
    assert neighbors_output["result"]["collection_id"] == "collection-1"

    main(
        [
            "panel",
            "labels",
            "filter",
            "--workspace",
            "default",
            "--value",
            "cat",
            "--json",
        ]
    )
    filter_output = json.loads(capsys.readouterr().out)
    assert filter_output["result"]["collection_id"] == "collection-1"

    main(
        [
            "panel",
            "labels",
            "filter",
            "--workspace",
            "default",
            "--clear",
            "--json",
        ]
    )
    _ = capsys.readouterr()

    assert recorded == [
        {
            "url": "http://127.0.0.1:6262/api/control/commands/run",
            "payload": {
                "command": "panel.samples.show-neighbors",
                "target": {"workspace_id": "default"},
                "args": {
                    "sample_id": "sample-2",
                    "layout_key": None,
                    "space_key": "clip",
                    "k": 12,
                    "source": "cli",
                },
            },
            "method": "POST",
        },
        {
            "url": "http://127.0.0.1:6262/api/control/commands/run",
            "payload": {
                "command": "panel.labels.filter",
                "target": {"workspace_id": "default"},
                "args": {
                    "field": "label",
                    "source": "cli",
                    "value": "cat",
                },
            },
            "method": "POST",
        },
        {
            "url": "http://127.0.0.1:6262/api/control/commands/run",
            "payload": {
                "command": "panel.labels.filter",
                "target": {"workspace_id": "default"},
                "args": {
                    "field": "label",
                    "source": "cli",
                    "clear": True,
                },
            },
            "method": "POST",
        },
    ]


def test_cli_dataset_create_list_and_inspect_use_persistent_storage(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    Image.new("RGB", (8, 8), color=(255, 0, 0)).save(images_dir / "a.png")
    Image.new("RGB", (8, 8), color=(0, 255, 0)).save(images_dir / "b.png")

    datasets_dir = tmp_path / "datasets"
    media_dir = tmp_path / "media"

    monkeypatch.setenv("HYPERVIEW_DATASETS_DIR", str(datasets_dir))
    monkeypatch.setenv("HYPERVIEW_MEDIA_DIR", str(media_dir))

    main(
        [
            "dataset",
            "create",
            "tiny-images",
            "--images-dir",
            str(images_dir),
            "--json",
        ]
    )
    create_payload = json.loads(capsys.readouterr().out)
    assert create_payload["dataset"]["name"] == "tiny-images"
    assert create_payload["dataset"]["num_samples"] == 2

    main(["dataset", "list", "--json"])
    list_payload = json.loads(capsys.readouterr().out)
    assert "tiny-images" in list_payload["datasets"]

    main(["dataset", "inspect", "tiny-images", "--json"])
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_payload["dataset"]["name"] == "tiny-images"
    assert inspect_payload["dataset"]["num_samples"] == 2


def test_cli_workspace_delete_removes_stale_workspace(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    workspace_registry_path = tmp_path / "workspaces.json"

    monkeypatch.setattr(
        "hyperview.runtime.get_workspace_registry_path",
        lambda: workspace_registry_path,
    )

    main(["workspace", "create", "research", "--activate", "--json"])
    capsys.readouterr()
    main(["workspace", "create", "stale-demo", "--json"])
    capsys.readouterr()

    main(["workspace", "delete", "stale-demo", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload["deleted_workspace_id"] == "stale-demo"
    assert payload["active_workspace_id"] == "research"
    assert [workspace["id"] for workspace in payload["workspaces"]] == ["default", "research"]


def test_cli_skill_install_copies_hyperview_skill(
    tmp_path: Path,
    capsys,
) -> None:
    destination = tmp_path / "hyperview-cli"

    main(["skill", "install", "--destination", str(destination), "--json"])
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert payload["skill"] == "hyperview-cli"
    assert payload["action"] == "installed"
    assert payload["installed"] is True
    assert payload["destination"] == str(destination.resolve())
    assert (destination / "SKILL.md").exists()
    assert (destination / "references" / "commands.md").exists()
    assert (destination / "references" / "panel-modules.md").exists()
    assert (destination / "references" / "extensions.md").exists()

    (destination / "SKILL.md").write_text("stale", encoding="utf-8")
    main(["skill", "install", "--destination", str(destination), "--json"])
    refreshed_payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert refreshed_payload["action"] == "replaced"
    assert refreshed_payload["installed"] is True
    assert "name: hyperview-cli" in (destination / "SKILL.md").read_text(encoding="utf-8")


def test_cli_skill_install_force_replaces_existing_destination(
    tmp_path: Path,
    capsys,
) -> None:
    destination = tmp_path / "hyperview-cli"
    destination.mkdir()
    (destination / "SKILL.md").write_text("stale", encoding="utf-8")

    main(["skill", "install", "--destination", str(destination), "--yes", "--json"])
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert payload["action"] == "replaced"
    assert payload["installed"] is True
    assert "name: hyperview-cli" in (destination / "SKILL.md").read_text(encoding="utf-8")


def test_cli_skill_install_custom_destination_refuses_ambiguous_replace(
    tmp_path: Path,
    capsys,
) -> None:
    destination = tmp_path / "skills"
    destination.mkdir()
    (destination / "other-skill.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="Refusing to replace"):
        main(["skill", "install", "--destination", str(destination), "--json"])

    assert (destination / "other-skill.txt").exists()
    assert capsys.readouterr().out == ""


def test_cli_skill_install_dry_run_does_not_write(
    tmp_path: Path,
    capsys,
) -> None:
    destination = tmp_path / "hyperview-cli"

    main(["skill", "install", "--destination", str(destination), "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert payload["action"] == "would-install"
    assert payload["installed"] is False
    assert not destination.exists()

    destination.mkdir()
    main(["skill", "install", "--destination", str(destination), "--dry-run", "--json"])
    replace_payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert replace_payload["action"] == "would-replace"
    assert replace_payload["installed"] is False


def test_cli_skill_install_all_known_returns_one_result_per_agent(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    from hyperview import skill_install as skill_install_module

    monkeypatch.setattr(
        skill_install_module,
        "AGENT_PROFILES",
        skill_install_module._build_agent_profiles(),
    )

    main(["skill", "install", "--all-known", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert isinstance(payload, list)
    assert len(payload) == len(skill_install_module.AGENT_PROFILES)
    agents_seen = {entry["agent"] for entry in payload}
    assert "claude-code" in agents_seen
    assert "universal" in agents_seen
    assert all(entry["action"] == "would-install" for entry in payload)


def test_cli_skill_install_auto_detect_only_picks_installed_agents(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".cursor").mkdir()  # simulate Cursor installed
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    from hyperview import skill_install as skill_install_module

    monkeypatch.setattr(
        skill_install_module,
        "AGENT_PROFILES",
        skill_install_module._build_agent_profiles(),
    )

    main(["skill", "install", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    agents_seen = {entry["agent"] for entry in payload}
    assert agents_seen == {"cursor", "universal"}


def test_cli_skill_install_specific_agents_writes_into_each(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(fake_home / ".config"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)

    from hyperview import skill_install as skill_install_module

    monkeypatch.setattr(
        skill_install_module,
        "AGENT_PROFILES",
        skill_install_module._build_agent_profiles(),
    )

    main(
        [
            "skill",
            "install",
            "--agent",
            "claude-code",
            "--agent",
            "cursor",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    agents_seen = {entry["agent"] for entry in payload}
    assert agents_seen == {"claude-code", "cursor"}
    assert all(entry["action"] == "installed" for entry in payload)
    assert (fake_home / ".claude" / "skills" / "hyperview-cli" / "SKILL.md").exists()
    assert (fake_home / ".cursor" / "skills" / "hyperview-cli" / "SKILL.md").exists()


def test_cli_skill_install_project_scope_uses_agent_specific_dirs(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_project = tmp_path / "project"
    fake_project.mkdir()
    monkeypatch.chdir(fake_project)

    main(
        [
            "skill",
            "install",
            "--scope",
            "project",
            "--agent",
            "github-copilot",
            "--agent",
            "cursor",
            "--agent",
            "universal",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    agents_seen = {entry["agent"] for entry in payload}
    assert agents_seen == {"github-copilot", "cursor", "universal"}
    assert (fake_project / ".github" / "skills" / "hyperview-cli" / "SKILL.md").exists()
    assert (fake_project / ".cursor" / "skills" / "hyperview-cli" / "SKILL.md").exists()
    assert (fake_project / ".agents" / "skills" / "hyperview-cli" / "SKILL.md").exists()


def test_cli_skill_install_project_scope_skips_when_source_is_destination(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source = tmp_path / ".agents" / "skills" / "hyperview-cli"
    references = source / "references"
    references.mkdir(parents=True)
    (source / "SKILL.md").write_text("source skill", encoding="utf-8")
    (references / "commands.md").write_text("source commands", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from hyperview import skill_install as skill_install_module

    monkeypatch.setattr(skill_install_module, "_resolve_skill_source", lambda: source)

    main(["skill", "install", "--scope", "project", "--agent", "universal", "--json"])
    payload = json.loads(capsys.readouterr().out)["skill_install"]

    assert payload[0]["action"] == "already-current"
    assert payload[0]["installed"] is True
    assert (source / "SKILL.md").read_text(encoding="utf-8") == "source skill"


def test_cli_skill_install_refuses_overlapping_destination(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source" / "hyperview-cli"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text("source skill", encoding="utf-8")

    from hyperview import skill_install as skill_install_module

    monkeypatch.setattr(skill_install_module, "_resolve_skill_source", lambda: source)

    with pytest.raises(ValueError, match="source and destination overlap"):
        main(
            [
                "skill",
                "install",
                "--destination",
                str(source / "nested"),
                "--json",
            ]
        )
