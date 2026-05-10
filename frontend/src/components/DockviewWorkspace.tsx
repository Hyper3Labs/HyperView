"use client";

import React, {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DockviewReact,
  type DockviewApi,
  type IDockviewHeaderActionsProps,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
  type IWatermarkPanelProps,
  themeAbyss,
} from "dockview";
import { Columns2 } from "lucide-react";

import { addRuntimePanel, removeRuntimePanel } from "@/lib/api";
import type { SamplesViewModel } from "@/lib/sampleCollections";
import { findLayoutByGeometry, getLayoutDimension } from "@/lib/layouts";
import {
  addBuiltInCenterPanel,
  CENTER_PANEL_COMPONENTS,
  getBuiltInCenterPanelIdForLayout,
  getScatterTabComponent,
  CENTER_PANEL_TAB_COMPONENTS,
  PANEL,
} from "@/panels/registry";
import { installHyperViewPanelSdkGlobal } from "@/panel-sdk";
import { useStore } from "@/store/useStore";
import type { Geometry, RuntimePanel } from "@/types";
import { cn } from "@/lib/utils";

import { Button } from "./ui/button";
import { DockviewContext, useDockviewContext } from "./DockviewContext";
import { ExplorerPanel } from "./ExplorerPanel";
import { HyperViewLogo } from "./icons";
import { PlaceholderPanel } from "./PlaceholderPanel";
import { RuntimeModulePanel } from "./RuntimeModulePanel";

const LAYOUT_STORAGE_KEY = "hyperview:dockview-layout:v7";
const DEFAULT_CONTAINER_WIDTH = 1200;
const DEFAULT_CONTAINER_HEIGHT = 800;
const MIN_SIDE_PANEL_WIDTH = 120;
const MIN_BOTTOM_PANEL_HEIGHT = 150;
const RUNTIME_PANEL_PREFIX = "runtime-panel:";
const OPEN_COPY_TITLE = "Open copy to the right";

const NON_ANCHOR_PANEL_IDS = new Set<string>([
  PANEL.EXPLORER,
  PANEL.RIGHT_PLACEHOLDER,
  PANEL.BOTTOM_PLACEHOLDER,
]);

const DRAG_LOCKED_PANEL_IDS = new Set<string>([PANEL.EXPLORER]);

const CENTER_ANCHOR_PANEL_IDS = [
  PANEL.GRID,
  PANEL.SCATTER_EUCLIDEAN,
  PANEL.SCATTER_POINCARE,
  PANEL.SCATTER_SPHERICAL,
  PANEL.SCATTER_EUCLIDEAN_3D,
  PANEL.SCATTER_SPHERICAL_3D,
  PANEL.SCATTER_DEFAULT,
] as const;

const getContainerWidth = (api?: DockviewApi | null) =>
  api?.width ??
  (typeof window === "undefined" ? DEFAULT_CONTAINER_WIDTH : window.innerWidth);

const getContainerHeight = (api?: DockviewApi | null) =>
  api?.height ??
  (typeof window === "undefined" ? DEFAULT_CONTAINER_HEIGHT : window.innerHeight);

const getDefaultLeftPanelWidth = (screenWidth: number) =>
  Math.round(Math.min(0.35 * screenWidth, 200));

const getDefaultRightPanelWidth = (screenWidth: number) =>
  Math.round(Math.min(0.45 * screenWidth, 300));

const getDefaultBottomPanelHeight = (containerHeight: number) =>
  Math.round(
    Math.min(Math.max(0.25 * containerHeight, MIN_BOTTOM_PANEL_HEIGHT), 250)
  );

const getBottomPanelMaxHeight = (containerHeight: number) =>
  Math.round(
    Math.max(containerHeight - MIN_BOTTOM_PANEL_HEIGHT, MIN_BOTTOM_PANEL_HEIGHT)
  );

function getCenterAnchorPanel(api: DockviewApi) {
  for (const id of CENTER_ANCHOR_PANEL_IDS) {
    const panel = api.getPanel(id);
    if (panel) {
      return panel;
    }
  }

  return api.panels.find((panel) => !NON_ANCHOR_PANEL_IDS.has(panel.id)) ?? null;
}

function getZonePosition(zone: "left" | "right" | "bottom") {
  return { direction: zone === "bottom" ? "below" : zone };
}

function getRuntimePanelPosition(
  api: DockviewApi,
  zone: "center" | "right" | "bottom",
  panel?: RuntimePanel
) {
  if (panel?.reference_panel_id && panel.direction) {
    const referencePanel = resolveRuntimeReferencePanel(api, panel.reference_panel_id);
    if (referencePanel) {
      return { referencePanel, direction: panel.direction };
    }
  }

  if (zone === "center") {
    return getCenterTabPosition(api) ?? undefined;
  }

  return getZonePosition(zone);
}

function resolveRuntimeReferencePanel(api: DockviewApi, panelId: string) {
  return api.getPanel(panelId) ?? api.getPanel(`${RUNTIME_PANEL_PREFIX}${panelId}`) ?? null;
}

function makePanelInstanceId(baseId: string) {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `${baseId}:copy-${suffix}`;
}

function stripRuntimePanelPrefix(panelId: string) {
  return panelId.startsWith(RUNTIME_PANEL_PREFIX)
    ? panelId.slice(RUNTIME_PANEL_PREFIX.length)
    : panelId;
}

function DockviewPanelActions(props: IDockviewHeaderActionsProps) {
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const customPanels = useStore((state) => state.customPanels);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const activePanel = props.activePanel;

  const handleOpenCopy = useCallback(async () => {
    if (!activePanel) return;

    if (activePanel.id.startsWith(RUNTIME_PANEL_PREFIX)) {
      const runtimePanelId = stripRuntimePanelPrefix(activePanel.id);
      const sourcePanel = customPanels.find((panel) => panel.id === runtimePanelId);
      if (!sourcePanel || !activeWorkspaceId) return;

      const nextPanelId = makePanelInstanceId(sourcePanel.id).replace(/:/g, "-");
      const snapshot = await addRuntimePanel({
        workspaceId: activeWorkspaceId,
        panelId: nextPanelId,
        title: sourcePanel.title,
        kind: sourcePanel.kind,
        moduleFile: sourcePanel.module_file,
        layoutKey: sourcePanel.layout_key,
        position: "center",
        referencePanelId: sourcePanel.id,
        direction: "right",
      });
      applyRuntimeSnapshot(snapshot);
      return;
    }

    const state = activePanel.toJSON();
    const nextPanel = props.containerApi.addPanel({
      id: makePanelInstanceId(activePanel.id),
      component: state.contentComponent ?? activePanel.api.component,
      tabComponent: state.tabComponent,
      title: activePanel.title,
      params: state.params,
      renderer: state.renderer,
      position: { referencePanel: activePanel, direction: "right" },
      minimumWidth: state.minimumWidth,
      minimumHeight: state.minimumHeight,
      maximumWidth: state.maximumWidth,
      maximumHeight: state.maximumHeight,
    });
    nextPanel.api.setActive();
  }, [activePanel, activeWorkspaceId, applyRuntimeSnapshot, customPanels, props.containerApi]);

  if (!activePanel || NON_ANCHOR_PANEL_IDS.has(activePanel.id)) {
    return null;
  }

  return (
    <div className="flex h-full items-center pr-1">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        title={OPEN_COPY_TITLE}
        aria-label={OPEN_COPY_TITLE}
        onClick={(event) => {
          event.stopPropagation();
          void handleOpenCopy();
        }}
        className={cn(
          "h-6 w-6 rounded-[4px] text-muted-foreground",
          "hover:bg-muted/50 hover:text-foreground active:scale-[0.98]"
        )}
      >
        <Columns2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function getCenterTabPosition(api: DockviewApi) {
  const anchor = getCenterAnchorPanel(api);
  if (anchor) {
    return { referencePanel: anchor, direction: "within" as const };
  }

  const rightPlaceholder = api.getPanel(PANEL.RIGHT_PLACEHOLDER);
  if (rightPlaceholder) {
    return { referencePanel: rightPlaceholder.id, direction: "left" as const };
  }

  const bottomPlaceholder = api.getPanel(PANEL.BOTTOM_PLACEHOLDER);
  if (bottomPlaceholder) {
    return { referencePanel: bottomPlaceholder.id, direction: "above" as const };
  }

  const explorer = api.getPanel(PANEL.EXPLORER);
  if (explorer) {
    return { referencePanel: explorer.id, direction: "right" as const };
  }

  return undefined;
}

export function useDockviewApi() {
  const ctx = useContext(DockviewContext);
  const datasetInfo = useStore((state) => state.datasetInfo);
  const {
    leftPanelOpen,
    rightPanelOpen,
    bottomPanelOpen,
    setLeftPanelOpen,
    setRightPanelOpen,
    setBottomPanelOpen,
  } = useStore();

  const addPanel = useCallback(
    (panelId: string) => {
      if (!ctx?.api) return;

      addBuiltInCenterPanel({
        api: ctx.api,
        panelId,
        datasetInfo,
        position: getCenterTabPosition(ctx.api) ?? undefined,
      });
    },
    [ctx?.api, datasetInfo]
  );

  const resetLayout = useCallback(() => {
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
    window.location.reload();
  }, []);

  const toggleZone = useCallback(
    (zone: "left" | "right" | "bottom") => {
      if (!ctx?.api) return;

      const api = ctx.api;
      const panelId =
        zone === "left"
          ? PANEL.EXPLORER
          : zone === "right"
            ? PANEL.RIGHT_PLACEHOLDER
            : PANEL.BOTTOM_PLACEHOLDER;
      const setOpen =
        zone === "left"
          ? setLeftPanelOpen
          : zone === "right"
            ? setRightPanelOpen
            : setBottomPanelOpen;
      const isOpen =
        zone === "left"
          ? leftPanelOpen
          : zone === "right"
            ? rightPanelOpen
            : bottomPanelOpen;

      const existingPanel = api.getPanel(panelId);
      if (isOpen && existingPanel) {
        existingPanel.api.close();
        setOpen(false);
        return;
      }

      if (isOpen) return;

      const containerWidth = getContainerWidth(api);
      const containerHeight = getContainerHeight(api);
      const position = getZonePosition(zone);

      let newPanel;
      if (zone === "left") {
        const targetWidth = getDefaultLeftPanelWidth(containerWidth);
        newPanel = api.addPanel({
          id: panelId,
          component: "explorer",
          title: "Labels",
          position,
          initialWidth: targetWidth,
          minimumWidth: MIN_SIDE_PANEL_WIDTH,
          maximumWidth: targetWidth,
        });

        if (newPanel) {
          newPanel.group.locked = true;
          newPanel.group.header.hidden = true;
          newPanel.api.setSize({ width: targetWidth });
        }
      } else if (zone === "right") {
        newPanel = api.addPanel({
          id: panelId,
          component: "placeholder",
          title: "Blank",
          position,
          initialWidth: getDefaultRightPanelWidth(containerWidth),
          minimumWidth: MIN_SIDE_PANEL_WIDTH,
          maximumWidth: Math.round(containerWidth * 0.65),
        });
      } else {
        newPanel = api.addPanel({
          id: panelId,
          component: "placeholder",
          title: "Blank",
          position,
          initialHeight: getDefaultBottomPanelHeight(containerHeight),
          minimumHeight: MIN_BOTTOM_PANEL_HEIGHT,
          maximumHeight: getBottomPanelMaxHeight(containerHeight),
        });
      }

      if (newPanel) {
        setOpen(true);
        newPanel.api.setActive();
      }
    },
    [
      bottomPanelOpen,
      ctx?.api,
      leftPanelOpen,
      rightPanelOpen,
      setBottomPanelOpen,
      setLeftPanelOpen,
      setRightPanelOpen,
    ]
  );

  if (!ctx) return null;

  return {
    api: ctx.api,
    addPanel,
    resetLayout,
    toggleZone,
  };
}

const ExplorerDockPanel = React.memo(function ExplorerDockPanel() {
  return <ExplorerPanel />;
});

const PlaceholderDockPanel = React.memo(function PlaceholderDockPanel(
  props: IDockviewPanelProps
) {
  const handleClose = React.useCallback(() => {
    props.api.close();
  }, [props.api]);

  return <PlaceholderPanel onClose={handleClose} />;
});

const Watermark = React.memo(function Watermark(_props: IWatermarkPanelProps) {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <div className="text-muted-foreground/20">
        <HyperViewLogo className="h-16 w-16" />
      </div>
    </div>
  );
});

const COMPONENTS = {
  ...CENTER_PANEL_COMPONENTS,
  explorer: ExplorerDockPanel,
  placeholder: PlaceholderDockPanel,
  runtimeModulePanel: RuntimeModulePanel,
};

const TAB_COMPONENTS = CENTER_PANEL_TAB_COMPONENTS;

function applyZonePolicies(api: DockviewApi) {
  const explorer = api.getPanel(PANEL.EXPLORER);
  if (explorer) {
    explorer.group.locked = true;
    explorer.group.header.hidden = true;
    explorer.api.setActive();
  }

  const rightPlaceholder = api.getPanel(PANEL.RIGHT_PLACEHOLDER);
  if (rightPlaceholder) {
    rightPlaceholder.group.header.hidden = true;
  }

  const bottomPlaceholder = api.getPanel(PANEL.BOTTOM_PLACEHOLDER);
  if (bottomPlaceholder) {
    bottomPlaceholder.group.header.hidden = true;
  }
}

interface DockviewProviderProps {
  children: ReactNode;
  samplesView: SamplesViewModel;
}

export function DockviewProvider({
  children,
  samplesView,
}: DockviewProviderProps) {
  const [api, setApi] = useState<DockviewApi | null>(null);

  const contextValue = useMemo(
    () => ({
      api,
      setApi,
      samplesView,
    }),
    [api, samplesView]
  );

  useEffect(() => {
    installHyperViewPanelSdkGlobal();
  }, []);

  return (
    <DockviewContext.Provider value={contextValue}>
      {children}
    </DockviewContext.Provider>
  );
}

export function DockviewWorkspace() {
  const ctx = useDockviewContext();
  const datasetInfo = useStore((state) => state.datasetInfo);
  const customPanels = useStore((state) => state.customPanels);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const requestedLayoutKey = useStore((state) => state.requestedLayoutKey);
  const {
    applyRuntimeSnapshot,
    setLeftPanelOpen,
    setRightPanelOpen,
    setBottomPanelOpen,
  } = useStore();

  const buildDefaultLayout = useCallback(
    (api: DockviewApi) => {
      const layouts = datasetInfo?.layouts ?? [];
      const renderableLayouts2d = layouts.filter(
        (layout) => getLayoutDimension(layout.layout_key) === 2
      );
      const renderableLayouts3d = layouts.filter(
        (layout) => getLayoutDimension(layout.layout_key) === 3
      );

      const euclideanLayout2d = findLayoutByGeometry(
        renderableLayouts2d,
        "euclidean",
        2
      );
      const poincareLayout2d = findLayoutByGeometry(
        renderableLayouts2d,
        "poincare",
        2
      );
      const sphericalLayout2d = findLayoutByGeometry(
        renderableLayouts2d,
        "spherical",
        2
      );
      const euclideanLayout3d = findLayoutByGeometry(
        renderableLayouts3d,
        "euclidean",
        3
      );
      const sphericalLayout3d = findLayoutByGeometry(
        renderableLayouts3d,
        "spherical",
        3
      );

      const fallbackLayout2d =
        !euclideanLayout2d && !poincareLayout2d && !sphericalLayout2d
          ? renderableLayouts2d[0]
          : null;
      const fallbackLayout3d =
        !euclideanLayout3d && !sphericalLayout3d ? renderableLayouts3d[0] : null;

      const hasLayouts = renderableLayouts2d.length > 0 || renderableLayouts3d.length > 0;

      const gridPanel =
        api.getPanel(PANEL.GRID) ??
        addBuiltInCenterPanel({
          api,
          panelId: PANEL.GRID,
          datasetInfo,
          focusIfPresent: false,
        });

      if (!gridPanel) {
        return;
      }

      let scatterPanel: typeof gridPanel | null = null;

      const addScatterPanel = (panelId: string) => {
        const position = scatterPanel
          ? { referencePanel: scatterPanel.id, direction: "within" as const }
          : { referencePanel: gridPanel.id, direction: "right" as const };

        const panel = addBuiltInCenterPanel({
          api,
          panelId,
          datasetInfo,
          position,
          focusIfPresent: false,
        });

        if (!scatterPanel && panel) {
          scatterPanel = panel;
        }
      };

      if (hasLayouts && euclideanLayout2d) addScatterPanel(PANEL.SCATTER_EUCLIDEAN);
      if (hasLayouts && poincareLayout2d) addScatterPanel(PANEL.SCATTER_POINCARE);
      if (hasLayouts && sphericalLayout2d) addScatterPanel(PANEL.SCATTER_SPHERICAL);
      if (hasLayouts && euclideanLayout3d) addScatterPanel(PANEL.SCATTER_EUCLIDEAN_3D);
      if (hasLayouts && sphericalLayout3d) addScatterPanel(PANEL.SCATTER_SPHERICAL_3D);

      if (!hasLayouts) {
        const euclideanPanel =
          api.getPanel(PANEL.SCATTER_EUCLIDEAN) ??
          addBuiltInCenterPanel({
            api,
            panelId: PANEL.SCATTER_EUCLIDEAN,
            datasetInfo,
            position: {
              referencePanel: gridPanel.id,
              direction: "right",
            },
            focusIfPresent: false,
          });

        if (euclideanPanel) {
          addBuiltInCenterPanel({
            api,
            panelId: PANEL.SCATTER_POINCARE,
            datasetInfo,
            position: {
              referencePanel: euclideanPanel.id,
              direction: "within",
            },
            focusIfPresent: false,
          });

          addBuiltInCenterPanel({
            api,
            panelId: PANEL.SCATTER_SPHERICAL,
            datasetInfo,
            position: {
              referencePanel: euclideanPanel.id,
              direction: "within",
            },
            focusIfPresent: false,
          });
        }

        scatterPanel = euclideanPanel;
      }

      if (fallbackLayout2d && !scatterPanel) {
        addBuiltInCenterPanel({
          api,
          panelId: PANEL.SCATTER_DEFAULT,
          datasetInfo,
          position: {
            referencePanel: gridPanel.id,
            direction: "right",
          },
          focusIfPresent: false,
        });
      }

      if (fallbackLayout3d && !scatterPanel) {
        addBuiltInCenterPanel({
          api,
          panelId: PANEL.SCATTER_DEFAULT,
          datasetInfo,
          position: {
            referencePanel: gridPanel.id,
            direction: "right",
          },
          focusIfPresent: false,
        });
      }

      const containerWidth = getContainerWidth(api);
      const explorerPanel =
        api.getPanel(PANEL.EXPLORER) ??
        api.addPanel({
          id: PANEL.EXPLORER,
          component: "explorer",
          title: "Labels",
          position: getZonePosition("left"),
          initialWidth: getDefaultLeftPanelWidth(containerWidth),
          minimumWidth: MIN_SIDE_PANEL_WIDTH,
          maximumWidth: getDefaultLeftPanelWidth(containerWidth),
        });

      if (explorerPanel) {
        explorerPanel.group.locked = true;
        explorerPanel.group.header.hidden = true;
        explorerPanel.api.setActive();
      }

      setLeftPanelOpen(Boolean(explorerPanel));
      setRightPanelOpen(false);
      setBottomPanelOpen(false);
    },
    [datasetInfo, setBottomPanelOpen, setLeftPanelOpen, setRightPanelOpen]
  );

  const onReady = useCallback(
    (event: DockviewReadyEvent) => {
      ctx.setApi(event.api);

      const stored = localStorage.getItem(LAYOUT_STORAGE_KEY);
      if (stored) {
        try {
          event.api.fromJSON(JSON.parse(stored));

          if (event.api.totalPanels === 0) {
            localStorage.removeItem(LAYOUT_STORAGE_KEY);
            buildDefaultLayout(event.api);
          }

          applyZonePolicies(event.api);
          setLeftPanelOpen(Boolean(event.api.getPanel(PANEL.EXPLORER)));
          setRightPanelOpen(Boolean(event.api.getPanel(PANEL.RIGHT_PLACEHOLDER)));
          setBottomPanelOpen(Boolean(event.api.getPanel(PANEL.BOTTOM_PLACEHOLDER)));
          return;
        } catch (err) {
          console.warn("Failed to restore dock layout, resetting.", err);
          localStorage.removeItem(LAYOUT_STORAGE_KEY);
        }
      }

      if (event.api.totalPanels === 0) {
        buildDefaultLayout(event.api);
      }
    },
    [buildDefaultLayout, ctx, setBottomPanelOpen, setLeftPanelOpen, setRightPanelOpen]
  );

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidLayoutChange(() => {
      if (api.totalPanels === 0) return;
      localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(api.toJSON()));
    });

    return () => disposable.dispose();
  }, [ctx.api]);

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidRemovePanel((event) => {
      if (event.id === PANEL.EXPLORER) setLeftPanelOpen(false);
      if (event.id === PANEL.RIGHT_PLACEHOLDER) setRightPanelOpen(false);
      if (event.id === PANEL.BOTTOM_PLACEHOLDER) setBottomPanelOpen(false);

      if (!event.id.startsWith(RUNTIME_PANEL_PREFIX) || !activeWorkspaceId) return;

      const panelId = stripRuntimePanelPrefix(event.id);
      if (!customPanels.some((panel) => panel.id === panelId)) return;

      void removeRuntimePanel({ workspaceId: activeWorkspaceId, panelId })
        .then(applyRuntimeSnapshot)
        .catch((error) => {
          console.error("Failed to remove runtime panel:", error);
        });
    });

    return () => disposable.dispose();
  }, [
    activeWorkspaceId,
    applyRuntimeSnapshot,
    ctx.api,
    customPanels,
    setBottomPanelOpen,
    setLeftPanelOpen,
    setRightPanelOpen,
  ]);

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidAddPanel((event) => {
      if (event.id === PANEL.RIGHT_PLACEHOLDER || event.id === PANEL.BOTTOM_PLACEHOLDER) {
        return;
      }

      const group = event.group;
      if (!group) return;

      const rightPlaceholder = api.getPanel(PANEL.RIGHT_PLACEHOLDER);
      const bottomPlaceholder = api.getPanel(PANEL.BOTTOM_PLACEHOLDER);

      if (rightPlaceholder && rightPlaceholder.group?.id === group.id) {
        rightPlaceholder.api.close();
      }

      if (bottomPlaceholder && bottomPlaceholder.group?.id === group.id) {
        bottomPlaceholder.api.close();
      }
    });

    return () => disposable.dispose();
  }, [ctx.api]);

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onWillDragPanel((event) => {
      if (DRAG_LOCKED_PANEL_IDS.has(event.panel.id)) {
        event.nativeEvent.preventDefault();
      }
    });

    return () => disposable.dispose();
  }, [ctx.api]);

  useEffect(() => {
    if (!ctx.api || !datasetInfo) return;

    const hasScatter =
      ctx.api.getPanel(PANEL.SCATTER_EUCLIDEAN) ||
      ctx.api.getPanel(PANEL.SCATTER_POINCARE) ||
      ctx.api.getPanel(PANEL.SCATTER_SPHERICAL) ||
      ctx.api.getPanel(PANEL.SCATTER_EUCLIDEAN_3D) ||
      ctx.api.getPanel(PANEL.SCATTER_SPHERICAL_3D) ||
      ctx.api.getPanel(PANEL.SCATTER_DEFAULT);

    if (!hasScatter) {
      buildDefaultLayout(ctx.api);
    }
  }, [buildDefaultLayout, ctx.api, datasetInfo]);

  useEffect(() => {
    const api = ctx.api;
    if (!api || !datasetInfo || !requestedLayoutKey) return;

    const panelId = getBuiltInCenterPanelIdForLayout({
      datasetInfo,
      layoutKey: requestedLayoutKey,
    });
    if (!panelId) return;

    addBuiltInCenterPanel({
      api,
      panelId,
      datasetInfo,
      position: getCenterTabPosition(api) ?? undefined,
      focusIfPresent: true,
    });
  }, [ctx.api, datasetInfo, requestedLayoutKey]);

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const desiredPanelIds = new Set(
      customPanels.map((panel) => `${RUNTIME_PANEL_PREFIX}${panel.id}`)
    );

    for (const panel of api.panels) {
      if (!panel.id.startsWith(RUNTIME_PANEL_PREFIX)) continue;
      if (desiredPanelIds.has(panel.id)) continue;
      panel.api.close();
    }

    for (const panel of customPanels) {
      const runtimePanelId = `${RUNTIME_PANEL_PREFIX}${panel.id}`;
      if (api.getPanel(runtimePanelId)) continue;

      if (panel.kind === "scatter") {
        const layoutDimension = panel.layout_dimension === 3 ? 3 : 2;
        api.addPanel({
          id: runtimePanelId,
          component: "scatter",
          title: panel.title,
          tabComponent: getScatterTabComponent({
            geometry: panel.geometry,
            layoutDimension,
          }),
          params: {
            layoutKey: panel.layout_key ?? undefined,
            geometry: (panel.geometry ?? undefined) as Geometry | undefined,
            layoutDimension,
            pinnedLayout: true,
          },
          position: getRuntimePanelPosition(api, panel.position, panel),
          renderer: "always",
        });
        continue;
      }

      api.addPanel({
        id: runtimePanelId,
        component: "runtimeModulePanel",
        title: panel.title,
        params: { panelId: panel.id },
        position: getRuntimePanelPosition(api, panel.position, panel),
        initialWidth: panel.position === "right" ? getDefaultRightPanelWidth(getContainerWidth(api)) : undefined,
        initialHeight:
          panel.position === "bottom"
            ? getDefaultBottomPanelHeight(getContainerHeight(api))
            : undefined,
      });
    }
  }, [ctx.api, customPanels]);

  return (
    <div className="h-full w-full">
      <DockviewReact
        className="dockview-theme-abyss hyperview-dockview"
        components={COMPONENTS}
        tabComponents={TAB_COMPONENTS}
        onReady={onReady}
        theme={themeAbyss}
        rightHeaderActionsComponent={DockviewPanelActions}
        defaultRenderer="always"
        scrollbars="native"
        watermarkComponent={Watermark}
      />
    </div>
  );
}
