from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.server.app import create_app


def _make_dataset() -> tuple[Dataset, str]:
    dataset = Dataset("similarity_api", persist=False)
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
        config={"provider": "test", "geometry": "euclidean"},
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


def test_similarity_endpoint_returns_query_sample_and_resolved_space() -> None:
    dataset, space_key = _make_dataset()
    client = TestClient(create_app(dataset))

    response = client.get("/api/search/similar/s0", params={"k": 2})

    assert response.status_code == 200
    payload = response.json()

    assert payload["query_id"] == "s0"
    assert payload["space_key"] == space_key
    assert payload["metric"] == "cosine"
    assert payload["query_sample"]["id"] == "s0"
    assert payload["query_sample"]["thumbnail"] is None
    assert payload["results"][0]["id"] == "s1"
    assert payload["results"][0]["distance"] < payload["results"][1]["distance"]


def test_dataset_similarity_accepts_layout_key() -> None:
    dataset, space_key = _make_dataset()
    layout_key = "test_layout"
    dataset._storage.ensure_layout(  # noqa: SLF001 - test setup for low-level layout metadata
        layout_key=layout_key,
        space_key=space_key,
        method="test",
        geometry="euclidean",
        params=None,
    )

    similar = dataset.find_similar("s0", k=1, layout_key=layout_key)
    vector_similar = dataset.find_similar_by_vector([1.0, 0.0], k=1, layout_key=layout_key)

    assert [sample.id for sample, _distance in similar] == ["s1"]
    assert [sample.id for sample, _distance in vector_similar] == ["s0"]
    with pytest.raises(ValueError, match="space_key does not match"):
        dataset.find_similar("s0", k=1, space_key="other-space", layout_key=layout_key)


def test_similarity_endpoint_embeds_thumbnails_only_when_requested() -> None:
    dataset, space_key = _make_dataset()
    dataset._storage.add_sample(
        Sample(
            id="s0",
            filepath="/missing/0.png",
            label="cat",
            thumbnail_base64="query-thumb",
        )
    )
    dataset._storage.add_sample(
        Sample(
            id="s1",
            filepath="/missing/1.png",
            label="cat",
            thumbnail_base64="neighbor-thumb",
        )
    )
    client = TestClient(create_app(dataset))

    default_response = client.get("/api/search/similar/s0", params={"k": 1, "space_key": space_key})
    inline_thumbnail_response = client.get(
        "/api/search/similar/s0",
        params={"k": 1, "space_key": space_key, "include_thumbnails": "true"},
    )

    assert default_response.status_code == 200
    assert inline_thumbnail_response.status_code == 200
    assert default_response.json()["query_sample"]["thumbnail"] is None
    assert default_response.json()["results"][0]["thumbnail"] is None
    assert default_response.json()["results"][0]["media_url"] == "/api/samples/s1/content"
    assert default_response.json()["results"][0]["thumbnail_url"] == "/api/samples/s1/thumbnail"
    assert inline_thumbnail_response.json()["query_sample"]["thumbnail"] == "query-thumb"
    assert inline_thumbnail_response.json()["results"][0]["thumbnail"] == "neighbor-thumb"


def test_similarity_endpoint_uses_hyperboloid_geodesic_distance() -> None:
    dataset = Dataset("similarity_hyperboloid_api", persist=False)
    ids = ["q", "near", "far"]
    for sample_id in ids:
        dataset.add_sample(Sample(id=sample_id, filepath=f"/missing/{sample_id}.png"))

    near_distance = 0.5
    far_distance = 1.0
    vectors = np.array(
        [
            [1.0, 0.0, 0.0],
            [np.cosh(near_distance), np.sinh(near_distance), 0.0],
            [np.cosh(far_distance), 0.0, np.sinh(far_distance)],
        ],
        dtype=np.float32,
    )
    space_key = "hyperboloid_space"
    dataset._storage.ensure_space(
        model_id="hyper-model",
        dim=3,
        config={"provider": "test", "geometry": "hyperboloid", "params": {"curvature": 1.0}},
        space_key=space_key,
    )
    dataset._storage.add_embeddings(space_key, ids, vectors)

    client = TestClient(create_app(dataset))
    response = client.get("/api/search/similar/q", params={"k": 2, "space_key": space_key})

    assert response.status_code == 200
    payload = response.json()
    assert payload["metric"] == "hyperboloid"
    assert [result["id"] for result in payload["results"]] == ["near", "far"]
    assert payload["results"][0]["distance"] == pytest.approx(near_distance)
    assert payload["results"][1]["distance"] == pytest.approx(far_distance)
