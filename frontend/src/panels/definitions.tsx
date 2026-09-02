"use client";

import React from "react";
import type { ComponentType } from "react";
import { X } from "lucide-react";
import type { DockviewPanelApi, IDockviewPanelHeaderProps } from "dockview-react";

import { isDockviewUserClosablePanelId } from "@/lib/dockviewPanelPolicy";

export type HyperViewPanelIcon = ComponentType<{ className?: string }>;

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
