# Panel Modules

Use this guide when writing a custom HyperView panel module that should behave like a built-in panel. Panel modules are shipped through [extensions.md](extensions.md).

## Model

HyperView no longer treats runtime-added panels as iframe HTML pages.

Runtime custom panels are now panel modules:

- the user writes a local `panel.jsx` module (preferred) or plain `.js` module
- the module is declared in an extension manifest (`file = "panel.jsx"`)
- the module is instantiated through `hv.ui.ExtensionPanel(...)` or `hyperview ui panel add --extension ...`
- HyperView loads that module through the host panel system (JSX is transformed on the server/export path)
- the module must use only the stable `window.HyperViewPanelSDK` surface

Built-in panels and runtime panels now share the same host panel system.

**Contract boundary:** HyperView standardizes documented props, `usePanelState`,
selection, collections/`useSamples`, `useSampleResults`, sibling
`usePanelActions().updateProps`, and tools. It does not standardize the panel's
visual design. Panel authors are free to create any JSX, CSS, SVG, Canvas, or
WebGL interface appropriate to the task. Prefer public hooks only; never call
private runtime/frontend internals from an extension panel.

Panels may use their own visual system. When matching the host is useful,
HyperView exposes resolved optional color tokens: `--hv-color-background`,
`--hv-color-foreground`, `--hv-color-surface`, `--hv-color-surface-muted`,
`--hv-color-border`, `--hv-color-accent`, `--hv-color-accent-contrast`, and
`--hv-color-muted-foreground`. These are conveniences, not required styling.

Use this surface for browser panel code. Package it as an extension even
when it does not need Python tools. If the task is to open several panels in a
particular arrangement, use a workspace view from Python
(`hv.ui.View(...)` with `hv.launch(..., view=...)`) or the CLI `hyperview ui ...`
commands.

An explicit view containing only `hv.ui.Samples` and/or
`hv.ui.ExtensionPanel` works directly from dataset records and does not need a
dummy embedding or layout. A view containing `hv.ui.Scatter` still requires a
real layout or embedding space.

## Panel Module Contract

A runtime panel module must export either:

- a default React component
- or a named export `Panel`

The module runs in the browser and should use the SDK from `window.HyperViewPanelSDK`.
When a Python view provides panel `props`, HyperView passes them to the component
as the `props` prop, alongside `panel` and `panelId`; panel code can also read
them from `HyperViewPanelSDK.hooks.usePanelState().props`.

Prefer `panel.jsx` so the module stays readable. Minimal example:

```jsx
const sdk = globalThis.HyperViewPanelSDK;
const { React, hooks } = sdk;
const { usePanelState, useSamples, useTool } = hooks;

export default function MyPanel() {
  const { panelId, props } = usePanelState();
  const { samples, total } = useSamples(props.collection_id);
  const { runTool } = useTool();

  return (
    <main style={{ padding: 12, font: "12px system-ui" }}>
      <div>{`Panel: ${panelId}`}</div>
      <div>{`Samples visible: ${samples.length} / ${total}`}</div>
    </main>
  );
}
```

## Stable SDK Surface

Current global SDK fields:

- `React`
- `hooks.useCommandClient()`
- `hooks.usePanelState()`
- `hooks.usePanelActions()`
- `hooks.useSelection()`
- `hooks.useSampleResults()`
- `hooks.useCollection(collectionId)`
- `hooks.useSamples(collectionId)`
- `hooks.useSample(sampleId)`
- `hooks.useSimilarSamples({ anchorSampleId, layoutKey?, spaceKey?, k? })`
- A ranked Samples panel may set `rank.showDistance: false` when comparing
  embedding spaces with different distance metrics. Rank badges remain visible,
  but the UI does not imply that raw hyperbolic and cosine distances share a scale.
- A Samples panel may set `labelField` (or `label_field`) to a string metadata
  key when a business-facing title should be shown instead of the dataset's
  canonical class label. This affects presentation only; IDs and metadata stay intact.
- A canonical Samples panel may set `showTextSearch: true` even when it starts
  with a prepared collection. HyperView still exposes the query bar only when
  the active Live Space advertises a text-capable index; Shared Spaces hide it.
- `hooks.useTool()`
- `hooks.listTools()`
- `hooks.useHostAdapter()`
- `hooks.useSupportsTextSearch()`
- `hooks.useSupportsLassoSelection(layoutDimension)`
- `hooks.useSupportsTools()`
- `createClient(workspaceId)`

Important distinction:

- `useCommandClient()` discovers and runs backend-owned control commands. Command results include snapshots; apply them instead of refetching runtime state.
- `usePanelState()` reads concrete panel props/state and patches panel-owned state through `workspace.panel.state.patch`.
- `usePanelActions()` updates documented props on a concrete panel through the host contract. In static exports this update is ephemeral and local to the visitor.
- `useSelection()` exposes current selection and selection setters.
- `useSampleResults()` presents an explicit ordered set in the canonical Samples panel while synchronizing selection and map focus. Reset restores the full collection.
- `useCollection(collectionId)` reads runtime collection metadata. `useSamples(collectionId)` materializes `all`/`filter`/`neighbors`/`search`/`selection` collections through the paged `GET /api/collections/{id}/items` endpoint (call `loadMore()` while `hasMore`); other kinds fall back to the host-loaded sample page. `scores` carries per-sample distances for neighbors/search collections.
- `useSample(sampleId)` resolves one sample through the same live/static media contract. Use it for compact anchors and evidence cards instead of fetching `/api/samples/*` directly.
- `useSimilarSamples({ anchorSampleId, layoutKey?, spaceKey?, k? })` reads one anchor and its ordered nearest neighbours through HyperView's similarity contract. It uses the live runtime when available and the precomputed similarity index in a static export; export with `--similarity-k K` for the largest `k` the panel requests.
- `useTool()` runs registered Python tools through the authenticated HyperView server request path, resolving the active workspace from host state. Tools require a live server and fail fast in static exports.
- `hooks.listTools()` lists registered Python tool metadata for discovery.
- `useHostAdapter()` exposes host-only focus/resize helpers. Use `workspace.panel.*` commands for durable panel layout changes.
- `useSupportsTextSearch()`, `useSupportsSampleSimilarity()`,
  `useSupportsLassoSelection(layoutDimension)`, and `useSupportsTools()` expose
  host capabilities so panels can omit unavailable affordances without
  detecting static mode themselves.

### Hook return shapes

Current hook return shapes:

- `useCommandClient()` → `{ listCommands(): Promise<CommandMetadata[]>, runCommand(command, envelope?): Promise<CommandResult> }`
- `usePanelState()` → `{ panel, panelId, props, state, stateRevision, patchState(statePatch, { replaceState?, expectedRevision? }): Promise<RuntimeSnapshot> }`
- `usePanelActions()` → `{ updateProps(panelId, props): Promise<RuntimeSnapshot> }`
- `useSelection()` → `{ selectedIds: string[], selectionSource, setSelection(ids): Promise<RuntimeSnapshot>, clearSelection(): Promise<RuntimeSnapshot> }`
- `useSampleResults()` → `{ showResults(ids, { focus?, source? }): Promise<CommandResult>, resetResults({ focus?, source? }): Promise<CommandResult> }`
- `useCollection(collectionId)` → `RuntimeCollection | null`
- `useSamples(collectionId, { pageSize? })` → `{ collection, samples, scores, total, loading, error, hasMore, loadMore }`
- `useSample(sampleId)` → `{ sample, loading, error }`
- `useSimilarSamples(query)` → `{ querySample, samples, total, metric, spaceKey, loading, error }`
- `useTool()` → `{ listTools(): Promise<ToolMetadata[]>, runTool(tool, params?): Promise<unknown> }`
- `hooks.listTools()` → `Promise<ToolMetadata[]>`
- `useHostAdapter()` → `{ focusPanel(panelId): boolean, resizePanel(panelId, options): Promise<RuntimeSnapshot> }`
- `useSupportsTextSearch()` → `boolean`
- `useSupportsSampleSimilarity()` → `boolean`
- `useSupportsLassoSelection(2 | 3)` → `boolean`

Use a `pageSize` of at most 500 and call `loadMore()` while `hasMore` when a
panel needs more rows. Sample reads default to `includeThumbnails: false` and return `thumbnail_url`
for image rendering. Request inline thumbnails only when the panel specifically
needs base64 thumbnail payloads.

To clear only the current selection from a panel, use `await useSelection().clearSelection()`. To show curated business-demo results in the canonical Samples panel, use `await useSampleResults().showResults(ids)` and `resetResults()`. To create nearest-neighbor or filtered Samples state, run `collection.neighbors.create`, `collection.filter.set`, or `panel.samples.retrieval.*` through `useCommandClient().runCommand(...)`.

To run an extension Python tool from a panel:

```jsx
const sdk = globalThis.HyperViewPanelSDK;
const { React, hooks } = sdk;
const { useTool } = hooks;

export default function LabelCountsPanel() {
  const { runTool } = useTool();
  const [result, setResult] = React.useState(null);

  React.useEffect(() => {
    void runTool("label_counts.compute", { top_k: 10 }).then(setResult);
  }, [runTool]);

  return <pre>{JSON.stringify(result, null, 2)}</pre>;
}
```

## Placement

Extension-backed panel instances can be added in:

- `right`
- `bottom`
- `center`

Center placement lets a runtime panel behave like a normal center tab.

## CLI Registration

Register the extension, then instantiate a panel module into a running workspace:

```bash
hyperview extension add .hyperview/extensions/label-histogram \
  --workspace imagenette-cli-20260412

hyperview ui panel add \
  --host 127.0.0.1 \
  --port 6262 \
  --workspace imagenette-cli-20260412 \
  --panel-id label-histogram \
  --extension label-histogram \
  --extension-panel label-histogram \
  --position right
```

## Good Practices

- Prefer panel modules over HTML or iframe content.
- Author modules as `panel.jsx` with a default-export React component. HyperView does not prescribe the component hierarchy or styling; use any browser-loadable visual implementation that suits the panel.
- Make prepared/active cases obvious in the panel UI (clear active affordance + durable `usePanelState` key) so demo visitors can see which case is driving selection and samples.
- Use `useSamples(collectionId)` for host-loaded samples and collection-backed display.
- Use `useSelection()` for selection reads and selection changes.
- Use `useSampleResults()` when an extension panel presents prepared or computed result ids in the canonical Samples panel. This keeps Samples, scatter selection, and focus synchronized in both full and static modes.
- Use `usePanelActions().updateProps(panelId, props)` for documented sibling-panel prop changes, including prepared-case switching in static exports. Multiple independent native result panes should use `hv.ui.Samples(..., props={"mode": "results", "collectionId": collection_id})`; switch each pane by updating those same props instead of writing raw requests or cloning Samples UI in the extension.
- Use `useCommandClient()` for control-plane writes and command discovery.
- Use `useTool()` for registered Python tools; feature-detect `hooks.useTool` when supporting older HyperView hosts.
- Run `collection.neighbors.create` or `panel.samples.retrieval.set-anchor` for nearest-neighbor UI state; pass the layout key and let HyperView resolve the associated embedding space.
- Use `usePanelState()` for durable panel-owned state. Patch with `expectedRevision` when concurrent edits would lose user work.
- Do not use browser storage, ad hoc events, or timers to coordinate startup state or cross-panel readiness; write durable intent through runtime commands or `usePanelState()`.
- Prefer `usePanelActions().updateProps(...)` over raw `workspace.panel.update` envelopes for sibling prop changes. Use the command client for less common control-plane writes.
- Use the command client for control-plane writes.
- Use `workspace.panel.focus`, `workspace.panel.show/close`, `workspace.panel.resize`, and `workspace.panel.move` when a panel needs to durably control panel view state. Use host adapters only for transient user actions.
- Do not use `window.dispatchEvent` / `window.addEventListener` to synchronize panel state. Keep shared state in the host/runtime model, or keep the interaction inside one owner panel until a public shared-state hook exists.
- Do not use `focusPanel` or `closePanel` from mount effects to create the initial workspace layout. Compose startup layout with `hv.ui.View(...)` or CLI panel commands.
- Pass only documented panel props.
- Do not embed large generated result sets, base64 contact sheets, or evaluation artifacts in panel JavaScript. Use compact props, extension assets, or extension tools that return artifact URLs.
- Keep the panel self-contained under `.hyperview/extensions/<extension-name>/`.
- If the panel needs sibling assets, keep them next to the module and reference them with relative URLs.
- Avoid duplicating the host's panel title unless the panel has a specific reason. Everything below the host frame is owned by the panel; no HyperView visual component or toolbar is required.

## Current Limitation

Panel modules must be browser-loadable ES modules. `.jsx` is transformed to plain JS by the HyperView host and static exporter; plain `.js` remains supported but is no longer the recommended authoring form.
