# Panel Modules

Use this guide when writing a custom HyperView panel module that should behave like a built-in panel. Panel modules are shipped through [extensions.md](extensions.md).

## Model

HyperView no longer treats runtime-added panels as iframe HTML pages.

Runtime custom panels are now panel modules:

- the user writes a local JavaScript module file
- the module is declared in an extension manifest
- the module is instantiated through `hv.ui.ExtensionPanel(...)` or `hyperview ui panel add --extension ...`
- HyperView loads that module directly into the host React tree
- the module can use the stable `window.HyperViewPanelSDK` surface

Built-in panels and runtime panels now share the same host panel system.

Use this surface for frontend-only panel code. Package it as an extension even
when it does not need Python tools. If the task is to open several panels in a
particular arrangement, use a workspace view from Python
(`hv.ui.View(...)` with `hv.launch(..., view=...)`) or the CLI `hyperview ui ...`
commands. Do not import `HyperViewRuntime`, `CustomPanelSpec`, or `Session` from
demo/user-facing scripts just to arrange panels.

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
- `usePanelHostState()` gives low-level read access to the same host state used by built-in panels, without importing frontend internals.
- `usePanelClient()` or `createClient()` is the escape hatch for direct backend reads and control-plane calls.
- `useTool(uri)` calls an installed backend tool registered by an extension and returns `{ loading, result, error, run, reset }`.

### Hook return shapes

Verified against the current `panel-sdk` surface:

- `usePanelSelection()` → `{ selectedIds: string[], selectionSource: SelectionUpdateSource }`
- `usePanelCommands()` → `{ setLabelFilter, setHoveredId, clearLassoSelection, clearSelection(): void, setSelection(ids, { source?, persist?, clearLasso? }): Promise<RuntimeSnapshot | null>, showSimilar({ sampleId, layoutKey?, spaceKey?, k?, source?, focus?, persist? }): Promise<RuntimeSnapshot | null>, setActiveLayout(layoutKey, { persist? }): Promise<RuntimeSnapshot | null>, setLayoutViewCamera(layoutKey, camera3d): void, setLayoutViewCameraPersisted(layoutKey, camera3d): Promise<null>, focusPanel(panelId): boolean, focusBuiltin(role): boolean, focusPanelByRole(role): boolean, closePanel(panelId): boolean }`
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
- `usePanelClient()` → low-level client; pair with `createClient(workspaceId)` for direct API calls. Useful methods include `querySamples`, `aggregateSamples`, `getSamplesByIds`, `searchSimilar`, `setSimilarityQuery`, `clearSimilarityQuery`, `setSelection`, and `selectSamples`.

To clear the current selection from a panel and persist it to the runtime, use `await usePanelCommands().setSelection([])`. Pass `{ persist: false }` only for local transient UI changes.

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

## Verification

After `hyperview ui panel add --extension ...`:

- `curl 'http://127.0.0.1:6262/api/runtime?workspace_id=<ws>'` should list the panel under `workspace.ui.custom_panels[*]` with `data.module_src` set to a `/api/panels/content/<ws>/<panel-id>/<file>` URL.
- Fetching `data.module_src` should return `application/javascript` with your module body.
- The panel should appear in the live UI in the requested `position` slot.

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
- Keep the panel self-contained under `.hyperview/extensions/<extension-name>/`.
- If the panel needs sibling assets, keep them next to the module and reference them with relative URLs.
- Do not render a second title/header inside a normal Dockview runtime panel unless there is a strong reason. Dockview already provides the tab title. Built-in center and runtime panels should usually start with the standardized `PanelToolbar` row.

## Current Limitation

Panel modules should currently be authored as browser-loadable JavaScript modules.

If an agent wants TypeScript or JSX ergonomics, it should bundle or transpile to JavaScript before registration.
