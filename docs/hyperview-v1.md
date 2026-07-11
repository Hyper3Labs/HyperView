# HyperView v1

Status: proposed architecture completion plan for `codex/hyperview-v1`.

## Purpose

HyperView v1 should establish the durable architecture for an agent-native
workbench. The runtime and workspace remain the source of truth, every product
capability is controllable through the CLI and public APIs, and the frontend
renders that state rather than privately owning it.

The defining v1 outcome for panels is:

> A panel can begin as a repo-local extension and later ship with HyperView
> without rewriting its component, data access, state, commands, or props.

"Built-in" should describe how a panel is distributed, not a separate panel
architecture.

## Existing v1 Foundation

The `codex/hyperview-v1` branch already establishes important parts of this
direction:

- A shared command control plane used by the CLI, Python API, HTTP API, and
  frontend.
- Runtime-managed panel state with revisions and machine-readable command
  results.
- A common frontend panel host for shipped and extension-backed renderers.
- Serializable panel definitions.
- First-class collections with paged item access.
- Static workspace export for backend-free demos.
- A smaller public panel SDK.

The remaining work is to make these contracts load-bearing across all panels,
remove the older parallel paths, and make extension-first development real.

## Pain Points v1 Must Solve

### 1. Built-in and extension panels are still different in practice

Built-in panels can access frontend stores, API helpers, and Dockview directly,
while extension panels must use the public SDK. This lets built-ins bypass SDK
limitations and allows the SDK to drift away from what useful panels actually
need.

### 2. Promoting an extension still requires conversion work

A successful custom panel may still need to be moved into the frontend source,
registered in internal renderer tables, and rewritten around internal imports
before it can ship with HyperView. This makes extensions a prototype format
rather than the normal panel development path.

### 3. Panel discovery does not describe the complete UI

Panel definitions exist in the runtime, but additional panel variants and
default panels are still described or assembled in the frontend. An agent
cannot reliably discover every panel, its capabilities, its defaults, or the
commands it exposes from one authoritative registry.

### 4. The panel SDK is not yet the complete panel platform

Panels need public access to dataset metadata, collections, pagination,
selection, embeddings, layouts, queries, panel state, commands, and host
actions. When any of these are missing, panel authors fall back to raw HTTP,
browser globals, frontend stores, or demo-specific workarounds.

### 5. Collections are not yet the universal data currency

Filtering, retrieval, neighbors, search, and selection can produce collection
state, but not every panel renders collections through the same path. Some
panels still own paging or reconstruct query behavior locally. This duplicates
logic and makes live and static behavior diverge.

### 6. Panel state and command ownership are unclear

Panel-specific behavior should not accumulate as global SDK methods or
workspace fields. Each panel type needs documented state, props, commands, and
queries. Other panels may read its public state, but mutations should go
through commands owned by that panel rather than arbitrary sibling prop or
state changes.

### 7. Workspace layout is not fully runtime-managed

Some Dockview layout state still lives in browser storage. As a result, the CLI
and APIs cannot always inspect, reproduce, or modify the exact view the user is
seeing. Panel visibility, focus, position, grouping, and sizing are workspace
state and must be agent-addressable.

### 8. Panel identity has overlapping concepts

Terms such as built-in, extension, module, kind, source, renderer, and panel
type currently overlap. This creates branching throughout the runtime,
transport models, frontend, and SDK, and makes the promotion path harder to
reason about.

### 9. Runtime snapshots contain duplicated or legacy state

Compatibility mirrors and duplicated panel state create multiple apparent
sources of truth, increase snapshot size, and make synchronization harder to
understand. V1 should expose one canonical representation for each resource.

### 10. Examples and skill guidance can drift from the real contract

Coding agents copy examples literally. Stale hooks, private APIs, raw control
requests, browser events, and panel-managed layout work quickly become repeated
patterns across demos. Examples and the HyperView skill therefore need to be
tested as part of the public API contract.

### 11. Static compatibility is not explicit enough

Some panels can run entirely from exported data, while others require Python
tools or a live runtime. Panel definitions must declare this clearly so static
exports can include supported panels and explain unavailable functionality.

### 12. The local control plane needs a clear security boundary

Repo-local extensions can remain trusted and run in process, but unrelated web
pages must not be able to mutate a running HyperView session. Local API origin
restrictions and session authentication are v1 release requirements, separate
from whether extensions themselves are sandboxed.

## Target Architecture

HyperView v1 should have a small set of distinct concepts:

- **Extension**: a package that contributes panel definitions, tools, commands,
  queries, and assets. An extension may be repo-local or shipped with
  HyperView.
- **Panel definition**: the reusable contract for a panel type, including its
  renderer, props, state, commands, queries, defaults, and capabilities.
- **Panel instance**: a concrete panel in a workspace with an id, type, bound
  data sources, props, state, and layout.
- **Collection**: a runtime-managed set of entities produced by filtering,
  retrieval, search, selection, or tools, including ordering and scores.
- **View**: the runtime-managed arrangement of panel instances, including
  grouping, visibility, sizing, and active state.
- **Command**: a typed mutation with a machine-readable result.
- **Query**: a typed read operation over runtime or dataset data.
- **Tool**: backend functionality contributed by HyperView or an extension and
  callable through the shared control surface.

These concepts should be discoverable through the runtime and usable through
the CLI, Python API, HTTP API, and panel SDK.

## Major Architectural Refactors

### 1. Make shipped panels shipped extensions

Introduce one extension packaging model for both repo-local and HyperView-
shipped panels. Promoting a panel should mean changing its distribution source
and including it in the HyperView package, not changing its implementation.

Native frontend renderers may remain as optimizations, but they must implement
the same definition, state, command, query, and SDK contracts.

### 2. Establish one authoritative panel registry

The runtime panel-definition registry should describe every panel the UI can
show. The frontend should only resolve a definition's renderer; it should not
maintain a second source of labels, defaults, capabilities, or panel variants.

Panel presets should be defaults for one panel type rather than separate types
unless their state or behavioral contracts are genuinely different.

### 3. Make the public SDK the only panel integration surface

Built-in and extension panels should use the same SDK for data, state,
selection, commands, queries, and host actions. Frontend stores, Dockview, and
raw API helpers remain private host implementation details.

The SDK should stay atomic: general collection, state, query, command, and host
primitives rather than a growing list of demo-specific methods.

### 4. Make collections the standard panel data input

Panels that display records should bind to collections. Retrieval, filtering,
neighbors, search, and tools should create or update collections, while panels
control only how those collections are presented.

The same collection-reading path must work in a live runtime and a static
export.

### 5. Make panel-owned state and commands first-class

Every panel definition may expose:

- Valid props and defaults.
- Durable state and defaults.
- Panel-owned commands.
- Read queries.
- Accepted data capabilities.

The command registry should expose panel commands through the same underlying
path in the CLI, Python API, HTTP API, and SDK. Cross-panel writes should call
the target panel's command instead of mutating its internal state directly.

### 6. Move the complete View into workspace state

The runtime View should represent panel instances, splits, tabs, position,
size constraints, visibility, collapsed state, and active panel. Dockview
becomes an adapter that applies and reports this model.

Browser storage should be limited to genuine local preferences such as theme
or display density.

### 7. Collapse the panel transport model

Use panel type to identify behavior, an implementation reference to identify
the renderer, and a distribution source to distinguish shipped from local
code. Remove overlapping kind-specific branches and compatibility fields once
the canonical model is in place.

### 8. Remove state mirrors and synchronization duplication

Store panel state once, reference it consistently, and remove legacy retrieval
or similarity mirrors. Command results and runtime events should carry enough
information for clients to update without unnecessary full-state refetches.

### 9. Preserve live and static panel parity

Extension manifests should declare whether panels support static export. The
exporter should include compatible panel modules, assets, definitions,
collections, layouts, and media. Unsupported panels should remain discoverable
with a clear unavailable reason.

### 10. Turn guidance and examples into contract tests

Maintain a reference extension that exercises props, state, commands, queries,
tools, collections, layout, and static export. Run the same extension as both a
repo-local and shipped extension without modifying its panel source.

CI should validate checked-in examples and keep the installed HyperView skill
synchronized with the real public surface.

### 11. Secure the local runtime boundary

Restrict allowed browser origins and authenticate mutating control requests
with a per-session credential. Keep the repo-local trusted-extension model;
iframe sandboxing and a remote plugin marketplace are not v1 requirements.

## Recommended Sequence

1. Define the reference extension and promotion acceptance test.
2. Finish collection-driven rendering for the built-in data panels.
3. Complete the SDK and migrate Explorer, Samples, and Scatter onto it.
4. Introduce shipped extensions and remove the parallel built-in contract.
5. Register every panel, command, and query in the runtime registry.
6. Move the full View and Dockview layout into workspace state.
7. Collapse legacy panel kinds, state mirrors, aliases, and dead metadata.
8. Validate live/static parity and update all examples and skill guidance.
9. Close the local control-plane security boundary before the v1 release.

## V1 Completion Criteria

HyperView v1 is complete when:

- A repo-local panel can become shipped without changing its source code.
- Built-in panels use only APIs available to extension panels.
- The runtime registry describes every panel the UI can display.
- Panel props, state, commands, queries, and capabilities are discoverable.
- Every mutation uses one shared command path across CLI, Python, HTTP, and
  SDK.
- Any panel can render its supported collection through a common data path.
- An agent can inspect and reproduce the complete workspace View.
- No panel imports frontend stores, Dockview, or raw API helpers.
- Runtime snapshots have one source of truth for panel and retrieval state.
- The reference extension passes unchanged as both local and shipped.
- Static exports clearly support or reject each panel.
- Examples and the HyperView skill are verified against the shipped public
  APIs.
- A browser outside the active HyperView session cannot mutate the runtime.

## Non-Goals for v1

- A public plugin marketplace.
- Sandboxing trusted repo-local extension code.
- A full multimodal field and annotation system.
- A large query language beyond the primitives required by current panels.
- Replacing LanceDB or renaming its physical storage model.
- Building fine-grained runtime event deltas before snapshot size becomes a
  measured problem.

