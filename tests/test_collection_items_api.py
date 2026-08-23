from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from hyperview import Dataset
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.server.app import create_app


def _service_with_dataset(tmp_path: Path) -> ControlService:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    dataset = Dataset("collection_items", persist=False)
    labels = ["cat", "cat", "dog", "cat", "dog"]
    for i, label in enumerate(labels):
        dataset.add_sample(
            Sample(id=f"s{i}", filepath=f"/virtual/s{i}.png", label=label)
        )
    dataset._storage.ensure_space(
        model_id="test-model",
        dim=2,
        config={"provider": "test", "geometry": "euclidean"},
        space_key="test_space",
    )
    dataset._storage.add_embeddings(
        "test_space",
        [f"s{i}" for i in range(len(labels))],
        np.asarray(
            [[1.0, 0.0], [0.9, 0.1], [-1.0, 0.0], [0.8, 0.2], [-0.9, -0.1]],
            dtype=np.float32,
        ),
    )
    runtime.attach_dataset_instance("default", dataset)
    return ControlService(runtime, create_default_command_registry())


def test_neighbors_collection_items_are_paged_and_ordered(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)
    result = service.run(
        CommandEnvelope(
            command="collection.neighbors.create",
            target={"workspace_id": "default"},
            args={"sample_id": "s0", "k": 3, "source": "test"},
        )
    )
    assert result.ok is True
    collection_id = result.result["collection"]["id"]

    client = TestClient(create_app(runtime=service.runtime))

    page1 = client.get(
        f"/api/collections/{collection_id}/items", params={"offset": 0, "limit": 2}
    )
    assert page1.status_code == 200
    body1 = page1.json()
    assert body1["kind"] == "neighbors"
    assert body1["total"] == 3
    assert body1["has_more"] is True
    assert len(body1["items"]) == 2
    assert body1["items"][0]["score"] <= body1["items"][1]["score"]

    page2 = client.get(
        f"/api/collections/{collection_id}/items", params={"offset": 2, "limit": 2}
    )
    body2 = page2.json()
    assert body2["has_more"] is False
    assert len(body2["items"]) == 1

    all_ids = [item["id"] for item in body1["items"]] + [item["id"] for item in body2["items"]]
    assert len(set(all_ids)) == 3


def test_filter_collection_items_are_paged(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)
    result = service.run(
        CommandEnvelope(
            command="collection.filter.set",
            target={"workspace_id": "default"},
            args={"value": "cat", "source": "test"},
        )
    )
    assert result.ok is True
    collection_id = result.result["collection"]["id"]

    client = TestClient(create_app(runtime=service.runtime))

    response = client.get(
        f"/api/collections/{collection_id}/items", params={"offset": 0, "limit": 2}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "filter"
    assert body["total"] == 3
    assert body["has_more"] is True
    assert all(item["label"] == "cat" for item in body["items"])
    assert all(item["score"] is None for item in body["items"])


def test_selection_collection_items_preserve_requested_order(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)
    result = service.run(
        CommandEnvelope(
            command="collection.selection.set",
            target={"workspace_id": "default"},
            args={"sample_ids": ["s4", "s1", "s3"], "source": "test"},
        )
    )
    assert result.ok is True
    collection_id = result.result["collection"]["id"]
    client = TestClient(create_app(runtime=service.runtime))

    response = client.get(
        f"/api/collections/{collection_id}/items", params={"offset": 0, "limit": 2}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "selection"
    assert body["total"] == 3
    assert body["has_more"] is True
    assert [item["id"] for item in body["items"]] == ["s4", "s1"]


def test_collection_items_404_for_unknown_collection(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)
    client = TestClient(create_app(runtime=service.runtime))

    response = client.get("/api/collections/does-not-exist/items")
    assert response.status_code == 404


def test_get_collection_metadata(tmp_path: Path) -> None:
    service = _service_with_dataset(tmp_path)
    result = service.run(
        CommandEnvelope(
            command="collection.filter.set",
            target={"workspace_id": "default"},
            args={"value": "dog", "source": "test"},
        )
    )
    collection_id = result.result["collection"]["id"]
    client = TestClient(create_app(runtime=service.runtime))

    response = client.get(f"/api/collections/{collection_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == collection_id
    assert body["kind"] == "filter"
    assert body["query"]["value"] == "dog"
