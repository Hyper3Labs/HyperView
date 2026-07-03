from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np

from hyperview import Dataset
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, SimilarityQueryState, WorkspaceRegistry
from hyperview.storage.schema import dict_to_sample, sample_to_dict


def _service(tmp_path: Path) -> ControlService:
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    dataset = Dataset("text_retrieval", persist=False)
    dataset.add_sample(
        Sample(
            id="s0",
            filepath="/virtual/s0.png",
            label="dog",
            text="a dog in the park",
            modality="multimodal",
        )
    )
    dataset.add_sample(
        Sample(
            id="s1",
            filepath="/virtual/s1.png",
            label="cat",
            text="a cat on a sofa",
            modality="multimodal",
        )
    )
    dataset._storage.ensure_space(
        model_id="openai/clip-vit-base-patch32",
        dim=3,
        config={"provider": "embed-anything", "geometry": "euclidean", "modality": "multimodal"},
        space_key="clip_space",
    )
    dataset._storage.add_embeddings(
        "clip_space",
        ["s0", "s1"],
        np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32),
    )
    runtime.attach_dataset_instance("default", dataset)
    return ControlService(runtime, create_default_command_registry())


def test_sample_schema_roundtrip_includes_text_and_modality() -> None:
    sample = Sample(
        id="abc",
        filepath="/tmp/abc.png",
        label="label",
        text="hello world",
        modality="multimodal",
    )
    restored = dict_to_sample(sample_to_dict(sample))
    assert restored.text == "hello world"
    assert restored.modality == "multimodal"


def test_similarity_query_state_supports_text_only() -> None:
    query = SimilarityQueryState.from_dict(
        {"query_text": "a dog playing", "k": 12, "space_key": "clip_space"}
    )
    assert query is not None
    assert query.query_text == "a dog playing"
    assert query.anchor_sample_id is None
    assert query.k == 12


def test_control_command_sets_text_retrieval_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.run(
        CommandEnvelope(
            command="samples.retrieval.set-text-query",
            target={"workspace_id": "default"},
            args={"query_text": "a dog in the park", "space_key": "clip_space", "k": 5},
        )
    )
    assert result.ok is True
    retrieval = result.workspace["ui"]["panels"]["samples"]["state"]["retrieval"]
    assert retrieval["query_text"] == "a dog in the park"
    assert retrieval["space_key"] == "clip_space"
    assert result.workspace["ui"]["panels"]["samples"]["state"]["collection"]["kind"] == "search"


def test_dataset_find_similar_by_text_uses_encoded_vector(tmp_path: Path) -> None:
    dataset = Dataset("text_query", persist=False)
    dataset.add_sample(Sample(id="s0", filepath="/virtual/s0.png", text="dog"))
    dataset.add_sample(Sample(id="s1", filepath="/virtual/s1.png", text="cat"))
    dataset._storage.ensure_space(
        model_id="openai/clip-vit-base-patch32",
        dim=3,
        config={"provider": "embed-anything", "geometry": "euclidean", "modality": "multimodal"},
        space_key="clip_space",
    )
    dataset._storage.add_embeddings(
        "clip_space",
        ["s0", "s1"],
        np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)[:2],
    )

    query_vector = np.asarray([0.95, 0.05, 0.0], dtype=np.float32)
    with patch("hyperview.embeddings.engine.get_engine") as get_engine:
        engine = get_engine.return_value
        engine.embed_texts.return_value = np.asarray([query_vector], dtype=np.float32)
        results = dataset.find_similar_by_text("dog in park", k=1, space_key="clip_space")

    assert len(results) == 1
    assert results[0][0].id == "s0"
