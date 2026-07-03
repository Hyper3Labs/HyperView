"use client";

import React from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { AlertTriangle, Puzzle } from "lucide-react";

import { PanelInstanceProvider } from "@/panel-sdk";
import { getBuiltInCenterPanelDefinitionForPanelType } from "@/panels/registry";
import { useStore } from "@/store/useStore";
import type { RuntimePanel } from "@/types";

import { Panel } from "./Panel";
import { PanelHeader } from "./PanelHeader";

interface RuntimeBuiltInPanelParams extends Record<string, unknown> {
  panelId: string;
  builtinPanelType?: string;
}

function panelInstanceValue(panel: RuntimePanel) {
  return {
    panel,
    panelId: panel.id,
    props: panel.props ?? {},
    state: panel.state ?? {},
    stateRevision: panel.state_revision ?? 0,
  };
}

export function RuntimeBuiltInPanel(
  props: IDockviewPanelProps<RuntimeBuiltInPanelParams>
) {
  const panelId = props.params?.panelId ?? "";
  const panel = useStore((state) =>
    state.customPanels.find((candidate) => candidate.id === panelId) ?? null
  );
  const builtinPanelType =
    props.params?.builtinPanelType ?? panel?.builtin_panel ?? panel?.panel_type;
  const definition = getBuiltInCenterPanelDefinitionForPanelType(builtinPanelType);

  if (!panel) {
    return (
      <Panel className="h-full">
        <PanelHeader title="Panel unavailable" icon={<Puzzle className="h-3.5 w-3.5" />} />
        <div className="flex h-full items-center justify-center px-4 text-sm text-muted-foreground">
          This runtime panel is no longer available.
        </div>
      </Panel>
    );
  }

  if (!definition) {
    return (
      <Panel className="h-full">
        <PanelHeader title={panel.title} icon={<AlertTriangle className="h-3.5 w-3.5" />} />
        <div className="flex h-full items-center justify-center px-4 text-sm text-muted-foreground">
          Unsupported built-in panel type: {builtinPanelType ?? "unknown"}
        </div>
      </Panel>
    );
  }

  const Component = definition.Component;
  const nextParams = {
    ...(panel.props ?? {}),
    ...(props.params ?? {}),
    panelId: panel.id,
    builtinPanelType,
  };

  return (
    <PanelInstanceProvider value={panelInstanceValue(panel)}>
      <Component {...props} params={nextParams} />
    </PanelInstanceProvider>
  );
}
