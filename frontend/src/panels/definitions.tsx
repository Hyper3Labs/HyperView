"use client";

import React from "react";
import type { ComponentType } from "react";
import type {
  DockviewApi,
  IDockviewPanelHeaderProps,
  IDockviewPanelProps,
} from "dockview";

import { PanelTitle } from "@/components/PanelTitle";
import type { DatasetInfo } from "@/types";

export type DockviewAddPanelOptions = Parameters<DockviewApi["addPanel"]>[0];
export type DockviewPanelPosition = DockviewAddPanelOptions["position"];
export type HyperViewPanelIcon = ComponentType<{ className?: string }>;
export type HyperViewDockviewPanelComponent<
  TParams extends Record<string, any> = Record<string, unknown>,
> = ComponentType<IDockviewPanelProps<TParams>>;

export interface BuiltInCenterPanelDefinition<
  TParams extends Record<string, any> = Record<string, unknown>,
> {
  id: string;
  component: string;
  title: string;
  label: string;
  icon: HyperViewPanelIcon;
  tabComponent: string;
  Component: HyperViewDockviewPanelComponent<TParams>;
  TabComponent: ComponentType<IDockviewPanelHeaderProps>;
  visibleInViewMenu?: boolean;
  buildAddPanelOptions: (args: {
    api: DockviewApi;
    datasetInfo: DatasetInfo | null;
    position?: DockviewPanelPosition;
  }) => DockviewAddPanelOptions;
}

export function createIconTabComponent(icon: HyperViewPanelIcon) {
  const IconTab = React.memo(function IconTab(props: IDockviewPanelHeaderProps) {
    return (
      <PanelTitle
        title={props.api.title}
        icon={React.createElement(icon, { className: "h-3.5 w-3.5" })}
        fullHeight
        className="h-full"
        titleClassName="truncate"
      />
    );
  });

  IconTab.displayName = `IconTab(${icon.displayName ?? icon.name ?? "Panel"})`;

  return IconTab;
}

export function defineBuiltInCenterPanel<
  TParams extends Record<string, any> = Record<string, unknown>,
>(
  definition: Omit<BuiltInCenterPanelDefinition<TParams>, "TabComponent"> & {
    TabComponent?: ComponentType<IDockviewPanelHeaderProps>;
  }
): BuiltInCenterPanelDefinition<TParams> {
  return {
    ...definition,
    TabComponent:
      definition.TabComponent ?? createIconTabComponent(definition.icon),
  };
}