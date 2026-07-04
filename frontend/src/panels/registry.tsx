"use client";

import React from "react";
import type {
  DockviewApi,
  IDockviewPanelHeaderProps,
  IDockviewPanelProps,
} from "dockview-react";
import { Circle, Disc, Globe2 } from "lucide-react";

import { ScatterPanel } from "@/components/ScatterPanel";
import {
  defineBuiltInCenterPanel,
  type BuiltInCenterPanelDefinition,
  type DockviewPanelPosition,
} from "@/panels/definitions";
import { samplesImageGridBuiltInPanel } from "@/panels/builtins/samplesImageGridPanel";
import { findLayoutByGeometry, findLayoutByKey, getLayoutDimension } from "@/lib/layouts";
import type { DatasetInfo, Geometry } from "@/types";

const PANEL = {
  EXPLORER: "explorer",
  GRID: samplesImageGridBuiltInPanel.id,
  SCATTER_EUCLIDEAN: "scatter-euclidean",
  SCATTER_POINCARE: "scatter-poincare",
  SCATTER_SPHERICAL: "scatter-spherical",
  SCATTER_EUCLIDEAN_3D: "scatter-euclidean-3d",
  SCATTER_SPHERICAL_3D: "scatter-spherical-3d",
  SCATTER_DEFAULT: "scatter-default",
} as const;

type ScatterPanelParams = {
  layoutKey?: string;
  geometry?: Geometry;
  layoutDimension?: 2 | 3;
  pinnedLayout?: boolean;
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
      layoutDimension={params.layoutDimension}
      pinnedLayout={params.pinnedLayout}
    />
  );
});

function getResolvedScatterLayout(args: {
  datasetInfo: DatasetInfo | null;
  geometry: Geometry;
  layoutDimension: 2 | 3;
}) {
  const { datasetInfo, geometry, layoutDimension } = args;
  const layouts = datasetInfo?.layouts ?? [];
  const renderableLayouts = layouts.filter(
    (layout) => getLayoutDimension(layout.layout_key) === layoutDimension
  );

  return (
    findLayoutByGeometry(renderableLayouts, geometry, layoutDimension) ?? null
  );
}

function createScatterPanelDefinition(args: {
  id: string;
  title: string;
  label: string;
  icon: typeof Circle;
  tabComponent: string;
  geometry: Geometry;
  layoutDimension: 2 | 3;
}) {
  const { id, title, label, icon, tabComponent, geometry, layoutDimension } = args;

  return defineBuiltInCenterPanel<ScatterPanelParams>({
    id,
    panelType: "scatter",
    component: "scatter",
    title,
    label,
    icon,
    tabComponent,
    Component: ScatterDockPanel,
    buildAddPanelOptions: ({ datasetInfo, position }) => {
      const resolvedLayout = getResolvedScatterLayout({
        datasetInfo,
        geometry,
        layoutDimension,
      });

      return {
        id,
        component: "scatter",
        title,
        tabComponent,
        params: {
          layoutKey: resolvedLayout?.layout_key,
          geometry,
          layoutDimension,
        },
        ...(position ? { position } : {}),
      };
    },
  });
}

const scatterEuclideanBuiltInPanel = createScatterPanelDefinition({
  id: PANEL.SCATTER_EUCLIDEAN,
  title: "Euclidean",
  label: "Euclidean",
  icon: Circle,
  tabComponent: "euclideanTab",
  geometry: "euclidean",
  layoutDimension: 2,
});

const scatterPoincareBuiltInPanel = createScatterPanelDefinition({
  id: PANEL.SCATTER_POINCARE,
  title: "Hyperbolic",
  label: "Hyperbolic",
  icon: Disc,
  tabComponent: "hyperbolicTab",
  geometry: "poincare",
  layoutDimension: 2,
});

const scatterSphericalBuiltInPanel = createScatterPanelDefinition({
  id: PANEL.SCATTER_SPHERICAL,
  title: "Spherical",
  label: "Spherical",
  icon: Globe2,
  tabComponent: "sphericalTab",
  geometry: "spherical",
  layoutDimension: 2,
});

const scatterEuclidean3DBuiltInPanel = createScatterPanelDefinition({
  id: PANEL.SCATTER_EUCLIDEAN_3D,
  title: "Euclidean 3D",
  label: "Euclidean 3D",
  icon: Circle,
  tabComponent: "euclidean3dTab",
  geometry: "euclidean",
  layoutDimension: 3,
});

const scatterSpherical3DBuiltInPanel = createScatterPanelDefinition({
  id: PANEL.SCATTER_SPHERICAL_3D,
  title: "Sphere 3D",
  label: "Sphere 3D",
  icon: Globe2,
  tabComponent: "spherical3dTab",
  geometry: "spherical",
  layoutDimension: 3,
});

const fallbackScatterBuiltInPanel = defineBuiltInCenterPanel<ScatterPanelParams>({
  id: PANEL.SCATTER_DEFAULT,
  panelType: "scatter",
  component: "scatter",
  title: "Embeddings",
  label: "Embeddings",
  icon: Circle,
  tabComponent: "embeddingsTab",
  Component: ScatterDockPanel,
  visibleInViewMenu: false,
  buildAddPanelOptions: ({ datasetInfo, position }) => {
    const layouts = datasetInfo?.layouts ?? [];
    const renderableLayouts2d = layouts.filter(
      (layout) => getLayoutDimension(layout.layout_key) === 2
    );
    const renderableLayouts3d = layouts.filter(
      (layout) => getLayoutDimension(layout.layout_key) === 3
    );

    const resolvedLayout = renderableLayouts2d[0] ?? renderableLayouts3d[0] ?? null;
    const layoutDimension = resolvedLayout
      ? (getLayoutDimension(resolvedLayout.layout_key) as 2 | 3)
      : 2;

    return {
      id: PANEL.SCATTER_DEFAULT,
      component: "scatter",
      title: "Embeddings",
      tabComponent: "embeddingsTab",
      params: {
        layoutKey: resolvedLayout?.layout_key,
        layoutDimension,
      },
      ...(position ? { position } : {}),
    };
  },
});

const BUILT_IN_CENTER_PANELS = [
  samplesImageGridBuiltInPanel,
  scatterEuclideanBuiltInPanel,
  scatterPoincareBuiltInPanel,
  scatterSphericalBuiltInPanel,
  scatterEuclidean3DBuiltInPanel,
  scatterSpherical3DBuiltInPanel,
  fallbackScatterBuiltInPanel,
] as const satisfies readonly BuiltInCenterPanelDefinition[];

const builtInCenterPanelById = new Map(
  BUILT_IN_CENTER_PANELS.map((panel) => [panel.id, panel])
);

const builtInCenterPanelByPanelType = new Map(
  BUILT_IN_CENTER_PANELS.map((panel) => [panel.panelType, panel])
);

export const CENTER_PANEL_DEFS = BUILT_IN_CENTER_PANELS.filter(
  (panel) => panel.visibleInViewMenu !== false
).map((panel) => ({
  id: panel.id,
  panelType: panel.panelType,
  label: panel.label,
  icon: panel.icon,
})) as ReadonlyArray<{
  id: string;
  panelType: string;
  label: string;
  icon: BuiltInCenterPanelDefinition["icon"];
}>;

export const CENTER_PANEL_COMPONENTS = {
  [samplesImageGridBuiltInPanel.component]: samplesImageGridBuiltInPanel.Component,
  scatter: ScatterDockPanel,
} satisfies Record<string, React.ComponentType<IDockviewPanelProps>>;

export const CENTER_PANEL_TAB_COMPONENTS = Object.fromEntries(
  BUILT_IN_CENTER_PANELS.map((panel) => [panel.tabComponent, panel.TabComponent])
) as Record<string, React.FunctionComponent<IDockviewPanelHeaderProps>>;

export function getBuiltInCenterPanelDefinition(panelId: string) {
  return builtInCenterPanelById.get(panelId) ?? null;
}

export function getBuiltInCenterPanelDefinitionForPanelType(panelType: string | null | undefined) {
  if (!panelType) return null;
  return builtInCenterPanelByPanelType.get(panelType) ?? null;
}

export function getBuiltInCenterPanelIdForLayout(args: {
  datasetInfo: DatasetInfo | null;
  layoutKey: string | null;
}): string | null {
  const { datasetInfo, layoutKey } = args;
  if (!datasetInfo || !layoutKey) {
    return null;
  }

  const layout = findLayoutByKey(datasetInfo.layouts, layoutKey);
  if (!layout) {
    return null;
  }

  const layoutDimension = getLayoutDimension(layout.layout_key);
  if (layout.geometry === "euclidean" && layoutDimension === 2) {
    return PANEL.SCATTER_EUCLIDEAN;
  }
  if (layout.geometry === "poincare" && layoutDimension === 2) {
    return PANEL.SCATTER_POINCARE;
  }
  if (layout.geometry === "spherical" && layoutDimension === 2) {
    return PANEL.SCATTER_SPHERICAL;
  }
  if (layout.geometry === "euclidean" && layoutDimension === 3) {
    return PANEL.SCATTER_EUCLIDEAN_3D;
  }
  if (layout.geometry === "spherical" && layoutDimension === 3) {
    return PANEL.SCATTER_SPHERICAL_3D;
  }

  return PANEL.SCATTER_DEFAULT;
}

export function getScatterTabComponent(args: {
  geometry?: Geometry | string | null;
  layoutDimension?: 2 | 3 | number | null;
}) {
  const layoutDimension = args.layoutDimension === 3 ? 3 : 2;
  if (args.geometry === "euclidean" && layoutDimension === 3) return "euclidean3dTab";
  if (args.geometry === "spherical" && layoutDimension === 3) return "spherical3dTab";
  if (args.geometry === "euclidean") return "euclideanTab";
  if (args.geometry === "poincare") return "hyperbolicTab";
  if (args.geometry === "spherical") return "sphericalTab";
  return "embeddingsTab";
}

export function addBuiltInCenterPanel(args: {
  api: DockviewApi;
  panelId: string;
  datasetInfo: DatasetInfo | null;
  position?: DockviewPanelPosition;
  focusIfPresent?: boolean;
}) {
  const { api, panelId, datasetInfo, position, focusIfPresent = true } = args;
  const existingPanel = api.getPanel(panelId);

  if (existingPanel) {
    if (focusIfPresent) {
      existingPanel.focus();
    }
    return existingPanel;
  }

  const definition = getBuiltInCenterPanelDefinition(panelId);
  if (!definition) {
    return null;
  }

  return api.addPanel(
    definition.buildAddPanelOptions({
      api,
      datasetInfo,
      position,
    })
  );
}

export { PANEL };
