# Changelog

## 1.0.0 - 2026-09-01

The v1 release unifies what were four drifting surfaces -- CLI, Python API, HTTP
control plane, and frontend -- onto one command path, and adds backend-free
static export so a workspace can ship as a plain web bundle.

### Features
- Route every mutation through one runtime command path with typed workspace,
  provider, compute, and extension specs, reachable identically from the CLI,
  `hyperview.api`, the HTTP control plane, and the panel SDK.
- Add `hyperview export`, which writes a workspace as a self-contained static
  bundle: paged collections, sharded samples, optional precomputed similarity,
  materialized text-search results, and mount-path rebasing so a bundle can be
  served from a subdirectory.
- Split representations from indexes, replacing the former single `space_key`
  with an explicit `--index-id` on retrieval commands.
- Expand the panel SDK to v2 and move the built-in panels onto it, so shipped
  and third-party panels use the same hooks; add `useTool`/`listTools` for tool
  calls through the authenticated path.
- Add shipped extensions with a core manifest for built-ins and a reference
  extension that promotes without source changes.
- Add session-token authentication with a CORS allowlist.

### Fixes
- Encode text queries correctly: pass list arguments to `embed_query` and
  resolve text capability per model rather than assuming every space supports
  text.
- Normalize legacy provider slugs in text search and resolve providers before
  consulting the cache.
- Keep edge-docked runtime panels at their authored size, including under
  hidden viewports and zero-size measurement races, which previously collapsed
  walkthrough panels in exported bundles into unreadable slivers.

### Documentation
- Document the extension, tool, and panel concepts and the boundaries between
  them; sync the packaged `hyperview-cli` skill to the v1 command surface.
- Test that the shipped skill and the shipped Python examples resolve against
  the CLI and API that actually ship.

## 0.6.2 - 2026-06-08

### Features
- Add runtime-managed panel update, resize, move, focus, close, and show controls through the CLI, API, Python UI controller, and panel SDK.
- Add built-in samples panels to the runtime panel contract, including ranked sample views backed by explicit similarity queries.
- Add public custom provider registration helpers for CLI and Python workflows.
- Add batch sample ingestion and thumbnail URL handling for larger image datasets.

### Fixes
- Keep explicit similarity queries separate from workspace selection so refreshing the UI no longer selects the first sample in the sample grid.
- Update the workspace layout code to use `dockview-react` directly and simplify panel state synchronization.
- Raise the LanceDB dependency floor and adjust vector index/upsert handling for the current LanceDB API.

### Documentation
- Refresh the packaged HyperView agent skill for provider registration, samples panels, durable panel layout controls, and panel-module guidance.
- Update release citation metadata.

## 0.6.1 - 2026-06-04

### Fixes
- Bump the `hyper-models` dependency requirement for current Hyper3-CLIP provider compatibility.

## 0.6.0 - 2026-06-04

### Features
- Add the public `hv.ui` composition API for launch scripts, including scatter panels, extension-backed panels, and horizontal/vertical/tab/grid view composition.
- Add session-level UI controls for active layouts, selections, explicit similarity queries, extension registration, and runtime panel placement.
- Add extension-backed panel instances with panel props, extension panel definitions, and frontend support for copying/removing runtime panels.
- Add panel SDK hooks and commands for host state, panel props, layout views, sample queries, aggregations, selected samples, hover state, pinned similarity search, and persisted UI commands.
- Add runtime sample query/aggregate endpoints and explicit layout/space-pinned nearest-neighbor state.
- Add geometry parameter resolution and hyperboloid curvature inference for embedding spaces, projections, LanceDB search reranking, and in-memory search.

### Fixes
- Preserve extension identity when Python-composed or manifest-instantiated panels are added to a workspace.
- Prevent `reuse_server=True` sessions from silently mutating a local runtime that is not serving the existing backend.
- Move the frontend development server to port 6363 and remove the stale OpenCode VS Code task.
- Resolve local sample file paths at ingestion time so media URLs keep working from backend-served sessions.

### Documentation
- Refresh the README around the current runtime, CLI, extension, and geometry workflows.
- Expand the architecture documentation for runtime-managed UI, extensions, panel modules, and geometry-aware storage.
- Update the packaged HyperView agent skill for extension panels, similarity commands, and panel-module authoring.

### Breaking Changes
- Direct module panel registration is no longer a public control-plane API; package custom panel code as an extension and add concrete panel instances with `kind='extension'`.

## 0.5.0 - 2026-05-15

### Features
- Add browserless `hyperview figure export` for paper-ready 3D embedding figures.
- Persist 3D scatter camera state so exported figures can reuse the UI view.
- Report geometry-aware nearest-neighbor distances, including exact hyperboloid geodesic distances.

### Documentation
- Document the figure export workflow in the packaged HyperView agent skill.

## 0.4.2 - 2026-05-11

### Fixes
- Prevent project-scope skill installs from deleting the repo-local `.agents/skills/hyperview-cli` source directory when source and destination are the same path.
- Cap supported Python metadata at `<3.14` and document `uv tool install --python 3.12` while upstream ML dependency wheels are unavailable for Python 3.14.

## 0.4.1 - 2026-05-10

### Fixes
- Report the installed package version from the HyperView health endpoint instead of the stale hardcoded server version.

## 0.4.0 - 2026-05-10

### Features
- Add the packaged `hyperview skill install` workflow for refreshing the HyperView agent skill across supported coding agents.
- Add runtime scatter panels that can be bound to explicit layout keys for side-by-side embedding comparisons.
- Add project-local extension discovery from the nearest `.hyperview/extensions` directory.

### Improvements
- Update the frontend to use `hyper-scatter` 0.4.0 and explicit Poincare pan anchors.
- Strengthen installer safeguards for custom skill destinations.
- Keep streaming Hugging Face ingestion working for iterable datasets without private fingerprints.

### Breaking Changes
- Remove the legacy top-level one-shot CLI flow; use explicit control-plane commands such as `hyperview dataset create`, `hyperview workspace create`, and `hyperview serve`.
- Reject unsupported persisted LanceDB layout registry schemas instead of silently rebuilding them.

## 0.3.1 - 2026-03-22

### Fixes
- Switch the frontend `hyper-scatter` dependency to the published npm package so clean installs and GitHub release builds resolve it without a local checkout.

### Notes
- This release supersedes the failed `0.3.0` PyPI publish and carries forward the user-facing changes documented below.

## 0.3.0 - 2026-03-22

### Features
- Add PCA projection support for Euclidean, Poincare, and spherical visualization layouts.
- Add 3D layout support for visualizations, including spherical views and 3D lasso selection.
- Add Hugging Face ingestion controls for subset configs, streaming, and configurable shuffle buffers.

### Improvements
- Preserve stable source indices and requested sample tracking during Hugging Face ingestion.
- Expand the demo workflow with ready-made Euclidean, Poincare, spherical, and PCA layouts.

### Breaking Changes
- Replace CLI `--geometry` with repeatable `--layout` flags such as `--layout euclidean`, `--layout poincare`, and `--layout spherical`.
- Replace `Dataset.compute_visualization(geometry=...)` with `Dataset.compute_visualization(layout=...)`; bare `spherical` layouts now resolve to 3D.
