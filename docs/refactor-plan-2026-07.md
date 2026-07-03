# Panel & Control Refactor Plan — July 2026

Status: active. Branch: `refactor/panel-control-2026-07` (WIP snapshot committed as baseline).

## Why

The uncommitted work of June/July 2026 (control command API, panel definitions,
Samples retrieval state, panel SDK expansion, text retrieval) was driven by the
hyperview-spaces demos. It moved the architecture in the right direction —
CLI/API-first, runtime as source of truth — but left migration debt behind.
This plan consolidates that work so the panel/control system matches
`docs/architecture.md` and `AGENTS.md` instead of accumulating demo-shaped
special cases.

## Current pain points

1. **Duplicated panel contracts.** Built-in panel definitions exist twice:
   `src/hyperview/panel_definitions.py` (Python) and
   `frontend/src/panels/definitions.tsx` (TS). They can silently drift.
2. **Three panel render paths.** Runtime scatter panels are special-cased apart
   from `RuntimeBuiltInPanel.tsx` and `RuntimeModulePanel.tsx`; panel type vs
   concrete Dockview tab id is muddled.
3. **Panel SDK is a leaky mega-surface.** `frontend/src/panel-sdk/index.tsx`
   re-exports store internals, Dockview context, API helpers, tools, selection,
   and layouts. It is becoming the de-facto frontend integration layer.
4. **Legacy state mirrors.** `ui.similarity_query` is still mirrored although
   the source of truth is `ui.panels.samples.state.retrieval`.
5. **Mixed command taxonomy.** `ui.panel.*`, `samples.retrieval.*`,
   `panel.samples.*`, `panel.labels.*` coexist without clear ownership.
6. **Collections are not yet the source of truth.** `CollectionState` exists,
   but panels re-run searches and infer display behavior from Samples state
   instead of rendering by `collection_id`.
7. **Inconsistent round trips.** Some command results carry a workspace
   snapshot that the frontend ignores, then re-fetches `/api/runtime`.

## Target architecture (from docs/architecture.md, made concrete)

- **One canonical `PanelDefinition`** lives in Python. The frontend fetches
  definitions from the runtime snapshot and only maps `panel_type` →
  renderer component. No panel contract data is hardcoded in TS.
- **One panel instance model** for built-ins and extensions alike:
  `{id, panel_type, sources (collection_id / layout_id / entity_ref), props,
  state, layout}`. "Built-in" only selects a shipped renderer.
- **Command taxonomy** with three clean namespaces:
  - `workspace.*` — layout, panels add/remove/move/focus, views
  - `panel.<type>.*` — panel-owned state transitions (e.g.
    `panel.samples.retrieval.set-anchor`)
  - `collection.*` — create/update/delete filter/search/neighbor collections
  Every command returns the same `CommandResult` shape: `{revision,
  changed: [resource refs], result?}`. The frontend applies the returned
  snapshot/diff instead of re-fetching.
- **Collections first-class.** Neighbor/filter/search results are materialized
  into collections with stable ids; Samples/ImageGrid become collection
  renderers, not owners of paging + filters + search modes.
- **Thin panel SDK.** The SDK exposes: command client (typed, discovered from
  `/api/control/commands`), `usePanelState`, `useSelection`, `useCollection`,
  `useSamples(collection_id)`, and host adapters for focus/resize. Nothing
  else. Store and Dockview never leak.

## Phases

### Phase 1 — De-duplicate and de-legacy (mechanical, low risk)

1. Export panel definitions from the runtime snapshot; delete the duplicated
   contract data from `frontend/src/panels/definitions.tsx`, keeping only the
   `panel_type → React component` renderer map.
2. Remove the `ui.similarity_query` mirror; migrate all readers to
   `ui.panels.samples.state.retrieval` (grep frontend + Python + tests).
3. Normalize command names into the three namespaces above with aliases for
   one release (`ui.panel.*` → `workspace.panel.*` etc.); emit deprecation
   warnings for aliases.
4. Make every command handler return `CommandResult` with `revision` +
   workspace snapshot, and make the frontend command client apply it (drop
   the extra `/api/runtime` fetch).
5. Tests: update `test_control_commands.py`, `test_control_command_api.py`,
   `test_cli_control.py`, `test_runtime_control_api.py`; all must pass; the
   frontend must build (`npm run build`).

### Phase 2 — One panel render path

1. Fold the runtime-scatter special case into `RuntimeBuiltInPanel`.
2. Merge `RuntimeBuiltInPanel` and `RuntimeModulePanel` behind a single
   `PanelHost` component: resolve renderer (built-in map or extension module
   loader), wrap in `PanelInstanceProvider`, done.
3. Slim `panel-sdk/index.tsx` to the surface listed above; extension demos in
   `examples/` and hyperview-spaces panels are the acceptance test.

### Phase 3 — Collections as source of truth

1. Materialize collection membership (result rows with ranks/scores) in the
   backend, paged via `GET /api/collections/{id}/items`.
2. Samples panel renders whatever `collection_id` it is pointed at; retrieval
   commands produce/update collections instead of panel-local result state.
3. Split `space_key` into representation/index per architecture doc.

### Phase 4 — Static export (`hyperview export`)

Motivated by hyperview-spaces (see
`hyperview-spaces/docs/deployment-architecture.md`): a workspace snapshot that
serves demos with **no Python at request time**.

1. `hyperview export <workspace> --out bundle/` writes:
   - the static frontend (already `output: "export"` in Next),
   - the runtime snapshot JSON (panels, definitions, layouts, collections),
   - materialized collection items + sample records as static JSON shards,
   - media/thumbnails,
   - precomputed layout coordinates.
2. A `fetch` adapter in the frontend API client resolves `/api/*` reads from
   the static bundle when `window.__HYPERVIEW_STATIC__` is set. Bundles are
   **read-only by product decision** (FiftyOne/Rerun examples-gallery
   style): panel state changes stay client-side and ephemeral; mutating
   commands are disabled behind a visible "read-only demo — run locally"
   affordance. Extension panel JS modules ship inside the bundle and load
   through the existing `RuntimeModulePanel` path.
3. Optional query path for text search over precomputed embeddings is a
   deployment concern (see spaces doc) — not part of core.

Phase 4 only needs Phases 1–2; it can start once the command client applies
snapshots (Phase 1.4).

## Ground rules for implementation

- Runtime/workspace state stays the source of truth; browser localStorage is
  user preference only.
- No new REST routes for panel behavior — commands only.
- Do not change the LanceDB storage backend.
- Every phase lands with green `uv run pytest` and a green
  `cd frontend && npm run build`, committed on
  `refactor/panel-control-2026-07`.
