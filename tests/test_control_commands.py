from __future__ import annotations

from pathlib import Path

import numpy as np

from hyperview import Dataset
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry


def _service_with_panel(tmp_path: Path) -> ControlService:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.add_runtime_panel(
        "default",
        panel_id="samples",
        kind="builtin",
        builtin_panel="samples",
        position="right",
        width=320,
        min_width=240,
    )
    return ControlService(runtime, create_default_command_registry())


def _service_with_dataset(tmp_path: Path) -> ControlService:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    dataset = Dataset("control_commands", persist=False)
    for sample_id, label in (("s0", "cat"), ("s1", "cat"), ("s2", "dog")):
        dataset.add_sample(Sample(id=sample_id, filepath=f"/virtual/{sample_id}.png", label=label))
    dataset._storage.ensure_space(
        model_id="test-model",
        dim=2,
        config={"provider": "test", "geometry": "euclidean"},
        space_key="test_space",
    )
    dataset._storage.add_embeddings(
        "test_space",
        ["s0", "s1", "s2"],
        np.asarray([[1.0, 0.0], [0.9, 0.1], [-1.0, 0.0]], dtype=np.float32),
    )
    runtime.attach_dataset_instance("default", dataset)
    return ControlService(runtime, create_default_command_registry())


def test_panel_resize_command_mutates_runtime_panel_layout(tmp_path: Path) -> None:
    service = _service_with_panel(tmp_path)

    result = service.run(
        CommandEnvelope(
            command="ui.panel.resize",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={"width": 420, "min_width": None},
        )
    )

    assert result.ok is True
    assert result.revision == 2
    assert result.workspace is not None
    panel = result.workspace["ui"]["custom_panels"][0]
    assert panel["width"] == 420
    assert panel["min_width"] is None


def test_panel_move_focus_close_show_commands_share_dispatch_path(tmp_path: Path) -> None:
    service = _service_with_panel(tmp_path)

    move_result = service.run(
        CommandEnvelope(
            command="ui.panel.move",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={
                "position": "bottom",
                "reference_panel_id": None,
                "direction": None,
            },
        )
    )
    assert move_result.ok is True
    assert move_result.workspace is not None
    assert move_result.workspace["ui"]["custom_panels"][0]["position"] == "bottom"

    focus_result = service.run(
        CommandEnvelope(
            command="ui.panel.focus",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert focus_result.ok is True
    assert focus_result.workspace is not None
    assert focus_result.workspace["ui"]["active_panel_id"] == "samples"

    close_result = service.run(
        CommandEnvelope(
            command="ui.panel.close",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert close_result.ok is True
    assert close_result.workspace is not None
    assert close_result.workspace["ui"]["custom_panels"][0]["visible"] is False
    assert close_result.workspace["ui"]["active_panel_id"] is None

    show_result = service.run(
        CommandEnvelope(
            command="ui.panel.show",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert show_result.ok is True
    assert show_result.workspace is not None
    assert show_result.workspace["ui"]["custom_panels"][0]["visible"] is True


def test_panel_add_update_remove_commands_share_dispatch_path(tmp_path: Path) -> None:
    service = _service_with_panel(tmp_path)

    add_result = service.run(
        CommandEnvelope(
            command="ui.panel.add",
            target={"workspace_id": "default"},
            args={
                "panel_id": "samples",
                "kind": "builtin",
                "builtin_panel": "samples",
                "position": "bottom",
                "width": 480,
            },
        )
    )
    assert add_result.ok is True
    assert add_result.workspace is not None
    panel = add_result.workspace["ui"]["custom_panels"][0]
    assert panel["position"] == "bottom"
    assert panel["width"] == 480

    update_result = service.run(
        CommandEnvelope(
            command="ui.panel.update",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={
                "title": "Sample Browser",
                "visible": False,
                "props": {"mode": "compact"},
            },
        )
    )
    assert update_result.ok is True
    assert update_result.workspace is not None
    panel = update_result.workspace["ui"]["custom_panels"][0]
    assert panel["title"] == "Sample Browser"
    assert panel["visible"] is False
    assert panel["props"] == {"mode": "compact"}

    remove_result = service.run(
        CommandEnvelope(
            command="ui.panel.remove",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert remove_result.ok is True
    assert remove_result.workspace is not None
    assert remove_result.workspace["ui"]["custom_panels"] == []


def test_panel_command_errors_are_machine_readable(tmp_path: Path) -> None:
    service = _service_with_panel(tmp_path)

    missing_panel = service.run(
        CommandEnvelope(
            command="ui.panel.resize",
            target={"workspace_id": "default", "panel_id": "missing"},
            args={"width": 420},
        )
    )
    assert missing_panel.ok is False
    assert missing_panel.error is not None
    assert missing_panel.error.code == "not_found"

    invalid_resize = service.run(
        CommandEnvelope(
            command="ui.panel.resize",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert invalid_resize.ok is False
    assert invalid_resize.error is not None
    assert invalid_resize.error.code == "validation_error"

    unknown = service.run(
        CommandEnvelope(
            command="ui.panel.unknown",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert unknown.ok is False
    assert unknown.error is not None
    assert unknown.error.code == "unknown_command"


def test_panel_dimension_commands_reject_non_positive_values(tmp_path: Path) -> None:
    service = _service_with_panel(tmp_path)

    resize_result = service.run(
        CommandEnvelope(
            command="ui.panel.resize",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={"width": 0},
        )
    )
    assert resize_result.ok is False
    assert resize_result.error is not None
    assert resize_result.error.code == "validation_error"

    add_result = service.run(
        CommandEnvelope(
            command="ui.panel.add",
            target={"workspace_id": "default"},
            args={
                "panel_id": "invalid",
                "kind": "builtin",
                "builtin_panel": "samples",
                "width": -1,
            },
        )
    )
    assert add_result.ok is False
    assert add_result.error is not None
    assert add_result.error.code == "validation_error"


def test_panel_state_commands_merge_patch_and_check_revision(tmp_path: Path) -> None:
    service = _service_with_panel(tmp_path)

    initial = service.run(
        CommandEnvelope(
            command="ui.panel.state.get",
            target={"workspace_id": "default", "panel_id": "samples"},
        )
    )
    assert initial.ok is True
    assert initial.result == {
        "panel_id": "samples",
        "state": {},
        "state_revision": 0,
    }

    first_patch = service.run(
        CommandEnvelope(
            command="ui.panel.state.patch",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={
                "state": {
                    "settings": {"density": "compact"},
                    "sort": "label",
                },
                "expected_revision": 0,
            },
        )
    )
    assert first_patch.ok is True
    assert first_patch.revision == 1
    assert first_patch.result == {
        "panel_id": "samples",
        "state": {
            "settings": {"density": "compact"},
            "sort": "label",
        },
        "state_revision": 1,
    }

    second_patch = service.run(
        CommandEnvelope(
            command="ui.panel.state.patch",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={
                "state": {
                    "settings": {"density": "comfortable", "columns": 4},
                    "sort": None,
                },
                "expected_revision": 1,
            },
        )
    )
    assert second_patch.ok is True
    assert second_patch.revision == 2
    assert second_patch.result["state"] == {
        "settings": {
            "density": "comfortable",
            "columns": 4,
        }
    }

    conflict = service.run(
        CommandEnvelope(
            command="ui.panel.state.patch",
            target={"workspace_id": "default", "panel_id": "samples"},
            args={
                "state": {"settings": {"density": "loose"}},
                "expected_revision": 1,
            },
        )
    )
    assert conflict.ok is False
    assert conflict.error is not None
    assert conflict.error.code == "conflict"


def test_labels_filter_command_creates_filter_collection(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)

    result = service.run(
        CommandEnvelope(
            command="panel.labels.filter",
            target={"workspace_id": "default"},
            args={"value": "cat", "source": "test"},
        )
    )

    assert result.ok is True
    assert result.workspace is not None
    collection = result.result["collection"]
    assert collection["kind"] == "filter"
    assert collection["query"] == {
        "field": "label",
        "op": "eq",
        "source": "test",
        "value": "cat",
    }
    samples_state = result.workspace["ui"]["panels"]["samples"]["state"]
    assert samples_state["mode"] == "collection"
    assert samples_state["collection_id"] == collection["id"]
    assert samples_state["collection"]["scores"] is None
    assert result.workspace["collections"][0]["id"] == collection["id"]

    clear_result = service.run(
        CommandEnvelope(
            command="panel.labels.filter",
            target={"workspace_id": "default"},
            args={"clear": True},
        )
    )
    assert clear_result.ok is True
    assert clear_result.result["collection_id"] is None
    assert clear_result.workspace is not None
    assert clear_result.workspace["ui"]["panels"]["samples"]["state"] == {}


def test_samples_neighbors_command_creates_neighbors_collection(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)

    result = service.run(
        CommandEnvelope(
            command="panel.samples.show-neighbors",
            target={"workspace_id": "default"},
            args={"sample_id": "s0", "k": 2, "source": "test"},
        )
    )

    assert result.ok is True
    assert result.workspace is not None
    collection = result.result["collection"]
    assert collection["kind"] == "neighbors"
    assert collection["query"]["anchor"] == {
        "datasetId": "control_commands",
        "entitySetId": "samples",
        "entityId": "s0",
    }
    assert collection["query"]["indexId"] == "space:test_space"
    assert collection["query"]["k"] == 2
    samples_state = result.workspace["ui"]["panels"]["samples"]["state"]
    assert samples_state["mode"] == "retrieval"
    assert samples_state["collection_id"] == collection["id"]
    assert samples_state["collection"]["scores"] is None
    assert "layoutId" in samples_state["collection"]["query"]
    assert samples_state["retrieval"]["space_key"] == "test_space"
    assert result.workspace["ui"]["similarity_query"] == samples_state["retrieval"]


def test_labels_filter_clear_does_not_clear_neighbors_collection(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)

    neighbors = service.run(
        CommandEnvelope(
            command="panel.samples.show-neighbors",
            target={"workspace_id": "default"},
            args={"sample_id": "s0", "k": 2, "source": "test"},
        )
    )
    assert neighbors.ok is True
    assert neighbors.workspace is not None
    neighbors_state = neighbors.workspace["ui"]["panels"]["samples"]["state"]
    neighbors_collection_id = neighbors_state["collection_id"]

    cleared_filter = service.run(
        CommandEnvelope(
            command="panel.labels.filter",
            target={"workspace_id": "default"},
            args={"clear": True},
        )
    )

    assert cleared_filter.ok is True
    assert cleared_filter.workspace is not None
    samples_state = cleared_filter.workspace["ui"]["panels"]["samples"]["state"]
    assert samples_state["mode"] == "retrieval"
    assert samples_state["collection_id"] == neighbors_collection_id
    assert samples_state["collection"]["kind"] == "neighbors"


def test_retrieval_clear_does_not_clear_filter_collection(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)

    filtered = service.run(
        CommandEnvelope(
            command="panel.labels.filter",
            target={"workspace_id": "default"},
            args={"value": "cat", "source": "test"},
        )
    )
    assert filtered.ok is True
    assert filtered.workspace is not None
    filter_state = filtered.workspace["ui"]["panels"]["samples"]["state"]
    filter_collection_id = filter_state["collection_id"]

    cleared_retrieval = service.run(
        CommandEnvelope(
            command="samples.retrieval.clear",
            target={"workspace_id": "default"},
            args={},
        )
    )

    assert cleared_retrieval.ok is True
    assert cleared_retrieval.workspace is not None
    samples_state = cleared_retrieval.workspace["ui"]["panels"]["samples"]["state"]
    assert samples_state["mode"] == "collection"
    assert samples_state["collection_id"] == filter_collection_id
    assert samples_state["collection"]["kind"] == "filter"


def test_samples_retrieval_commands_own_samples_panel_state(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)
    service.runtime.set_selection("default", ["s1"])

    result = service.run(
        CommandEnvelope(
            command="samples.retrieval.set-anchor",
            target={"workspace_id": "default"},
            args={"sample_id": "s0", "k": 2, "source": "test"},
        )
    )

    assert result.ok is True
    assert result.workspace is not None
    assert result.workspace["ui"]["selected_ids"] == []
    expected_retrieval = {
        "anchor_sample_id": "s0",
        "layout_key": None,
        "space_key": "test_space",
        "k": 2,
        "source": "test",
    }
    samples_state = result.workspace["ui"]["panels"]["samples"]["state"]
    assert samples_state["mode"] == "retrieval"
    assert samples_state["retrieval"] == expected_retrieval
    assert result.workspace["ui"]["similarity_query"] == expected_retrieval
    assert samples_state["collection"]["kind"] == "neighbors"
    assert result.result["panel_id"] == "samples"
    assert result.result["collection_id"] == samples_state["collection_id"]

    set_k = service.run(
        CommandEnvelope(
            command="samples.retrieval.set-k",
            target={"workspace_id": "default"},
            args={"k": 3},
        )
    )
    assert set_k.ok is True
    assert set_k.workspace is not None
    set_k_retrieval = set_k.workspace["ui"]["panels"]["samples"]["state"]["retrieval"]
    assert set_k_retrieval["k"] == 3
    assert set_k.workspace["ui"]["similarity_query"] == set_k_retrieval

    clear = service.run(
        CommandEnvelope(
            command="samples.retrieval.clear",
            target={"workspace_id": "default"},
        )
    )
    assert clear.ok is True
    assert clear.workspace is not None
    assert clear.result == {
        "panel_id": "samples",
        "collection_id": None,
        "collection": None,
    }
    assert clear.workspace["ui"]["similarity_query"] is None
    assert clear.workspace["ui"]["panels"]["samples"]["state"] == {}
