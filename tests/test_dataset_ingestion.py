from __future__ import annotations

from unittest.mock import patch

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.storage import LanceDBBackend, StorageConfig


def test_add_samples_batches_and_skips_existing_rows() -> None:
    dataset = Dataset("batch_samples_demo", persist=False)

    added, skipped = dataset.add_samples(
        [
            Sample(
                id="a",
                filepath="/tmp/a.png",
                label="alpha",
                metadata={"kind": "first"},
            ),
            Sample(
                id="b",
                filepath="/tmp/b.png",
                label="beta",
                metadata={"kind": "second"},
            ),
        ],
        skip_existing=True,
    )

    assert (added, skipped) == (2, 0)
    assert len(dataset) == 2
    assert dataset["a"].label == "alpha"
    assert dataset["b"].metadata["kind"] == "second"

    with patch.object(
        dataset._storage,
        "add_samples_batch",
        wraps=dataset._storage.add_samples_batch,
    ) as add_samples_batch:
        added, skipped = dataset.add_samples(
            [
                Sample(id="a", filepath="/tmp/a-new.png", label="new"),
                Sample(id="b", filepath="/tmp/b-new.png", label="new"),
                Sample(id="c", filepath="/tmp/c.png", label="gamma"),
            ],
            skip_existing=True,
        )

    assert (added, skipped) == (1, 2)
    add_samples_batch.assert_called_once()
    assert [sample.id for sample in add_samples_batch.call_args.args[0]] == ["c"]
    assert dataset["a"].label == "alpha"
    assert dataset["c"].label == "gamma"


def test_add_samples_can_batch_refresh_existing_rows() -> None:
    dataset = Dataset("batch_samples_refresh_demo", persist=False)
    dataset.add_samples(
        [Sample(id="a", filepath="/tmp/a.png", label="old")],
    )

    with patch.object(
        dataset._storage,
        "add_samples_batch",
        wraps=dataset._storage.add_samples_batch,
    ) as add_samples_batch:
        added, skipped = dataset.add_samples(
            [Sample(id="a", filepath="/tmp/a-new.png", label="new")],
            skip_existing=False,
        )

    assert (added, skipped) == (1, 0)
    add_samples_batch.assert_called_once()
    assert dataset["a"].label == "new"
    assert dataset["a"].filepath == "/tmp/a-new.png"


def test_add_samples_deduplicates_incoming_sample_ids_last_wins() -> None:
    dataset = Dataset("batch_samples_duplicate_ids_demo", persist=False)

    added, skipped = dataset.add_samples(
        [
            Sample(id="same", filepath="/tmp/first.png", label="old"),
            Sample(id="same", filepath="/tmp/second.png", label="new"),
        ]
    )

    assert (added, skipped) == (1, 0)
    assert len(dataset) == 1
    assert dataset["same"].label == "new"
    assert dataset["same"].filepath == "/tmp/second.png"


def test_add_sample_uses_batch_write_path() -> None:
    dataset = Dataset("single_sample_batch_path_demo", persist=False)
    sample = Sample(id="a", filepath="/tmp/a.png", label="alpha")

    with patch.object(
        dataset,
        "add_samples",
        wraps=dataset.add_samples,
    ) as add_samples:
        dataset.add_sample(sample)

    add_samples.assert_called_once()
    assert add_samples.call_args.args[0] == [sample]
    assert add_samples.call_args.kwargs == {"skip_existing": False}
    assert dataset["a"].label == "alpha"


def test_lancedb_backend_deduplicates_batch_before_merge_insert(tmp_path) -> None:
    storage = LanceDBBackend(
        "lancedb_duplicate_ids_demo",
        StorageConfig(
            datasets_dir=tmp_path / "datasets",
            media_dir=tmp_path / "media",
        ),
    )

    storage.add_samples_batch(
        [
            Sample(id="same", filepath="/tmp/first.png", label="old"),
            Sample(id="same", filepath="/tmp/second.png", label="new"),
        ]
    )

    assert len(storage) == 1
    assert storage.get_sample("same").label == "new"
    assert any("id" in index.columns for index in storage._samples_table.list_indices())

    storage.add_samples_batch(
        [
            Sample(id="same", filepath="/tmp/third.png", label="refreshed"),
            Sample(id="other", filepath="/tmp/other.png", label="other"),
        ]
    )

    assert len(storage) == 2
    assert storage.get_sample("same").label == "refreshed"


def test_lancedb_backend_indexes_filter_columns_and_counts_filtered_rows(tmp_path) -> None:
    storage = LanceDBBackend(
        "lancedb_filter_indices_demo",
        StorageConfig(
            datasets_dir=tmp_path / "datasets",
            media_dir=tmp_path / "media",
        ),
    )
    storage.add_samples_batch(
        [
            Sample(id="a", filepath="/tmp/a.png", label="cat"),
            Sample(id="b", filepath="/tmp/b.png", label="dog"),
            Sample(id="c", filepath="/tmp/c.png", label="kid's label"),
        ]
    )

    filtered, total = storage.get_samples_paginated(label="kid's label")

    assert total == 1
    assert [sample.id for sample in filtered] == ["c"]
    sample_indices = {
        index.columns[0]: index.index_type.lower()
        for index in storage._samples_table.list_indices()
    }
    assert sample_indices["id"] == "btree"
    assert sample_indices["label"] == "bitmap"

    storage.ensure_layout("demo_space__euclidean_umap__2d", "demo_space", "umap", "euclidean")
    storage.add_layout_coords(
        "demo_space__euclidean_umap__2d",
        ["a", "b", "c"],
        [[0.0, 0.0], [5.0, 5.0], [1.0, 1.0]],
    )

    candidate_ids, coords = storage.get_lasso_candidates_aabb(
        layout_key="demo_space__euclidean_umap__2d",
        x_min=-1.0,
        x_max=2.0,
        y_min=-1.0,
        y_max=2.0,
        label_filter="kid's label",
    )

    assert candidate_ids == ["c"]
    assert coords.tolist() == [[1.0, 1.0]]
    layout_table = storage._db.open_table("layouts__demo_space__euclidean_umap__2d")
    layout_indices = {
        index.columns[0]: index.index_type.lower() for index in layout_table.list_indices()
    }
    assert layout_indices["id"] == "btree"
    assert layout_indices["x"] == "btree"
    assert layout_indices["y"] == "btree"
