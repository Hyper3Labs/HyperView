"use client";

import React, { useEffect, useMemo, useState, type ComponentType } from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { AlertTriangle, Puzzle } from "lucide-react";

import { backendUrl } from "@/lib/api";
import { getBuiltInCenterPanelDefinitionForPanelType } from "@/panels/registry";
import { installHyperViewPanelSdkGlobal } from "@/panel-sdk";
import { useStore } from "@/store/useStore";
import type { RuntimePanel } from "@/types";

import { Panel } from "./Panel";
import { PanelHeader } from "./PanelHeader";
import { PanelInstanceProvider } from "./PanelHostContext";

interface PanelHostParams extends Record<string, unknown> {
  panelId: string;
  builtinPanelType?: string;
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

function panelInstanceValue(panel: RuntimePanel) {
  return {
    panel,
    panelId: panel.id,
    props: panel.props ?? {},
    state: panel.state ?? {},
    stateRevision: panel.state_revision ?? 0,
  };
}

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

function PanelUnavailable() {
  return (
    <Panel className="h-full">
      <PanelHeader title="Panel unavailable" icon={<Puzzle className="h-3.5 w-3.5" />} />
      <div className="flex h-full items-center justify-center px-4 text-sm text-muted-foreground">
        This runtime panel is no longer available.
      </div>
    </Panel>
  );
}

function PanelMessage({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Panel className="h-full">
      <PanelHeader title={title} icon={icon} />
      <div className="flex h-full items-center justify-center px-4 text-sm text-muted-foreground">
        {children}
      </div>
    </Panel>
  );
}

function BuiltInPanelHost({
  panel,
  props,
}: {
  panel: RuntimePanel;
  props: IDockviewPanelProps<PanelHostParams>;
}) {
  const builtinPanelType =
    props.params?.builtinPanelType ?? panel.builtin_panel ?? panel.panel_type;
  const definition = getBuiltInCenterPanelDefinitionForPanelType(builtinPanelType);

  if (!definition) {
    return (
      <PanelMessage
        title={panel.title}
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
      >
        Unsupported built-in panel type: {builtinPanelType ?? "unknown"}
      </PanelMessage>
    );
  }

  const Component = definition.Component;
  const nextParams = {
    ...(panel.props ?? {}),
    ...(props.params ?? {}),
    panelId: panel.id,
    builtinPanelType,
  };

  return <Component {...props} params={nextParams} />;
}

function ModulePanelHost({ panel }: { panel: RuntimePanel }) {
  const [LoadedPanel, setLoadedPanel] = useState<ComponentType<RuntimePanelComponentProps> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const moduleSrc = useMemo(() => backendUrl(panel.data.module_src), [panel.data.module_src]);

  useEffect(() => {
    let cancelled = false;

    async function loadPanelModule(src: string) {
      installHyperViewPanelSdkGlobal();
      setLoadedPanel(null);
      setError(null);

      try {
        const loadedModule = await import(/* webpackIgnore: true */ src);
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
      setError("Panel module source is not available.");
    }

    return () => {
      cancelled = true;
    };
  }, [moduleSrc]);

  if (error) {
    return (
      <PanelMessage
        title={panel.title}
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
      >
        {error}
      </PanelMessage>
    );
  }

  if (!LoadedPanel) {
    return (
      <PanelMessage title={panel.title} icon={<Puzzle className="h-3.5 w-3.5" />}>
        Loading panel module...
      </PanelMessage>
    );
  }

  const panelProps = panel.props ?? {};
  return <LoadedPanel panel={panel} panelId={panel.id} props={panelProps} />;
}

export function PanelHost(props: IDockviewPanelProps<PanelHostParams>) {
  const panelId = props.params?.panelId ?? "";
  const panel = useStore((state) =>
    state.customPanels.find((candidate) => candidate.id === panelId) ?? null
  );

  if (!panel) {
    return <PanelUnavailable />;
  }

  return (
    <PanelInstanceProvider value={panelInstanceValue(panel)}>
      {panel.kind === "module" ? (
        <ModulePanelHost panel={panel} />
      ) : (
        <BuiltInPanelHost panel={panel} props={props} />
      )}
    </PanelInstanceProvider>
  );
}
