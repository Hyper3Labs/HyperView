# Plugins

Use this guide when creating a HyperView plugin that includes backend Python tools and a frontend panel.

## Model

A plugin is a local extension folder with an `extension.toml` manifest. One folder can register Python tools, native panel modules, or both.

Typical shape:

```text
agent-context/extensions/selection-profile/
  extension.toml
  tools.py
  panel.jsx
```

Use `agent-context/extensions/<name>/` for explicit local installs. Use `.hyperview/extensions/<name>/` only when the plugin should be auto-discovered when `hyperview serve` starts from that repo root.

## Manifest

Use a stable extension `name`. Tool-generated artifacts are served by extension name through `ctx.url_for(...)`, while panel modules are served by panel id.

```toml
name = "selection-profile"
description = "Selection profile panel"

[[tools]]
file = "tools.py"

[[panels]]
id = "selection-profile"
title = "Selection Profile"
position = "right"
file = "panel.jsx"
```

Valid panel positions are `right`, `bottom`, and `center`.

## Backend Tools

Tools are plain Python functions decorated with `@tool("namespace.name")`. The first argument is a `RunContext`.

```python
from __future__ import annotations

from collections import Counter
from typing import Any

from hyperview.tools import RunContext, tool


@tool("selection_profile.summarize")
def summarize_selection(ctx: RunContext, *, sample_ids: list[str] | None = None) -> dict[str, Any]:
    if ctx.dataset is None:
        raise ValueError("No active dataset")

    ids = sample_ids or ctx.workspace.ui.selected_ids
    selected_samples = ctx.dataset.get_samples_by_ids(ids) if ids else []
    label_counts = Counter(sample.label or "unlabeled" for sample in selected_samples)

    return {
        "dataset": ctx.dataset.name,
        "selection_count": len(selected_samples),
        "labels": [
            {"label": label, "count": count}
            for label, count in label_counts.most_common(8)
        ],
    }
```

Use `ctx.dataset` for active dataset reads, `ctx.workspace` for workspace UI state, `ctx.extension_storage` for per-plugin writable files, `ctx.url_for(path)` for renderable artifact URLs, and `ctx.submit_job(...)` for long-running work.

## Frontend Panel

Panel modules must be browser-loadable JavaScript modules. They export a default React component or named `Panel`, and use `globalThis.HyperViewPanelSDK` rather than importing from app internals.

```js
const sdk = globalThis.HyperViewPanelSDK;
if (!sdk) throw new Error("HyperViewPanelSDK is not available on window.");

const { React, components, hooks } = sdk;
const { Panel, PanelToolbar, PanelToolbarButton } = components;
const { usePanelSelection, useTool } = hooks;

export default function SelectionProfilePanel() {
  const { selectedIds } = usePanelSelection();
  const profile = useTool("selection_profile.summarize");
  const selectionKey = selectedIds.join("|");

  React.useEffect(() => {
    profile.run({ sample_ids: selectedIds });
  }, [profile.run, selectionKey]);

  const result = profile.result;

  return React.createElement(
    Panel,
    { className: "h-full" },
    React.createElement(PanelToolbar, {
      items: [
        { id: "selection", label: "Selection", value: String(selectedIds.length) },
        { id: "status", label: "Status", value: profile.loading ? "running" : result ? "ready" : "idle" },
      ],
      actions: React.createElement(PanelToolbarButton, { onClick: () => profile.run({ sample_ids: selectedIds }) }, "Refresh"),
    }),
    React.createElement("pre", { style: { padding: 12, overflow: "auto" } }, JSON.stringify(result, null, 2))
  );
}
```

Available SDK hooks include `usePanelRuntimeState`, `usePanelDatasetInfo`, `usePanelSamplesView`, `usePanelSelection`, `usePanelCommands`, `usePanelUiState`, `usePanelClient`, and `useTool`.

## CLI Workflow

Start a runtime for an existing workspace and dataset:

```bash
hyperview serve --workspace research --dataset cifar10_demo --no-browser
```

Install the plugin into the running workspace:

```bash
hyperview extension add agent-context/extensions/selection-profile \
  --workspace research \
  --json
```

Inspect the result:

```bash
hyperview extension list --json
hyperview tools list --json
curl --max-time 2 'http://127.0.0.1:6262/api/runtime?workspace_id=research'
```

Run a tool directly:

```bash
hyperview tools run selection_profile.summarize \
  --workspace research \
  --param 'sample_ids=["sample-1","sample-8"]' \
  --json
```

Reload after editing files:

```bash
hyperview extension reload selection-profile --json
```

## Verification

A good plugin smoke test proves all of these paths:

- `extension add` returns the plugin with expected tools and panels.
- `/api/tools` includes the tool URI.
- `hyperview tools run ...` returns data from the active dataset.
- Tool-generated files under `ctx.extension_storage` are fetchable from URLs returned by `ctx.url_for(...)`.
- `/api/runtime` includes a custom panel with a `data.module_src` URL.
- Fetching `data.module_src` returns JavaScript.
- In the browser, the panel imports successfully and a `useTool()` call returns a result.

## Constraints

- Treat plugins as trusted local code. Python tools are imported and executed in the HyperView runtime process.
- Do not use bare npm imports in panel modules unless you bundle first.
- Keep plugin source outside `frontend/src`; the runtime loads it from local files.
- Keep plugin examples small and high-level. Avoid private HyperView APIs in user-facing examples.
