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
  type SerializedDockview,
  type DockviewTheme,
  type IDockviewPanelProps,
  type IWatermarkPanelProps,
  themeAbyss,
} from "dockview-react";
import { Columns2 } from "lucide-react";

import {
  addRuntimePanel,
  getRuntimeClientId,
  isStaticBundle,
  removeRuntimePanel,
  runControlCommand,
} from "@/lib/api";
import type { SamplesViewModel } from "@/lib/sampleCollections";
import {
  CENTER_PANEL_TAB_COMPONENTS,
  getPanelTabComponent,
  PANEL,
} from "@/panels/registry";
import { installHyperViewPanelSdkGlobal } from "@/panel-sdk";
import { useStore } from "@/store/useStore";
import type {
  DatasetInfo,
  Geometry,
  RuntimePanel,
  RuntimePanelDefinition,
  RuntimePanelStateEntry,
} from "@/types";
import { cn } from "@/lib/utils";
import {
  isDockviewUserClosablePanelId,
  RUNTIME_PANEL_PREFIX,
} from "@/lib/dockviewPanelPolicy";

import { Button } from "./ui/button";
import { DockviewContext, useDockviewContext } from "./DockviewContext";
import { HyperViewLogo } from "./icons";
import { PanelHost } from "./PanelHost";

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
  PANEL.SCATTER,
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

function definitionLayout(definition: RuntimePanelDefinition) {
  return definition.default_layout ?? {};
}

function defaultPanelId(definition: RuntimePanelDefinition) {
  const id = definitionLayout(definition).id;
  return typeof id === "string" && id.length > 0 ? id : definition.panel_type;
}

function defaultPanelProps(definition: RuntimePanelDefinition) {
  const props = { ...definition.default_props };
  const presetName = definitionLayout(definition).preset;
  const presets = props.presets;
  if (
    typeof presetName === "string" &&
    isRecord(presets) &&
    isRecord(presets[presetName])
  ) {
    Object.assign(props, presets[presetName], { preset: presetName });
  }
  return props;
}

function panelDefinition(
  definitions: RuntimePanelDefinition[],
  panel: RuntimePanel
) {
  return definitions.find((item) => item.panel_type === panel.panel_type) ?? null;
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
  zone: "center" | "left" | "right" | "bottom",
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
  return "panelHost";
}

function getDockPanelId(panel: RuntimePanel) {
  return panel.kind === "builtin" ? panel.id : `${RUNTIME_PANEL_PREFIX}${panel.id}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getSamplesRankFromPanelState(panelState?: RuntimePanelStateEntry) {
  const retrieval = panelState?.state.retrieval;
  if (!isRecord(retrieval)) return null;
  const anchorSampleId = retrieval.anchor_sample_id;
  const queryText = retrieval.query_text;
  const hasAnchor = typeof anchorSampleId === "string" && anchorSampleId.length > 0;
  const hasText = typeof queryText === "string" && queryText.length > 0;
  if (!hasAnchor && !hasText) return null;
  const layoutKey = retrieval.layout_key;
  const spaceKey = retrieval.space_key;
  const k = retrieval.k;
  const source = retrieval.source;
  return {
    anchorSampleId: hasAnchor ? anchorSampleId : undefined,
    queryText: hasText ? queryText : undefined,
    layoutKey: typeof layoutKey === "string" ? layoutKey : undefined,
    spaceKey: typeof spaceKey === "string" ? spaceKey : undefined,
    k: typeof k === "number" ? k : undefined,
    source: typeof source === "string" ? source : undefined,
  };
}

function getRuntimeSamplesPanelParams(
  panel: RuntimePanel,
  panelState?: RuntimePanelStateEntry
) {
  const stateMode = panelState?.state.mode;
  const mode = stateMode === "retrieval" ? "ranked" : panel.props?.mode;
  const rank = getSamplesRankFromPanelState(panelState) ?? panel.props?.rank;
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

function getRuntimePanelHostParams(
  panel: RuntimePanel,
  panelState?: RuntimePanelStateEntry
) {
  const baseParams = {
    ...(panel.props ?? {}),
    panelId: panel.id,
    builtinPanelType: panel.builtin_panel ?? panel.panel_type,
    runtimePlacementKey: getRuntimePanelPlacementKey(panel),
  };

  if (panel.panel_type === "scatter") {
    const presetName = typeof panel.props?.preset === "string" ? panel.props.preset : null;
    const presets = isRecord(panel.props?.presets) ? panel.props.presets : null;
    const preset = presetName && presets && isRecord(presets[presetName])
      ? presets[presetName]
      : null;
    const presetDimension = preset?.layout_dimension;
    const layoutDimension =
      panel.layout_dimension === 3 || presetDimension === 3 ? 3 : 2;
    const presetGeometry = preset?.geometry;
    return {
      ...baseParams,
      layoutKey: panel.layout_key ?? undefined,
      geometry: (panel.geometry ?? presetGeometry ?? undefined) as Geometry | undefined,
      layoutDimension,
      pinnedLayout: true,
    };
  }

  if (panel.builtin_panel === "samples" || panel.panel_type === "samples") {
    return {
      ...baseParams,
      ...getRuntimeSamplesPanelParams(panel, panelState),
    };
  }

  return baseParams;
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
          sourcePanel.kind === "module"
            ? "extension"
            : sourcePanel.panel_type === "scatter"
              ? "scatter"
              : "builtin",
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
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const customPanels = useStore((state) => state.customPanels);
  const panelDefinitions = useStore((state) => state.panelDefinitions);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const setWorkspaceLayoutLocal = useStore((state) => state.setWorkspaceLayoutLocal);

  const addPanel = useCallback(
    (panelId: string) => {
      if (!ctx?.api || !activeWorkspaceId) return;
      const existing = customPanels.find((panel) => panel.id === panelId);
      if (existing) {
        ctx.api.getPanel(getDockPanelId(existing))?.focus();
        return;
      }
      const definition = panelDefinitions.find(
        (item) => defaultPanelId(item) === panelId
      );
      if (!definition || isStaticBundle()) return;
      void addRuntimePanel({
        workspaceId: activeWorkspaceId,
        panelId,
        kind: "builtin",
        builtinPanel: definition.panel_type,
        title: definition.title,
        position: "center",
        props: defaultPanelProps(definition),
      }).then(applyRuntimeSnapshot).catch((error) => {
        console.error("Failed to add built-in panel:", error);
      });
    },
    [activeWorkspaceId, applyRuntimeSnapshot, ctx?.api, customPanels, panelDefinitions]
  );

  const resetLayout = useCallback(() => {
    setWorkspaceLayoutLocal(null);
    if (isStaticBundle() || !activeWorkspaceId) {
      window.location.reload();
      return;
    }
    void runControlCommand({
      command: "workspace.layout.set",
      target: { workspace_id: activeWorkspaceId },
      args: { layout: null, client_id: getRuntimeClientId() },
    }).finally(() => window.location.reload());
  }, [activeWorkspaceId, setWorkspaceLayoutLocal]);

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
        const explorer = customPanels.find((panel) => panel.panel_type === "explorer");
        if (explorer) applyExplorerPanelPolicy(api.getPanel(getDockPanelId(explorer)));
        else addPanel(PANEL.EXPLORER);
      }
      ctx.notifyEdgeStateChange();
    },
    [addPanel, ctx, customPanels]
  );

  if (!ctx) return null;

  return {
    api: ctx.api,
    addPanel,
    resetLayout,
    toggleZone,
  };
}

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
  panelHost: PanelHost,
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
  const panelDefinitions = useStore((state) => state.panelDefinitions);
  const panelStates = useStore((state) => state.panelStates);
  const activePanelId = useStore((state) => state.activePanelId);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const hasExplicitView = useStore((state) => state.hasExplicitView);
  const requestedLayoutKey = useStore((state) => state.requestedLayoutKey);
  const workspaceLayout = useStore((state) => state.workspaceLayout);
  const workspaceLayoutRevision = useStore((state) => state.workspaceLayoutRevision);
  const setWorkspaceLayoutLocal = useStore((state) => state.setWorkspaceLayoutLocal);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const runtimeSyncClosedPanels = useRef(new Set<string>());
  const bootstrappingWorkspace = useRef<string | null>(null);
  const restoredLayoutRevision = useRef<number | null>(null);
  const layoutSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const buildDefaultLayout = useCallback(
    (api: DockviewApi) => {
      const orderedDefinitions = panelDefinitions
        .filter((definition) => typeof definitionLayout(definition).id === "string")
        .toSorted((left, right) => {
          const leftOrder = definitionLayout(left).order;
          const rightOrder = definitionLayout(right).order;
          return (typeof leftOrder === "number" ? leftOrder : 0) -
            (typeof rightOrder === "number" ? rightOrder : 0);
        });

      for (const definition of orderedDefinitions) {
        const id = defaultPanelId(definition);
        if (api.getPanel(id)) continue;
        const layout = definitionLayout(definition);
        const referenceId = typeof layout.reference_panel_id === "string"
          ? layout.reference_panel_id
          : null;
        const referencePanel = referenceId ? api.getPanel(referenceId) : null;
        const dockZone = layout.dock_zone;
        const position = dockZone === "left"
          ? { referenceGroup: showEdgeGroup(api, "left").id }
          : referencePanel
            ? {
                referencePanel,
                direction:
                  layout.direction === "left" || layout.direction === "above" ||
                  layout.direction === "below" || layout.direction === "within"
                    ? layout.direction
                    : "right",
              }
            : undefined;
        const panel = api.addPanel({
          id,
          component: "panelHost",
          title: definition.title,
          tabComponent: getPanelTabComponent(definition.panel_type),
          params: {
            panelId: id,
            builtinPanelType: definition.panel_type,
            definitionProps: defaultPanelProps(definition),
            definitionTitle: definition.title,
          },
          position,
        });
        if (definition.panel_type === "explorer") applyExplorerPanelPolicy(panel);
      }

      ensureEdgeGroup(api, "right");
      ensureEdgeGroup(api, "bottom");
      hideEdgeGroup(api, "right");
      hideEdgeGroup(api, "bottom");
    },
    [panelDefinitions]
  );

  const onReady = useCallback(
    (event: DockviewReadyEvent) => {
      ctx.setApi(event.api);
      if (workspaceLayout) {
        try {
          event.api.fromJSON(workspaceLayout as unknown as SerializedDockview);
          restoredLayoutRevision.current = workspaceLayoutRevision;

          if (event.api.totalPanels === 0) {
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
        }
      }

      if (isStaticBundle() && !hasExplicitView && event.api.totalPanels === 0) {
        buildDefaultLayout(event.api);
      }
    },
    [
      buildDefaultLayout,
      ctx,
      hasExplicitView,
      workspaceLayout,
      workspaceLayoutRevision,
    ]
  );

  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidLayoutChange(() => {
      if (api.totalPanels === 0) return;
      const nextLayout = api.toJSON() as unknown as Record<string, unknown>;
      setWorkspaceLayoutLocal(nextLayout);
      if (layoutSaveTimer.current) clearTimeout(layoutSaveTimer.current);
      if (isStaticBundle() || !activeWorkspaceId) return;
      layoutSaveTimer.current = setTimeout(() => {
        void runControlCommand({
          command: "workspace.layout.set",
          target: { workspace_id: activeWorkspaceId },
          args: { layout: nextLayout, client_id: getRuntimeClientId() },
        }).catch((error) => {
          console.error("Failed to persist workspace layout:", error);
        });
      }, 150);
    });

    return () => {
      disposable.dispose();
      if (layoutSaveTimer.current) clearTimeout(layoutSaveTimer.current);
    };
  }, [activeWorkspaceId, ctx.api, setWorkspaceLayoutLocal]);

  useEffect(() => {
    const api = ctx.api;
    if (!api || !workspaceLayout) return;
    if (restoredLayoutRevision.current === workspaceLayoutRevision) return;
    try {
      api.fromJSON(workspaceLayout as unknown as SerializedDockview);
      restoredLayoutRevision.current = workspaceLayoutRevision;
      ensureEdgeGroups(api);
      hideEmptySecondaryEdgeGroups(api);
      applyZonePolicies(api);
    } catch (error) {
      console.warn("Failed to apply runtime workspace layout:", error);
    }
  }, [ctx.api, workspaceLayout, workspaceLayoutRevision]);

  useEffect(() => {
    if (
      !ctx.api ||
      !activeWorkspaceId ||
      workspaceLayout ||
      hasExplicitView ||
      isStaticBundle() ||
      panelDefinitions.length === 0 ||
      bootstrappingWorkspace.current === activeWorkspaceId
    ) return;

    bootstrappingWorkspace.current = activeWorkspaceId;
    const existingIds = new Set(customPanels.map((panel) => panel.id));
    const defaults = panelDefinitions
      .filter((definition) => typeof definitionLayout(definition).id === "string")
      .toSorted((left, right) => {
        const leftOrder = definitionLayout(left).order;
        const rightOrder = definitionLayout(right).order;
        return (typeof leftOrder === "number" ? leftOrder : 0) -
          (typeof rightOrder === "number" ? rightOrder : 0);
      });

    void (async () => {
      try {
        for (const definition of defaults) {
          const panelId = defaultPanelId(definition);
          if (existingIds.has(panelId)) continue;
          const layout = definitionLayout(definition);
          const position = layout.position === "center" || layout.position === "bottom"
            ? layout.position
            : "right";
          const direction =
            layout.direction === "left" || layout.direction === "above" ||
            layout.direction === "below" || layout.direction === "within"
              ? layout.direction
              : layout.direction === "right" ? "right" : null;
          const snapshot = await addRuntimePanel({
            workspaceId: activeWorkspaceId,
            panelId,
            kind: "builtin",
            builtinPanel: definition.panel_type,
            title: definition.title,
            position,
            referencePanelId:
              typeof layout.reference_panel_id === "string"
                ? layout.reference_panel_id
                : null,
            direction,
            props: defaultPanelProps(definition),
          });
          existingIds.add(panelId);
          applyRuntimeSnapshot(snapshot);
        }
      } catch (error) {
        console.error("Failed to create default runtime panels:", error);
        bootstrappingWorkspace.current = null;
      }
    })();
  }, [
    activeWorkspaceId,
    applyRuntimeSnapshot,
    ctx.api,
    customPanels,
    hasExplicitView,
    panelDefinitions,
    workspaceLayout,
  ]);

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
    if (!api || !requestedLayoutKey || hasExplicitView) return;

    // The scatter panel itself resolves the requested layout (geometry/dimension
    // live in panel state now); the host only guarantees a scatter panel is open.
    const existingScatter = customPanels.find(
      (panel) =>
        panel.visible !== false &&
        (panel.builtin_panel ?? panel.panel_type) === "scatter"
    );
    if (existingScatter) {
      api.getPanel(getDockPanelId(existingScatter))?.api.setActive();
      return;
    }
    if (isStaticBundle() || !activeWorkspaceId) return;

    void addRuntimePanel({
      workspaceId: activeWorkspaceId,
      panelId: `scatter-${requestedLayoutKey.replace(/[^a-zA-Z0-9_-]/g, "-")}`,
      kind: "builtin",
      builtinPanel: "scatter",
      title: "Embeddings",
      position: "center",
      props: { layout_key: requestedLayoutKey },
    })
      .then(applyRuntimeSnapshot)
      .catch((error) => {
        console.error("Failed to open scatter panel for requested layout:", error);
      });
  }, [
    activeWorkspaceId,
    applyRuntimeSnapshot,
    ctx.api,
    customPanels,
    hasExplicitView,
    requestedLayoutKey,
  ]);

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
        const placementChanged =
          existingPlacementKey !== undefined && existingPlacementKey !== placementKey;
        if (!expectedComponent || currentComponent !== expectedComponent || placementChanged) {
          runtimeSyncClosedPanels.current.add(panel.id);
          existingPanel.api.close();
          existingPanel = undefined;
        } else {
          existingPanel.api.setTitle(panel.title);
          existingPanel.api.updateParameters(
            getRuntimePanelHostParams(panel, panelStates[panel.id])
          );
          continue;
        }
      }

      const builtInPanelType = panel.builtin_panel ?? panel.panel_type;
      const layout = getRuntimePanelAddLayout(panel);
      api.addPanel({
        id: runtimePanelId,
        component: "panelHost",
        title: panel.title,
        tabComponent:
          panel.kind === "module" ? undefined : getPanelTabComponent(builtInPanelType),
        params: getRuntimePanelHostParams(panel, panelStates[panel.id]),
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

  }, [ctx.api, customPanels, datasetInfo, hasExplicitView, panelStates]);

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
