"use client";

import React, { useEffect, useState, type ComponentType } from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { AlertTriangle, Puzzle } from "lucide-react";

import { backendUrl } from "@/lib/api";
import { PanelInstanceProvider, installHyperViewPanelSdkGlobal } from "@/panel-sdk";
import type { RuntimePanel } from "@/types";
import { useStore } from "@/store/useStore";

import { Panel } from "./Panel";
import { PanelHeader } from "./PanelHeader";

interface RuntimeModulePanelParams {
  panelId: string;
}

interface RuntimePanelComponentProps {
  panel: RuntimePanel;
  panelId: string;
  props?: Record<string, unknown>;
}

type RuntimePanelModuleExport =
  | ComponentType<RuntimePanelComponentProps>
  | {
      Component: ComponentType<RuntimePanelComponentProps>;
    };

function resolveRuntimePanelComponent(moduleValue: unknown): ComponentType<RuntimePanelComponentProps> {
  const runtimeModule = moduleValue as {
    default?: RuntimePanelModuleExport;
    Panel?: ComponentType<RuntimePanelComponentProps>;
  };

  const candidate = runtimeModule.default ?? runtimeModule.Panel ?? null;
  if (!candidate) {
    throw new Error(
      "Panel module must export a React component as the default export or named export 'Panel'."
    );
  }

  if (typeof candidate === "function") {
    return candidate as ComponentType<RuntimePanelComponentProps>;
  }

  if (typeof candidate === "object" && candidate && "Component" in candidate) {
    return candidate.Component;
  }

  throw new Error("Unsupported panel module export shape.");
}

export function RuntimeModulePanel(
  props: IDockviewPanelProps<RuntimeModulePanelParams>
) {
  const panelId = props.params?.panelId ?? "";
  const panel = useStore((state) =>
    state.customPanels.find((candidate) => candidate.id === panelId) ?? null
  );
  const [LoadedPanel, setLoadedPanel] = useState<ComponentType<RuntimePanelComponentProps> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const moduleSrc = backendUrl(panel?.data.module_src);
  const hasPanel = panel !== null;

  useEffect(() => {
    let cancelled = false;

    async function loadPanelModule(moduleSrc: string) {
      installHyperViewPanelSdkGlobal();
      setLoadedPanel(null);
      setError(null);

      try {
        const loadedModule = await import(/* webpackIgnore: true */ moduleSrc);
        const Component = resolveRuntimePanelComponent(loadedModule);
        if (!cancelled) {
          setLoadedPanel(() => Component);
        }
      } catch (loadError) {
        if (!cancelled) {
          const message = loadError instanceof Error ? loadError.message : String(loadError);
          setError(message);
        }
      }
    }

    if (moduleSrc) {
      void loadPanelModule(moduleSrc);
    } else {
      setLoadedPanel(null);
      setError(hasPanel ? "Panel module source is not available." : null);
    }

    return () => {
      cancelled = true;
    };
  }, [hasPanel, moduleSrc]);

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

  if (error) {
    return (
      <Panel className="h-full">
        <PanelHeader title={panel.title} icon={<AlertTriangle className="h-3.5 w-3.5" />} />
        <div className="flex h-full items-center justify-center px-4 text-sm text-muted-foreground">
          {error}
        </div>
      </Panel>
    );
  }

  if (!LoadedPanel) {
    return (
      <Panel className="h-full">
        <PanelHeader title={panel.title} icon={<Puzzle className="h-3.5 w-3.5" />} />
        <div className="flex h-full items-center justify-center px-4 text-sm text-muted-foreground">
          Loading panel module...
        </div>
      </Panel>
    );
  }

  const panelProps = panel.props ?? {};
  return (
    <PanelInstanceProvider
      value={{
        panel,
        panelId: panel.id,
        props: panelProps,
        state: panel.state ?? {},
        stateRevision: panel.state_revision ?? 0,
      }}
    >
      <LoadedPanel panel={panel} panelId={panel.id} props={panelProps} />
    </PanelInstanceProvider>
  );
}
