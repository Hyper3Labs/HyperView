from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.runtime import SimilarityQueryState
from hyperview.server.app import _resolve_collection_items, create_app
from hyperview.storage.schema import (
    index_id_for_space_key,
    space_key_from_index_ref,
)


def _make_dataset() -> tuple[Dataset, str]:
    dataset = Dataset("representation_index_api", persist=False)
    ids = ["s0", "s1", "s2"]

    for index, sample_id in enumerate(ids):
        dataset.add_sample(
            Sample(
                id=sample_id,
                filepath=f"/missing/{index}.png",
                label="cat" if index < 2 else "dog",
            )
        )

    space_key = "test_space"
    dataset._storage.ensure_space(
        model_id="test-model",
        dim=2,
        config={"provider": "test", "geometry": "euclidean", "modality": "multimodal"},
        space_key=space_key,
    )
    dataset._storage.add_embeddings(
        space_key,
        ids,
        np.array(
            [
                [1.0, 0.0],
                [0.9, 0.1],
                [-1.0, 0.0],
            ],
            dtype=np.float32,
        ),
    )

    return dataset, space_key


def test_space_key_from_index_ref_accepts_index_id_and_bare_key() -> None:
    assert space_key_from_index_ref("space:clip_b32") == "clip_b32"
    assert space_key_from_index_ref("clip_b32") == "clip_b32"
    assert space_key_from_index_ref("  space:clip_b32  ") == "clip_b32"
    assert space_key_from_index_ref("space:") is None
    assert space_key_from_index_ref("") is None
    assert space_key_from_index_ref(None) is None
    assert space_key_from_index_ref(42) is None


def test_dataset_info_exposes_representations_and_indexes() -> None:
    dataset, space_key = _make_dataset()
    client = TestClient(create_app(dataset))

    response = client.get("/api/dataset")

    assert response.status_code == 200
    payload = response.json()

    representations = payload["representations"]
    assert len(representations) == 1
    representation = representations[0]
    assert representation["id"] == space_key
    assert representation["entity_set_id"] == "samples"
    assert representation["field_path"] == f"embeddings.{space_key}"
    assert representation["kind"] == "vector"
    assert representation["shape"] == [2]
    assert representation["model_id"] == "test-model"
    assert representation["modality"] == "multimodal"
    assert representation["geometry"] == "euclidean"

    indexes = payload["indexes"]
    assert len(indexes) == 1
    index = indexes[0]
    assert index["id"] == index_id_for_space_key(space_key)
    assert index["representation_id"] == space_key
    assert index["query_modes"] == ["nearest", "text"]
    assert index["scorer"] == "cosine"


def test_image_only_space_index_has_no_text_query_mode() -> None:
    dataset = Dataset("representation_index_image_only", persist=False)
    dataset.add_sample(Sample(id="s0", filepath="/missing/0.png"))
    dataset._storage.ensure_space(
        model_id="image-model",
        dim=2,
        config={"provider": "test", "geometry": "euclidean", "modality": "image"},
        space_key="image_space",
    )
    client = TestClient(create_app(dataset))

    payload = client.get("/api/dataset").json()

    assert payload["indexes"][0]["query_modes"] == ["nearest"]


def test_similarity_endpoint_accepts_index_id() -> None:
    dataset, space_key = _make_dataset()
    client = TestClient(create_app(dataset))

    by_space_key = client.get(
        "/api/search/similar/s0", params={"k": 2, "space_key": space_key}
    )
    by_index_id = client.get(
        "/api/search/similar/s0",
        params={"k": 2, "index_id": index_id_for_space_key(space_key)},
    )

    assert by_space_key.status_code == 200
    assert by_index_id.status_code == 200
    assert by_index_id.json()["space_key"] == space_key
    assert [item["id"] for item in by_index_id.json()["results"]] == [
        item["id"] for item in by_space_key.json()["results"]
    ]


def test_similarity_query_state_accepts_index_id() -> None:
    state = SimilarityQueryState.from_dict(
        {"anchor_sample_id": "s0", "index_id": "space:test_space"}
    )
    assert state is not None
    assert state.space_key == "test_space"

    explicit = SimilarityQueryState.from_dict(
        {"anchor_sample_id": "s0", "space_key": "explicit", "index_id": "space:other"}
    )
    assert explicit is not None
    assert explicit.space_key == "explicit"


def test_collection_items_resolver_accepts_index_id_only_query() -> None:
    dataset, space_key = _make_dataset()
    collection = SimpleNamespace(
        kind="neighbors",
        query={
            "anchor": {"entityId": "s0"},
            "indexId": index_id_for_space_key(space_key),
            "k": 2,
        },
    )

    items, total, has_more = _resolve_collection_items(
        dataset, collection, offset=0, limit=10
    )

    assert total == 2
    assert has_more is False
    assert [sample.id for sample, _score in items] == ["s1", "s2"]
