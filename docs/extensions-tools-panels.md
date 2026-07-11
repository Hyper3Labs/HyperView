# Extensions, Tools, and Panels — concepts and boundaries

Status: reference. Written 2026-07-12 against `codex/hyperview-v1` (post Wave 5).
Companion to `docs/panel-extension-refactor-2026-07.md` (design rationale) and
`docs/multimodal-plan-2026-07.md` (M2 renderer registration, deferred).

The one-sentence version: **extensions ship things, tools compute things, panels
show things.**

## The three concepts

### Tool — a verb

A tool is a named server-side function registered with the `@tool` decorator
(`src/hyperview/tools.py`):

```python
from hyperview.tools import RunContext, tool

@tool("label_counts.compute")
def compute_label_counts(ctx: RunContext, *, top_k: int = 10) -> dict:
    ...
```

It receives a `RunContext` (active dataset, workspace) and returns JSON. It has
no UI. The defining property: **a tool must make sense when called headlessly**
— from a panel, the CLI, a notebook, or an agent. The name is deliberate: tools
map 1:1 onto LLM tool-calling, which is what makes the runtime agent-addressable.

Tools are listed at `GET /api/tools` and invoked via `POST /api/tools/run`.
Panels reach them through the panel SDK (`useTool`), never raw `fetch`.

### Panel — a view

A panel is a UI surface in the dockview workspace. It has two halves:

- **Metadata** (Python, serializable): a `PanelDefinition`
  (`src/hyperview/panel_definitions.py`) — panel type, label, props/state
  schemas, default layout, which commands and queries it uses, and
  `static_compatible`. This is the half agents and the runtime reason about;
  it is listed at `GET /api/panel-definitions`.
- **Renderer** (JS): either a built-in React component
  (`frontend/src/panels/builtins/`) or an extension ES module served with a
  JSX transform and dynamically imported against the `window.HyperViewPanelSDK`
  global (`frontend/src/components/PanelHost.tsx`).

A panel owns presentation and interaction state only. Panel state is
runtime-owned, revisioned, and patched via `usePanelState().patchState` — which
is why workspaces snapshot, sync over SSE, and export statically. Everything a
panel reads comes through SDK queries and collections; everything it changes
goes through commands or tools.

### Extension — a package

An extension is a folder with an `extension.toml` manifest
(`src/hyperview/extensions.py`), usually under `.hyperview/extensions/` in the
user's repo:

```toml
name = "lrp"
description = "LRP explainability"

[[tools]]
file = "tools.py"

[[panels]]
id = "lrp"
title = "LRP"
position = "right"
file = "panel.jsx"
```

An extension is **not a runtime concept**. At runtime there are only its
contributions — tools and panels (and, once M2 lands, sample renderers) —
tagged with the extension name so they register and unregister as a group. The
extension is the unit of distribution and trust, nothing more. The trust model
is repo-local: extension Python runs in-process and panel JS runs in the main
frame, which is acceptable precisely because an extension is a folder somebody
(or somebody's agent) checked into their own repo.

## Boundary rules

Two rules resolve almost every "where does this code go?" question:

1. **The static-export test.** A panel must be able to render from a static
   bundle's snapshot data alone. If your code needs the live dataset or
   compute, it is a tool, and the panel calls it. If a panel genuinely cannot
   work statically, it declares `static_compatible = false` with a
   `static_reason` — the host renders that reason instead of a broken panel.
2. **Commands are the runtime's verbs; tools are yours.** The control command
   registry (`src/hyperview/control/`) holds the runtime's own operations —
   workspace, panel, collection, and job lifecycle. They are namespaced
   (`workspace.*`, `panel.<type>.*`, `collection.*`, `jobs.*`), schema'd,
   versioned, and snapshot-coupled: a command result carries the runtime
   snapshot that makes it replayable in static exports. Extension logic never
   adds control commands; it adds tools. If you are about to add a REST
   endpoint or a control command for domain logic, write a tool instead.

Corollaries:

- A panel that fetches data outside the SDK is a bug, even if it works. Raw
  `fetch` misses session-token auth and static-bundle URL rewriting, and it
  couples the panel to routes that are not part of the SDK contract.
- A tool that returns HTML or drives layout is a bug. If it needs a UI, it
  needs a panel; the panel decides how to render the tool's JSON.
- Static exports run panels, not tools. Design demo extensions so the
  interesting artifacts are precomputed into collections/panel state where
  possible; reserve tool calls for genuinely interactive compute.

## What this means in practice

To add a capability to HyperView you write an extension folder containing:

| You want | You write | It shows up as |
|---|---|---|
| a computation/mutation | `@tool` function in `tools.py` | `POST /api/tools/run`, callable by panels, CLI, agents |
| a UI surface | `[[panels]]` entry + `panel.jsx` (default export a component using `window.HyperViewPanelSDK` hooks) | a dockview panel with runtime-managed state |
| a way to draw a sample type | (deferred — M2 `[[renderers]]`, see multimodal plan D4) | tile renderer in sample grids |

No frontend fork, no build step, no core PR. This is the deliberate contrast
with FiftyOne's plugin model (source install + Vite config + coupling to
internal state) and it is the property to protect when extending any of this.

## Known seams (deliberate, revisit later)

- **Tools vs. commands duality.** Two dispatch paths exist today. The likely
  end state is tools becoming commands under an `ext.<name>.*` namespace with
  `owner=<extension>`, giving one enumerable surface for agents. Deferred
  until real tool usage patterns exist; the two-tier rule above is the
  contract in the meantime.
- **M2 renderer registration** (`[[renderers]]` in the manifest) and **Phase 9
  `accepts` declarations** are designed but not built.
- **No sandboxing** of extension code, by design of the repo-local trust
  model. Revisit if extensions ever install from outside the repo.
