from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import lancedb
import pyarrow as pa
from fastapi.testclient import TestClient

from hyperview import Dataset
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.server.app import create_app
from hyperview.static_export import export_runtime_workspace
from hyperview.storage import LanceDBBackend, StorageConfig


def _storage(tmp_path: Path, name: str) -> LanceDBBackend:
    return LanceDBBackend(
        name,
        StorageConfig(datasets_dir=tmp_path / "datasets", media_dir=tmp_path / "media"),
    )


def test_text_only_sample_round_trips_api_and_static_export_without_pil(tmp_path: Path) -> None:
    dataset = Dataset("text-only", storage=_storage(tmp_path, "text-only"))
    dataset.add_sample(
        Sample(
            id="text-1",
            filepath=None,
            text="A text-only record",
            modality="text",
            media_type=None,
            metadata={"language": "en"},
        )
    )

    reopened = Dataset("text-only", storage=_storage(tmp_path, "text-only"))
    sample = reopened["text-1"]
    assert sample.filepath is None
    assert sample.text == "A text-only record"
    assert sample.width is None
    assert sample.height is None

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("default", reopened, activate_workspace=True)
    app = create_app(runtime=runtime)
    client = TestClient(app, headers={"Authorization": f"Bearer {app.state.api_token}"})

    with patch("PIL.Image.open", side_effect=AssertionError("PIL must not be called")):
        sample_response = client.get("/api/samples/text-1", params={"include_thumbnails": True})
        thumbnail_response = client.get("/api/samples/text-1/thumbnail")
        out_dir = tmp_path / "bundle"
        export_runtime_workspace(runtime, "default", out_dir, similarity_k=0)

    assert sample_response.status_code == 200
    assert sample_response.json()["filepath"] is None
    assert sample_response.json()["media_type"] is None
    assert sample_response.json()["thumbnail"] is None
    assert thumbnail_response.status_code == 404

    shard = json.loads(
        (out_dir / "api" / "samples" / "shards" / "000000.json").read_text()
    )
    assert shard["samples"][0]["text"] == "A text-only record"
    assert shard["samples"][0]["filepath"] is None
    assert not (out_dir / "api" / "samples" / "text-1" / "content").exists()


def test_existing_samples_table_evolves_for_multimodal_columns(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "datasets" / "legacy"
    dataset_dir.mkdir(parents=True)
    db = lancedb.connect(dataset_dir)
    legacy_schema = pa.schema(
        [
            pa.field("id", pa.utf8(), nullable=False),
            pa.field("filepath", pa.utf8(), nullable=False),
            pa.field("label", pa.utf8(), nullable=True),
            pa.field("text", pa.utf8(), nullable=True),
            pa.field("modality", pa.utf8(), nullable=False),
            pa.field("metadata_json", pa.utf8(), nullable=True),
            pa.field("thumbnail_base64", pa.utf8(), nullable=True),
        ]
    )
    db.create_table(
        "samples",
        data=pa.Table.from_pylist(
            [
                {
                    "id": "image-1",
                    "filepath": "/tmp/image.png",
                    "label": None,
                    "text": None,
                    "modality": "image",
                    "metadata_json": None,
                    "thumbnail_base64": None,
                }
            ],
            schema=legacy_schema,
        ),
    )

    storage = _storage(tmp_path, "legacy")
    assert storage._samples_table is not None
    assert storage._samples_table.schema.field("filepath").nullable
    assert storage._samples_table.schema.field("media_type").type == pa.utf8()
    assert storage._samples_table.schema.field("duration_s").type == pa.float64()

    storage.add_sample(Sample(id="text-1", filepath=None, text="hello", modality="text"))
    assert storage.get_sample("text-1").filepath is None


def test_dataset_api_exposes_typed_field_catalog(tmp_path: Path) -> None:
    dataset = Dataset("fields", persist=False)
    dataset.add_sample(
        Sample(
            id="sample-1",
            filepath=None,
            text="hello",
            modality="text",
            metadata={"language": "en"},
        )
    )
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("default", dataset, activate_workspace=True)
    app = create_app(runtime=runtime)
    client = TestClient(app, headers={"Authorization": f"Bearer {app.state.api_token}"})

    response = client.get("/api/dataset")

    assert response.status_code == 200
    fields = response.json()["fields"]
    assert fields["id"] == {"type": "scalar", "nullable": False, "source": "builtin"}
    assert fields["filepath"]["type"] == "media"
    assert fields["text"]["type"] == "text"
    assert fields["label"]["type"] == "label"
    assert fields["metadata.language"]["source"] == "metadata"
