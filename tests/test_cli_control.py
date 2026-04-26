from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from hyperview.cli import main


class LocalProviderFixture:
    pass


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


def test_cli_panel_add_posts_native_panel_module_file(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    panel_file = tmp_path / "panel.js"
    panel_file.write_text("export default function Panel() { return null; }")

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
            "--title",
            "Agent Panel",
            "--module-file",
            str(panel_file),
            "--position",
            "right",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["workspace"]["id"] == "default"
    assert recorded["method"] == "POST"
    assert recorded["url"] == "http://127.0.0.1:6262/api/control/ui/panels"
    assert recorded["payload"] == {
        "workspace_id": "default",
        "panel_id": "agent-panel",
        "title": "Agent Panel",
        "module_file": str(panel_file.resolve()),
        "position": "right",
    }


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