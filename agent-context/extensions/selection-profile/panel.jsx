const sdk = globalThis.HyperViewPanelSDK;
if (!sdk) throw new Error("HyperViewPanelSDK is not available on window.");

const { React, components, hooks } = sdk;
const { Panel, PanelToolbar, PanelToolbarButton } = components;
const { usePanelSelection, usePanelRuntimeState, useTool } = hooks;

function LabelBar({ item, total }) {
  const pct = total > 0 ? Math.round((item.count / total) * 100) : 0;
  return React.createElement(
    "div",
    { style: { display: "grid", gap: 4 } },
    React.createElement(
      "div",
      { style: { display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12 } },
      React.createElement("span", { style: { color: "var(--foreground)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, item.label),
      React.createElement("span", { style: { color: "var(--muted-foreground)", fontVariantNumeric: "tabular-nums" } }, `${item.count} - ${pct}%`)
    ),
    React.createElement(
      "div",
      { style: { height: 4, overflow: "hidden", borderRadius: 999, background: "rgba(148,163,184,0.18)" } },
      React.createElement("div", { style: { width: `${pct}%`, height: "100%", background: "#38bdf8" } })
    )
  );
}

export default function SelectionProfilePanel() {
  const { selectedIds } = usePanelSelection();
  const { activeWorkspaceId } = usePanelRuntimeState();
  const profile = useTool("selection_profile.summarize");
  const selectionKey = selectedIds.join("|");

  React.useEffect(() => {
    profile.run({ sample_ids: selectedIds });
  }, [profile.run, selectionKey]);

  const result = profile.result;
  const toolbarItems = [
    { id: "workspace", label: "Workspace", value: activeWorkspaceId || "none" },
    { id: "selection", label: "Selection", value: String(selectedIds.length) },
    { id: "status", label: "Status", value: profile.loading ? "running" : profile.error ? "error" : result ? "ready" : "idle" },
  ];

  return React.createElement(
    Panel,
    { className: "h-full" },
    React.createElement(PanelToolbar, {
      items: toolbarItems,
      actions: React.createElement(PanelToolbarButton, { onClick: () => profile.run({ sample_ids: selectedIds }) }, "Refresh"),
    }),
    React.createElement(
      "div",
      { style: { height: "100%", overflow: "auto", padding: 12, display: "grid", alignContent: "start", gap: 12 } },
      profile.error
        ? React.createElement("div", { style: { color: "var(--destructive, #ef4444)", fontSize: 12 } }, profile.error)
        : null,
      !result
        ? React.createElement("div", { style: { color: "var(--muted-foreground)", fontSize: 13, lineHeight: 1.5 } }, "Waiting for selection profile data.")
        : React.createElement(
            React.Fragment,
            null,
            React.createElement(
              "section",
              { style: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 } },
              React.createElement(Metric, { label: "selected", value: result.selection_count }),
              React.createElement(Metric, { label: "dataset", value: result.total_samples })
            ),
            React.createElement(
              "section",
              { style: { display: "grid", gap: 8 } },
              React.createElement("div", { style: { fontSize: 12, color: "var(--muted-foreground)" } }, "Label mix"),
              result.labels.length === 0
                ? React.createElement("div", { style: { color: "var(--muted-foreground)", fontSize: 13 } }, "Select samples to profile labels.")
                : result.labels.map((item) => React.createElement(LabelBar, { key: item.label, item, total: result.selection_count }))
            ),
            React.createElement(
              "section",
              { style: { display: "grid", gap: 6 } },
              React.createElement("div", { style: { fontSize: 12, color: "var(--muted-foreground)" } }, "Sample preview"),
              result.samples.map((sample) =>
                React.createElement(
                  "div",
                  { key: sample.id, style: { display: "grid", gridTemplateColumns: "1fr auto", gap: 8, padding: "6px 0", borderTop: "1px solid rgba(148,163,184,0.14)" } },
                  React.createElement("span", { style: { color: "var(--foreground)", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, sample.filename),
                  React.createElement("span", { style: { color: "var(--muted-foreground)", fontSize: 11 } }, sample.label || "unlabeled")
                )
              )
            )
          )
    )
  );
}

function Metric({ label, value }) {
  return React.createElement(
    "div",
    { style: { border: "1px solid rgba(148,163,184,0.18)", borderRadius: 6, padding: 10, background: "rgba(15,23,42,0.24)" } },
    React.createElement("div", { style: { color: "var(--muted-foreground)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0 } }, label),
    React.createElement("div", { style: { color: "var(--foreground)", fontSize: 20, fontWeight: 600, fontVariantNumeric: "tabular-nums" } }, String(value))
  );
}
