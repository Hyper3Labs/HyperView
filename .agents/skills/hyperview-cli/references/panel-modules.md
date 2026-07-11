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
them from `HyperViewPanelSDK.hooks.usePanelState().props`.

Minimal example:

```js
const sdk = globalThis.HyperViewPanelSDK;
const { React, hooks } = sdk;
const { usePanelState, useSamples } = hooks;

export default function MyPanel() {
  const { panelId, props } = usePanelState();
  const { samples, total } = useSamples(props.collection_id);

  return React.createElement(
    "main",
    { style: { padding: 12, font: "12px system-ui" } },
    React.createElement("div", null, `Panel: ${panelId}`),
    React.createElement("div", null, `Samples visible: ${samples.length} / ${total}`)
  );
}
```

## Stable SDK Surface

Current global SDK fields:

- `React`
- `hooks.useCommandClient()`
- `hooks.usePanelState()`
- `hooks.usePanelSamples()`
- `hooks.useSelection()`
- `hooks.useCollection(collectionId)`
- `hooks.useSamples(collectionId)`
- `hooks.useHostAdapter()`
- `createClient(workspaceId)`

Important distinction:

- `useCommandClient()` discovers and runs backend-owned control commands. Command results include snapshots; apply them instead of refetching runtime state.
- `usePanelState()` reads concrete panel props/state and patches panel-owned state through `workspace.panel.state.patch`.
- `useSelection()` exposes current selection and selection setters.
- `useCollection(collectionId)` reads runtime collection metadata. `useSamples(collectionId)` materializes `all`/`filter`/`neighbors`/`search` collections through the paged `GET /api/collections/{id}/items` endpoint (call `loadMore()` while `hasMore`); other kinds fall back to the host-loaded sample page. `scores` carries per-sample distances for neighbors/search collections.
- `useHostAdapter()` exposes host-only focus/resize helpers. Use `workspace.panel.*` commands for durable panel layout changes.

### Hook return shapes

Current hook return shapes:

- `useCommandClient()` → `{ listCommands(): Promise<CommandMetadata[]>, runCommand(command, envelope?): Promise<CommandResult> }`
- `usePanelState()` → `{ panel, panelId, props, state, stateRevision, patchState(statePatch, { replaceState?, expectedRevision? }): Promise<RuntimeSnapshot> }`
- `useSelection()` → `{ selectedIds: string[], selectionSource, setSelection(ids): Promise<RuntimeSnapshot>, clearSelection(): Promise<RuntimeSnapshot> }`
- `useCollection(collectionId)` → `RuntimeCollection | null`
- `useSamples(collectionId, { pageSize? })` → `{ collection, samples, scores, total, loading, error, hasMore, loadMore }`
- `useHostAdapter()` → `{ focusPanel(panelId): boolean, resizePanel(panelId, options): Promise<RuntimeSnapshot> }`

Sample reads default to `includeThumbnails: false` and return `thumbnail_url`
for image rendering. Request inline thumbnails only when the panel specifically
needs base64 thumbnail payloads.

To clear the current selection from a panel, use `await useSelection().clearSelection()`. To create nearest-neighbor or filtered Samples state, run `collection.neighbors.create`, `collection.filter.set`, or `panel.samples.retrieval.*` through `useCommandClient().runCommand(...)`.

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
- Use `useSamples(collectionId)` for host-loaded samples and collection-backed display.
- Use `useSelection()` for selection reads and selection changes.
- Use `useCommandClient()` for control-plane writes and command discovery.
- Run `collection.neighbors.create` or `panel.samples.retrieval.set-anchor` for nearest-neighbor UI state; pass the layout key and let HyperView resolve the associated embedding space.
- Use `usePanelState()` for durable panel-owned state. Patch with `expectedRevision` when concurrent edits would lose user work.
- Do not use browser storage, ad hoc events, or timers to coordinate startup state or cross-panel readiness; write durable intent through runtime commands or `usePanelState()`.
- Run `workspace.panel.update` instead of hand-building panel-control HTTP requests from panel modules.
- Use the command client for control-plane writes.
- Use `workspace.panel.focus`, `workspace.panel.show/close`, `workspace.panel.resize`, and `workspace.panel.move` when a panel needs to durably control panel view state. Use host adapters only for transient user actions.
- Do not use `window.dispatchEvent` / `window.addEventListener` to synchronize panel state. Keep shared state in the host/runtime model, or keep the interaction inside one owner panel until a public shared-state hook exists.
- Do not use `focusPanel` or `closePanel` from mount effects to create the initial workspace layout. Compose startup layout with `hv.ui.View(...)` or CLI panel commands.
- Pass only documented panel props.
- Do not embed large generated result sets, base64 contact sheets, or evaluation artifacts in panel JavaScript. Use compact props, extension assets, or extension tools that return artifact URLs.
- Keep the panel self-contained under `.hyperview/extensions/<extension-name>/`.
- If the panel needs sibling assets, keep them next to the module and reference them with relative URLs.
- Avoid duplicate title/header rows unless the panel has a specific reason. Built-in center and runtime panels should usually start with the standardized `PanelToolbar` row.

## Current Limitation

Panel modules must be browser-loadable JavaScript modules.
