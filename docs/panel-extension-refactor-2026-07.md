# Panel & Extension Refactor — Phases 5+ (2026-07)

Status: proposed. Follows `docs/refactor-plan-2026-07.md` (Phases 1, 2, 4 landed; Phase 3
backend landed, frontend half outstanding) and `docs/refactor-plan-2026-07-gap-assessment.md`.

## Assessment of the current panel/extension architecture

The bones are right, and they are differentiated. One command control plane
(`/api/control/commands/run` + `ControlService`), runtime snapshots over SSE, panels as
plain ESM modules served with server-side JSX transform (`src/hyperview/server/app.py:561`),
extensions as repo-local folders with `extension.toml`. This deliberately avoids FiftyOne's
worst plugin problem — JS plugin authors there need a source install of the app plus a Vite
config linking into `fiftyone/app`, and their plugins couple to internal Recoil atoms.
HyperView's "an agent writes a folder into your repo" model is a real moat. Keep it.

The problem is that the contract exists but is not load-bearing:

1. **Built-ins bypass the SDK.** `SamplesImageGridPanel`
   (`frontend/src/panels/builtins/samplesImageGridPanel.tsx:333`), `ScatterPanel`
   (`frontend/src/components/ScatterPanel.tsx:42`), and `ExplorerPanel`
   (`frontend/src/components/ExplorerPanel.tsx:17`) read the Zustand store and API helpers
   directly. The SDK (`frontend/src/panel-sdk/index.tsx`) is only exercised by extension
   panels, so nothing stops it drifting from what panels actually need. FiftyOne has the
   same disease (built-ins vs plugin surface); we should not inherit it.

2. **The SDK's data surface is decorative.** `useSamples()` filters the *already-loaded*
   client sample array and only understands `label eq` filters
   (`frontend/src/panel-sdk/index.tsx:238`). A panel cannot page, filter, or query the
   dataset. Meanwhile Phase 3 already shipped the paged
   `GET /api/collections/{id}/items` endpoint — the SDK just never grew a hook over it.

3. **Two panel-definition registries that disagree.** Backend `PanelDefinition` built-ins
   are `samples` and `scatter` only (`src/hyperview/panel_definitions.py:75`); the frontend
   registry has the samples grid plus five scatter variants (`frontend/src/panels/registry.tsx:202`);
   Explorer/Labels is a hand-added Dockview component that no definition describes
   (`frontend/src/components/DockviewWorkspace.tsx:683`). An agent listing
   `/api/panel-definitions` does not see the UI that actually exists — this directly
   undercuts the agent-addressable-UI thesis.

4. **Contract residue.** `lifecycle` metadata is parsed and serialized but never invoked
   (`src/hyperview/extensions.py:72`). `kind="extension"` is accepted by the control add
   path but normalized back to `kind="module"` (`src/hyperview/runtime.py:1736`), while
   `from_dict` silently coerces unknown kinds to `"module"` (`src/hyperview/runtime.py:323`)
   — three spellings of the same concept. Checked-in example panels under
   `agent-context/extensions/*/panel.jsx` and the skill doc
   (`.agents/skills/hyperview-cli/references/panel-modules.md:61`) reference SDK hooks
   (`useTool`, `usePanelSamples`, `components`) that the current global does not expose.
   For an agent-native product, stale examples are worse than no examples: agents copy them.

5. **Snapshot duplication.** Panel state is serialized into both `workspace.ui.panels` and
   each `workspace.ui.custom_panels[]` entry (`src/hyperview/runtime.py:2588`).

6. **No sandbox, wide-open CORS.** Extension Python runs in-process and panel JS runs in
   the main frame — acceptable for the repo-local trust model, but the server has
   `allow_origins=["*"]` with mutating commands (`src/hyperview/server/app.py:464`), so any
   webpage can drive a running local runtime. That must be fixed regardless of panel work
   (see `docs/architecture-review-2026-07.md`, issue #1).

## Design principles for the next phases

- **One contract, dogfooded.** Built-ins consume the identical SDK surface extension panels
  get. If a built-in needs something the SDK lacks, the SDK grows — that is the feature.
- **Backend `PanelDefinition` is the single registry.** The frontend maps `panel_type` →
  component and nothing else. What `/api/panel-definitions` returns is what exists.
- **Collections are the data currency.** Panels render `collection_id`s; retrieval,
  filtering, and ranking produce collections. (This is the Phase 3 thesis — finish it.)
- **Commands mutate, queries read.** No new REST for panel behavior; the paged collection
  items endpoint is data-plane and stays REST.
- Ground rules from `refactor-plan-2026-07.md` continue to apply (runtime is source of
  truth, LanceDB untouched, every phase lands with `uv run pytest` + `npm run build` green).

## Phase 5 — Finish Phase 3 (frontend collections + space_key split)

Already scoped in the original plan; restated here because Phases 6–7 depend on it.

- Samples panel renders from `collection_id` via `GET /api/collections/{id}/items`
  (paged), replacing direct `/api/samples` usage inside the panel.
- Retrieval commands (`panel.samples.retrieval.*`) resolve to collections; the panel state
  stores the bound `collection_id`, not query echoes.
- Split `space_key` into `representation` / `index` per `docs/architecture.md`.
- Static export: collection shards already exist (`src/hyperview/static_export.py`); verify
  the collection-driven panel reads them unchanged.

Exit criteria: Samples grid shows any collection (all / filter / neighbors / lasso /
search) through one code path; `ui.similarity_query` migration shim in
`src/hyperview/runtime.py:747` deleted.

## Phase 6 — Make the SDK the only data path

1. **Real query hooks.** Add `useCollectionItems(collectionId, { offset, limit, fields })`
   backed by the paged endpoint, with static-bundle shard support. Reimplement
   `useSamples()` on top of it or delete it (it currently lies about what it does).
2. **Port built-ins onto the SDK.** Order: Explorer (smallest), then Samples grid, then
   Scatter. Scatter will need SDK access to embeddings/layouts queries — add
   `useQuery(query_id, args)` mapping to the declared `queries` in `PanelDefinition`
   (`embeddings`, `layouts`, `samples.query`, `samples.similar`) so the query surface is
   also declared, not ad-hoc fetches.
3. **Selection/state stay as-is** (`useSelection`, `usePanelState` are already right); add
   `useDatasetInfo()` for labels/counts so Explorer doesn't need raw API helpers.
4. Zustand remains the host's internal cache; the rule is *panels* (built-in or not) import
   only from `panel-sdk`. Enforce with an ESLint boundary rule
   (`no-restricted-imports` for `store/`, `lib/api` inside `panels/**`).

Exit criteria: `grep -r "useStore\|lib/api" frontend/src/panels/` returns nothing; an
extension panel can reproduce the built-in samples grid using only documented SDK hooks.

## Phase 7 — One panel registry

1. Backend `PanelDefinition` becomes the source of truth for *all* panels: add `explorer`;
   collapse the five scatter variants into one `scatter` definition with a `preset` prop
   (variants become `default_props` presets, not distinct types).
2. Frontend registry reduces to `panel_type → React component` lookup; default layout is
   built from backend definitions' `default_layout`, not hardcoded in
   `DockviewWorkspace.tsx:661`.
3. Dockview layout persistence moves from `localStorage` into workspace UI state via a
   `workspace.layout.*` command (echo-suppressed with `client_id`, as panel state already
   does). localStorage keeps only true user preferences (theme, thumbnail size). This
   closes the "agent cannot see the actual layout" gap and honors the source-of-truth
   ground rule.

Exit criteria: `/api/panel-definitions` lists every panel the UI can show; a fresh
workspace's layout is fully reproducible from runtime state.

## Phase 8 — Contract hygiene

- Collapse panel `kind` to `builtin | module` everywhere; make control add/`from_dict`/
  frontend types agree (`src/hyperview/runtime.py:323`, `frontend/src/types/index.ts:131`).
- Delete `lifecycle` from manifests and `PanelDefinition`, or implement it; do not ship
  parsed-but-dead contract fields. (Recommendation: delete; snapshot-driven React needs no
  mount hooks, and reintroducing later is cheap.)
- Remove the snapshot duplication of panel state (keep `workspace.ui.panels` keyed by id;
  `custom_panels[]` carries only spec + `state_revision`).
- Rewrite `agent-context/extensions/*` examples and
  `.agents/skills/hyperview-cli/references/panel-modules.md` against the v2 SDK; add a CI
  smoke test that installs each example extension and asserts the panel module imports and
  its hooks exist on `window.HyperViewPanelSDK`.
- Set a removal date for `src/hyperview/control/aliases.py` deprecated command names and
  emit a deprecation warning in `CommandResult.messages` when one is used.

## Phase 9 (forward-looking) — Capability declarations

Prerequisite for multimodal (see `docs/multimodal-plan-2026-07.md`): panels declare the
data shapes they accept (Rerun-style capability declaration, FiftyOne sample-renderer
`media_types` analog):

```toml
[[panels]]
type = "my-text-browser"
accepts = { entity_sets = ["samples"], modalities = ["text"], fields = ["text", "label"] }
```

The host uses `accepts` to (a) filter which panels an agent/user can open on a given
collection, and (b) let one grid delegate tile rendering to modality-specific renderers.
Renderer registration becomes a third extension surface next to tools and panels.

## Non-goals

- Iframe/postMessage sandboxing of panels — wrong trade for the repo-local trust model;
  revisit only if remote/marketplace extensions ever become a goal.
- A plugin marketplace — `PLUGIN_ARCHITECTURE_2026-04-20.md` already rejected it; still right.
- Scoped SSE deltas — real, but an infrastructure concern tracked in the architecture
  review, not panel-contract work.

## Sequencing & risk

Phase 5 → 6 → 7 are strictly ordered (6 needs collection hooks from 5; 7 needs built-ins
on the SDK from 6). Phase 8 can interleave. Riskiest item is porting Scatter to SDK-only
data access (hyper-scatter's data feeding is tangled with the store via
`useHyperScatter.ts`); if it drags, ship Phases 6.1–6.2 with Scatter exempted and tracked,
rather than blocking the registry work.
