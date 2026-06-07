"use client";

export const RUNTIME_PANEL_PREFIX = "runtime-panel:";
export const PANEL_COPY_MARKER = ":copy-";

export function isDockviewUserClosablePanelId(panelId: string) {
  return (
    panelId.startsWith(RUNTIME_PANEL_PREFIX) ||
    panelId.includes(PANEL_COPY_MARKER)
  );
}
