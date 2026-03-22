from __future__ import annotations

from argparse import Namespace
from collections.abc import Iterator
from pathlib import Path
from random import Random
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from PIL import Image

from hyperview import Dataset
from hyperview.cli import _ingest_huggingface


class DummyHFDataset:
    def __init__(self, rows: list[dict], *, config_name: str = "default") -> None:
        self._rows = rows
        self._fingerprint = "abcdef123456"
        self.features = {
            "image": object(),
            "label": object(),
        }
        self.info = SimpleNamespace(config_name=config_name, version="1.0.0")

    def __len__(self) -> int:
        return len(self._rows)

    def __getitem__(self, index: int) -> dict:
        return self._rows[index]

    def select(self, indices: list[int]) -> DummyHFDataset:
        return DummyHFDataset(
            [self._rows[index] for index in indices],
            config_name=self.info.config_name,
        )


class DummyStorageConfig:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get_huggingface_media_dir(self, dataset_name: str, split: str) -> Path:
        media_dir = self._root / dataset_name.replace("/", "_") / split
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir


class DummyHFStreamingDataset:
    def __init__(
        self,
        rows: list[dict],
        *,
        config_name: str = "default",
        history: list[tuple] | None = None,
        selected_columns: list[str] | None = None,
    ) -> None:
        self._rows = [dict(row) for row in rows]
        self._history = history if history is not None else []
        self._selected_columns = selected_columns
        self.features = {
            "image": object(),
            "label": object(),
            "extra": object(),
        }
        self.info = SimpleNamespace(config_name=config_name, version="1.0.0")

    def _clone(
        self,
        rows: list[dict] | None = None,
        *,
        selected_columns: list[str] | None = None,
    ) -> DummyHFStreamingDataset:
        clone = DummyHFStreamingDataset(
            rows if rows is not None else self._rows,
            config_name=self.info.config_name,
            history=self._history,
            selected_columns=self._selected_columns if selected_columns is None else selected_columns,
        )
        clone.features = dict(self.features)
        return clone

    def _project_row(self, row: dict) -> dict:
        if self._selected_columns is None:
            return dict(row)
        return {
            key: value
            for key, value in row.items()
            if key in self._selected_columns or key.startswith("__hyperview_")
        }

    def select_columns(self, columns: list[str]) -> DummyHFStreamingDataset:
        self._history.append(("select_columns", tuple(columns)))
        clone = self._clone(selected_columns=list(columns))
        clone.features = {key: self.features[key] for key in columns if key in self.features}
        return clone

    def map(self, fn, with_indices: bool = False) -> DummyHFStreamingDataset:
        self._history.append(("map", with_indices))
        if not with_indices:
            raise AssertionError("streaming path should request source indices")
        mapped_rows = [fn(self._project_row(row), idx) for idx, row in enumerate(self._rows)]
        clone = self._clone(rows=mapped_rows)
        clone.features = dict(self.features)
        return clone

    def reshard(self) -> DummyHFStreamingDataset:
        self._history.append(("reshard", None))
        return self._clone()

    def shuffle(self, *, seed: int, buffer_size: int) -> DummyHFStreamingDataset:
        self._history.append(("shuffle", seed, buffer_size))
        rows = list(self._rows)
        Random(seed).shuffle(rows)
        return self._clone(rows=rows)

    def take(self, count: int) -> Iterator[dict]:
        self._history.append(("take", count))
        return iter(self._project_row(row) for row in self._rows[:count])

    def __iter__(self) -> Iterator[dict]:
        self._history.append(("iter", len(self._rows)))
        return iter(self._project_row(row) for row in self._rows)


def test_add_from_huggingface_passes_subset_config(tmp_path: Path) -> None:
    dataset = Dataset("subset_demo", persist=False)
    hf_dataset = DummyHFDataset(
        [{"image": Image.new("RGB", (8, 8), color="white"), "label": "jaguar_01"}]
    )

    with (
        patch("hyperview.core.dataset.load_dataset", return_value=hf_dataset) as load_dataset_mock,
        patch(
            "hyperview.storage.StorageConfig.default",
            return_value=DummyStorageConfig(tmp_path),
        ),
    ):
        added, skipped = dataset.add_from_huggingface(
            "hyper3labs/jaguar-re-id",
            config="default",
            split="train",
            image_key="image",
            label_key="label",
            show_progress=False,
        )

    assert (added, skipped) == (1, 0)
    load_dataset_mock.assert_called_once_with(
        "hyper3labs/jaguar-re-id",
        name="default",
        split="train",
        download_config=ANY,
    )

    sample = next(iter(dataset))
    assert sample.metadata["config"] == "default"
    assert sample.id.startswith("hyper3labs_jaguar-re-id_default_abcdef12_train_")
    assert dataset.last_requested_sample_ids == [sample.id]


def test_add_from_huggingface_tracks_requested_ids_when_samples_already_exist(
    tmp_path: Path,
) -> None:
    dataset = Dataset("subset_demo_repeat", persist=False)
    hf_dataset = DummyHFDataset(
        [{"image": Image.new("RGB", (8, 8), color="white"), "label": "jaguar_01"}]
    )

    with (
        patch("hyperview.core.dataset.load_dataset", return_value=hf_dataset),
        patch(
            "hyperview.storage.StorageConfig.default",
            return_value=DummyStorageConfig(tmp_path),
        ),
    ):
        dataset.add_from_huggingface(
            "hyper3labs/jaguar-re-id",
            config="default",
            split="train",
            image_key="image",
            label_key="label",
            show_progress=False,
        )
        added, skipped = dataset.add_from_huggingface(
            "hyper3labs/jaguar-re-id",
            config="default",
            split="train",
            image_key="image",
            label_key="label",
            show_progress=False,
        )

    assert (added, skipped) == (0, 1)
    assert dataset.last_requested_sample_ids == [
        "hyper3labs_jaguar-re-id_default_abcdef12_train_0"
    ]


def test_cli_forwards_hf_subset_config() -> None:
    dataset = Mock()
    dataset.add_from_huggingface.return_value = (2, 1)
    args = Namespace(
        hf_config="default",
        split="train",
        image_key="image",
        label_key="label",
        label_names_key=None,
        samples=100,
        shuffle=True,
        seed=42,
        hf_streaming=True,
        hf_shuffle_buffer_size=256,
    )

    _ingest_huggingface(dataset, args, "hyper3labs/jaguar-re-id")

    dataset.add_from_huggingface.assert_called_once_with(
        "hyper3labs/jaguar-re-id",
        config="default",
        split="train",
        image_key="image",
        label_key="label",
        label_names_key=None,
        max_samples=100,
        shuffle=True,
        seed=42,
        streaming=True,
        shuffle_buffer_size=256,
    )


def test_add_from_huggingface_streaming_preserves_source_indices(tmp_path: Path) -> None:
    dataset = Dataset("streaming_subset_demo", persist=False)
    history: list[tuple] = []
    hf_dataset = DummyHFStreamingDataset(
        [
            {"image": Image.new("RGB", (8, 8), color="white"), "label": "jaguar_01", "extra": "a"},
            {"image": Image.new("RGB", (8, 8), color="black"), "label": "jaguar_02", "extra": "b"},
            {"image": Image.new("RGB", (8, 8), color="gray"), "label": "jaguar_03", "extra": "c"},
        ],
        history=history,
    )

    with (
        patch("hyperview.core.dataset.load_dataset", return_value=hf_dataset) as load_dataset_mock,
        patch(
            "hyperview.storage.StorageConfig.default",
            return_value=DummyStorageConfig(tmp_path),
        ),
    ):
        added, skipped = dataset.add_from_huggingface(
            "hyper3labs/jaguar-re-id",
            config="default",
            split="train",
            image_key="image",
            label_key="label",
            max_samples=2,
            streaming=True,
            show_progress=False,
        )

    assert (added, skipped) == (2, 0)
    load_dataset_mock.assert_called_once_with(
        "hyper3labs/jaguar-re-id",
        name="default",
        split="train",
        streaming=True,
    )
    assert ("select_columns", ("image", "label")) in history
    assert ("map", True) in history
    assert ("take", 2) in history

    samples = list(dataset)
    assert [sample.metadata["index"] for sample in samples] == [0, 1]
    assert [sample.label for sample in samples] == ["jaguar_01", "jaguar_02"]


def test_add_from_huggingface_streaming_shuffle_uses_buffer_size(tmp_path: Path) -> None:
    dataset = Dataset("streaming_shuffle_demo", persist=False)
    history: list[tuple] = []
    hf_dataset = DummyHFStreamingDataset(
        [
            {"image": Image.new("RGB", (8, 8), color="white"), "label": "jaguar_01"},
            {"image": Image.new("RGB", (8, 8), color="black"), "label": "jaguar_02"},
            {"image": Image.new("RGB", (8, 8), color="gray"), "label": "jaguar_03"},
        ],
        history=history,
    )

    with (
        patch("hyperview.core.dataset.load_dataset", return_value=hf_dataset),
        patch(
            "hyperview.storage.StorageConfig.default",
            return_value=DummyStorageConfig(tmp_path),
        ),
    ):
        added, skipped = dataset.add_from_huggingface(
            "hyper3labs/jaguar-re-id",
            config="default",
            split="train",
            image_key="image",
            label_key="label",
            max_samples=2,
            shuffle=True,
            seed=7,
            streaming=True,
            shuffle_buffer_size=7,
            show_progress=False,
        )

    assert (added, skipped) == (2, 0)
    assert ("reshard", None) in history
    assert ("shuffle", 7, 7) in history
    indices = [sample.metadata["index"] for sample in dataset]
    assert len(indices) == 2
    assert len(set(indices)) == 2
    assert set(indices).issubset({0, 1, 2})
