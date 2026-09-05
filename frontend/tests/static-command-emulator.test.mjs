// Node's built-in runner: `npm test` (node --test tests/).
//
// The static bundle emulates the control plane in the browser. These tests pin
// the part that is easy to get wrong: which panel's state a collection command
// writes. A bundle can host several panels, so a command issued by an extension
// panel must land on that panel, not on a panel literally named "samples".
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import { pathToFileURL } from "node:url";

// api.ts imports the generated capability table through the "@/" alias that
// tsconfig defines. Node resolves modules without tsconfig, so teach it the
// one alias this graph uses.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      return nextResolve(
        new URL(`../src/${specifier.slice(2)}.ts`, import.meta.url).href,
        context
      );
    }
    return nextResolve(specifier, context);
  },
});

const API_MODULE = pathToFileURL(
  new URL("../src/lib/api.ts", import.meta.url).pathname
).href;

const { CAPABILITY_MODES } = await import(
  new URL("../src/generated/capabilities.ts", import.meta.url).href
);

function panel(id) {
  return {
    id,
    panel_type: id,
    source: "extension",
    renderer: `extension:${id}`,
    title: id,
    position: "right",
    builtin_panel: null,
    extension: "demo",
    extension_panel: id,
    module_file: "panel.jsx",
    layout_key: null,
    geometry: null,
    layout_dimension: null,
    reference_panel_id: null,
    direction: null,
    width: null,
    height: null,
    min_width: null,
    min_height: null,
    max_width: null,
    max_height: null,
    visible: true,
    active: false,
    props: {},
    state_revision: 0,
    layout: {
      position: "right",
      reference_panel_id: null,
      direction: null,
      width: null,
      height: null,
      min_width: null,
      min_height: null,
      max_width: null,
      max_height: null,
    },
    data: { module_src: null },
  };
}

function snapshot() {
  return {
    runtime_id: "runtime",
    version: 1,
    active_workspace_id: "demo",
    panel_definitions: [],
    workspaces: [{ id: "demo", dataset_name: "demo" }],
    workspace: {
      id: "demo",
      dataset_name: "demo",
      collections: [
        {
          id: "all",
          dataset_id: "demo",
          entity_set_id: "samples",
          kind: "all",
          query: {},
          scores: null,
          created_at: 0,
        },
      ],
      ui: {
        active_layout_key: null,
        selected_ids: [],
        layout: null,
        layout_revision: 0,
        panels: {},
        layout_views: {},
        custom_panels: [panel("samples"), panel("region-readout")],
        has_explicit_view: true,
        active_panel_id: null,
        view_revision: 1,
      },
    },
  };
}

// Each test needs its own module instance: the emulator caches the snapshot it
// mutates in module scope.
async function loadStaticApi({ commands = CAPABILITY_MODES.static.commands } = {}) {
  globalThis.window = {
    __HYPERVIEW_STATIC__: true,
    location: { href: "http://localhost/bundle/" },
    dispatchEvent: () => true,
  };
  const json = (body, status = 200) =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  globalThis.fetch = async (input) => {
    const url = String(input);
    // The bundle's manifest is the emulator's own contract: it says which
    // commands this host runs (D6).
    if (url.endsWith("hyperview-static.json")) {
      return json({
        schema_version: 1,
        kind: "hyperview-static-space",
        capabilities: { ...CAPABILITY_MODES.static, commands },
      });
    }
    if (url.endsWith("api/runtime.json")) return json(snapshot());
    // A bundle exported without a similarity index answers the neighbors path
    // with an empty result set, which is enough to pin the panel routing.
    if (url.endsWith("api/search/similar/index.json")) return json({ detail: "absent" }, 404);
    if (url.endsWith("api/samples/index.json")) return json({ shards: [] });
    if (url.endsWith("api/dataset.json")) {
      return json({ name: "demo", num_samples: 0, labels: [], layouts: [] });
    }
    throw new Error(`unexpected static fetch: ${url}`);
  };
  return import(`${API_MODULE}?instance=${Math.random()}`);
}

test("a collection command writes the panel state of the panel that issued it", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.selection.set",
    target: { workspace_id: "demo", panel_id: "region-readout" },
    args: { sample_ids: ["a", "b"], source: "region-readout" },
  });

  assert.equal(payload.ok, true);
  assert.equal(payload.result.panel_id, "region-readout");
  const panels = payload.snapshot.workspace.ui.panels;
  assert.equal(panels["region-readout"].state_revision, 1);
  assert.deepEqual(panels["region-readout"].state.collection.query.ids, ["a", "b"]);
  assert.equal(panels.samples, undefined);
  assert.equal(payload.revision, 1);
});

test("a label filter issued by an extension panel stays on that panel", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.filter.set",
    target: { workspace_id: "demo", panel_id: "region-readout" },
    args: { field: "label", value: "cat" },
  });

  assert.equal(payload.ok, true);
  assert.equal(payload.result.panel_id, "region-readout");
  const panels = payload.snapshot.workspace.ui.panels;
  assert.equal(panels["region-readout"].state.mode, "collection");
  assert.equal(panels.samples, undefined);
});

test("an untargeted command still writes the shared Samples state slot", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.selection.set",
    target: { workspace_id: "demo" },
    args: { sample_ids: ["a"], source: "panel" },
  });

  assert.equal(payload.result.panel_id, "samples");
  assert.equal(payload.snapshot.workspace.ui.panels.samples.state_revision, 1);
});

test("an unknown panel id falls back to the Samples state slot", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.selection.set",
    target: { workspace_id: "demo", panel_id: "not-a-panel" },
    args: { sample_ids: ["a"], source: "panel" },
  });

  assert.equal(payload.result.panel_id, "samples");
});

test("a neighbors collection issued by an extension panel stays on that panel", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.neighbors.create",
    target: { workspace_id: "demo", panel_id: "region-readout" },
    args: { sample_id: "a", k: 2, source: "region-readout" },
  });

  assert.equal(payload.result.panel_id, "region-readout");
  const panels = payload.snapshot.workspace.ui.panels;
  assert.equal(panels["region-readout"].state.mode, "retrieval");
  assert.equal(panels.samples, undefined);
});

// `panel.samples.retrieval.set-anchor` now takes a CollectionTarget on the live
// server, so the emulator honours its panel target too: a bundle and a Live
// Space have to route the same command the same way.
test("a retrieval anchor targeted at a panel writes that panel", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "panel.samples.retrieval.set-anchor",
    target: { workspace_id: "demo", panel_id: "region-readout" },
    args: { sample_id: "a", k: 2, source: "panel" },
  });

  assert.equal(payload.result.panel_id, "region-readout");
  assert.equal(payload.snapshot.workspace.ui.panels["region-readout"].state.mode, "retrieval");
  assert.equal(payload.snapshot.workspace.ui.panels.samples, undefined);
});

// The retrieval commands that stayed workspace-scoped still ignore a panel id.
test("a workspace-scoped retrieval command ignores a panel target", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "panel.samples.retrieval.set-anchor",
    target: { workspace_id: "demo" },
    args: { sample_id: "a", k: 2, source: "panel" },
  });

  assert.equal(payload.result.panel_id, "samples");
  assert.equal(payload.snapshot.workspace.ui.panels["region-readout"], undefined);
});

test("a filter targeted at the Samples alias writes the shared Samples slot", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.filter.set",
    target: { workspace_id: "demo", panel_id: "grid" },
    args: { field: "label", value: "cat" },
  });

  assert.equal(payload.result.panel_id, "samples");
  assert.equal(payload.snapshot.workspace.ui.panels.samples.state.mode, "collection");
});

// The manifest is authoritative: a host that does not list a command does not
// half-emulate it, and the frontend keeps no allowlist of its own.
test("the emulator refuses a command the manifest does not list", async () => {
  const { runControlCommand } = await loadStaticApi({
    commands: {
      ...CAPABILITY_MODES.static.commands,
      allowed: CAPABILITY_MODES.static.commands.allowed.filter(
        (command) => command !== "collection.filter.set"
      ),
    },
  });

  const payload = await runControlCommand({
    command: "collection.filter.set",
    target: { workspace_id: "demo" },
    args: { field: "label", value: "cat" },
  });

  assert.equal(payload.ok, false);
  assert.equal(payload.error.code, "conflict");
  assert.equal(payload.snapshot.workspace.ui.panels.samples, undefined);
});

test("a command outside the exported surface is refused by default", async () => {
  const { runControlCommand } = await loadStaticApi();

  const payload = await runControlCommand({
    command: "collection.search.create",
    target: { workspace_id: "demo" },
    args: { query_text: "a cat", k: 5 },
  });

  assert.equal(payload.ok, false);
  assert.match(payload.error.message, /Live Space/);
});
