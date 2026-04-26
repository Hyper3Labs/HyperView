---
name: hyperview-cli
description: Use HyperView's control-plane CLI when operating a running HyperView session or setting up a workspace for it. Trigger on tasks involving workspaces, one dataset per workspace, embeddings, layouts, custom providers, runtime jobs, UI layout switching, native module panels, or backend-plus-frontend plugins/extensions from local files.
---

# HyperView CLI

Use the `hyperview` CLI as the primary agent interface to HyperView.

## When to use it

- Create or inspect a persisted dataset.
- Create or inspect a workspace.
- Set the single dataset attached to a workspace.
- Start or control a running HyperView runtime.
- Register a custom embedding provider.
- Compute embeddings or layouts without restarting the UI.
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
7. For plugins, create an extension folder and install it into the running workspace.

## Current model

- One dataset per workspace.
- Datasets are created separately from workspaces.
- The workspace owns the dataset selection.
- `ui layout set` changes the active layout and the frontend opens the matching built-in scatter panel.
- Runtime-added panels are native module panels loaded into the host React tree.
- Runtime-added panels use the stable `HyperViewPanelSDK` surface on `window`.
- Plugins are repo-local extension folders with `extension.toml`, optional Python tools, and optional native panel modules.
- Plugin panels call backend tools through `HyperViewPanelSDK.hooks.useTool()` or `hyperview tools run`.
- In practice, create datasets and workspaces before starting the runtime for that workspace. The current runtime loads workspace registry state on startup.

Read [references/native-panels.md](references/native-panels.md) when the task involves authoring or registering a custom panel.
Read [references/plugins.md](references/plugins.md) when the task involves backend-plus-frontend plugins/extensions.

## Commands

Create a persisted dataset from Hugging Face:

```bash
hyperview dataset create cifar10_demo \
  --hf-dataset uoft-cs/cifar10 \
  --split train \
  --image-key img \
  --label-key label
```

Create a persisted dataset from a local image directory:

```bash
hyperview dataset create local_assets_demo \
  --images-dir assets
```

Create a workspace with its dataset in one step:

```bash
hyperview workspace create research \
  --dataset cifar10_demo \
  --activate
```

Change the dataset attached to a workspace:

```bash
hyperview workspace set-dataset research imagenette_clip_20260411
```

Start the runtime:

```bash
hyperview serve --workspace research --dataset cifar10_demo --no-browser
```

Register a custom provider:

```bash
hyperview provider register my-provider \
  --import-path my_pkg.provider:MyProvider
```

Compute checkpoint-backed embeddings and a layout:

```bash
hyperview embeddings compute \
  --workspace research \
  --dataset cifar10_demo \
  --provider my-provider \
  --model-id experiment-a \
  --checkpoint /path/to/checkpoint.json \
  --layout euclidean:2d
```

Add a new layout to an existing embedding space:

```bash
hyperview layouts compute \
  --workspace research \
  --dataset cifar10_demo \
  --space-key <space-key> \
  --layout euclidean:3d
```

Switch the live UI to a layout and selection:

```bash
hyperview ui layout set --workspace research --layout-key <layout-key>
hyperview ui selection set --workspace research --ids sample-1,sample-8
```

When the chosen layout is Euclidean 3D, HyperView opens or focuses the Euclidean 3D scatter panel.

Add a native panel from a local JavaScript module file:

```bash
hyperview ui panel add \
  --workspace research \
  --panel-id label-histogram \
  --title "Label Histogram" \
  --position right \
  --module-file agent-context/panels/label-histogram/index.js
```

Install a backend-plus-frontend plugin from a local extension folder:

```bash
hyperview extension add agent-context/extensions/selection-profile \
  --workspace research \
  --json
```

Inspect and run installed plugin tools:

```bash
hyperview extension list --json
hyperview tools list --json
hyperview tools run selection_profile.summarize \
  --workspace research \
  --param 'sample_ids=["sample-1","sample-8"]' \
  --json
```

## Agent guidance

- Prefer CLI commands over direct file edits when the goal is to operate a running HyperView session.
- Treat dataset creation and workspace binding as separate steps when needed: `dataset create ...` creates persisted data, `workspace create --dataset ...` or `workspace set-dataset ...` binds it to a workspace.
- Prefer `workspace create --dataset ...` over separate create and dataset-attach calls when setting up a new workspace.
- For custom panels, have the agent write panel modules outside the app source tree, for example under `agent-context/`, and then add them through `hyperview ui panel add --module-file ...`.
- For plugins, prefer `agent-context/extensions/<plugin-name>/` for explicit local installs or `.hyperview/extensions/<plugin-name>/` when you want `hyperview serve` auto-discovery.
- Tools can write files under `ctx.extension_storage` and return `ctx.url_for(path)` for panel-renderable artifact URLs.
- Keep plugins self-contained: `extension.toml`, `tools.py`, `panel.js` or `panel.jsx`, and any local assets in the same folder.
- Prefer `--json` output when chaining commands or inspecting results programmatically.
- Wait for embedding/layout jobs to finish before issuing layout-switch commands that depend on their results.
- Use `hyperview jobs list` or `hyperview jobs inspect <job-id>` if a compute command is long-running or you started it with `--no-wait`.
- For provider args, use repeated `--provider-arg key=value` flags.
- Treat the workspace as the durable unit. Changing datasets means setting a new workspace dataset, not switching among many datasets inside one workspace.
- Prefer native module panels over raw HTML. The panel system no longer relies on iframes.