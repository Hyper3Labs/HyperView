"use client";

import React from "react";
import type { IDockviewPanelHeaderProps, IDockviewPanelProps } from "dockview-react";
import { Circle, Grid3X3, Tag } from "lucide-react";

import { ExplorerPanel } from "@/components/ExplorerPanel";
import { ScatterPanel } from "@/panels/builtins/scatterPanel";
import { samplesImageGridBuiltInPanel } from "@/panels/builtins/samplesImageGridPanel";
import { createIconTabComponent } from "@/panels/definitions";

export const PANEL = {
  EXPLORER: "explorer",
  GRID: "samples",
  SCATTER: "scatter",
} as const;

const ExplorerDockPanel = React.memo(function ExplorerDockPanel() {
  return <ExplorerPanel />;
});

/** The frontend registry owns implementation lookup only; metadata lives in PanelDefinition. */
const BUILTIN_PANEL_COMPONENTS = {
  samples: samplesImageGridBuiltInPanel.Component,
  scatter: ScatterPanel,
  explorer: ExplorerDockPanel,
} satisfies Record<string, React.ComponentType<IDockviewPanelProps<Record<string, unknown>>>>;

export function getBuiltInPanelComponent(panelType: string | null | undefined) {
  if (!panelType) return null;
  return BUILTIN_PANEL_COMPONENTS[panelType as keyof typeof BUILTIN_PANEL_COMPONENTS] ?? null;
}

// Compatibility shape consumed by Header. Presets are intentionally absent: Scatter is one type.
export const CENTER_PANEL_DEFS = [
  { id: PANEL.GRID, panelType: "samples", label: "Samples", icon: Grid3X3 },
  { id: PANEL.SCATTER, panelType: "scatter", label: "Embeddings", icon: Circle },
] as const;

export const CENTER_PANEL_TAB_COMPONENTS = {
  samplesTab: createIconTabComponent(Grid3X3),
  scatterTab: createIconTabComponent(Circle),
  explorerTab: createIconTabComponent(Tag),
} satisfies Record<string, React.FunctionComponent<IDockviewPanelHeaderProps>>;

export function getPanelTabComponent(panelType: string) {
  if (panelType === "samples") return "samplesTab";
  if (panelType === "scatter") return "scatterTab";
  if (panelType === "explorer") return "explorerTab";
  return undefined;
}
