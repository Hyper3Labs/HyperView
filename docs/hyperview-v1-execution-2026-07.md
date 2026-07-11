# HyperView v1 — Remaining Work & Execution Waves (2026-07)

Status: active. What is left on `codex/hyperview-v1` after the static-spaces work, per
`docs/panel-extension-refactor-2026-07.md`, `docs/multimodal-plan-2026-07.md`,
`docs/architecture-review-2026-07.md`, and the branch audit of 2026-07-11.

Execution model: work is distributed to codex minions in waves; tasks within a wave touch
disjoint file surfaces (one shared working tree, no worktree merging). Every task must
land with `uv run pytest` and `cd frontend && npm run build` green, and gets a review
pass before the next wave starts.

## Remaining work inventory

| # | Item | Source | Status |
|---|------|--------|--------|
| W1a | Static ephemeral-collection 404: `static-filter-*` collections must resolve client-side, not fetch nonexistent `items.json` | branch audit | open |
| W1b | Static `dataset.json` missing `representations[]`/`indexes[]` (live/static contract divergence) | branch audit | open |
| W1c | Warm-worker reads `hyperview_version`, health returns `version`; `export_frontend.sh` references nonexistent `hyperview demo` | arch review #9 | open |
| W1d | Phase 8 hygiene: snapshot panel-state de-dup, panel `kind` collapse to `builtin\|module`, delete dead `lifecycle`, alias deprecation warnings in `CommandResult`, rewrite stale `agent-context/extensions/*` examples + skill docs | refactor Phase 8 | open |
| W2a | CORS allowlist + per-session bearer token on control routes | arch review #1 | open |
| W2b | Phase 5/6 frontend: Samples built-in renders `collection_id` via SDK only; Explorer ported to SDK; `useDatasetInfo()`; ESLint boundary rule for `panels/**` | refactor Phases 5–6 | open |
| W3a | Real representation/index split: `index_id` accepted in control command models, `SpaceInfo` stops aliasing `space_key`, delete `ui.similarity_query` shim | refactor Phase 5 | shimmed only |
| W3b | Multimodal M0: `media_type`/`duration_s` columns, nullable `filepath`, typed `Field` registry, static-export media guards | multimodal M0 | open |
| W4a | Scatter built-in on SDK (`useQuery` for embeddings/layouts) | refactor Phase 6 | open, riskiest |
| W4b | Phase 7: one backend panel registry (explorer definition, scatter presets), Dockview layout into runtime state | refactor Phase 7 | open |
| Later | SSE wakeup + delta encoding, thumbnail path consolidation, jobs persistence, god-module splits, repo boundaries | arch review #2,#4,#5,#6,#8 | deferred |

## Waves

- **Wave 1 (parallel, disjoint):** W1a+W1b (static parity — `static_export.py`,
  `frontend/src/lib/api.ts`, static tests) · W1c (warm-worker + script) · W1d (hygiene —
  `runtime.py`, `panel_definitions.py`, `extensions.py`, `aliases.py`,
  `frontend/src/types`, `agent-context/`, `.agents/`).
- **Wave 2 (parallel, disjoint):** W2a (security — `server/app.py`, `api.py`, `cli.py`,
  auth header in `lib/api.ts` + SDK client) · W2b (panels — `frontend/src/panels/**`,
  `panel-sdk/index.tsx`, `ExplorerPanel`).
- **Wave 3 (parallel, disjoint):** W3a (control plane — `control/*`, `runtime.py`,
  `storage/schema.py` representation fields) · W3b (data model — `core/sample.py`,
  `core/dataset.py`, `storage/schema.py` sample columns, `static_export.py` guards).
  W3a/W3b both touch `storage/schema.py` in different regions; serialized if conflicts bite.
- **Wave 4 (sequential):** W4a then W4b (both concentrate in the frontend panel layer).

Rule of thumb carried over from the plan docs: no new REST routes for panel behavior
(commands only), LanceDB backend untouched, runtime state stays the source of truth.
