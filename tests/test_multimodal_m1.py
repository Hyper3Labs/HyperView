from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.server.app import create_app
from hyperview.storage import LanceDBBackend, StorageConfig


class _StubMultimodalProvider:
    supports = {"image", "text"}

    def __init__(self) -> None:
        self.image_inputs: list[str] = []
        self.text_inputs: list[str] = []

    @property
    def geometry(self) -> str:
        return "euclidean"

    def compute_source_embeddings(self, inputs: list[str]) -> list[np.ndarray]:
        self.image_inputs.extend(inputs)
        return [np.asarray([1.0, float(index)], dtype=np.float32) for index, _ in enumerate(inputs)]

    def compute_query_embeddings(self, query: str) -> list[np.ndarray]:
        self.text_inputs.append(query)
        return [np.asarray([0.0, float(len(query))], dtype=np.float32)]


class _StubImageProvider(_StubMultimodalProvider):
    supports = {"image"}


class _StubRegistry:
    def __init__(self, provider: Any) -> None:
        self.provider = provider

    def get(self, alias: str) -> object | None:
        return object() if alias == "stub" else None

    def instantiate(self, alias: str, **_kwargs: Any) -> Any:
        assert alias == "stub"
        return self.provider


def test_add_texts_round_trips_files_and_field_registry(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps({"doc_id": "a", "body": "first document", "topic": "news"}),
                json.dumps({"doc_id": "b", "body": "second document", "topic": "science"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = StorageConfig(datasets_dir=tmp_path / "datasets", media_dir=tmp_path / "media")
    backend = LanceDBBackend("text_roundtrip", config)
    dataset = Dataset("text_roundtrip", storage=backend)

    assert dataset.add_texts(
        source,
        text_field="body",
        label_field="topic",
        id_field="doc_id",
    ) == (2, 0)
    backend.close()

    restored = Dataset(
        "text_roundtrip",
        storage=LanceDBBackend("text_roundtrip", config),
    )
    assert restored["a"].metadata == {}
    assert restored["a"].text == "first document"
    assert restored["a"].label == "news"
    assert restored["a"].filepath is None
    assert restored["a"].modality == "text"
    assert restored["a"].media_type == "text/plain"
    assert restored.fields["text"] == {
        "type": "text",
        "nullable": False,
        "source": "body",
    }
    assert restored.fields["label"]["source"] == "topic"
    assert restored.fields["id"]["source"] == "doc_id"
    assert [sample.id for sample in restored._find_text_matches("second", 5)] == ["b"]

    csv_source = tmp_path / "more.csv"
    csv_source.write_text("id,text,label\nc,csv document,archive\n", encoding="utf-8")
    assert restored.add_texts(csv_source) == (1, 0)
    assert restored["c"].text == "csv document"


def test_mixed_image_and_text_samples_embed_into_one_space_and_skip_existing() -> None:
    dataset = Dataset("mixed_embedding", persist=False)
    dataset.add_sample(Sample(id="image", filepath="/virtual/image.png"))
    dataset.add_texts([{"id": "text", "text": "caption"}])
    provider = _StubMultimodalProvider()
    registry = _StubRegistry(provider)

    space_key = dataset.compute_embeddings(
        model="stub-model",
        provider="stub",
        show_progress=False,
        _provider_registry=registry,
    )

    ids, vectors = dataset._storage.get_embeddings(space_key)
    assert set(ids) == {"image", "text"}
    assert vectors.shape == (2, 2)
    assert provider.image_inputs == ["/virtual/image.png"]
    assert provider.text_inputs == ["caption"]

    dataset.add_texts([{"id": "text-2", "text": "new caption"}])
    dataset.compute_embeddings(
        model="stub-model",
        provider="stub",
        show_progress=False,
        _provider_registry=registry,
    )
    assert provider.image_inputs == ["/virtual/image.png"]
    assert provider.text_inputs == ["caption", "new caption"]


def test_embedding_provider_capability_error_names_missing_modality() -> None:
    dataset = Dataset("text_capability", persist=False)
    dataset.add_texts([{"id": "text", "text": "cannot encode me"}])

    with pytest.raises(
        ValueError,
        match=r"does not support required modality 'text'.*supported modalities: \['image'\]",
    ):
        dataset.compute_embeddings(
            model="stub-model",
            provider="stub",
            show_progress=False,
            _provider_registry=_StubRegistry(_StubImageProvider()),
        )


def test_hybrid_text_search_uses_rrf_and_is_opt_in() -> None:
    dataset = Dataset("hybrid_search", persist=False)
    dataset.add_texts(
        [
            {"id": "vector-first", "text": "ordinary document"},
            {"id": "fts-first", "text": "rare exact phrase"},
            {"id": "other", "text": "unrelated"},
        ]
    )
    dataset._storage.ensure_space(
        model_id="stub-model",
        dim=2,
        config={"provider": "stub", "geometry": "euclidean", "modality": "multimodal"},
        space_key="mixed-space",
    )
    dataset._storage.add_embeddings(
        "mixed-space",
        ["vector-first", "fts-first", "other"],
        np.asarray([[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]], dtype=np.float32),
    )
    engine = SimpleNamespace(
        embed_texts=lambda _texts, _spec: np.asarray([[1.0, 0.0]], dtype=np.float32)
    )
    app = create_app(dataset)
    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {app.state.api_token}"},
    )

    with patch("hyperview.embeddings.engine.get_engine", return_value=engine):
        vector_response = client.post(
            "/api/search/text",
            json={"query_text": "rare", "space_key": "mixed-space", "k": 2},
        )
        hybrid_response = client.post(
            "/api/search/text",
            json={
                "query_text": "rare",
                "space_key": "mixed-space",
                "k": 2,
                "hybrid": True,
            },
        )

    assert vector_response.status_code == 200
    assert vector_response.json()["results"][0]["id"] == "vector-first"
    assert hybrid_response.status_code == 200
    assert hybrid_response.json()["metric"] == "hybrid_rrf"
    assert hybrid_response.json()["results"][0]["id"] == "fts-first"
