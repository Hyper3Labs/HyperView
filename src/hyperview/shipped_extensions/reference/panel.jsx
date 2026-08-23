const sdk = globalThis.HyperViewPanelSDK;
if (!sdk || sdk.version !== "2") {
  throw new Error("HyperViewPanelSDK v2 is not available on window.");
}

const { React, hooks } = sdk;
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

  return React.createElement(
    "main",
    { style: { display: "grid", gap: 10, height: "100%", overflow: "auto", padding: 12 } },
    React.createElement("strong", null, props.heading || "Extension contract"),
    React.createElement("span", null, `${selectedIds.length} selected`),
    React.createElement("span", null, collection ? `Collection: ${collection.id}` : "No collection bound"),
    React.createElement("textarea", {
      "aria-label": "Reference panel notes",
      value: panelState.state.notes || "",
      onChange: updateNotes,
    }),
    React.createElement(
      "button",
      { type: "button", onClick: inspectWorkspace, disabled: !supportsTools },
      supportsTools ? "Inspect workspace" : "Live tools unavailable"
    ),
    error ? React.createElement("p", { role: "alert" }, error) : null,
    description ? React.createElement("pre", null, JSON.stringify(description, null, 2)) : null
  );
}
