---
name: hyperview-cli
description: Use HyperView's control-plane CLI for hyperview serve, dataset create, workspace create, embeddings compute, layouts compute, browserless paper figure export, runtime jobs, ui layout set, ui selection set, ui panel add, extension add, tools run, native module panels, backend tools, and local HyperView plugin workflows.
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
- Export paper-ready static 3D embedding figures without a browser or Node runtime.
- Switch the active workspace, layout, or selection in a running session.
- Add or remove agent-authored native module panels from local files.
- Create, install, reload, or test a local plugin/extension with Python backend tools and a frontend panel.

## Core workflow

1. Create a workspace, usually with its dataset in the same command.
2. Create the dataset if it does not exist yet.
3. Start or target a running `hyperview serve` runtime.
4. Register a provider if needed.
5. Submit embedding or layout jobs through the runtime.
6. Use `hyperview ui ...` commands to switch what the live UI shows.
7. Export paper figures with `hyperview figure export` when the user needs screenshots or publication diagrams.
8. For plugins, create an extension folder and install it into the running workspace.

## Current model

- One dataset per workspace.
- Datasets are created separately from workspaces.
- The workspace owns the dataset selection.
- `ui layout set` changes the active layout and the frontend opens the matching built-in scatter panel.
- Runtime-added panels can be typed scatter instances bound to explicit layout keys, or native module panels loaded into the host React tree.
- Runtime-added panels use the stable `HyperViewPanelSDK` surface on `window`.
- Plugins are repo-local extension folders with `extension.toml`, optional Python tools, and optional native panel modules.
- Plugin panels call backend tools through `HyperViewPanelSDK.hooks.useTool()` or `hyperview tools run`.
- In practice, create datasets and workspaces before starting the runtime for that workspace. The current runtime loads workspace registry state on startup.
- `figure export` is browserless and supports 3D layouts only. It reuses the persisted 3D camera for the layout when available, otherwise it chooses a paper-oriented default view.
- Paper figure defaults are square, white-background, opaque PNGs with a faint sphere guide and direct labels for small label sets.

Read [references/commands.md](references/commands.md) for command recipes covering datasets, workspaces, providers, embeddings, layouts, paper figures, runtime UI state, selections, and jobs.
Read [references/native-panels.md](references/native-panels.md) when the task involves authoring or registering a custom panel.
Read [references/plugins.md](references/plugins.md) when the task involves backend-plus-frontend plugins/extensions.

## Agent guidance

- Prefer CLI commands over direct file edits when the goal is to operate a running HyperView session.
- Treat dataset creation and workspace binding as separate steps when needed: `dataset create ...` creates persisted data, `workspace create --dataset ...` or `workspace set-dataset ...` binds it to a workspace.
- Prefer `workspace create --dataset ...` over separate create and dataset-attach calls when setting up a new workspace.
- For custom module panels, have the agent write panel modules outside the app source tree, for example under `agent-context/`, and then add them through `hyperview ui panel add --module-file ...`.
- For side-by-side embedding comparisons, add typed scatter panels through `hyperview ui panel add --kind scatter --layout-key ... --reference-panel-id ... --direction right`.
- For plugins, prefer `.hyperview/extensions/<plugin-name>/` in the project root. `hyperview serve` auto-discovers those folders and attaches them to the launched workspace, so they can live in version control with the dataset/project code.
- Tools can write files under `ctx.extension_storage` and return `ctx.url_for(path)` for panel-renderable artifact URLs.
- Keep plugins self-contained: `extension.toml`, `tools.py`, `panel.js` or `panel.jsx`, and any local assets in the same folder.
- Prefer `--json` output when chaining commands or inspecting results programmatically.
- Wait for embedding/layout jobs to finish before issuing layout-switch commands that depend on their results.
- Use `hyperview jobs list` or `hyperview jobs inspect <job-id>` if a compute command is long-running or you started it with `--no-wait`.
- For provider args, use repeated `--provider-arg key=value` flags.
- Treat the workspace as the durable unit. Changing datasets means setting a new workspace dataset, not switching among many datasets inside one workspace.
- Prefer native module panels over raw HTML. The panel system no longer relies on iframes.
- For paper diagrams, prefer `hyperview figure export` over browser screenshots unless the user explicitly needs exact UI chrome. It does not require Playwright, browser bundling, or Node at runtime.
- For publication figures, keep the defaults first: `--theme light`, `--guide-style paper`, and `--legend auto`. Use `--show-selection` only when selected samples are meaningful and will be explained in the caption.
- The first `uv run hyperview ...` invocation in a session can take 30+ seconds (torch/datasets imports). Allow generous timeouts and avoid sending SIGINT.

## Inspecting runtime state

The runtime exposes JSON discovery endpoints alongside the CLI. Use them to obtain layout keys, sample IDs, and registered tools/panels for follow-up commands:

- `GET /api/runtime?workspace_id=<ws>` &mdash; full snapshot. Read `workspace.ui.active_layout_key`, `workspace.ui.selected_ids`, `workspace.ui.custom_panels[*].data.module_src`, and registered `extensions`/`tools`.
- `GET /api/embeddings?workspace_id=<ws>` &mdash; the active or default layout, including `layout_key`, `geometry`, and sample `ids`. Use the returned `layout_key` for `hyperview ui layout set --layout-key ...` and pick from `ids` for `hyperview ui selection set --ids ...`.
- `GET /api/tools` &mdash; registered tool URIs (also returned by `hyperview tools list --json`).

Layout keys encode geometry and dimension as a substring (e.g. `..._euclidean_umap__2d_...`, `..._hyperbolic_umap__3d_...`). Match on those substrings when filtering by geometry/dimension.
