"use client";

import React, { useEffect, useMemo, useState, type ComponentType } from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { AlertTriangle, Puzzle } from "lucide-react";

import { backendUrl, isStaticBundle } from "@/lib/api";
import { getNativePanelComponent } from "@/panels/registry";
import { installHyperViewPanelSdkGlobal } from "@/panel-sdk";
import { useStore } from "@/store/useStore";
import type { RuntimePanel, RuntimePanelStateEntry } from "@/types";

import { Panel } from "./Panel";
import { PanelHeader } from "./PanelHeader";
import { PanelInstanceProvider } from "./PanelHostContext";

interface PanelHostParams extends Record<string, unknown> {
  panelId: string;
  builtinPanelType?: string;
  renderer?: string;
  definitionProps?: Record<string, unknown>;
  definitionTitle?: string;
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

function panelInstanceValue(
  panel: RuntimePanel,
  panelState?: RuntimePanelStateEntry,
  hostProps?: Record<string, unknown>
) {
  return {
    panel,
    panelId: panel.id,
    props: hostProps ? { ...(panel.props ?? {}), ...hostProps } : panel.props ?? {},
    state: panelState?.state ?? {},
    stateRevision: panelState?.state_revision ?? panel.state_revision ?? 0,
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
}: {
  panel: RuntimePanel;
}) {
  const renderer = panel.renderer;
  const Component = getNativePanelComponent(renderer);

  if (!Component) {
    return (
      <PanelMessage
        title={panel.title}
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
      >
        Unsupported native panel renderer: {renderer ?? "unknown"}
      </PanelMessage>
    );
  }

  return <Component />;
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

function StaticPanelUnavailable({ panel }: { panel: RuntimePanel }) {
  return (
    <PanelMessage
      title={panel.title}
      icon={<AlertTriangle className="h-3.5 w-3.5" />}
    >
      {panel.data.static_reason ?? "This panel requires the full HyperView server."}
    </PanelMessage>
  );
}

export function PanelHost(props: IDockviewPanelProps<PanelHostParams>) {
  const panelId = props.params?.panelId ?? "";
  const panel = useStore((state) =>
    state.customPanels.find((candidate) => candidate.id === panelId) ?? null
  );
  const panelState = useStore((state) => state.panelStates[panelId]);

  if (!panel) {
    const renderer = props.params?.renderer;
    const Component = getNativePanelComponent(renderer);
    if (!Component || !renderer) return <PanelUnavailable />;
    const panelId = props.params?.panelId ?? props.api.id;
    return (
      <PanelInstanceProvider
        value={{
          panel: null,
          panelId,
          props: props.params?.definitionProps ?? {},
          state: panelState?.state ?? {},
          stateRevision: panelState?.state_revision ?? 0,
        }}
      >
        <Component />
      </PanelInstanceProvider>
    );
  }

  if (isStaticBundle() && panel.data.static_compatible === false) {
    return <StaticPanelUnavailable panel={panel} />;
  }

  return (
    <PanelInstanceProvider
      value={panelInstanceValue(
        panel,
        panelState,
        panel.kind === "builtin" ? props.params : undefined
      )}
    >
      {panel.kind === "module" ? (
        <ModulePanelHost panel={panel} />
      ) : (
        <BuiltInPanelHost panel={panel} />
      )}
    </PanelInstanceProvider>
  );
}
