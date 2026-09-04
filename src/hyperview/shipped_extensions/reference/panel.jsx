const sdk = globalThis.HyperViewPanelSDK;
if (!sdk || sdk.version !== "2") {
  throw new Error("HyperViewPanelSDK v2 is not available on window.");
}

const { React, components = {}, hooks = {} } = sdk;
const {
  Panel = ({ children, className = "" }) => (
    <div className={`flex flex-col h-full bg-card overflow-hidden ${className}`.trim()} style={{ height: "100%" }}>
      {children}
    </div>
  ),
  PanelHeader = ({ title }) => (
    <div className="border-b px-3 py-2 text-sm font-medium">{title}</div>
  ),
  PanelToolbar = ({ items, actions }) => (
    <div className="flex items-center justify-between border-b px-3 py-1.5 text-xs">{actions}</div>
  ),
  PanelToolbarButton = ({ children, ...rest }) => (
    <button type="button" className="rounded px-2 py-1 text-xs border" {...rest}>{children}</button>
  ),
} = components;
const { useCollection, usePanelState, useSelection, useSupportsTools, useTool } = hooks;

export default function ReferencePanel({ panelId, props }) {
  const { selectedIds } = useSelection();
  const panelState = usePanelState(panelId);
  const collectionId = panelState.state.collection_id || null;
  const collection = useCollection(collectionId);
  const { runTool } = useTool();
  const supportsTools = useSupportsTools();
  const [description, setDescription] = React.useState(null);
  const [error, setError] = React.useState(null);

  const updateNotes = React.useCallback(
    (event) => {
      void panelState.patchState({ notes: event.target.value });
    },
    [panelState.patchState]
  );

  const inspectWorkspace = React.useCallback(async () => {
    setError(null);
    try {
      setDescription(await runTool("reference.describe"));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    }
  }, [runTool]);

  const toolbarItems = [
    { id: "selection", label: "Selected", value: String(selectedIds.length) },
    {
      id: "collection",
      label: "Collection",
      value: collection ? collection.id : "none",
    },
  ];

  return React.createElement(
    Panel,
    null,
    React.createElement(PanelHeader, { title: props.heading || "Extension contract" }),
    React.createElement(PanelToolbar, {
      items: toolbarItems,
      actions: React.createElement(
        PanelToolbarButton,
        { type: "button", onClick: inspectWorkspace, disabled: !supportsTools },
        supportsTools ? "Inspect workspace" : "Tools unavailable"
      ),
    }),
    React.createElement(
      "div",
      { style: { display: "grid", gap: 10, minHeight: 0, overflow: "auto", padding: 12 } },
      React.createElement("textarea", {
        "aria-label": "Reference panel notes",
        value: panelState.state.notes || "",
        onChange: updateNotes,
      }),
      error ? React.createElement("p", { role: "alert" }, error) : null,
      description ? React.createElement("pre", null, JSON.stringify(description, null, 2)) : null
    )
  );
}
