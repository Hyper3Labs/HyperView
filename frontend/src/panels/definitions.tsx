"use client";

import React from "react";
import type { ComponentType } from "react";
import { X } from "lucide-react";
import type {
  DockviewApi,
  DockviewPanelApi,
  IDockviewPanelHeaderProps,
  IDockviewPanelProps,
} from "dockview-react";

import { isDockviewUserClosablePanelId } from "@/lib/dockviewPanelPolicy";
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

function useDockviewTabTitle(api: DockviewPanelApi) {
  const [title, setTitle] = React.useState(api.title);

  React.useEffect(() => {
    const disposable = api.onDidTitleChange((event) => {
      setTitle(event.title);
    });

    setTitle(api.title);

    return () => disposable.dispose();
  }, [api]);

  return title;
}

export function createIconTabComponent(icon: HyperViewPanelIcon) {
  const IconTab = React.memo(function IconTab(props: IDockviewPanelHeaderProps) {
    const Icon = icon;
    const title = useDockviewTabTitle(props.api);
    const isClosable = isDockviewUserClosablePanelId(props.api.id);

    const closePanel = React.useCallback(
      (event: React.MouseEvent<HTMLButtonElement>) => {
        event.preventDefault();
        event.stopPropagation();
        props.api.close();
      },
      [props.api]
    );

    return (
      <div className="dv-default-tab hyperview-dockview-icon-tab">
        <span className="dv-default-tab-content">
          <Icon className="hyperview-dockview-icon-tab-icon h-3.5 w-3.5" />
          <span className="hyperview-dockview-icon-tab-title">{title ?? ""}</span>
        </span>
        {isClosable && (
          <button
            type="button"
            aria-label="Close panel"
            title="Close panel"
            className="dv-default-tab-action"
            onClick={closePanel}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
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
