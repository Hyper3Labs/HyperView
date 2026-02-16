"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useState,
  createContext,
  useContext,
  type ReactNode,
} from "react";
import {
  DockviewReact,
  type DockviewApi,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
  type IDockviewPanelHeaderProps,
  type IWatermarkPanelProps,
  themeAbyss,
} from "dockview";
import { Circle, Disc, Grid3X3 } from "lucide-react";

import type { Geometry, Sample } from "@/types";
import { useStore } from "@/store/useStore";
import { findLayoutByGeometry } from "@/lib/layouts";
import { ImageGrid } from "./ImageGrid";
import { ScatterPanel } from "./ScatterPanel";
import { ExplorerPanel } from "./ExplorerPanel";
import { PlaceholderPanel } from "./PlaceholderPanel";
import { HyperViewLogo } from "./icons";
import { PanelTitle } from "./PanelTitle";

const LAYOUT_STORAGE_KEY = "hyperview:dockview-layout:v4";

// Panel IDs
const PANEL = {
  EXPLORER: "explorer",
  GRID: "grid",
  SCATTER_EUCLIDEAN: "scatter-euclidean",
  SCATTER_POINCARE: "scatter-poincare",
  SCATTER_DEFAULT: "scatter-default",
  RIGHT_PLACEHOLDER: "right-placeholder",
  BOTTOM_PLACEHOLDER: "bottom-placeholder",
} as const;

const CENTER_PANEL_IDS = [
  PANEL.GRID,
  PANEL.SCATTER_EUCLIDEAN,
  PANEL.SCATTER_POINCARE,
  PANEL.SCATTER_DEFAULT,
] as const;

export const CENTER_PANEL_DEFS = [
  { id: PANEL.GRID, label: "Samples", icon: Grid3X3 },
  { id: PANEL.SCATTER_EUCLIDEAN, label: "Euclidean", icon: Circle },
  { id: PANEL.SCATTER_POINCARE, label: "Hyperbolic", icon: Disc },
] as const;

const NON_ANCHOR_PANEL_IDS = new Set<string>([
  PANEL.EXPLORER,
  PANEL.RIGHT_PLACEHOLDER,
  PANEL.BOTTOM_PLACEHOLDER,
]);

const DRAG_LOCKED_PANEL_IDS = new Set<string>([PANEL.EXPLORER]);

const DEFAULT_CONTAINER_WIDTH = 1200;
const DEFAULT_CONTAINER_HEIGHT = 800;
const MIN_SIDE_PANEL_WIDTH = 120;
const MIN_BOTTOM_PANEL_HEIGHT = 150;

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
  for (const id of CENTER_PANEL_IDS) {
    const panel = api.getPanel(id);
    if (panel) return panel;
  }

  const fallback = api.panels.find((panel) => !NON_ANCHOR_PANEL_IDS.has(panel.id));
  return fallback ?? api.activePanel;
}

function getZonePosition(zone: "left" | "right" | "bottom") {
  return { direction: zone === "bottom" ? "below" : zone };
}

function getCenterTabPosition(api: DockviewApi) {
  const anchor = getCenterAnchorPanel(api);
  if (!anchor) return undefined;
  return { referencePanel: anchor, direction: "within" as const };
}

// -----------------------------------------------------------------------------
// Context for sharing dockview API across components
// -----------------------------------------------------------------------------
interface DockviewContextValue {
  api: DockviewApi | null;
  setApi: (api: DockviewApi) => void;
  samples: Sample[];
  onLoadMore: () => void;
  hasMore: boolean;
}

const DockviewContext = createContext<DockviewContextValue | null>(null);

function useDockviewContext() {
  const ctx = useContext(DockviewContext);
  if (!ctx) throw new Error("useDockviewContext must be used within DockviewProvider");
  return ctx;
}

// Public hook for components like Header
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

      const api = ctx.api;
      const position = getCenterTabPosition(api);
      const baseOptions = position ? { position } : {};

      const layouts = datasetInfo?.layouts ?? [];
      const euclideanLayout = findLayoutByGeometry(layouts, "euclidean");
      const poincareLayout = findLayoutByGeometry(layouts, "poincare");

      // Don't add if already exists - just focus it
      if (api.getPanel(panelId)) {
        api.getPanel(panelId)?.focus();
        return;
      }

      switch (panelId) {
        case PANEL.GRID:
          api.addPanel({
            id: PANEL.GRID,
            component: "grid",
            title: "Samples",
            tabComponent: "samplesTab",
            renderer: "always",
            ...baseOptions,
          });
          break;

        case PANEL.SCATTER_EUCLIDEAN:
          api.addPanel({
            id: PANEL.SCATTER_EUCLIDEAN,
            component: "scatter",
            title: "Euclidean",
            tabComponent: "euclideanTab",
            params: {
              layoutKey: euclideanLayout?.layout_key,
              geometry: "euclidean" as Geometry,
            },
            renderer: "always",
            ...baseOptions,
          });
          break;

        case PANEL.SCATTER_POINCARE:
          api.addPanel({
            id: PANEL.SCATTER_POINCARE,
            component: "scatter",
            title: "Hyperbolic",
            tabComponent: "hyperbolicTab",
            params: {
              layoutKey: poincareLayout?.layout_key,
              geometry: "poincare" as Geometry,
            },
            renderer: "always",
            ...baseOptions,
          });
          break;
      }
    },
    [ctx?.api, datasetInfo]
  );

  const resetLayout = useCallback(() => {
    localStorage.removeItem(LAYOUT_STORAGE_KEY);
    window.location.reload();
  }, []);

  // Toggle zone visibility
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
          // Explicitly set the width to ensure it's applied
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
        // Activate the panel so its content renders immediately
        newPanel.api.setActive();
      }
    },
    [
      ctx?.api,
      leftPanelOpen,
      rightPanelOpen,
      bottomPanelOpen,
      setLeftPanelOpen,
      setRightPanelOpen,
      setBottomPanelOpen,
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

// -----------------------------------------------------------------------------
// Panel Components - stable references defined outside component
// -----------------------------------------------------------------------------
type ScatterPanelParams = {
  layoutKey?: string;
  geometry?: Geometry;
};

const ScatterDockPanel = React.memo(function ScatterDockPanel(
  props: IDockviewPanelProps<ScatterPanelParams>
) {
  const params = props.params ?? {};
  return (
    <ScatterPanel
      className="h-full"
      layoutKey={params.layoutKey}
      geometry={params.geometry}
    />
  );
});

// Custom tab component with icon (like Rerun's "Image and segmentation mask" tab)
type TabWithIconProps = IDockviewPanelHeaderProps & {
  icon: React.ReactNode;
};

const TabWithIcon = React.memo(function TabWithIcon({ api, icon }: TabWithIconProps) {
  return (
    <PanelTitle
      title={api.title}
      icon={icon}
      fullHeight
      className="h-full"
      titleClassName="truncate"
    />
  );
});

// Tab components for different panel types
const EuclideanTab = React.memo(function EuclideanTab(props: IDockviewPanelHeaderProps) {
  return <TabWithIcon {...props} icon={<Circle className="h-3.5 w-3.5" />} />;
});

const HyperbolicTab = React.memo(function HyperbolicTab(props: IDockviewPanelHeaderProps) {
  return <TabWithIcon {...props} icon={<Disc className="h-3.5 w-3.5" />} />;
});

const SamplesTab = React.memo(function SamplesTab(props: IDockviewPanelHeaderProps) {
  return <TabWithIcon {...props} icon={<Grid3X3 className="h-3.5 w-3.5" />} />;
});

// Grid panel uses context to get samples
const GridDockPanel = React.memo(function GridDockPanel() {
  const ctx = useDockviewContext();
  return (
    <ImageGrid
      samples={ctx.samples}
      onLoadMore={ctx.onLoadMore}
      hasMore={ctx.hasMore}
    />
  );
});

// Explorer panel for left zone
const ExplorerDockPanel = React.memo(function ExplorerDockPanel() {
  return <ExplorerPanel />;
});

// Placeholder panel for right/bottom zones
const PlaceholderDockPanel = React.memo(function PlaceholderDockPanel(
  props: IDockviewPanelProps
) {
  const handleClose = React.useCallback(() => {
    props.api.close();
  }, [props.api]);

  return <PlaceholderPanel onClose={handleClose} />;
});

// Watermark shown when dock is empty - just the logo, no text
const Watermark = React.memo(function Watermark(_props: IWatermarkPanelProps) {
  return (
    <div className="flex items-center justify-center h-full w-full">
      <div className="text-muted-foreground/20">
        <HyperViewLogo className="w-16 h-16" />
      </div>
    </div>
  );
});

// Stable components object - never changes
const COMPONENTS = {
  grid: GridDockPanel,
  scatter: ScatterDockPanel,
  explorer: ExplorerDockPanel,
  placeholder: PlaceholderDockPanel,
};

// Tab components with icons
const TAB_COMPONENTS = {
  euclideanTab: EuclideanTab,
  hyperbolicTab: HyperbolicTab,
  samplesTab: SamplesTab,
};

// -----------------------------------------------------------------------------
// Provider Component
// -----------------------------------------------------------------------------
interface DockviewProviderProps {
  children: ReactNode;
  samples: Sample[];
  onLoadMore: () => void;
  hasMore: boolean;
}

export function DockviewProvider({
  children,
  samples,
  onLoadMore,
  hasMore,
}: DockviewProviderProps) {
  const [api, setApi] = useState<DockviewApi | null>(null);

  const contextValue = useMemo(
    () => ({
      api,
      setApi,
      samples,
      onLoadMore,
      hasMore,
    }),
    [api, samples, onLoadMore, hasMore]
  );

  return (
    <DockviewContext.Provider value={contextValue}>
      {children}
    </DockviewContext.Provider>
  );
}

function applyZonePolicies(api: DockviewApi) {
  const explorer = api.getPanel(PANEL.EXPLORER);
  if (explorer) {
    explorer.group.locked = true;
    explorer.group.header.hidden = true;
    explorer.api.setActive();
  }

  // Hide tab headers for placeholder panels
  const rightPlaceholder = api.getPanel(PANEL.RIGHT_PLACEHOLDER);
  if (rightPlaceholder) {
    rightPlaceholder.group.header.hidden = true;
  }

  const bottomPlaceholder = api.getPanel(PANEL.BOTTOM_PLACEHOLDER);
  if (bottomPlaceholder) {
    bottomPlaceholder.group.header.hidden = true;
  }
}

// -----------------------------------------------------------------------------
// Workspace Component - the actual dockview renderer
// -----------------------------------------------------------------------------
export function DockviewWorkspace() {
  const ctx = useDockviewContext();
  const datasetInfo = useStore((state) => state.datasetInfo);
  const { setLeftPanelOpen, setRightPanelOpen, setBottomPanelOpen } = useStore();

  const buildDefaultLayout = useCallback(
    (api: DockviewApi) => {
      const layouts = datasetInfo?.layouts ?? [];
      const euclideanLayout = findLayoutByGeometry(layouts, "euclidean");
      const poincareLayout = findLayoutByGeometry(layouts, "poincare");
      const fallbackLayout = !euclideanLayout && !poincareLayout ? layouts[0] : null;
      const hasLayouts = layouts.length > 0;

      // Create the grid panel first (center zone)
      const gridPanel =
        api.getPanel(PANEL.GRID) ??
        api.addPanel({
          id: PANEL.GRID,
          component: "grid",
          title: "Samples",
          tabComponent: "samplesTab",
          renderer: "always",
        });

      let scatterPanel: typeof gridPanel | null = null;

      if (hasLayouts && euclideanLayout) {
        scatterPanel =
          api.getPanel(PANEL.SCATTER_EUCLIDEAN) ??
          api.addPanel({
            id: PANEL.SCATTER_EUCLIDEAN,
            component: "scatter",
            title: "Euclidean",
            tabComponent: "euclideanTab",
            params: {
              layoutKey: euclideanLayout.layout_key,
              geometry: "euclidean" as Geometry,
            },
            position: {
              referencePanel: gridPanel.id,
              direction: "right",
            },
            renderer: "always",
          });
      }

      if (hasLayouts && poincareLayout) {
        const position = scatterPanel
          ? { referencePanel: scatterPanel.id, direction: "within" as const }
          : { referencePanel: gridPanel.id, direction: "right" as const };

        const poincarePanel =
          api.getPanel(PANEL.SCATTER_POINCARE) ??
          api.addPanel({
            id: PANEL.SCATTER_POINCARE,
            component: "scatter",
            title: "Hyperbolic",
            tabComponent: "hyperbolicTab",
            params: {
              layoutKey: poincareLayout.layout_key,
              geometry: "poincare" as Geometry,
            },
            position,
            renderer: "always",
          });

        if (!scatterPanel) {
          scatterPanel = poincarePanel;
        }
      }

      if (!hasLayouts) {
        const euclideanPanel =
          api.getPanel(PANEL.SCATTER_EUCLIDEAN) ??
          api.addPanel({
            id: PANEL.SCATTER_EUCLIDEAN,
            component: "scatter",
            title: "Euclidean",
            tabComponent: "euclideanTab",
            params: {
              geometry: "euclidean" as Geometry,
            },
            position: {
              referencePanel: gridPanel.id,
              direction: "right",
            },
            renderer: "always",
          });

        api.getPanel(PANEL.SCATTER_POINCARE) ??
          api.addPanel({
            id: PANEL.SCATTER_POINCARE,
            component: "scatter",
            title: "Hyperbolic",
            tabComponent: "hyperbolicTab",
            params: {
              geometry: "poincare" as Geometry,
            },
            position: {
              referencePanel: euclideanPanel.id,
              direction: "within" as const,
            },
            renderer: "always",
          });

        scatterPanel = euclideanPanel;
      }

      if (fallbackLayout && !scatterPanel) {
        api.getPanel(PANEL.SCATTER_DEFAULT) ??
          api.addPanel({
            id: PANEL.SCATTER_DEFAULT,
            component: "scatter",
            title: "Embeddings",
            params: {
              layoutKey: fallbackLayout.layout_key,
            },
            position: {
              referencePanel: gridPanel.id,
              direction: "right",
            },
            renderer: "always",
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

      setLeftPanelOpen(!!explorerPanel);
      setRightPanelOpen(false);
      setBottomPanelOpen(false);
    },
    [datasetInfo, setLeftPanelOpen, setRightPanelOpen, setBottomPanelOpen]
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

          // Re-apply side-zone policies after restore (header hidden, no-drop targets, etc)
          applyZonePolicies(event.api);
          
          // Sync store state with restored layout
          setLeftPanelOpen(!!event.api.getPanel(PANEL.EXPLORER));
          setRightPanelOpen(!!event.api.getPanel(PANEL.RIGHT_PLACEHOLDER));
          setBottomPanelOpen(!!event.api.getPanel(PANEL.BOTTOM_PLACEHOLDER));
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
    [buildDefaultLayout, ctx, setLeftPanelOpen, setRightPanelOpen, setBottomPanelOpen]
  );

  // Save layout on changes
  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidLayoutChange(() => {
      if (api.totalPanels === 0) return;
      const layout = api.toJSON();
      localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(layout));
    });

    return () => disposable.dispose();
  }, [ctx.api]);

  // Sync panel state when panels are closed
  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidRemovePanel((e) => {
      if (e.id === PANEL.EXPLORER) setLeftPanelOpen(false);
      if (e.id === PANEL.RIGHT_PLACEHOLDER) setRightPanelOpen(false);
      if (e.id === PANEL.BOTTOM_PLACEHOLDER) setBottomPanelOpen(false);
    });

    return () => disposable.dispose();
  }, [ctx.api, setLeftPanelOpen, setRightPanelOpen, setBottomPanelOpen]);

  // When a real panel is dropped into a placeholder group, close the placeholder
  useEffect(() => {
    const api = ctx.api;
    if (!api) return;

    const disposable = api.onDidAddPanel((e) => {
      // Skip if the added panel is a placeholder itself
      if (e.id === PANEL.RIGHT_PLACEHOLDER || e.id === PANEL.BOTTOM_PLACEHOLDER) {
        return;
      }

      // Check if this panel was added to the same group as a placeholder
      const group = e.group;
      if (!group) return;

      // Find and close any placeholder panels in the same group
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

  // Prevent dragging locked panels (explorer only)
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

  // Rebuild layout when dataset info changes
  useEffect(() => {
    if (!ctx.api) return;
    if (!datasetInfo) return;

    const hasScatter =
      ctx.api.getPanel(PANEL.SCATTER_EUCLIDEAN) ||
      ctx.api.getPanel(PANEL.SCATTER_POINCARE) ||
      ctx.api.getPanel(PANEL.SCATTER_DEFAULT);

    if (!hasScatter) {
      buildDefaultLayout(ctx.api);
    }
  }, [buildDefaultLayout, datasetInfo, ctx.api]);

  return (
    <div className="h-full w-full">
      <DockviewReact
        className="dockview-theme-abyss hyperview-dockview"
        components={COMPONENTS}
        tabComponents={TAB_COMPONENTS}
        onReady={onReady}
        theme={themeAbyss}
        defaultRenderer="always"
        scrollbars="native"
        watermarkComponent={Watermark}
      />
    </div>
  );
}
