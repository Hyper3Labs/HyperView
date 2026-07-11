from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from hyperview import Dataset
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.sample import Sample
from hyperview.runtime import (
    HyperViewRuntime,
    ProviderRegistry,
    SimilarityQueryState,
    WorkspaceRegistry,
)
from hyperview.storage.schema import dict_to_sample, sample_to_dict


class _CanonicalEmbedAnythingProvider:
    supports = {"image", "text"}
    geometry = "euclidean"

    def compute_source_embeddings(self, inputs: list[str]) -> list[np.ndarray]:
        return [
            np.asarray([1.0, float(index)], dtype=np.float32)
            for index, _ in enumerate(inputs)
        ]

    def compute_query_embeddings(self, _query: str) -> list[np.ndarray]:
        return [np.asarray([1.0, 0.0], dtype=np.float32)]


class _CanonicalProviderRegistry:
    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.requested_aliases: list[str] = []

    def get(self, alias: str) -> object | None:
        self.requested_aliases.append(alias)
        return object() if alias == "embed-anything" else None

    def instantiate(self, alias: str, **_kwargs: Any) -> Any:
        assert alias == "embed-anything"
        return self.provider


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
            command="panel.samples.retrieval.set-text-query",
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


def test_legacy_embed_anything_space_resolves_canonical_provider() -> None:
    dataset = Dataset("legacy_provider_alias", persist=False)
    dataset.add_sample(Sample(id="s0", filepath="/virtual/s0.png"))
    dataset._storage.ensure_space(
        model_id="openai/clip-vit-base-patch32",
        dim=2,
        config={"provider": "embed_anything", "geometry": "euclidean"},
        space_key="legacy_alias_space",
    )
    dataset._storage.add_embeddings(
        "legacy_alias_space",
        ["s0"],
        np.asarray([[1.0, 0.0]], dtype=np.float32),
    )
    registry = _CanonicalProviderRegistry(_CanonicalEmbedAnythingProvider())

    results = dataset.find_similar_by_text(
        "a sample",
        space_key="legacy_alias_space",
        _provider_registry=registry,
    )

    assert results[0][0].id == "s0"
    assert registry.requested_aliases
    assert set(registry.requested_aliases) == {"embed-anything"}


def test_unknown_provider_legacy_clip_space_resolves_canonical_provider() -> None:
    dataset = Dataset("legacy_unknown_clip", persist=False)
    dataset.add_sample(Sample(id="s0", filepath="/virtual/s0.png"))
    dataset._storage.ensure_space(
        model_id="openai/clip-vit-base-patch32",
        dim=2,
        config=None,
        space_key="legacy_unknown_space",
    )
    dataset._storage.add_embeddings(
        "legacy_unknown_space",
        ["s0"],
        np.asarray([[1.0, 0.0]], dtype=np.float32),
    )
    registry = _CanonicalProviderRegistry(_CanonicalEmbedAnythingProvider())

    results = dataset.find_similar_by_text(
        "a sample",
        space_key="legacy_unknown_space",
        _provider_registry=registry,
    )

    assert results[0][0].id == "s0"
    assert set(registry.requested_aliases) == {"embed-anything"}


def test_unknown_provider_unrecognized_model_requires_metadata_migration() -> None:
    dataset = Dataset("legacy_unknown_unrecognized", persist=False)
    dataset._storage.ensure_space(
        model_id="custom/image-model-v1",
        dim=2,
        config=None,
        space_key="unrecognized_space",
    )

    with pytest.raises(
        ValueError,
        match=(
            r"Embedding space 'unrecognized_space' has stored provider 'unknown'.*"
            r"Migrate the space metadata"
        ),
    ):
        dataset._embedding_spec_for_space("unrecognized_space")


def test_compute_embeddings_persists_canonical_provider_for_legacy_alias() -> None:
    dataset = Dataset("canonical_compute_provider", persist=False)
    dataset.add_sample(Sample(id="s0", filepath="/virtual/s0.png"))
    registry = _CanonicalProviderRegistry(_CanonicalEmbedAnythingProvider())

    space_key = dataset.compute_embeddings(
        model="openai/clip-vit-base-patch32",
        provider="embed_anything",
        show_progress=False,
        _provider_registry=registry,
    )

    space = next(item for item in dataset.list_spaces() if item.space_key == space_key)
    assert space_key.startswith("embed-anything__")
    assert space.config is not None
    assert space.config["provider"] == "embed-anything"
    assert set(registry.requested_aliases) == {"embed-anything"}
