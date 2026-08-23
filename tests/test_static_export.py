from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote

import numpy as np
import pytest
from PIL import Image

from hyperview import Dataset, Session
from hyperview.control import CommandEnvelope, ControlService, create_default_command_registry
from hyperview.core.sample import Sample
from hyperview.runtime import HyperViewRuntime, ProviderRegistry, WorkspaceRegistry
from hyperview.static_export import (
    copy_static_bundle,
    export_runtime_workspace,
    normalize_static_mount_path,
)
from hyperview.storage.schema import representation_id_for_space_key


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
                'file = "panel.jsx"',
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
    (folder / "panel.jsx").write_text(
        'import View from "./view.jsx";\n'
        "export default function Panel() { return <View />; }\n",
        encoding="utf-8",
    )
    (folder / "view.jsx").write_text(
        "export default function View() { return <div>Static panel</div>; }\n",
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
    assert result.warnings == ()

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "window.__HYPERVIEW_STATIC__ = true;" in index_html

    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text(encoding="utf-8"))
    assert snapshot["active_workspace_id"] == "demo"
    assert snapshot["workspaces"] == [{"id": "demo", "dataset_name": dataset.name}]
    assert snapshot["workspace"]["id"] == "demo"
    assert snapshot["workspace"]["ui"]["active_layout_key"]
    assert snapshot["panel_definitions"]
    assert str(tmp_path) not in json.dumps(snapshot)
    panels = {panel["id"]: panel for panel in snapshot["workspace"]["ui"]["custom_panels"]}
    assert panels["readout"]["data"]["static_compatible"] is True
    assert panels["readout"]["data"]["module_src"] == (
        "/api/panels/content/demo/readout/panel.js"
    )
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
    representation_id = representation_id_for_space_key(space_key)
    assert representations_by_id[representation_id] == expected_space.to_representation_dict()
    assert indexes_by_representation[representation_id] == expected_space.to_index_dict()
    expected_representation_ids = {representation_id_for_space_key(key) for key in spaces_by_id}
    assert representations_by_id.keys() == expected_representation_ids
    assert indexes_by_representation.keys() == expected_representation_ids

    samples_index = json.loads(
        (out_dir / "api" / "samples" / "index.json").read_text(encoding="utf-8")
    )
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
    assert "filepath" not in shard["samples"][0]

    assert (out_dir / "api" / "samples" / "sample-0" / "content").is_file()
    assert (out_dir / "api" / "samples" / "sample-0" / "thumbnail").is_file()
    assert not (out_dir / "media").exists()
    assert (out_dir / "api" / "embeddings" / "default.json").is_file()
    assert (out_dir / "api" / "panels" / "content" / "demo" / "readout" / "panel.js").is_file()
    panel_module = (
        out_dir / "api" / "panels" / "content" / "demo" / "readout" / "panel.js"
    ).read_text(encoding="utf-8")
    assert 'from "./view.js"' in panel_module
    assert (out_dir / "api" / "panels" / "content" / "demo" / "readout" / "view.js").is_file()
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
    assert manifest["capabilities"]["layouts"] is True
    assert manifest["capabilities"]["lasso_2d"] is True
    assert manifest["capabilities"]["text_search"] is False
    assert manifest["capabilities"]["python_tools"] is False
    assert manifest["deployment"]["cloudflare"]["mode"] == "static-assets-only"
    assert manifest["warnings"] == []
    wrangler = json.loads((out_dir / "wrangler.jsonc").read_text(encoding="utf-8"))
    assert wrangler["assets"]["directory"] == "."
    assert wrangler["assets"]["not_found_handling"] == "single-page-application"


def test_static_export_without_layout_does_not_advertise_scatter(tmp_path: Path) -> None:
    dataset = Dataset("static_export_no_layout", persist=False)
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (12, 10), (40, 40, 180)).save(image_path)
    dataset.add_sample(Sample(id="sample", filepath=str(image_path), label="cat"))
    runtime = HyperViewRuntime(
        provider_registry=ProviderRegistry(tmp_path / "providers.json"),
        workspace_registry=WorkspaceRegistry(tmp_path / "workspaces.json"),
    )
    runtime.attach_dataset_instance("no-layout", dataset, activate_workspace=True)
    out_dir = tmp_path / "bundle"

    export_runtime_workspace(runtime, "no-layout", out_dir)

    manifest = json.loads((out_dir / "hyperview-static.json").read_text())
    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text())
    assert manifest["capabilities"]["layouts"] is False
    assert manifest["capabilities"]["lasso_2d"] is False
    assert manifest["artifacts"]["embeddings"] is None
    assert all(
        definition["panel_type"] != "scatter"
        for definition in snapshot["panel_definitions"]
    )


def test_session_export_uses_runtime_workspace(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    session = Session(runtime, "127.0.0.1", 6262)
    out_dir = tmp_path / "session-bundle"

    payload = session.export(
        out_dir,
        workspace_id="demo",
        similarity_k=0,
        mount_path="/spaces/demo/",
    )

    assert payload["workspace_id"] == "demo"
    assert Path(payload["output_dir"]).is_dir()
    assert (out_dir / "hyperview-static.json").is_file()
    assert payload["similarity_k"] == 0
    assert payload["mount_path"] == "/spaces/demo"
    assert not (out_dir / "api" / "search" / "similar" / "index.json").exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/", "/"),
        ("/spaces/demo", "/spaces/demo"),
        ("/spaces/demo/", "/spaces/demo"),
    ],
)
def test_normalize_static_mount_path(value: str, expected: str) -> None:
    assert normalize_static_mount_path(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "spaces/demo",
        "//spaces/demo",
        "/spaces//demo",
        "/spaces/../demo",
        "/spaces/%2Fdemo",
        "/spaces/demo?tab=1",
        "/spaces/demo#panel",
        r"/spaces\demo",
    ],
)
def test_normalize_static_mount_path_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_static_mount_path(value)


def test_static_export_mount_path_rebases_shell_but_not_api_data(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    out_dir = tmp_path / "mounted"

    result = export_runtime_workspace(
        runtime,
        "demo",
        out_dir,
        mount_path="/spaces/demo/",
    )

    assert result.mount_path == "/spaces/demo"
    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert 'window.__HYPERVIEW_MOUNT_PATH__ = "/spaces/demo";' in index_html
    assert 'src="/spaces/demo/_next/' in index_html
    assert 'href="/spaces/demo/_next/' in index_html
    assert 'href="/spaces/demo/icon.png' in index_html

    manifest = json.loads((out_dir / "hyperview-static.json").read_text(encoding="utf-8"))
    assert manifest["mount_path"] == "/spaces/demo"
    assert manifest["deployment"]["hosting"] == {
        "mode": "path-mounted-static-assets",
        "copy_contents_to": "spaces/demo",
    }
    assert manifest["deployment"]["cloudflare"] is None
    assert not (out_dir / "wrangler.jsonc").exists()

    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text(encoding="utf-8"))
    panels = {panel["id"]: panel for panel in snapshot["workspace"]["ui"]["custom_panels"]}
    assert panels["readout"]["data"]["module_src"].startswith("/api/")
    shard = json.loads(
        (out_dir / "api" / "samples" / "shards" / "000000.json").read_text(
            encoding="utf-8"
        )
    )
    assert shard["samples"][0]["media_url"].startswith("/api/")


def test_copy_static_bundle_rebases_existing_reviewed_bundle(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    source_dir = tmp_path / "root-bundle"
    out_dir = tmp_path / "mounted-bundle"
    export_runtime_workspace(runtime, "demo", source_dir)
    stale_chunk = source_dir / "_next" / "static" / "chunks" / "stale-build.js"
    stale_chunk.parent.mkdir(parents=True, exist_ok=True)
    stale_chunk.write_text("stale", encoding="utf-8")

    result = copy_static_bundle(
        source_dir,
        out_dir,
        mount_path="/spaces/copied/",
    )

    assert result.mount_path == "/spaces/copied"
    assert not out_dir.joinpath("_next", "static", "chunks", "stale-build.js").exists()
    assert source_dir.joinpath("wrangler.jsonc").is_file()
    assert not out_dir.joinpath("wrangler.jsonc").exists()
    mounted_index = out_dir.joinpath("index.html").read_text(encoding="utf-8")
    assert 'window.__HYPERVIEW_MOUNT_PATH__ = "/spaces/copied";' in mounted_index
    assert 'src="/spaces/copied/_next/' in mounted_index
    mounted_manifest = json.loads(
        out_dir.joinpath("hyperview-static.json").read_text(encoding="utf-8")
    )
    assert mounted_manifest["mount_path"] == "/spaces/copied"
    assert mounted_manifest["warnings"] == []


def test_copy_static_bundle_preserves_same_non_root_mount_path(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    source_dir = tmp_path / "source-bundle"
    out_dir = tmp_path / "mounted-bundle"
    export_runtime_workspace(
        runtime,
        "demo",
        source_dir,
        mount_path="/spaces/copied",
    )

    copy_static_bundle(
        source_dir,
        out_dir,
        mount_path="/spaces/copied",
    )

    mounted_index = out_dir.joinpath("index.html").read_text(encoding="utf-8")
    assert 'window.__HYPERVIEW_MOUNT_PATH__ = "/spaces/copied";' in mounted_index
    assert 'src="/spaces/copied/_next/' in mounted_index
    assert 'src="/_next/' not in mounted_index
    assert 'href="/_next/' not in mounted_index


def test_static_asset_urls_are_scoped_to_the_declared_mount_path() -> None:
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
  __HYPERVIEW_MOUNT_PATH__: "/spaces/alpha",
  location: {
    href: "https://example.test/spaces/alpha/",
    origin: "https://example.test",
  },
  dispatchEvent: () => {},
};
const requests = [];
global.fetch = async (url) => {
  requests.push(String(url));
  const path = new URL(url).pathname;
  const payloads = {
    "/spaces/alpha/api/dataset.json": { name: "mounted", spaces: [], layouts: [] },
    "/spaces/alpha/api/samples/index.json": {
      total: 1,
      shard_size: 500,
      shards: [{ path: "shards/000000.json", offset: 0, count: 1 }],
    },
    "/spaces/alpha/api/samples/shards/000000.json": {
      total: 1,
      offset: 0,
      limit: 500,
      samples: [{
        id: "sample-0",
        thumbnail: "/api/samples/sample-0/thumbnail",
        media_url: "/api/samples/sample-0/content",
        thumbnail_url: "/api/samples/sample-0/thumbnail",
      }],
    },
  };
  return new Response(JSON.stringify(payloads[path]), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
};

const module = { exports: {} };
new Function("exports", "require", "module", "__filename", "__dirname", compiled)(
  module.exports, require, module, "api.ts", "."
);

(async () => {
  await module.exports.fetchDataset();
  const samples = await module.exports.fetchSamples(0, 1);
  process.stdout.write(JSON.stringify({ requests, sample: samples.samples[0] }));
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
    assert result["requests"] == [
        "https://example.test/spaces/alpha/api/dataset.json",
        "https://example.test/spaces/alpha/api/samples/index.json",
        "https://example.test/spaces/alpha/api/samples/shards/000000.json",
    ]
    assert result["sample"]["media_url"] == (
        "https://example.test/spaces/alpha/api/samples/sample-0/content"
    )
    assert result["sample"]["thumbnail_url"] == (
        "https://example.test/spaces/alpha/api/samples/sample-0/thumbnail"
    )


def test_static_export_warns_when_sample_media_is_missing(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    dataset = runtime.get_dataset(workspace_id="demo")
    Path(dataset.samples[0].filepath).unlink()

    result = export_runtime_workspace(runtime, "demo", tmp_path / "bundle")

    assert len(result.warnings) == 1
    assert "1 image samples reference missing local media files" in result.warnings[0]
    manifest = json.loads((tmp_path / "bundle" / "hyperview-static.json").read_text())
    assert manifest["warnings"] == list(result.warnings)


def test_static_export_marks_missing_panel_module_incompatible(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    workspace = runtime.get_workspace("demo")
    panel = next(item for item in workspace.ui.custom_panels if item.id == "readout")
    Path(panel.module_file).unlink()

    result = export_runtime_workspace(runtime, "demo", tmp_path / "bundle")

    assert result.warnings == (
        "Panel 'readout' was omitted: Panel module source is missing from the workspace host.",
    )
    snapshot = json.loads((tmp_path / "bundle" / "api" / "runtime.json").read_text())
    exported = next(
        item for item in snapshot["workspace"]["ui"]["custom_panels"] if item["id"] == "readout"
    )
    assert exported["data"]["static_compatible"] is False
    assert exported["data"]["static_reason"] == (
        "Panel module source is missing from the workspace host."
    )


def test_static_export_omits_similarity_by_default(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    out_dir = tmp_path / "default-bundle"

    result = export_runtime_workspace(runtime, "demo", out_dir)

    assert result.similarity_k == 0
    assert result.num_similarity_queries == 0
    assert not (out_dir / "api" / "search" / "similar" / "index.json").exists()


def test_static_export_materializes_text_search_collections(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    dataset = runtime.get_dataset(workspace_id="demo")
    space_key = _add_text_search_space(dataset, [sample.id for sample in dataset.samples])
    service = ControlService(runtime, create_default_command_registry())
    engine = SimpleNamespace(
        supported_modalities=lambda _spec: frozenset({"image", "text"}),
        embed_texts=lambda *_args, **_kwargs: np.asarray([[1.0, 0.0]], dtype=np.float32),
    )
    with patch("hyperview.embeddings.engine.get_engine", return_value=engine):
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

    items_path = out_dir / "api" / "collections" / quote(collection_id, safe=":") / "items.json"
    payload = json.loads(items_path.read_text(encoding="utf-8"))

    assert payload["collection_id"] == collection_id
    assert payload["total"] == 2
    assert [item["sample_id"] for item in payload["items"]]
    assert all(item["score"] is not None for item in payload["items"])


def test_static_export_prunes_unreferenced_historical_text_search(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    dataset = runtime.get_dataset(workspace_id="demo")
    space_key = _add_text_search_space(dataset, [sample.id for sample in dataset.samples])
    service = ControlService(runtime, create_default_command_registry())
    engine = SimpleNamespace(
        supported_modalities=lambda _spec: frozenset({"image", "text"}),
        embed_texts=lambda *_args, **_kwargs: np.asarray([[1.0, 0.0]], dtype=np.float32),
    )
    with patch("hyperview.embeddings.engine.get_engine", return_value=engine):
        search = service.run(
            CommandEnvelope(
                command="panel.samples.retrieval.set-text-query",
                target={"workspace_id": "demo"},
                args={"query_text": "cat sample", "space_key": space_key, "k": 2},
            )
        )
    search_id = search.result["collection"]["id"]
    cleared = service.run(
        CommandEnvelope(
            command="collection.selection.set",
            target={"workspace_id": "demo"},
            args={"clear": True, "focus": False},
        )
    )
    assert cleared.ok is True

    out_dir = tmp_path / "pruned-search-bundle"
    with patch(
        "hyperview.embeddings.engine.get_engine",
        side_effect=AssertionError("unreferenced search must not be recomputed"),
    ):
        export_runtime_workspace(runtime, "demo", out_dir)

    snapshot = json.loads((out_dir / "api" / "runtime.json").read_text())
    assert search_id not in {
        collection["id"] for collection in snapshot["workspace"]["collections"]
    }
    assert not (out_dir / "api" / "collections" / quote(search_id, safe=":")).exists()


def test_static_export_materializes_selection_collections_in_requested_order(tmp_path: Path) -> None:
    runtime = _make_runtime(tmp_path)
    service = ControlService(runtime, create_default_command_registry())
    result = service.run(
        CommandEnvelope(
            command="collection.selection.set",
            target={"workspace_id": "demo"},
            args={"sample_ids": ["sample-2", "sample-0"], "source": "test"},
        )
    )
    assert result.ok is True
    collection_id = result.result["collection"]["id"]
    out_dir = tmp_path / "selection-bundle"

    export_runtime_workspace(runtime, "demo", out_dir)

    items_path = out_dir / "api" / "collections" / quote(collection_id, safe=":") / "items.json"
    payload = json.loads(items_path.read_text(encoding="utf-8"))
    assert [item["sample_id"] for item in payload["items"]] == ["sample-2", "sample-0"]


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


def test_static_selection_commands_are_serialized_and_panel_patches_preserve_selection() -> None:
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
const payloads = {
  "/api/runtime.json": {
    version: 1,
    workspace: {
      id: "demo",
      dataset_name: "static_export_dataset",
      collections: [
        {
          id: "all:demo", dataset_id: "static_export_dataset", entity_set_id: "samples",
          kind: "all", query: {}, scores: null, created_at: 1,
        },
        {
          id: "selection:prepared", dataset_id: "static_export_dataset", entity_set_id: "samples",
          kind: "selection", query: { ids: ["sample-2"], source: "prepared comparison" },
          scores: null, created_at: 1,
        },
      ],
      ui: {
        selected_ids: [], view_revision: 0,
        panels: { samples: { state: { collection_id: "all:demo" }, state_revision: 0 } },
        custom_panels: [
          { id: "proof", props: { case: "one" }, state: {}, state_revision: 0 },
          { id: "ranked", props: { rank: { anchorSampleId: "sample-0" } }, state: {}, state_revision: 0 },
        ],
      },
    },
  },
  "/api/samples/index.json": {
    total: 3,
    shard_size: 500,
    shards: [{
      path: "shards/000000.json", offset: 0, count: 3,
      sample_ids: ["sample-0", "sample-1", "sample-2"],
    }],
  },
  "/api/samples/shards/000000.json": {
    total: 3, offset: 0, limit: 500,
    samples: [
      { id: "sample-0", label: "cat" },
      { id: "sample-1", label: "dog" },
      { id: "sample-2", label: "cat" },
    ],
  },
};
const requests = [];
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
  module.exports, require, module, "api.ts", "."
);

(async () => {
  const api = module.exports;
  const [, second] = await Promise.all([
    api.runControlCommand({
      command: "collection.selection.set",
      target: { workspace_id: "demo" },
      args: { sample_ids: ["sample-0"], source: "test" },
    }),
    api.runControlCommand({
      command: "collection.selection.set",
      target: { workspace_id: "demo" },
      args: { sample_ids: ["sample-2", "sample-1"], source: "test" },
    }),
  ]);
  const page = await api.fetchCollectionItems(second.result.collection_id, { offset: 0, limit: 10 });
  if (page.items.map((item) => item.sample.id).join(",") !== "sample-2,sample-1") {
    throw new Error(`unexpected selection page: ${JSON.stringify(page)}`);
  }
  await api.updateStaticSelection(["sample-1"]);
  const patched = await api.runControlCommand({
    command: "workspace.panel.state.patch",
    target: { workspace_id: "demo", panel_id: "proof" },
    args: { state: { active_case: "two" } },
  });
  if (patched.snapshot.workspace.ui.selected_ids.join(",") !== "sample-1") {
    throw new Error(`selection was lost: ${JSON.stringify(patched.snapshot.workspace.ui)}`);
  }
  const updated = await api.runControlCommand({
    command: "workspace.panel.update-props",
    target: { workspace_id: "demo", panel_id: "ranked" },
    args: { props: { rank: { anchorSampleId: "sample-2", k: 8 } } },
  });
  const ranked = updated.snapshot.workspace.ui.custom_panels.find((panel) => panel.id === "ranked");
  if (ranked.props.rank.anchorSampleId !== "sample-2" || ranked.props.rank.k !== 8) {
    throw new Error(`panel props were not updated: ${JSON.stringify(ranked)}`);
  }
  if (updated.snapshot.workspace.ui.selected_ids.join(",") !== "sample-1") {
    throw new Error(`selection was lost after props update: ${JSON.stringify(updated.snapshot.workspace.ui)}`);
  }
  const focused = await api.runControlCommand({
    command: "workspace.panel.focus",
    target: { workspace_id: "demo", panel_id: "proof" },
    args: {},
  });
  if (focused.snapshot.workspace.ui.active_panel_id !== "proof") {
    throw new Error(`panel was not focused: ${JSON.stringify(focused.snapshot.workspace.ui)}`);
  }
  if (focused.snapshot.workspace.ui.selected_ids.join(",") !== "sample-1") {
    throw new Error(`selection was lost after panel focus: ${JSON.stringify(focused.snapshot.workspace.ui)}`);
  }
  process.stdout.write(JSON.stringify({
    selected: focused.snapshot.workspace.ui.selected_ids,
    anchor: ranked.props.rank.anchorSampleId,
    activePanelId: focused.snapshot.workspace.ui.active_panel_id,
    collectionIds: focused.snapshot.workspace.collections.map((collection) => collection.id),
  }));
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
    assert result["selected"] == ["sample-1"]
    assert result["anchor"] == "sample-2"
    assert result["activePanelId"] == "proof"
    assert "selection:prepared" in result["collectionIds"]


def test_static_similarity_anchor_command_materializes_neighbors() -> None:
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
const spaceKey = "clip-space";
const shardPath = "clip-space/shards/000000.json";
const payloads = {
  "/api/runtime.json": {
    runtime_id: "static", version: 1, active_workspace_id: "demo", panel_definitions: [], workspaces: [],
    workspace: {
      id: "demo", dataset_name: "catalog", collections: [{
        id: "all:demo", dataset_id: "catalog", entity_set_id: "samples", kind: "all",
        query: {}, scores: null, created_at: 1,
      }],
      ui: {
        selected_ids: ["sample-1"], view_revision: 0, layout: null, layout_revision: 0,
        layout_views: {}, custom_panels: [], has_explicit_view: true, active_panel_id: "samples",
        active_layout_key: "clip-layout",
        panels: { samples: { state: { collection_id: "all:demo" }, state_revision: 0 } },
      },
    },
  },
  "/api/dataset.json": {
    name: "catalog", num_samples: 2, labels: [], fields: {}, spaces: [], representations: [], indexes: [],
    layouts: [{ layout_key: "clip-layout", space_key: spaceKey, method: "umap", geometry: "euclidean", count: 2, params: null }],
  },
  "/api/samples/index.json": {
    total: 2, shard_size: 500,
    shards: [{ path: "shards/000000.json", offset: 0, count: 2, sample_ids: ["sample-0", "sample-1"] }],
  },
  "/api/samples/shards/000000.json": {
    total: 2, offset: 0, limit: 500,
    samples: [{ id: "sample-0", label: "anchor" }, { id: "sample-1", label: "neighbor" }],
  },
  "/api/search/similar/index.json": {
    schema_version: 1, k: 10, default_space_key: spaceKey,
    spaces: { [spaceKey]: { metric: "cosine", shards: [{ path: shardPath, sample_ids: ["sample-0"] }] } },
  },
  ["/api/search/similar/" + shardPath]: {
    space_key: spaceKey, metric: "cosine", k: 10,
    queries: { "sample-0": { results: [{ sample_id: "sample-1", distance: 0.1 }] } },
  },
};
const requests = [];
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
  module.exports, require, module, "api.ts", "."
);

(async () => {
  const result = await module.exports.runControlCommand({
    command: "panel.samples.retrieval.set-anchor",
    target: { workspace_id: "demo" },
    args: { sample_id: "sample-0", layout_key: "clip-layout", k: 8, source: "test" },
  });
  if (!result.ok) throw new Error(JSON.stringify(result.error));
  const state = result.snapshot.workspace.ui.panels.samples.state;
  if (state.collection.kind !== "neighbors" || state.retrieval.anchor_sample_id !== "sample-0") {
    throw new Error(JSON.stringify(state));
  }
  if (result.snapshot.workspace.ui.selected_ids.length !== 0) {
    throw new Error("anchor command did not clear selection");
  }
  const page = await module.exports.fetchCollectionItems(result.result.collection_id, {
    offset: 0,
    limit: 10,
  });
  if (page.total !== 1 || page.items[0]?.sample.id !== "sample-1" || page.items[0]?.score !== 0.1) {
    throw new Error(`unexpected neighbor page: ${JSON.stringify(page)}`);
  }
  if (requests.some((path) => path.startsWith("/api/collections/"))) {
    throw new Error(`fetched a synthetic collection file: ${JSON.stringify(requests)}`);
  }
  process.stdout.write(JSON.stringify({ collection: state.collection, retrieval: state.retrieval, page }));
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

    assert result["collection"]["kind"] == "neighbors"
    assert result["retrieval"]["anchor_sample_id"] == "sample-0"
