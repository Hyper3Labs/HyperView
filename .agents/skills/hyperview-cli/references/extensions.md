# Extensions

Use this guide when creating a HyperView extension that includes Python tools and a browser panel.

## Model

An extension is a local folder with an `extension.toml` manifest. One folder can register Python tools, panel modules, or both.

Extensions define reusable capabilities. They should not encode a whole workspace
layout or know about sibling panels. Compose concrete demo/workspace layouts
from Python with `hv.ui.View(...)` and `session.ui.apply_view(...)`, or from
the CLI with `hyperview ui panel add --extension ...`.

Extensions should also keep generated data out of panel source. If a panel
needs ranked query results, benchmark summaries, contact sheets, or other
artifacts, generate or read them from an extension tool and return compact JSON or
URLs from `ctx.url_for(...)`.

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

Browser-only panels are static-compatible by default. A panel that requires a
live API or Python tool must declare that requirement so static exports can keep
the panel in the view without publishing an unusable module:

```toml
static_compatible = false
static_reason = "Requires the selection_profile.summarize Python tool."
```

Valid panel positions are `right`, `bottom`, and `center`.

Treat `position` as a weak default for where the panel usually belongs. Cross-panel
relationships such as "this scatter is right of that scatter" belong to the
workspace view/composition layer, not the extension manifest.

## Python Tools

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

## Browser Panel

Prefer `panel.jsx`. Modules export a default React component or named `Panel`,
and must use only `globalThis.HyperViewPanelSDK` public hooks. Prioritize the
data/interaction contract (props, selection, collections, sample results,
sibling prop updates, panel state) over visual polish.

```jsx
const sdk = globalThis.HyperViewPanelSDK;
if (!sdk) throw new Error("HyperViewPanelSDK is not available on window.");

const { React, hooks } = sdk;
const { useSelection, usePanelState } = hooks;

export default function SelectionProfilePanel() {
  const { selectedIds } = useSelection();
  const { state, patchState } = usePanelState();
  const selectionKey = selectedIds.join("|");

  React.useEffect(() => {
    patchState({ last_selection: selectedIds });
  }, [patchState, selectionKey]);

  return (
    <main style={{ padding: 12, font: "12px system-ui" }}>
      <div>{`Selected: ${selectedIds.length}`}</div>
      <pre>{JSON.stringify(state, null, 2)}</pre>
    </main>
  );
}
```

Available SDK hooks are intentionally thin: `useCommandClient`, `usePanelState`,
`usePanelActions`, `useSelection`, `useSampleResults`, `useCollection`,
`useSamples`, `useTool`, `listTools`, and `useHostAdapter`. See
[panel-modules.md](panel-modules.md) for return shapes.

For dataset-wide panel behavior, prefer runtime collections and
`useSamples(collectionId)` over scanning a fixed page or hand-building API URLs
in the browser. When a panel needs a new filtered or nearest-neighbor result
set, run `collection.filter.set`, `collection.neighbors.create`, or
`panel.samples.retrieval.*` through `useCommandClient()`.

Use `useSelection()` for synchronized selection state. Use `usePanelState()` for
panel-owned props/state. Use `usePanelActions().updateProps(...)` for documented
sibling panel prop changes (including prepared-case switching in static exports).
For two independent prepared result panes, construct each native Samples panel
with `props={{"mode": "results", "collectionId": collection_id}}`; then switch
the bound collection with `updateProps(panelId, { mode: "results", collectionId })`.
Result mode preserves prepared order, shows rank numbers, and suppresses the
live text-search bar. Use `useSampleResults()` instead when one canonical
Samples panel should own the shared result surface.
Use `useHostAdapter()` only for transient host actions such as focus; durable
layout/state changes should go through `workspace.*` commands. In static
exports, mutating backend commands are disabled, while selection and panel
state patches remain client-side and ephemeral.

Do not use browser globals such as `window.dispatchEvent` to synchronize panels,
and use SDK commands for control-plane writes. Python tools are invoked with
`hyperview tools run` or from the panel via `useTool()` when the host exposes it.

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

Extensions distributed with HyperView use the same folder, manifest, panel,
tool, props, state, command, query, and static-export contracts. Install one by
name without locating its package folder:

```bash
hyperview extension add --shipped <extension-name> \
  --workspace research \
  --json
```

Promotion from repo-local to shipped distribution must not require changes to
the extension's panel or tool source.

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

Reload an installed extension:

```bash
hyperview extension reload selection-profile --json
```

Compose a demo view from Python:

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
        layout=hv.ui.PanelLayout(width=340, min_width=280),
    ),
    active_panel="readout",
)

session = hv.launch(dataset, block=False)
session.ui.add_extension(".hyperview/extensions/catalog-readout")
session.ui.apply_view(view)
```

## Constraints

- Treat extensions as trusted local code. Python tools are imported and executed in the HyperView runtime process.
- Panel modules should use the SDK global and extension-local assets.
- Keep extension files under `.hyperview/extensions/<name>/`.
- Keep extension examples small and high-level. Use documented HyperView APIs.
