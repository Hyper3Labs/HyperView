# Panel Modules

Use this guide when writing a custom HyperView panel module that should behave like a built-in panel. Panel modules are shipped through [extensions.md](extensions.md).

## Model

HyperView no longer treats runtime-added panels as iframe HTML pages.

Runtime custom panels are now panel modules:

- the user writes a local JavaScript module file
- the module is declared in an extension manifest
- the module is instantiated through `hv.ui.ExtensionPanel(...)` or `hyperview ui panel add --extension ...`
- HyperView loads that module through the host panel system
- the module can use the stable `window.HyperViewPanelSDK` surface

Built-in panels and runtime panels now share the same host panel system.

Use this surface for browser panel code. Package it as an extension even
when it does not need Python tools. If the task is to open several panels in a
particular arrangement, use a workspace view from Python
(`hv.ui.View(...)` with `hv.launch(..., view=...)`) or the CLI `hyperview ui ...`
commands.

## Panel Module Contract

A runtime panel module must export either:

- a default React component
- or a named export `Panel`

The module runs in the browser and should use the SDK from `window.HyperViewPanelSDK`.
When a Python view provides panel `props`, HyperView passes them to the component
as the `props` prop, alongside `panel` and `panelId`; panel code can also read
them with `HyperViewPanelSDK.hooks.usePanelProps()`.

Minimal example:

```js
const sdk = globalThis.HyperViewPanelSDK;
const { React, components, hooks } = sdk;
const { Panel, PanelToolbar } = components;
const { usePanelRuntimeState } = hooks;

export default function MyPanel() {
  const { runtimeDatasetName } = usePanelRuntimeState();

  return React.createElement(
    Panel,
    { className: "h-full" },
    React.createElement(PanelToolbar, {
      items: [{ id: "dataset", label: "Dataset", value: runtimeDatasetName || "unknown" }],
    }),
    React.createElement("div", { style: { padding: 12 } }, "Hello from a panel module")
  );
}
```

## Stable SDK Surface

Current global SDK fields:

- `React`
- `components.Panel`
- `components.PanelHeader`
- `components.PanelTitle`
- `components.PanelToolbar`
- `components.PanelToolbarButton`
- `components.PanelToolbarMenu`
- `hooks.usePanelClient()`
- `hooks.usePanelCommands()`
- `hooks.usePanelDatasetInfo()`
- `hooks.usePanelHostState()`
- `hooks.usePanelHover()`
- `hooks.usePanelInstance()`
- `hooks.usePanelLayouts()`
- `hooks.usePanelLayoutView()`
- `hooks.usePanelProps()`
- `hooks.usePanelRuntimeState()`
- `hooks.usePanelSamples()`
- `hooks.usePanelSamplesView()`
- `hooks.usePanelSelectedSamples()`
- `hooks.usePanelSelection()`
- `hooks.usePanelUiState()`
- `hooks.useTool(uri)`
- `createClient(workspaceId)`

Important distinction:

- `usePanelSamplesView()` gives access to host-managed collection state and is the best hook for panels that should stay synchronized with the visible HyperView UI.
- `usePanelHostState()` gives read access to the same host state used by built-in panels.
- `usePanelClient()` is an escape hatch for API data reads that are not already exposed through host state or commands.
- `useTool(uri)` calls an installed Python tool registered by an extension and returns `{ loading, result, error, run, reset }`.

### Hook return shapes

Current hook return shapes:

- `usePanelSelection()` → `{ selectedIds: string[], selectionSource: SelectionUpdateSource }`
- `usePanelCommands()` → `{ setLabelFilter, setHoveredId, clearLassoSelection, clearSelection(): void, setSelection(ids, { source?, persist?, clearLasso? }): Promise<RuntimeSnapshot | null>, showSimilar({ sampleId, layoutKey, k?, source?, focus?, persist? }): Promise<RuntimeSnapshot | null>, setActiveLayout(layoutKey, { persist? }): Promise<RuntimeSnapshot | null>, setLayoutViewCamera(layoutKey, camera3d): void, setLayoutViewCameraPersisted(layoutKey, camera3d): Promise<null>, setPanelLayout(panelId, { width?, height?, minWidth?, minHeight?, maxWidth?, maxHeight? }), resizePanel(panelId, { width?, height?, minWidth?, minHeight?, maxWidth?, maxHeight? }), movePanel(panelId, { position, referencePanelId?, direction? }), setPanelVisible(panelId, visible), setActivePanel(panelId), focusPanel(panelId): boolean, focusBuiltin(role): boolean, focusPanelByRole(role): boolean, closePanel(panelId): boolean }`. `showSimilar` is layout-scoped: pass the layout key and HyperView resolves the associated embedding space automatically. `persist` accepts `true`, `false`, or `"background"` for selection/layout/similarity commands; omitted/`"background"` updates local state immediately and writes runtime state asynchronously, `true` waits for runtime persistence, and `false` is local-only.
- `usePanelHover()` → `{ hoveredId, setHoveredId(id), clearHover() }`
- `usePanelLayoutView(layoutKey?)` → `{ layoutKey, view, camera3d, setCamera3d(camera3d) }`
- `usePanelLayouts()` → `{ layouts, spaces, get(layoutKey), getSpace(spaceKey), find(query), filter(query) }`; query supports `layoutKey`, `spaceKey`, `geometry`, `modelId`, and `dimension`.
- `usePanelSelectedSamples({ includeThumbnails? })` → `{ selectedIds, samples, loading, error }`
- `usePanelRuntimeState()` → `{ activeWorkspaceId, runtimeDatasetName, activeLayoutKey, activeSimilarityQuery, requestedLayoutKey, workspaces, customPanels, viewRevision, layoutViews }`
- `usePanelHostState()` → grouped low-level host state: `{ instance, runtime, datasetInfo, samples, samplesView, selection, hover, ui, filters, lasso, neighbors }`
- `usePanelProps()` → props supplied by the concrete `hv.ui.ExtensionPanel(...)` instance
- `usePanelUiState()` → `{ sampleGridSize, setSampleGridSize, scatterLabelOverlayMode, setScatterLabelOverlayMode }`
- `usePanelDatasetInfo()` / `usePanelSamples()` / `usePanelSamplesView()` → host-managed dataset and view state
- `useTool(uri)` → `{ loading: boolean, result: TResult | null, error: string | null, run(params?): Promise<TResult | null>, reset(): void }`
- `usePanelClient()` → API data client. Prefer host hooks and `usePanelCommands()` for UI state; useful data methods include `querySamples`, `aggregateSamples`, `getSamplesByIds`, `searchSimilar`, and `selectSamples`.

Sample reads default to `includeThumbnails: false` and return `thumbnail_url`
for image rendering. Request inline thumbnails only when the panel specifically
needs base64 thumbnail payloads.

To clear the current selection from a panel and enqueue runtime persistence, use `await usePanelCommands().setSelection([])`. Pass `{ persist: true }` when the code must wait for runtime persistence, and pass `{ persist: false }` only for local transient UI changes.

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
- Use `usePanelSamplesView()` for view-synchronized behavior.
- Use `usePanelCommands()` for host interactions such as label filtering or selection changes.
- Use `usePanelHostState()` when a custom panel needs low-level synchronized host state such as hover, selection, lasso, neighbors, layout views, or active workspace context.
- Use `usePanelLayouts()` for layout/space lookup instead of scanning `datasetInfo.layouts` by hand.
- Use `usePanelSelectedSamples()` for selected sample metadata instead of manually watching selected ids and fetching samples.
- Use `usePanelClient()` only for data that is not already available through the host state.
- Use `usePanelClient().querySamples(...)`, `aggregateSamples(...)`, or `selectSamples(...)` for dataset-wide behavior instead of fixed-limit client scans.
- Use `usePanelClient().searchSimilar(...)` instead of hand-building `/api/search/similar/...` URLs.
- Use `commands.showSimilar({ sampleId, layoutKey })` for nearest-neighbor UI state; pass the layout key and let HyperView resolve the embedding space.
- Use SDK commands or client methods for control-plane writes.
- Use `setActivePanel`, `setPanelVisible`, `resizePanel`, and `movePanel` when a panel needs to durably control panel view state. Use local `focusPanel` and `closePanel` only for transient user actions.
- Do not use `window.dispatchEvent` / `window.addEventListener` to synchronize panel state. Keep shared state in the host/runtime model, or keep the interaction inside one owner panel until a public shared-state hook exists.
- Do not use `focusPanel` or `closePanel` from mount effects to create the initial workspace layout. Compose startup layout with `hv.ui.View(...)` or CLI panel commands.
- Pass only documented panel props.
- Do not embed large generated result sets, base64 contact sheets, or evaluation artifacts in panel JavaScript. Use compact props, extension assets, or extension tools that return artifact URLs.
- Keep the panel self-contained under `.hyperview/extensions/<extension-name>/`.
- If the panel needs sibling assets, keep them next to the module and reference them with relative URLs.
- Avoid duplicate title/header rows unless the panel has a specific reason. Built-in center and runtime panels should usually start with the standardized `PanelToolbar` row.

## Current Limitation

Panel modules must be browser-loadable JavaScript modules.
