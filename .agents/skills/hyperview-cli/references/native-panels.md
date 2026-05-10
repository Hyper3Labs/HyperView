# Native Panels

Use this guide when writing a custom HyperView panel that should behave like a native built-in panel. If the panel also needs backend Python tools, use [plugins.md](plugins.md) instead.

## Model

HyperView no longer treats runtime-added panels as iframe HTML pages.

Runtime panels are now native module panels:

- the user writes a local JavaScript module file
- the module is registered through the CLI with `hyperview ui panel add --module-file ...`
- HyperView loads that module directly into the host React tree
- the module can use the stable `window.HyperViewPanelSDK` surface

Built-in panels and runtime panels now share the same host panel system.

## Panel Module Contract

A runtime panel module must export either:

- a default React component
- or a named export `Panel`

The module runs in the browser and should use the SDK from `window.HyperViewPanelSDK`.

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
    React.createElement("div", { style: { padding: 12 } }, "Hello from a native panel")
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
- `hooks.usePanelRuntimeState()`
- `hooks.usePanelSamples()`
- `hooks.usePanelSamplesView()`
- `hooks.usePanelSelection()`
- `hooks.usePanelUiState()`
- `hooks.useTool(uri)`
- `createClient(workspaceId)`

Important distinction:

- `usePanelSamplesView()` gives access to host-managed collection state and is the best hook for panels that should stay synchronized with the visible HyperView UI.
- `usePanelClient()` or `createClient()` is the escape hatch for direct backend reads and control-plane calls.
- `useTool(uri)` calls an installed backend tool registered by an extension and returns `{ loading, result, error, run, reset }`.

### Hook return shapes

Verified against the current `panel-sdk` surface:

- `usePanelSelection()` → `{ selectedIds: string[], selectionSource: SelectionUpdateSource, setSelection(ids: string[], source?: SelectionUpdateSource): void, clearSelection(): void }`
- `usePanelCommands()` → `{ setLabelFilter, setHoveredId, clearLassoSelection, clearSelection(): void, setSelection(ids: string[], source?: SelectionUpdateSource): void, focusPanel(panelId: string): boolean, closePanel(panelId: string): boolean }`
- `usePanelRuntimeState()` → `{ activeWorkspaceId, runtimeDatasetName, activeLayoutKey, requestedLayoutKey, workspaces, customPanels }`
- `usePanelUiState()` → `{ sampleGridSize, setSampleGridSize, scatterLabelOverlayMode, setScatterLabelOverlayMode }`
- `usePanelDatasetInfo()` / `usePanelSamples()` / `usePanelSamplesView()` → host-managed dataset and view state
- `useTool(uri)` → `{ loading: boolean, result: TResult | null, error: string | null, run(params?): Promise<TResult | null>, reset(): void }`
- `usePanelClient()` → low-level client; pair with `createClient(workspaceId)` for direct API calls.

To clear the current selection from a panel use `usePanelSelection().clearSelection()` or `usePanelCommands().setSelection([])`.

## Placement

Native runtime panels can be added in:

- `right`
- `bottom`
- `center`

Center placement lets a runtime panel behave like a normal center tab.

## CLI Registration

Register a panel module into a running workspace:

```bash
hyperview ui panel add \
  --host 127.0.0.1 \
  --port 6262 \
  --workspace imagenette-cli-20260412 \
  --panel-id native-label-histogram \
  --title "Native Label Histogram" \
  --position right \
  --module-file agent-context/panels/native-label-histogram/index.js
```

## Verification

After `hyperview ui panel add ...`:

- `curl 'http://127.0.0.1:6262/api/runtime?workspace_id=<ws>'` should list the panel under `workspace.ui.custom_panels[*]` with `data.module_src` set to a `/api/panels/content/<ws>/<panel-id>/<file>` URL.
- Fetching `data.module_src` should return `application/javascript` with your module body.
- The panel should appear in the live UI in the requested `position` slot.

## Good Practices

- Prefer native module panels over HTML or iframe content.
- Use `usePanelSamplesView()` for view-synchronized behavior.
- Use `usePanelCommands()` for host interactions such as label filtering or selection changes.
- Use `usePanelClient()` only for data that is not already available through the host state.
- Keep the panel self-contained under `agent-context/panels/<panel-name>/`.
- If the panel needs sibling assets, keep them next to the module and reference them with relative URLs.
- Do not render a second title/header inside a normal Dockview runtime panel unless there is a strong reason. Dockview already provides the tab title. Built-in center and runtime panels should usually start with the standardized `PanelToolbar` row.

## Current Limitation

Runtime module panels should currently be authored as browser-loadable JavaScript modules.

If an agent wants TypeScript or JSX ergonomics, it should bundle or transpile to JavaScript before registration.