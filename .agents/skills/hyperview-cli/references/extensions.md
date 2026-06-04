# Extensions

Use this guide when creating a HyperView extension that includes backend Python tools and a frontend panel.

## Model

An extension is a local folder with an `extension.toml` manifest. One folder can register Python tools, panel modules, or both.

Extensions define reusable capabilities. They should not encode a whole workspace
layout or know about sibling panels. Compose concrete demo/workspace layouts
from Python with `hv.ui.View(...)` and `session.ui.apply_view(...)`, or from
the CLI with `hyperview ui panel add --extension ...`.

Preferred shape for agent-authored, project-versioned extensions:

```text
.hyperview/extensions/selection-profile/
  extension.toml
  tools.py
  panel.jsx
```

Use `.hyperview/extensions/<name>/` by default. `hyperview serve` auto-discovers those folders from the project root, even when launched from a nested directory. Use `agent-context/extensions/<name>/` only for scratch or explicit local installs that should not attach automatically on launch.

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

Treat `position` as a weak default for where the panel usually belongs. Cross-panel
relationships such as "this scatter is right of that scatter" belong to the
workspace view/composition layer, not the extension manifest.

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

Use `ctx.dataset` for active dataset reads, `ctx.workspace` for workspace UI state, `ctx.extension_storage` for per-extension writable files, `ctx.url_for(path)` for renderable artifact URLs, and `ctx.submit_job(...)` for long-running work.

### RunContext and Sample shapes

- `ctx.dataset` &mdash; the active `Dataset`. Iterate samples with `for s in ctx.dataset.samples:` (returns `list[Sample]`). Look up by id with `ctx.dataset.get_samples_by_ids(ids)`.
- `ctx.workspace.ui.selected_ids` &mdash; current selection (`list[str]`).
- `ctx.extension_storage` &mdash; `pathlib.Path` to a writable per-extension folder.
- `ctx.url_for(path)` &mdash; returns a fetchable URL for a file under `extension_storage`.
- `ctx.submit_job(...)` &mdash; schedule long-running work; returns a job handle.

`Sample` (from `hyperview.core.sample`) exposes:

- `sample.id: str`
- `sample.label: str | None`
- `sample.metadata: dict[str, Any]`

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

Available SDK hooks include `usePanelRuntimeState`, `usePanelHostState`, `usePanelDatasetInfo`, `usePanelSamplesView`, `usePanelSelectedSamples`, `usePanelSelection`, `usePanelHover`, `usePanelLayouts`, `usePanelLayoutView`, `usePanelCommands`, `usePanelUiState`, `usePanelClient`, and `useTool`.

For dataset-wide panel behavior, prefer `usePanelClient().querySamples(...)`,
`aggregateSamples(...)`, `selectSamples(...)`, `getSamplesByIds(...)`,
`searchSimilar(...)`, or a backend tool over scanning a fixed
`listSamples({ limit: ... })` page or hand-building API URLs in the browser.

Use `usePanelHostState()` for low-level synchronized host state instead of
importing frontend internals. Use narrower hooks such as `usePanelSelection()`,
`usePanelSelectedSamples()`, `usePanelHover()`, `usePanelLayouts()`, and
`usePanelLayoutView()` when the panel only needs one part of that state. Use
`usePanelCommands()` for host writes. Selection and active-layout changes
persist to runtime UI state by default; pass `{ persist: false }` only for
local transient UI changes.

`useTool(uri)` returns `{ run, result, loading, error, reset }`. Call `run(params)` to invoke the tool; `result` holds the last successful return value, `loading` is true while a call is in flight, and `error` is the last failure message (or `null`). See [panel-modules.md](panel-modules.md#hook-return-shapes) for the full hook return shape table.

## CLI Workflow

Start a runtime for an existing workspace and dataset:

```bash
hyperview serve --workspace research --dataset cifar10_demo --no-browser
```

If the extension already exists under `.hyperview/extensions/`, starting `hyperview serve` registers it automatically. For a server that is already running, install or reload the extension explicitly:

```bash
hyperview extension add .hyperview/extensions/selection-profile \
  --workspace research \
  --json
```

Installing an extension registers its tools and panel definitions. To instantiate
a panel from the CLI, add an extension-backed panel instance:

```bash
hyperview ui panel add \
  --workspace research \
  --panel-id selection-profile \
  --extension selection-profile \
  --extension-panel selection-profile \
  --position right \
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

Compose a demo view from Python instead of importing runtime internals:

```python
import hyperview as hv

view = hv.ui.View(
    hv.ui.Horizontal(
        hv.ui.Scatter("clip-map", title="CLIP", layout_key=clip_layout),
        hv.ui.Scatter("hycoclip-map", title="HyCoCLIP", layout_key=hycoclip_layout),
    ),
    hv.ui.ExtensionPanel(
        "readout",
        extension="catalog-readout",
        panel="readout",
        position="right",
    ),
)

session = hv.launch(dataset, block=False)
session.ui.add_extension(".hyperview/extensions/catalog-readout")
session.ui.apply_view(view)
```

## Verification

A good extension smoke test proves all of these paths:

- `extension add` returns the extension with expected tools and panel definitions.
- `GET /api/tools` (or `hyperview tools list --json`) includes the tool URI.
- `hyperview tools run ...` returns data from the active dataset.
- Tool-generated files under `ctx.extension_storage` are fetchable from URLs returned by `ctx.url_for(...)`.
- `GET /api/runtime?workspace_id=<workspace>` includes the panel under `workspace.ui.custom_panels[*]` with `data.module_src` set to a `/api/panels/content/<workspace>/<panel-id>/<file>` URL.
- Fetching `data.module_src` returns `application/javascript` with your module body.
- In the browser, the panel imports successfully and a `useTool()` call returns a result.

## Constraints

- Treat extensions as trusted local code. Python tools are imported and executed in the HyperView runtime process.
- Do not use bare npm imports in panel modules unless you bundle first.
- Keep extension source outside `frontend/src`; the runtime loads panel modules from local extension files.
- Keep extension examples small and high-level. Avoid private HyperView APIs in user-facing examples.
