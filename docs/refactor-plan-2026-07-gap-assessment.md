# Gap assessment: refactor-plan-2026-07 vs the fuller AGENTS.md direction

Assessed 2026-07-04, after Phase 1/2/4 landed. Cross-references AGENTS.md's
stated direction (agent-native workbench, provider registration, generic
dataset records/field mapping, embeddings, layouts, panels, jobs,
machine-readable outcomes) against the current codebase, to see what
`docs/refactor-plan-2026-07.md` still needs to cover beyond Phase 3.

## 1. Provider registration — already adequate

`ProviderRegistry` / `ProviderRegistration` (`src/hyperview/runtime.py:170-220`),
public `register_provider`/`unregister_provider` API (`src/hyperview/api.py:77-102`,
re-exported from `src/hyperview/__init__.py`). Embedding engine resolves
providers through it (`src/hyperview/embeddings/engine.py:130`,
`src/hyperview/embeddings/pipelines.py:34-106`). Real registry, not ad hoc.
**No gap.**

## 2. Generic dataset records + explicit field mapping — partial gap

Field mapping exists but is dataset-type-specific and hardcoded, not a generic
runtime concept: `--image-key`/`--label-key` CLI flags
(`src/hyperview/cli.py:188-210`) map directly to a fixed `image_key: str = "img"`
parameter on the HF ingestion path (`src/hyperview/core/dataset.py:252-438`).
There is no generic `FieldMapping`/`Field` schema that panels or extensions can
discover (per `docs/architecture.md`'s `Field` vocabulary). This matches
`docs/architecture.md`'s own "Current vs Target Model" table (Fields: "mostly
implicit" -> "typed fields/components discoverable by panels", priority
Medium). **Real gap, but architecture.md already scopes it Medium, not a Phase 3
blocker.** Recommend as its own follow-up phase, not folded into Phase 3/4.

## 3. Jobs — already adequate

First-class `JobState` + `register_job` in `src/hyperview/runtime.py:2085-2145`,
run on background threads, tracked by id. Exposed via `/api/jobs` routes in
`server/app.py` (`list_jobs`, `get_job`). **No gap.**

## 4. Machine-readable outcomes — already adequate

`CommandResult` (`src/hyperview/control/models.py:51`) is the uniform shape
Phase 1 introduced; all control commands return it, asserted in
`tests/test_cli_control.py`. **No gap.**

## 5. Extension surfaces — matches Phase 2 scope

Panel extension via `RuntimeModulePanel`/`PanelHost` (Phase 2) plus Phase 4's
static export copying extension panel JS modules into the bundle. No evidence
of a second extension axis being asked for beyond what `register_provider`
already allows programmatically. **No gap beyond what AGENTS.md already
describes** — provider registration, native/runtime panels, and explicit
extension surfaces all have a concrete mechanism today.

## 6. Layouts and embeddings as runtime-managed state — already adequate

`space_key`/embedding spaces are runtime/storage-backed (`storage/backend.py`,
`lancedb_backend.py`, `memory_backend.py`), not frontend-local. Layouts resolve
server-side (`runtime.py:_resolve_retrieval_context`). Confirms "runtime/
workspace state is the source of truth" is honored. **No gap.**

## 7. Collections materialization (Phase 3, landed)

`GET /api/collections/{id}` and `GET /api/collections/{id}/items` exist for
neighbors/search/filter/all collection kinds. `useSamples(collectionId)` in
`frontend/src/panel-sdk/index.tsx` now pages through that endpoint for those
kinds (51a712f), in live servers and static bundles alike; non-materializable
kinds (selection/lasso/tool_result/extension) keep the legacy client-side
filter. The `space_key` -> representation/index split landed at the contract
level (c90bfca): `/api/dataset` exposes derived `representations[]` and
`indexes[]`, and `index_id` (`space:<space_key>`) is accepted at every
retrieval boundary. Remaining follow-ups: point the built-in Samples grid's
host view model at a `collection_id`, and eventually key storage by
representation/index instead of `space_key`.

## Conclusion

The only concrete architectural gap beyond what `refactor-plan-2026-07.md`
already scopes is generic field mapping / typed Field discovery — Medium
priority per architecture.md, own follow-up phase. Phase 3's frontend half
and the contract-level representation/index split have landed; the storage
rename and the built-in grid's collection_id rendering are named follow-ups.
No changes needed to phase ordering.
