"use client";

import React from "react";
import type { IDockviewPanelHeaderProps } from "dockview-react";
import { Circle, Grid3X3, Puzzle, Tag, type LucideIcon } from "lucide-react";

import { ExplorerPanel } from "@/components/ExplorerPanel";
import { ScatterPanel } from "@/panels/builtins/scatterPanel";
import { SamplesImageGridPanel } from "@/panels/builtins/samplesImageGridPanel";
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
const NATIVE_PANEL_COMPONENTS = {
  "native:samples": SamplesImageGridPanel,
  "native:scatter": ScatterPanel,
  "native:explorer": ExplorerDockPanel,
} satisfies Record<string, React.ComponentType>;

export function getNativePanelComponent(renderer: string | null | undefined) {
  if (!renderer) return null;
  return NATIVE_PANEL_COMPONENTS[renderer as keyof typeof NATIVE_PANEL_COMPONENTS] ?? null;
}

const PANEL_ICONS: Record<string, LucideIcon> = {
  grid: Grid3X3,
  scatter: Circle,
  tags: Tag,
  puzzle: Puzzle,
};

export function getPanelIcon(icon: string | null, panelType: string): LucideIcon {
  return PANEL_ICONS[icon ?? ""] ?? PANEL_ICONS[panelType] ?? Puzzle;
}

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
