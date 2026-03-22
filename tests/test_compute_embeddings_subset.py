from __future__ import annotations

from unittest.mock import Mock, patch

import numpy as np

from hyperview import Dataset
from hyperview.core.sample import Sample


def test_compute_embeddings_can_be_limited_to_requested_sample_ids() -> None:
    dataset = Dataset("subset_embeddings_demo", persist=False)
    dataset.add_sample(Sample(id="s0", filepath="/tmp/s0.png"))
    dataset.add_sample(Sample(id="s1", filepath="/tmp/s1.png"))
    dataset.add_sample(Sample(id="s2", filepath="/tmp/s2.png"))

    engine = Mock()
    engine.get_space_config.return_value = {"provider": "mock"}
    engine.embed_images.return_value = np.array(
        [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        dtype=np.float32,
    )

    with patch("hyperview.embeddings.engine.get_engine", return_value=engine):
        space_key = dataset.compute_embeddings(
            model="mock-model",
            sample_ids=["s0", "s1"],
            show_progress=False,
        )

    assert [sample.id for sample in engine.embed_images.call_args.kwargs["samples"]] == ["s0", "s1"]

    engine.embed_images.reset_mock()

    with patch("hyperview.embeddings.engine.get_engine", return_value=engine):
        same_space_key = dataset.compute_embeddings(
            model="mock-model",
            sample_ids=["s0", "s1"],
            show_progress=False,
        )

    assert same_space_key == space_key
    engine.embed_images.assert_not_called()

    engine.embed_images.return_value = np.array([[0.7, 0.8, 0.9]], dtype=np.float32)

    with patch("hyperview.embeddings.engine.get_engine", return_value=engine):
        dataset.compute_embeddings(model="mock-model", show_progress=False)

    assert [sample.id for sample in engine.embed_images.call_args.kwargs["samples"]] == ["s2"]
