"use client";

import React, {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  DockviewReact,
  type BuiltInContextMenuItem,
  type DockviewApi,
  type DockviewGroupPanelApi,
  type GetTabContextMenuItemsParams,
  type IDockviewHeaderActionsProps,
  type IDockviewPanel,
  type DockviewReadyEvent,
  type EdgeGroupPosition,
  type DockviewTheme,
  type IDockviewPanelProps,
  type IWatermarkPanelProps,
  themeAbyss,
} from "dockview-react";
import { Columns2 } from "lucide-react";

import { addRuntimePanel, removeRuntimePanel } from "@/lib/api";
import type { SamplesViewModel } from "@/lib/sampleCollections";
import { getLayoutDimension } from "@/lib/layouts";
import {
  addBuiltInCenterPanel,
  CENTER_PANEL_COMPONENTS,
  getBuiltInCenterPanelDefinition,
  getBuiltInCenterPanelIdForLayout,
  getScatterTabComponent,
  CENTER_PANEL_TAB_COMPONENTS,
  PANEL,
} from "@/panels/registry";
import { installHyperViewPanelSdkGlobal } from "@/panel-sdk";
import { useStore } from "@/store/useStore";
import type { DatasetInfo, Geometry, RuntimePanel } from "@/types";
import { cn } from "@/lib/utils";
import {
  isDockviewUserClosablePanelId,
  RUNTIME_PANEL_PREFIX,
} from "@/lib/dockviewPanelPolicy";

import { Button } from "./ui/button";
import { DockviewContext, useDockviewContext } from "./DockviewContext";
import { ExplorerPanel } from "./ExplorerPanel";
import { HyperViewLogo } from "./icons";
import { RuntimeModulePanel } from "./RuntimeModulePanel";

const LAYOUT_STORAGE_KEY = "hyperview:dockview-layout:v10";
const DEFAULT_CONTAINER_WIDTH = 1200;
const DEFAULT_CONTAINER_HEIGHT = 800;
const MIN_SIDE_PANEL_WIDTH = 120;
const MIN_BOTTOM_PANEL_HEIGHT = 150;
const OPEN_COPY_TITLE = "Open copy to the right";
const HYPERVIEW_DOCKVIEW_THEME = {
  ...themeAbyss,
  name: "hyperview",
  className: `${themeAbyss.className} hyperview-dockview`,
  edgeGroupCollapsedSize: 24,
} satisfies DockviewTheme;

const NON_ANCHOR_PANEL_IDS = new Set<string>([
  PANEL.EXPLORER,
]);

const DRAG_LOCKED_PANEL_IDS = new Set<string>([PANEL.EXPLORER]);

const CENTER_ANCHOR_PANEL_IDS = [PANEL.GRID] as const;
const CENTER_ANCHOR_PANEL_ID_SET = new Set<string>(CENTER_ANCHOR_PANEL_IDS);
type DockviewEdgeZone = Extract<EdgeGroupPosition, "left" | "right" | "bottom">;
const EDGE_GROUP_IDS = {
  left: "hyperview-edge-left",
  right: "hyperview-edge-right",
  bottom: "hyperview-edge-bottom",
} as const satisfies Record<DockviewEdgeZone, string>;
const EDGE_ZONES = ["left", "right", "bottom"] as const satisfies readonly DockviewEdgeZone[];
const DEFAULT_BUILT_IN_PANEL_IDS = [
  PANEL.EXPLORER,
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

const getLayoutStorageKey = (
  workspaceId: string | null,
  viewRevision: number | null | undefined,
  hasExplicitView: boolean
) =>
  `${LAYOUT_STORAGE_KEY}:${workspaceId ?? "default"}:${viewRevision ?? 0}:${
    hasExplicitView ? "explicit" : "default"
  }`;

function getDefaultScatterPanelId(
  datasetInfo: DatasetInfo | null,
  requestedLayoutKey: string | null
) {
  const layouts = datasetInfo?.layouts ?? [];
  const requestedLayout =
    requestedLayoutKey === null
      ? null
      : layouts.find((layout) => layout.layout_key === requestedLayoutKey) ?? null;
  const euclideanLayout2d =
    layouts.find(
      (layout) =>
        layout.geometry === "euclidean" && getLayoutDimension(layout.layout_key) === 2
    ) ?? null;
  const fallbackLayout2d =
    layouts.find((layout) => getLayoutDimension(layout.layout_key) === 2) ?? null;
  const fallbackLayout3d =
    layouts.find((layout) => getLayoutDimension(layout.layout_key) === 3) ?? null;
  const layout = requestedLayout ?? euclideanLayout2d ?? fallbackLayout2d ?? fallbackLayout3d;

  return layout
    ? getBuiltInCenterPanelIdForLayout({ datasetInfo, layoutKey: layout.layout_key })
    : null;
}

function getCenterAnchorPanel(api: DockviewApi) {
  for (const id of CENTER_ANCHOR_PANEL_IDS) {
    const panel = api.getPanel(id);
    if (panel) {
      return panel;
    }
  }

  return api.panels.find((panel) => !NON_ANCHOR_PANEL_IDS.has(panel.id)) ?? null;
}

function getEdgeGroupOptions(api: DockviewApi, zone: DockviewEdgeZone) {
  const containerWidth = getContainerWidth(api);
  const containerHeight = getContainerHeight(api);

  if (zone === "left") {
    const targetWidth = getDefaultLeftPanelWidth(containerWidth);
    return {
      id: EDGE_GROUP_IDS.left,
      initialSize: targetWidth,
      minimumSize: MIN_SIDE_PANEL_WIDTH,
      maximumSize: targetWidth,
      collapsed: false,
    };
  }

  if (zone === "right") {
    return {
      id: EDGE_GROUP_IDS.right,
      initialSize: getDefaultRightPanelWidth(containerWidth),
      minimumSize: MIN_SIDE_PANEL_WIDTH,
      maximumSize: Math.round(containerWidth * 0.65),
      collapsed: false,
    };
  }

  return {
    id: EDGE_GROUP_IDS.bottom,
    initialSize: getDefaultBottomPanelHeight(containerHeight),
    minimumSize: MIN_BOTTOM_PANEL_HEIGHT,
    maximumSize: getBottomPanelMaxHeight(containerHeight),
    collapsed: false,
  };
}

function ensureEdgeGroup(
  api: DockviewApi,
  zone: DockviewEdgeZone
): DockviewGroupPanelApi {
  const group = api.getEdgeGroup(zone) ?? api.addEdgeGroup(zone, getEdgeGroupOptions(api, zone));
  if (zone !== "left") {
    group.setHeaderPosition("top");
  }
  return group;
}

function ensureEdgeGroups(api: DockviewApi) {
  for (const zone of EDGE_ZONES) {
    ensureEdgeGroup(api, zone);
  }
}

function showEdgeGroup(api: DockviewApi, zone: DockviewEdgeZone) {
  const group = ensureEdgeGroup(api, zone);
  api.setEdgeGroupVisible(zone, true);
  group.expand();
  return group;
}

function hideEdgeGroup(api: DockviewApi, zone: DockviewEdgeZone) {
  if (!api.getEdgeGroup(zone)) return;
  api.setEdgeGroupVisible(zone, false);
}

function edgeGroupHasPanels(api: DockviewApi, zone: DockviewEdgeZone) {
  const group = api.getEdgeGroup(zone);
  return Boolean(
    group && api.panels.some((panel) => panel.group.id === group.id)
  );
}

function hideEmptySecondaryEdgeGroups(api: DockviewApi) {
  for (const zone of ["right", "bottom"] as const) {
    if (!edgeGroupHasPanels(api, zone)) {
      hideEdgeGroup(api, zone);
    }
  }
}

function getEdgeZonePosition(api: DockviewApi, zone: DockviewEdgeZone) {
  const group = showEdgeGroup(api, zone);
  return { referenceGroup: group.id };
}

function isEdgeZoneOpen(api: DockviewApi, zone: DockviewEdgeZone) {
  const group = api.getEdgeGroup(zone);
  return Boolean(group && api.isEdgeGroupVisible(zone) && !group.isCollapsed());
}

function getPositivePanelNumber(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) return undefined;
  return Math.round(value);
}

function getRuntimePanelNumber(
  panel: RuntimePanel,
  field: keyof Pick<
    RuntimePanel,
    "width" | "height" | "min_width" | "min_height" | "max_width" | "max_height"
  >
) {
  return getPositivePanelNumber(panel[field]);
}

function getRuntimePanelPlacementKey(panel: RuntimePanel) {
  return JSON.stringify([
    panel.position,
    panel.reference_panel_id ?? null,
    panel.direction ?? null,
    panel.width ?? null,
    panel.height ?? null,
    panel.min_width ?? null,
    panel.min_height ?? null,
    panel.max_width ?? null,
    panel.max_height ?? null,
  ]);
}

function getRuntimePanelAddLayout(spec: RuntimePanel) {
  return {
    initialWidth: getRuntimePanelNumber(spec, "width"),
    initialHeight: getRuntimePanelNumber(spec, "height"),
    minimumWidth: getRuntimePanelNumber(spec, "min_width"),
    minimumHeight: getRuntimePanelNumber(spec, "min_height"),
    maximumWidth: getRuntimePanelNumber(spec, "max_width"),
    maximumHeight: getRuntimePanelNumber(spec, "max_height"),
  };
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

  return getEdgeZonePosition(api, zone);
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

function isClosableDockPanel(panelId: string) {
  return (
    isDockviewUserClosablePanelId(panelId) ||
    (!NON_ANCHOR_PANEL_IDS.has(panelId) && !CENTER_ANCHOR_PANEL_ID_SET.has(panelId))
  );
}

function getExpectedRuntimePanelComponent(panel: RuntimePanel) {
  if (panel.kind === "scatter") return "scatter";
  if (panel.kind === "builtin" && panel.builtin_panel === "samples") {
    return getBuiltInCenterPanelDefinition(PANEL.GRID)?.component ?? null;
  }
  return "runtimeModulePanel";
}

function getRuntimeSamplesPanelParams(panel: RuntimePanel) {
  const mode = panel.props?.mode;
  const rank = panel.props?.rank;
  return {
    panelId: panel.id,
    runtimePlacementKey: getRuntimePanelPlacementKey(panel),
    mode:
      mode === "auto" || mode === "browse" || mode === "ranked"
        ? mode
        : undefined,
    rank: rank && typeof rank === "object" && !Array.isArray(rank) ? rank : undefined,
  };
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
        kind:
          sourcePanel.kind === "module" ? "extension" : sourcePanel.kind,
        builtinPanel: sourcePanel.builtin_panel,
        extension: sourcePanel.extension,
        extensionPanel: sourcePanel.extension_panel,
        layoutKey: sourcePanel.layout_key,
        position: "center",
        referencePanelId: sourcePanel.id,
        direction: "right",
        width: sourcePanel.width,
        height: sourcePanel.height,
        minWidth: sourcePanel.min_width,
        minHeight: sourcePanel.min_height,
        maxWidth: sourcePanel.max_width,
        maxHeight: sourcePanel.max_height,
        props: sourcePanel.props,
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
    <div className="flex h-full items-center gap-0.5 pr-1">
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

function getDockviewTabContextMenuItems(
  params: GetTabContextMenuItemsParams
): BuiltInContextMenuItem[] {
  return isClosableDockPanel(params.panel.id) ? ["close"] : [];
}

function getCenterTabPosition(api: DockviewApi) {
  const anchor = getCenterAnchorPanel(api);
  if (anchor) {
    return { referencePanel: anchor, direction: "within" as const };
  }

  return undefined;
}

export function useDockviewApi() {
  const ctx = useContext(DockviewContext);
  const datasetInfo = useStore((state) => state.datasetInfo);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const viewRevision = useStore((state) => state.viewRevision);
  const hasExplicitView = useStore((state) => state.hasExplicitView);

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
    localStorage.removeItem(
      getLayoutStorageKey(activeWorkspaceId, viewRevision, hasExplicitView)
    );
    window.location.reload();
  }, [activeWorkspaceId, hasExplicitView, viewRevision]);

  const toggleZone = useCallback(
    (zone: "left" | "right" | "bottom") => {
      if (!ctx?.api) return;

      const api = ctx.api;
      if (isEdgeZoneOpen(api, zone)) {
        hideEdgeGroup(api, zone);
        ctx.notifyEdgeStateChange();
        return;
      }

      const group = showEdgeGroup(api, zone);
      if (zone === "left") {
        const explorer =
          api.getPanel(PANEL.EXPLORER) ??
          api.addPanel({
            id: PANEL.EXPLORER,
            component: "explorer",
            title: "Labels",
            position: { referenceGroup: group.id },
          });

        applyExplorerPanelPolicy(explorer);
      }
      ctx.notifyEdgeStateChange();
    },
    [ctx]
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
  runtimeModulePanel: RuntimeModulePanel,
};

const TAB_COMPONENTS = CENTER_PANEL_TAB_COMPONENTS;

function applyExplorerPanelPolicy(panel: IDockviewPanel | undefined) {
  if (!panel) return;

  panel.group.api.locked = true;
  // Dockview exposes hideHeader for regular group creation, but not EdgeGroupOptions.
  panel.group.header.hidden = true;
  panel.api.setActive();
}

function applyZonePolicies(api: DockviewApi) {
  applyExplorerPanelPolicy(api.getPanel(PANEL.EXPLORER));
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
  const [edgeStateRevision, setEdgeStateRevision] = useState(0);
  const notifyEdgeStateChange = useCallback(() => {
    setEdgeStateRevision((revision) => revision + 1);
  }, []);

  const contextValue = useMemo(
    () => ({
      api,
      setApi,
      edgeStateRevision,
      notifyEdgeStateChange,
      samplesView,
    }),
    [api, edgeStateRevision, notifyEdgeStateChange, samplesView]
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
  const activePanelId = useStore((state) => state.activePanelId);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const viewRevision = useStore((state) => state.viewRevision);
  const hasExplicitView = useStore((state) => state.hasExplicitView);
  const requestedLayoutKey = useStore((state) => state.requestedLayoutKey);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const runtimeSyncClosedPanels = useRef(new Set<string>());

  const buildDefaultLayout = useCallback(
    (api: DockviewApi) => {
      const gridPanel =
        api.getPanel(PANEL.GRID) ??
        addBuiltInCenterPanel({
          api,
          panelId: PANEL.GRID,
          datasetInfo,
          focusIfPresent: false,
        });

      const scatterPanelId = getDefaultScatterPanelId(datasetInfo, requestedLayoutKey);
      if (gridPanel && scatterPanelId) {
        addBuiltInCenterPanel({
          api,
          panelId: scatterPanelId,
          datasetInfo,
          position: { referencePanel: gridPanel.id, direction: "right" },
          focusIfPresent: false,
        });
      }

      const leftGroup = showEdgeGroup(api, "left");
      const explorerPanel =
        api.getPanel(PANEL.EXPLORER) ??
        api.addPanel({
          id: PANEL.EXPLORER,
          component: "explorer",
          title: "Labels",
          position: { referenceGroup: leftGroup.id },
        });

      applyExplorerPanelPolicy(explorerPanel);

      ensureEdgeGroup(api, "right");
      ensureEdgeGroup(api, "bottom");
      hideEdgeGroup(api, "right");
      hideEdgeGroup(api, "bottom");
    },
    [datasetInfo, requestedLayoutKey]
  );

  const onReady = useCallback(
    (event: DockviewReadyEvent) => {
      ctx.setApi(event.api);

      const layoutStorageKey = getLayoutStorageKey(
        activeWorkspaceId,
        viewRevision,
        hasExplicitView
      );
      const stored = hasExplicitView ? null : localStorage.getItem(layoutStorageKey);
      if (stored) {
        try {
          event.api.fromJSON(JSON.parse(stored));

          if (event.api.totalPanels === 0) {
            localStorage.removeItem(layoutStorageKey);
            if (!hasExplicitView) {
              buildDefaultLayout(event.api);
            }
          }

          ensureEdgeGroups(event.api);
          hideEmptySecondaryEdgeGroups(event.api);
          applyZonePolicies(event.api);
          return;
        } catch (err) {
          console.warn("Failed to restore dock layout, resetting.", err);
          localStorage.removeItem(layoutStorageKey);
        }
      }

      if (!hasExplicitView && event.api.totalPanels === 0) {
        buildDefaultLayout(event.api);
      }
    },
    [
      activeWorkspaceId,
      buildDefaultLayout,
      ctx,
      hasExplicitView,
      viewRevision,
    ]
  );

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    if (hasExplicitView) return;

    const disposable = api.onDidLayoutChange(() => {
      if (api.totalPanels === 0) return;
      localStorage.setItem(
        getLayoutStorageKey(activeWorkspaceId, viewRevision, hasExplicitView),
        JSON.stringify(api.toJSON())
      );
    });

    return () => disposable.dispose();
  }, [activeWorkspaceId, ctx.api, hasExplicitView, viewRevision]);

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidRemovePanel((event) => {
      hideEmptySecondaryEdgeGroups(api);
      ctx.notifyEdgeStateChange();

      if (!event.id.startsWith(RUNTIME_PANEL_PREFIX) || !activeWorkspaceId) return;

      const panelId = stripRuntimePanelPrefix(event.id);
      if (runtimeSyncClosedPanels.current.delete(panelId)) return;
      if (!customPanels.some((panel) => panel.id === panelId)) return;

      void removeRuntimePanel({ workspaceId: activeWorkspaceId, panelId })
        .then(applyRuntimeSnapshot)
        .catch((error) => {
          console.error("Failed to remove runtime panel:", error);
        });
    });

    return () => disposable.dispose();
  }, [activeWorkspaceId, applyRuntimeSnapshot, ctx, customPanels]);

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
    const api = ctx.api;
    if (!api || !datasetInfo || !requestedLayoutKey || hasExplicitView) return;

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
  }, [ctx.api, datasetInfo, hasExplicitView, requestedLayoutKey]);

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const visibleRuntimePanels = customPanels.filter((panel) => panel.visible !== false);
    const desiredPanelIds = new Set(
      visibleRuntimePanels.map((panel) => `${RUNTIME_PANEL_PREFIX}${panel.id}`)
    );

    if (hasExplicitView) {
      for (const panelId of DEFAULT_BUILT_IN_PANEL_IDS) {
        api.getPanel(panelId)?.api.close();
      }
      hideEdgeGroup(api, "left");
    }

    for (const panel of api.panels) {
      if (!panel.id.startsWith(RUNTIME_PANEL_PREFIX)) continue;
      if (desiredPanelIds.has(panel.id)) continue;
      runtimeSyncClosedPanels.current.add(stripRuntimePanelPrefix(panel.id));
      panel.api.close();
    }

    for (const panel of visibleRuntimePanels) {
      const runtimePanelId = `${RUNTIME_PANEL_PREFIX}${panel.id}`;
      let existingPanel = api.getPanel(runtimePanelId);
      if (existingPanel) {
        const state = existingPanel.toJSON();
        const currentComponent = state.contentComponent ?? existingPanel.api.component;
        const expectedComponent = getExpectedRuntimePanelComponent(panel);
        const placementKey = getRuntimePanelPlacementKey(panel);
        const existingPlacementKey = (existingPanel.api.getParameters() as {
          runtimePlacementKey?: string;
        }).runtimePlacementKey;
        if (!expectedComponent || currentComponent !== expectedComponent || existingPlacementKey !== placementKey) {
          runtimeSyncClosedPanels.current.add(panel.id);
          existingPanel.api.close();
          existingPanel = undefined;
        } else {
          existingPanel.api.setTitle(panel.title);
          if (panel.kind === "scatter") {
            const layoutDimension = panel.layout_dimension === 3 ? 3 : 2;
            existingPanel.api.updateParameters({
              layoutKey: panel.layout_key ?? undefined,
              geometry: (panel.geometry ?? undefined) as Geometry | undefined,
              layoutDimension,
              pinnedLayout: true,
              runtimePlacementKey: placementKey,
            });
          } else if (panel.kind === "builtin" && panel.builtin_panel === "samples") {
            existingPanel.api.updateParameters(getRuntimeSamplesPanelParams(panel));
          } else {
            existingPanel.api.updateParameters({
              panelId: panel.id,
              runtimePlacementKey: placementKey,
            });
          }
          continue;
        }
      }

      if (panel.kind === "scatter") {
        const layoutDimension = panel.layout_dimension === 3 ? 3 : 2;
        const layout = getRuntimePanelAddLayout(panel);
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
            runtimePlacementKey: getRuntimePanelPlacementKey(panel),
          },
          position: getRuntimePanelPosition(api, panel.position, panel),
          ...layout,
        });
        continue;
      }

      if (panel.kind === "builtin" && panel.builtin_panel === "samples") {
        const samplesParams = getRuntimeSamplesPanelParams(panel);
        const samplesDefinition = getBuiltInCenterPanelDefinition(PANEL.GRID);
        if (!samplesDefinition) continue;
        const layout = getRuntimePanelAddLayout(panel);

        const options = samplesDefinition.buildAddPanelOptions({
          api,
          datasetInfo,
          position: getRuntimePanelPosition(api, panel.position, panel),
        });

        api.addPanel({
          ...options,
          id: runtimePanelId,
          title: panel.title,
          params: {
            ...(options.params ?? {}),
            ...samplesParams,
          },
          ...layout,
        });
        continue;
      }

      const layout = getRuntimePanelAddLayout(panel);
      api.addPanel({
        id: runtimePanelId,
        component: "runtimeModulePanel",
        title: panel.title,
        params: {
          panelId: panel.id,
          runtimePlacementKey: getRuntimePanelPlacementKey(panel),
        },
        position: getRuntimePanelPosition(api, panel.position, panel),
        initialWidth:
          layout.initialWidth ??
          (panel.position === "right" ? getDefaultRightPanelWidth(getContainerWidth(api)) : undefined),
        initialHeight:
          layout.initialHeight ??
          (panel.position === "bottom"
            ? getDefaultBottomPanelHeight(getContainerHeight(api))
            : undefined),
        minimumWidth: layout.minimumWidth,
        minimumHeight: layout.minimumHeight,
        maximumWidth: layout.maximumWidth,
        maximumHeight: layout.maximumHeight,
      });
    }

  }, [ctx.api, customPanels, datasetInfo, hasExplicitView]);

  useEffect(() => {
    const api = ctx.api;
    if (!api || !activePanelId) return;
    const panel = resolveRuntimeReferencePanel(api, activePanelId);
    if (!panel) return;
    panel.api.setActive();
    panel.focus();
  }, [activePanelId, ctx.api, customPanels]);

  return (
    <div className="h-full w-full">
      <DockviewReact
        components={COMPONENTS}
        tabComponents={TAB_COMPONENTS}
        onReady={onReady}
        theme={HYPERVIEW_DOCKVIEW_THEME}
        rightHeaderActionsComponent={DockviewPanelActions}
        getTabContextMenuItems={getDockviewTabContextMenuItems}
        scrollbars="native"
        watermarkComponent={Watermark}
      />
    </div>
  );
}
