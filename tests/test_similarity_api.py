from __future__ import annotations

import numpy as np
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