from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import numpy as np
from PIL import Image

from hyperview import Dataset, Session
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.static_export import export_runtime_workspace


def _write_extension(folder: Path) -> None:
    folder.mkdir(parents=True)
    (folder / "extension.toml").write_text(
        "\n".join(
            [
                'name = "export-demo"',
                "",
                "[[panels]]",
                'id = "readout"',
                'title = "Readout"',
                'position = "right"',
                'file = "panel.js"',
                "",
                "[[panels]]",
                'id = "server-readout"',
                'title = "Server Readout"',
                'position = "bottom"',
                'file = "server-panel.js"',
                "static_compatible = false",
                'static_reason = "Requires a Python extension tool."',
            ]
        ),
        encoding="utf-8",
    )
    (folder / "server-panel.js").write_text(
        "export default function Panel() { return null; }\n",
        encoding="utf-8",
    )
    (folder / "panel.js").write_text(
        "export default function Panel() { return null; }\n",
        encoding="utf-8",
    )


def _make_runtime(tmp_path: Path) -> HyperViewRuntime:
    dataset = Dataset("static_export_dataset", persist=False)
    sample_ids: list[str] = []
    for index, label in enumerate(["cat", "dog", "cat"]):
        image_path = tmp_path / f"sample-{index}.png"
        Image.new("RGB", (12 + index, 10 + index), (index * 40, 40, 180)).save(image_path)
        sample_id = f"sample-{index}"
        sample_ids.append(sample_id)
        dataset.add_sample(
            Sample(
                id=sample_id,
                filepath=str(image_path),
                label=label,
                metadata={"index": index},
            )
        )
    layout_key = dataset.set_coords(
        "euclidean",
        sample_ids,
        np.asarray([[0.0, 0.0], [1.0, 0.5], [2.0, 0.25]], dtype=np.float32),
    )

    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("demo", dataset, activate_workspace=True)
    runtime.set_active_layout("demo", layout_key)

    extension_dir = tmp_path / "export-demo-extension"
    _write_extension(extension_dir)
    runtime.install_extension("demo", extension_dir, add_panels=True)
    return runtime


def _add_text_search_space(dataset: Dataset, sample_ids: list[str]) -> str:
    space_key = "text_search_space"
    dataset._storage.ensure_space(
        model_id="test-text-model",
        dim=2,
        config={"provider": "test", "geometry": "euclidean", "modality": "multimodal"},
        space_key=space_key,
    )
    dataset._storage.add_embeddings(
        space_key,
        sample_ids,
        np.asarray([[1.0, 0.0], [0.8, 0.2], [-1.0, 0.0]], dtype=np.float32),
    )
    return space_key


def test_static_export_writes_bundle_snapshot_samples_media_and_flag(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    dataset = runtime.get_dataset(workspace_id="demo")
    space_key = _add_text_search_space(dataset, [sample.id for sample in dataset.samples])
    out_dir = tmp_path / "bundle"

    result = export_runtime_workspace(runtime, "demo", out_dir, similarity_k=2)

    assert result.workspace_id == "demo"
    assert result.num_samples == 3
    assert result.num_layouts == 1
    assert result.num_similarity_queries == 3
    assert result.similarity_k == 2
    assert result.num_files > 0
    assert result.bundle_bytes > 0

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "window.__HYPERVIEW_STATIC__ = true;" in index_html

    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text(encoding="utf-8"))
    assert snapshot["workspace"]["id"] == "demo"
    assert snapshot["workspace"]["ui"]["active_layout_key"]
    assert snapshot["panel_definitions"]
    panels = {panel["id"]: panel for panel in snapshot["workspace"]["ui"]["custom_panels"]}
    assert panels["readout"]["data"]["static_compatible"] is True
    assert panels["server-readout"]["data"]["static_compatible"] is False

    dataset_payload = json.loads((out_dir / "api" / "dataset.json").read_text(encoding="utf-8"))
    spaces_by_id = {space["space_key"]: space for space in dataset_payload["spaces"]}
    representations_by_id = {
        representation["id"]: representation
        for representation in dataset_payload["representations"]
    }
    indexes_by_representation = {
        index["representation_id"]: index for index in dataset_payload["indexes"]
    }
    expected_space = next(space for space in dataset.list_spaces() if space.space_key == space_key)
    assert representations_by_id[space_key] == expected_space.to_representation_dict()
    assert indexes_by_representation[space_key] == expected_space.to_index_dict()
    assert spaces_by_id.keys() == representations_by_id.keys() == indexes_by_representation.keys()

    samples_index = json.loads((out_dir / "api" / "samples" / "index.json").read_text(encoding="utf-8"))
    assert samples_index["total"] == 3
    shard_entry = samples_index["shards"][0]
    assert shard_entry["sample_ids"] == ["sample-0", "sample-1", "sample-2"]
    assert {entry["value"]: entry["count"] for entry in shard_entry["label_counts"]} == {
        "cat": 2,
        "dog": 1,
    }
    shard = json.loads(
        (out_dir / "api" / "samples" / shard_entry["path"]).read_text(encoding="utf-8")
    )
    assert shard["samples"][0]["media_url"] == "/api/samples/sample-0/content"
    assert shard["samples"][0]["thumbnail_url"] == "/api/samples/sample-0/thumbnail"

    assert (out_dir / "api" / "samples" / "sample-0" / "content").is_file()
    assert (out_dir / "api" / "samples" / "sample-0" / "thumbnail").is_file()
    assert not (out_dir / "media").exists()
    assert (out_dir / "api" / "embeddings" / "default.json").is_file()
    assert (out_dir / "api" / "panels" / "content" / "demo" / "readout" / "panel.js").is_file()
    assert not (
        out_dir / "api" / "panels" / "content" / "demo" / "server-readout" / "server-panel.js"
    ).exists()

    similarity_index = json.loads(
        (out_dir / "api" / "search" / "similar" / "index.json").read_text(encoding="utf-8")
    )
    assert similarity_index["default_space_key"] == space_key
    assert similarity_index["k"] == 2
    similarity_shard = similarity_index["spaces"][space_key]["shards"][0]
    similarity_payload = json.loads(
        (out_dir / "api" / "search" / "similar" / similarity_shard["path"]).read_text(
            encoding="utf-8"
        )
    )
    assert similarity_payload["queries"]["sample-0"]["results"][0].keys() == {
        "distance",
        "sample_id",
    }

    manifest = json.loads((out_dir / "hyperview-static.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "hyperview-static-space"
    assert manifest["workspace"]["fingerprint"]
    assert manifest["capabilities"]["sample_similarity"] is True
    assert manifest["capabilities"]["python_tools"] is False
    assert manifest["deployment"]["cloudflare"]["mode"] == "static-assets-only"
    wrangler = json.loads((out_dir / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert wrangler["assets"]["directory"] == "."
    assert wrangler["assets"]["not_found_handling"] == "single-page-application"


def test_session_export_uses_runtime_workspace(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    session = Session(runtime, "127.0.0.1", 6262)
    out_dir = tmp_path / "session-bundle"

    payload = session.export(out_dir, workspace_id="demo", similarity_k=0)

    assert payload["workspace_id"] == "demo"
    assert Path(payload["output_dir"]).is_dir()
    assert (out_dir / "hyperview-static.json").is_file()
    assert payload["similarity_k"] == 0
    assert not (out_dir / "api" / "search" / "similar" / "index.json").exists()


def test_static_export_materializes_text_search_collections(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    dataset = runtime.get_dataset(workspace_id="demo")
    space_key = _add_text_search_space(dataset, [sample.id for sample in dataset.samples])
    service = ControlService(runtime, create_default_command_registry())
    result = service.run(
        CommandEnvelope(
            command="panel.samples.retrieval.set-text-query",
            target={"workspace_id": "demo"},
            args={
                "query_text": "cat sample",
                "space_key": space_key,
                "k": 2,
                "source": "test",
            },
        )
    )
    assert result.ok is True
    collection_id = result.result["collection"]["id"]
    out_dir = tmp_path / "text-search-bundle"

    with patch("hyperview.embeddings.engine.get_engine") as get_engine:
        engine = get_engine.return_value
        engine.embed_texts.return_value = np.asarray([[1.0, 0.0]], dtype=np.float32)
        export_runtime_workspace(runtime, "demo", out_dir)

    items_path = out_dir / "api" / "collections" / quote(collection_id, safe="") / "items.json"
    payload = json.loads(items_path.read_text(encoding="utf-8"))

    assert payload["collection_id"] == collection_id
    assert payload["total"] == 2
    assert [item["sample_id"] for item in payload["items"]]
    assert all(item["score"] is not None for item in payload["items"])


def test_static_ephemeral_filter_resolves_samples_without_collection_file_fetch() -> None:
    script = r"""
const fs = require("fs");
const ts = require("./frontend/node_modules/typescript");
const source = fs.readFileSync("./frontend/src/lib/api.ts", "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  fileName: "api.ts",
}).outputText;

global.window = {
  __HYPERVIEW_STATIC__: true,
  location: { href: "https://example.test/index.html" },
  dispatchEvent: () => {},
};

const requests = [];
const payloads = {
  "/api/runtime.json": {
    version: 1,
    workspace: {
      id: "demo",
      dataset_name: "static_export_dataset",
      collections: [],
      ui: { selected_ids: [], panels: {}, custom_panels: [] },
    },
  },
  "/api/samples/index.json": {
    total: 3,
    shard_size: 500,
    shards: [{
      path: "shards/000000.json",
      offset: 0,
      count: 3,
      sample_ids: ["sample-0", "sample-1", "sample-2"],
    }],
  },
  "/api/samples/shards/000000.json": {
    total: 3,
    offset: 0,
    limit: 500,
    samples: [
      { id: "sample-0", label: "cat" },
      { id: "sample-1", label: "dog" },
      { id: "sample-2", label: "cat" },
    ],
  },
};
global.fetch = async (url) => {
  const path = new URL(url).pathname;
  requests.push(path);
  const payload = payloads[path];
  return new Response(payload === undefined ? "missing" : JSON.stringify(payload), {
    status: payload === undefined ? 404 : 200,
    headers: { "content-type": payload === undefined ? "text/plain" : "application/json" },
  });
};

const module = { exports: {} };
new Function("exports", "require", "module", "__filename", "__dirname", compiled)(
  module.exports,
  require,
  module,
  "api.ts",
  "."
);

(async () => {
  const api = module.exports;
  const result = await api.runControlCommand({
    command: "collection.filter.set",
    target: { workspace_id: "demo" },
    args: { field: "label", value: "cat", source: "test" },
  });
  const collectionId = result.result.collection_id;
  const page = await api.fetchCollectionItems(collectionId, { offset: 0, limit: 10 });
  if (page.total !== 2 || page.items.map((item) => item.sample.id).join(",") !== "sample-0,sample-2") {
    throw new Error(`unexpected page: ${JSON.stringify(page)}`);
  }
  if (requests.some((path) => path.startsWith("/api/collections/"))) {
    throw new Error(`fetched an exported collection file: ${JSON.stringify(requests)}`);
  }
  process.stdout.write(JSON.stringify({ collectionId, requests }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["collectionId"].startswith("static-filter-")
    assert "/api/samples/shards/000000.json" in result["requests"]
    assert not any(path.startswith("/api/collections/") for path in result["requests"])
