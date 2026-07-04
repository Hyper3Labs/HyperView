---
name: hyperview-cli
description: Use HyperView's control-plane CLI for hyperview serve, static workspace export, dataset create, workspace create, embeddings compute, layouts compute, browserless paper figure export, runtime jobs, ui layout set, ui selection set, ui panel add/update, extension add, tools run, panel modules, Python tools, and local HyperView extension workflows.
license: MIT
compatibility: Requires Python 3.10-3.13 and the hyperview CLI (`uv tool install --python 3.12 hyperview`). Runtime-control commands require a running HyperView server.
metadata:
  homepage: https://github.com/Hyper3Labs/HyperView
---

# HyperView CLI

Use the `hyperview` CLI as the primary agent interface to HyperView.

## Install the Skill

For users who installed HyperView from a package, install or refresh this agent skill with:

```bash
uv tool install --python 3.12 --upgrade hyperview && hyperview skill install
```

HyperView currently supports Python 3.10 through 3.13; `--python 3.12` keeps the persistent CLI on a broadly supported runtime. Re-running `hyperview skill install` replaces old HyperView skill copies. By default this installs into detected agent locations plus the universal `~/.agents/skills/` fallback. Limit targets with repeated `--agent` flags such as `--agent claude-code`, `--agent github-copilot`, `--agent cursor`, or `--agent universal`; use `--all-known` when you explicitly want every known agent profile. Use `--scope project` to write project-local skills such as `.claude/skills/`, `.github/skills/`, `.cursor/skills/`, or `.agents/skills/` depending on the selected agent.

## When to use it

- Create or inspect a persisted dataset.
- Create or inspect a workspace.
- Set the single dataset attached to a workspace.
- Start or control a running HyperView runtime.
- Register a custom embedding provider.
- Compute embeddings or layouts without restarting the UI.
- Export paper-ready static 3D embedding figures without opening the UI.
- Export read-only static demo bundles with `hyperview export`.
- Switch the active workspace, layout, or selection in a running session.
- Add, remove, or compose extension-backed panel instances.
- Create, install, reload, or use a local extension with Python tools and browser panels.

## Core workflow

1. Create a workspace, usually with its dataset in the same command.
2. Create the dataset if it does not exist yet.
3. Start or target a running `hyperview serve` runtime.
4. Register a provider if needed.
5. Submit embedding or layout jobs through the runtime.
6. Use `hyperview ui ...` commands to switch what the live UI shows.
7. Export paper figures with `hyperview figure export` when the user needs screenshots or publication diagrams.
8. Export read-only static demos with `hyperview export <workspace-id> --out bundle/`.
9. For extensions, create an extension folder and install it into the running workspace.

## Current model

- One dataset per workspace.
- Datasets are created separately from workspaces.
- The workspace owns the dataset selection.
- `ui layout set` changes the active layout and opens the matching built-in scatter panel.
- Samples retrieval state lives under the runtime-managed Samples panel state. `ui samples retrieval set-anchor` selects an anchor sample and pins nearest-neighbor context to an explicit layout or space.
- Runtime-added panels can be built-in samples panels, typed scatter instances bound to explicit layout keys, or extension-backed panel modules loaded into the host React tree.
- Runtime control commands use canonical namespaced ids: `workspace.*`, `panel.<type>.*`, and `collection.*`. Older command ids remain deprecated aliases for compatibility only.
- Command results carry the runtime snapshot in a `CommandResult` envelope (`ok`, `command`, `result`, `workspace`, `snapshot`, `revision`, `error`). Frontends and agents should apply the returned snapshot instead of doing an immediate `/api/runtime` refetch.
- Runtime-added panels use the stable thin `HyperViewPanelSDK` surface on `window`.
- Extensions are repo-local folders with `extension.toml`, optional Python tools, and optional panel modules.
- Extension panels run control commands through the SDK command client; Python tools are still reachable through `hyperview tools run`.
- Extensions define reusable tools/panels; workspace views compose concrete panel instances and layout. In Python launch scripts, register extensions with `session.ui.add_extension(...)` and place panels with `hv.ui.ExtensionPanel(...)`.
- In practice, create datasets and workspaces before starting the runtime for that workspace.
- `figure export` is browserless and supports 3D layouts only. It reuses the persisted 3D camera for the layout when available, otherwise it chooses a paper-oriented default view.
- Paper figure defaults are square, white-background, opaque PNGs with a faint sphere guide and direct labels for small label sets.
- `hyperview export <workspace-id> --out bundle/` writes a self-contained static frontend + JSON/API/media bundle. It is intentionally read-only: visitors can browse, select, pan/zoom, inspect panels, and use exported precomputed data, but mutations are disabled with a "Read-only demo — pip install hyperview for the full workbench" notice.

Read [references/commands.md](references/commands.md) for command recipes covering datasets, workspaces, providers, embeddings, layouts, paper figures, runtime UI state, selections, and jobs.
Read [references/panel-modules.md](references/panel-modules.md) when the task involves authoring a browser panel module.
Read [references/extensions.md](references/extensions.md) when the task involves packaging or registering custom panel code or Python tools.

## Agent guidance

- Prefer CLI commands when the goal is to operate a running HyperView session.
- Treat dataset creation and workspace binding as separate steps when needed: `dataset create ...` creates persisted data, `workspace create --dataset ...` or `workspace set-dataset ...` binds it to a workspace.
- Prefer `workspace create --dataset ...` over separate create and dataset-attach calls when setting up a new workspace.
- In Python dataset setup code, use public ingestion helpers such as `dataset.add_samples([...])` or `dataset.add_images_dir(...)`.
- Prefer built-in providers before registering custom providers. For Hyper3-CLIP, use `dataset.compute_embeddings(model="hyper3-clip-v0.5", provider="hyper-models")`.
- In comparison demos, fail fast when a required model/provider cannot compute embeddings; do not silently substitute the baseline model as a "candidate" fallback.
- When a project truly needs a custom Python provider, use `hyperview provider register ...` from the CLI or `hv.register_provider(...)` in Python.
- For custom panel code, create an extension under `.hyperview/extensions/<extension-name>/`; do not register arbitrary panel module files directly.
- For side-by-side embedding comparisons, add typed scatter panels through `hyperview ui panel add --kind scatter --layout-key ... --reference-panel-id ... --direction right`.
- Use first-class view layout fields for panel sizing and visibility: `hv.ui.PanelLayout(width=..., min_width=...)` in Python, or `hyperview ui panel resize/move/focus/close/show` from the CLI. Do not pass Dockview-specific sizing through panel props.
- Runtime panel add/update/remove, sizing, placement, focus, visibility, and state commands share the same control path in CLI and Python. Use `hyperview ui panel ...` or `session.ui`/`session.control`; do not call raw panel-control HTTP routes from examples or demos.
- When invoking raw commands, prefer canonical command names: `workspace.panel.add/update/remove/resize/move/focus/close/show`, `workspace.panel.state.get/patch`, `panel.samples.retrieval.*`, `collection.neighbors.create`, and `collection.filter.set`. Treat legacy `ui.*` command ids as deprecated aliases.
- To retitle an existing runtime panel or replace its props, use `hyperview ui panel update --panel-id ... --title ... --props-json ...` instead of remove/re-add when preserving panel identity matters.
- For nearest-neighbor comparisons, use `hyperview ui samples retrieval set-anchor --sample-id ... --layout-key ...` or run `panel.samples.retrieval.set-anchor` / `collection.neighbors.create` through the SDK command client; do not infer neighbor space from whichever scatter panel is focused.
- For collection-backed Samples panel actions, use `hyperview panel samples show-neighbors ...` and `hyperview panel labels filter ...`; read the returned `result.collection_id` and `result.collection`.
- Use `hyperview ui panel state get/patch` or SDK `usePanelState()` when a panel needs durable panel-owned state. Keep durable state under runtime panel state instead of browser local storage or ad hoc events.
- For reset controls in panels, run the relevant runtime command through the SDK command client when both selection and nearest-neighbor context should be cleared.
- Do not use timers or browser storage to wait for panel readiness or guard startup state. Write the intended state through runtime commands or `usePanelState()`.
- When a panel needs to update another runtime panel's documented props, run `workspace.panel.update` through the SDK command client; do not hand-roll panel-control HTTP requests from panel code.
- For extensions, prefer `.hyperview/extensions/<extension-name>/` in the project root. `hyperview serve` auto-discovers those folders and attaches them to the launched workspace, so they can live in version control with the dataset/project code.
- For demos/spaces that launch HyperView from Python, compose panels with `hv.ui.Horizontal`, `hv.ui.Vertical`, `hv.ui.Tabs`, `hv.ui.Grid`, `hv.ui.Scatter`, `hv.ui.Samples`, `hv.ui.ExtensionPanel`, and `hv.ui.PanelLayout`; keep extension manifests focused on reusable panel/tool definitions.
- Keep layout orchestration out of panel modules. A panel should not close, hide, or rearrange sibling panels on mount; use `hv.ui.View(...)` or `hyperview ui panel ...` to compose the workspace.
- Treat host focus/resize helpers as transient user-action helpers, not as startup layout machinery. For durable control from a panel, run the corresponding `workspace.panel.*` command.
- Pass only documented panel props through `hv.ui.ExtensionPanel(..., props=...)`.
- Tools can write files under `ctx.extension_storage` and return `ctx.url_for(path)` for panel-renderable artifact URLs.
- Put query results, benchmark tables, contact sheets, and other generated artifacts behind extension tools or compact panel props. Do not embed large base64 payloads or generated datasets inside panel JavaScript.
- Keep cross-panel coordination in host/runtime state. Do not use `window.dispatchEvent` / `window.addEventListener` as shared panel state.
- Keep extensions self-contained: `extension.toml`, `tools.py`, `panel.js` or `panel.jsx`, and any local assets in the same folder.
- Prefer `--json` output when chaining commands or inspecting results programmatically.
- Wait for embedding/layout jobs to finish before issuing layout-switch commands that depend on their results.
- Use `hyperview jobs list` or `hyperview jobs inspect <job-id>` if a compute command is long-running or you started it with `--no-wait`.
- For provider args, use repeated `--provider-arg key=value` flags.
- Treat the workspace as the durable unit. Changing datasets means setting a new workspace dataset, not switching among many datasets inside one workspace.
- Prefer panel modules over raw HTML. The panel system no longer relies on iframes.
- For paper diagrams, prefer `hyperview figure export` over browser screenshots unless the user explicitly needs exact UI chrome.
- For public, read-only examples-gallery demos, prefer `hyperview export <workspace-id> --out bundle/` over a sleeping Python server.
- For publication figures, keep the defaults first: `--theme light`, `--guide-style paper`, and `--legend auto`. Use `--show-selection` only when selected samples are meaningful and will be explained in the caption.
- The first `uv run hyperview ...` invocation in a session can take 30+ seconds (torch/datasets imports). Allow generous timeouts and avoid sending SIGINT.

## Inspecting runtime state

The runtime exposes JSON discovery endpoints alongside the CLI. Use them to obtain layout keys, sample IDs, and registered tools/panels for follow-up commands:

- `GET /api/runtime?workspace_id=<ws>` &mdash; full snapshot. Read `workspace.ui.active_layout_key`, `workspace.ui.selected_ids`, `workspace.ui.panels`, `workspace.ui.custom_panels[*].state`, `workspace.ui.custom_panels[*].data.module_src`, and registered `extensions`/`tools`.
- `GET /api/embeddings?workspace_id=<ws>` &mdash; the active or default layout, including `layout_key`, `geometry`, and sample `ids`. Use the returned `layout_key` for `hyperview ui layout set --layout-key ...` and pick from `ids` for `hyperview ui selection set --ids ...`.
- `GET /api/tools` &mdash; registered tool URIs (also returned by `hyperview tools list --json`).

Prefer layout metadata over parsing layout-key strings. Use `/api/dataset`, exported runtime snapshots, or `dataset.list_layouts()` when filtering by geometry, dimension, model, or space.
