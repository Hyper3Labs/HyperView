"use client";

import React from "react";
import type { IDockviewPanelProps } from "dockview-react";
import { Settings2 } from "lucide-react";

import { Panel } from "@/components/Panel";
import {
  PanelToolbar,
  PanelToolbarMenu,
  type PanelToolbarItem,
  type PanelToolbarOption,
} from "@/components/PanelToolbar";
import { useHyperScatter } from "@/components/useHyperScatter";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { buildLabelsInfo } from "@/lib/labelLegend";
import {
  findLayoutByGeometry,
  getLayoutDimension,
  listAvailableGeometries,
} from "@/lib/layouts";
import {
  useActiveLayout,
  useCommandClient,
  useDatasetInfo,
  usePanelInteractions,
  usePanelState,
  useQuery,
  useSelection,
} from "@/panel-sdk";
import type { Geometry } from "@/types";

export interface ScatterPanelParams extends Record<string, unknown> {
  panelId?: string;
  layoutKey?: string;
  geometry?: Geometry;
  layoutDimension?: 2 | 3;
  pinnedLayout?: boolean;
}

type LabelOverlayMode = "off" | "auto" | "coarse" | "fine";
type Camera3D = {
  yaw: number;
  pitch: number;
  distance: number;
  target_x: number;
  target_y: number;
  target_z: number;
  ortho_scale: number;
};

function stringState(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isGeometry(value: unknown): value is Geometry {
  return value === "euclidean" || value === "poincare" || value === "spherical";
}

function isLabelOverlayMode(value: unknown): value is LabelOverlayMode {
  return value === "off" || value === "auto" || value === "coarse" || value === "fine";
}

function cameraState(value: unknown): Camera3D | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const camera = value as Partial<Camera3D>;
  const values = [
    camera.yaw,
    camera.pitch,
    camera.distance,
    camera.target_x,
    camera.target_y,
    camera.target_z,
    camera.ortho_scale,
  ];
  return values.every((item) => typeof item === "number" && Number.isFinite(item))
    ? (camera as Camera3D)
    : null;
}

export const ScatterPanel = React.memo(function ScatterPanel(
  props: IDockviewPanelProps<ScatterPanelParams>
) {
  const params = props.params ?? {};
  const panelState = usePanelState(params.panelId ?? props.api.id);
  const datasetInfo = useDatasetInfo();
  const layoutsQuery = useQuery("layouts");
  const selection = useSelection();
  const interaction = usePanelInteractions();
  const workspaceLayout = useActiveLayout();
  const commandClient = useCommandClient();

  const layoutDimension = params.layoutDimension === 3 ? 3 : 2;
  const fixedGeometry = isGeometry(params.geometry) ? params.geometry : null;
  const stateGeometry = isGeometry(panelState.state.geometry) ? panelState.state.geometry : null;
  const [localGeometry, setLocalGeometry] = React.useState<Geometry>(
    fixedGeometry ?? stateGeometry ?? "euclidean"
  );
  const [localLayoutKey, setLocalLayoutKey] = React.useState<string | null>(
    stringState(panelState.state.layout_key) ?? params.layoutKey ?? null
  );
  const [labelOverlayMode, setLabelOverlayMode] = React.useState<LabelOverlayMode>(
    isLabelOverlayMode(panelState.state.label_overlay_mode)
      ? panelState.state.label_overlay_mode
      : interaction.scatterLabelOverlayMode
  );
  const stateLayoutKey = stringState(panelState.state.layout_key);
  const stateSpaceKey = stringState(panelState.state.space_key);
  const stateProjectionMethod = stringState(panelState.state.projection_method);

  React.useEffect(() => {
    if (stateLayoutKey) setLocalLayoutKey(stateLayoutKey);
  }, [stateLayoutKey]);

  React.useEffect(() => {
    if (isLabelOverlayMode(panelState.state.label_overlay_mode)) {
      setLabelOverlayMode(panelState.state.label_overlay_mode);
    }
  }, [panelState.state.label_overlay_mode]);

  const layouts = React.useMemo(
    () => layoutsQuery.data ?? datasetInfo.dataset?.layouts ?? [],
    [datasetInfo.dataset?.layouts, layoutsQuery.data]
  );
  const renderableLayouts = React.useMemo(
    () => layouts.filter((layout) => getLayoutDimension(layout.layout_key) === layoutDimension),
    [layoutDimension, layouts]
  );
  const availableGeometries = React.useMemo(
    () => listAvailableGeometries(renderableLayouts, layoutDimension),
    [layoutDimension, renderableLayouts]
  );

  React.useEffect(() => {
    if (fixedGeometry || availableGeometries.length === 0) return;
    if (!availableGeometries.includes(localGeometry)) {
      setLocalGeometry(availableGeometries[0]);
    }
  }, [availableGeometries, fixedGeometry, localGeometry]);

  const resolvedGeometry = fixedGeometry ?? localGeometry;

  React.useEffect(() => {
    if (params.pinnedLayout || !workspaceLayout.requestedLayoutKey) return;
    const requested = renderableLayouts.find(
      (layout) => layout.layout_key === workspaceLayout.requestedLayoutKey
    );
    if (requested?.geometry === resolvedGeometry) setLocalLayoutKey(requested.layout_key);
  }, [params.pinnedLayout, renderableLayouts, resolvedGeometry, workspaceLayout.requestedLayoutKey]);

  const resolvedLayoutKey = React.useMemo(() => {
    if (localLayoutKey && renderableLayouts.some((layout) => layout.layout_key === localLayoutKey)) {
      return localLayoutKey;
    }
    if (params.layoutKey && renderableLayouts.some((layout) => layout.layout_key === params.layoutKey)) {
      return params.layoutKey;
    }
    const stateChoice = renderableLayouts.find(
      (layout) =>
        (!stateSpaceKey || layout.space_key === stateSpaceKey) &&
        (!stateProjectionMethod || layout.method === stateProjectionMethod) &&
        layout.geometry === resolvedGeometry
    );
    if (stateChoice) return stateChoice.layout_key;
    const matching = findLayoutByGeometry(renderableLayouts, resolvedGeometry, layoutDimension);
    return matching?.layout_key ?? (fixedGeometry ? null : renderableLayouts[0]?.layout_key ?? null);
  }, [
    fixedGeometry,
    layoutDimension,
    localLayoutKey,
    params.layoutKey,
    renderableLayouts,
    resolvedGeometry,
    stateProjectionMethod,
    stateSpaceKey,
  ]);

  React.useEffect(() => {
    if (localLayoutKey && !renderableLayouts.some((layout) => layout.layout_key === localLayoutKey)) {
      setLocalLayoutKey(null);
    }
  }, [localLayoutKey, renderableLayouts]);

  const embeddingsQuery = useQuery("embeddings", { layoutKey: resolvedLayoutKey });
  const embeddings =
    resolvedLayoutKey && embeddingsQuery.data?.layout_key === resolvedLayoutKey
      ? embeddingsQuery.data
      : null;
  const resolvedLayout = React.useMemo(
    () => renderableLayouts.find((layout) => layout.layout_key === resolvedLayoutKey) ?? null,
    [renderableLayouts, resolvedLayoutKey]
  );
  const geometryLayouts = React.useMemo(
    () => renderableLayouts.filter((layout) => layout.geometry === resolvedGeometry),
    [renderableLayouts, resolvedGeometry]
  );
  const resolvedSpace = React.useMemo(
    () => datasetInfo.dataset?.spaces.find((space) => space.space_key === resolvedLayout?.space_key) ?? null,
    [datasetInfo.dataset?.spaces, resolvedLayout?.space_key]
  );

  const patchRuntimePanelState = React.useCallback(
    (patch: Record<string, unknown>) => {
      // TODO(w4a): Phase 7 must turn legacy direct Dockview scatter variants into
      // runtime panel instances. Until then the backend cannot accept panel-state
      // writes for those variants; workspace layout state below preserves behavior.
      if (!panelState.panel) return;
      void panelState.patchState(patch).catch((error) => {
        console.error("Failed to persist scatter panel state:", error);
      });
    },
    [panelState]
  );

  const selectLayout = React.useCallback(
    (layoutKey: string) => {
      const layout = renderableLayouts.find((candidate) => candidate.layout_key === layoutKey);
      if (!layout) return;
      setLocalLayoutKey(layout.layout_key);
      if (!fixedGeometry) setLocalGeometry(layout.geometry);
      patchRuntimePanelState({
        layout_key: layout.layout_key,
        space_key: layout.space_key,
        projection_method: layout.method,
        geometry: layout.geometry,
      });
    },
    [fixedGeometry, patchRuntimePanelState, renderableLayouts]
  );

  const modelOptions = React.useMemo<PanelToolbarOption[]>(() => {
    const seen = new Set<string>();
    return geometryLayouts.flatMap((layout) => {
      if (seen.has(layout.space_key)) return [];
      seen.add(layout.space_key);
      const space = datasetInfo.dataset?.spaces.find((candidate) => candidate.space_key === layout.space_key);
      return [{ value: layout.space_key, label: space?.model_id ?? layout.space_key, group: space?.provider }];
    });
  }, [datasetInfo.dataset?.spaces, geometryLayouts]);
  const selectedSpaceKey = resolvedLayout?.space_key ?? modelOptions[0]?.value ?? "";
  const selectedProjectionMethod = resolvedLayout?.method ?? "";
  const selectedModelLabel =
    modelOptions.find((option) => option.value === selectedSpaceKey)?.label ?? resolvedSpace?.model_id ?? "";
  const projectionMethodOptions = React.useMemo(() => {
    const selectedModelMethods = geometryLayouts
      .filter((layout) => layout.space_key === selectedSpaceKey)
      .map((layout) => layout.method);
    return Array.from(
      new Set(selectedModelMethods.length > 0 ? selectedModelMethods : geometryLayouts.map((layout) => layout.method))
    ).sort();
  }, [geometryLayouts, selectedSpaceKey]);

  const handleModelChange = React.useCallback(
    (nextSpaceKey: string) => {
      const target =
        geometryLayouts.find(
          (layout) => layout.space_key === nextSpaceKey && layout.method === selectedProjectionMethod
        ) ?? geometryLayouts.find((layout) => layout.space_key === nextSpaceKey);
      if (target) selectLayout(target.layout_key);
    },
    [geometryLayouts, selectLayout, selectedProjectionMethod]
  );
  const handleProjectionMethodChange = React.useCallback(
    (nextMethod: string) => {
      const target =
        geometryLayouts.find(
          (layout) => layout.method === nextMethod && layout.space_key === selectedSpaceKey
        ) ?? geometryLayouts.find((layout) => layout.method === nextMethod);
      if (target) selectLayout(target.layout_key);
    },
    [geometryLayouts, selectLayout, selectedSpaceKey]
  );

  const toolbarItems = React.useMemo<PanelToolbarItem[]>(
    () => [
      {
        id: "model",
        kind: "select",
        label: "Model",
        showLabel: false,
        value: selectedSpaceKey,
        placeholder: "Select model",
        valueTitle: selectedModelLabel,
        valueClassName: "max-w-[340px]",
        options: modelOptions,
        onValueChange: handleModelChange,
        disabled: modelOptions.length === 0,
      },
    ],
    [handleModelChange, modelOptions, selectedModelLabel, selectedSpaceKey]
  );

  const toolbarActions = React.useMemo(
    () => (
      <PanelToolbarMenu
        icon={<Settings2 className="h-3.5 w-3.5" />}
        label="Scatter settings"
        title={selectedProjectionMethod ? `Projection method: ${selectedProjectionMethod}` : "Scatter settings"}
        contentClassName="min-w-[220px]"
      >
        <DropdownMenuLabel>Projection method</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {projectionMethodOptions.length > 0 ? (
          <DropdownMenuRadioGroup value={selectedProjectionMethod} onValueChange={handleProjectionMethodChange}>
            {projectionMethodOptions.map((method) => (
              <DropdownMenuRadioItem key={method} value={method}>
                <span className="truncate">{method}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        ) : (
          <div className="px-2 py-1.5 text-[12px] leading-[16px] text-muted-foreground">
            No projection methods available
          </div>
        )}
        {layoutDimension === 2 ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Topic labels</DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={labelOverlayMode}
              onValueChange={(value) => {
                if (!isLabelOverlayMode(value)) return;
                setLabelOverlayMode(value);
                interaction.setScatterLabelOverlayMode(value);
                patchRuntimePanelState({ label_overlay_mode: value });
              }}
            >
              <DropdownMenuRadioItem value="off"><span className="truncate">Hidden</span></DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="auto"><span className="truncate">Auto</span></DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="coarse"><span className="truncate">Coarse</span></DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="fine"><span className="truncate">Fine</span></DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </>
        ) : null}
      </PanelToolbarMenu>
    ),
    [handleProjectionMethodChange, interaction, labelOverlayMode, layoutDimension, patchRuntimePanelState, projectionMethodOptions, selectedProjectionMethod]
  );

  const selectedIds = React.useMemo(() => new Set(selection.selectedIds), [selection.selectedIds]);
  const labelsInfo = React.useMemo(
    () =>
      buildLabelsInfo({
        datasetLabels: datasetInfo.labels,
        embeddings,
        labelColorMapId: interaction.labelColorMapId,
      }),
    [datasetInfo.labels, embeddings, interaction.labelColorMapId]
  );
  const panelCamera =
    stringState(panelState.state.camera_layout_key) === resolvedLayoutKey
      ? cameraState(panelState.state.camera_3d)
      : null;
  const workspaceCamera = resolvedLayoutKey
    ? cameraState(workspaceLayout.layoutViews[resolvedLayoutKey]?.camera_3d)
    : null;
  const savedView3d = panelCamera ?? workspaceCamera;

  const handleView3DChange = React.useCallback(
    (view: Camera3D) => {
      if (!resolvedLayoutKey) return;
      patchRuntimePanelState({ camera_layout_key: resolvedLayoutKey, camera_3d: view });
      void commandClient.setLayoutView(resolvedLayoutKey, view).catch((error) => {
        console.error("Failed to persist 3D scatter view:", error);
      });
    },
    [commandClient, patchRuntimePanelState, resolvedLayoutKey]
  );
  const handleSelectionChange = React.useCallback(
    (ids: Set<string>) => {
      void selection.setSelection(Array.from(ids)).catch((error) => {
        console.error("Failed to persist scatter selection:", error);
      });
    },
    [selection]
  );
  const handleLassoSelection = React.useCallback(
    (query: Parameters<typeof selection.selectLasso>[0]) => {
      void selection.selectLasso(query).catch((error) => {
        console.error("Lasso selection failed:", error);
      });
    },
    [selection]
  );

  const scatter = useHyperScatter({
    embeddings,
    labelsInfo,
    labelFilter: interaction.labelFilter,
    semanticLabelDisplayMode: labelOverlayMode,
    initialView3d: savedView3d,
    selectedIds,
    highlightedIds: interaction.highlightedIds,
    hoveredId: interaction.hoveredId,
    onSelectionChange: handleSelectionChange,
    onLassoSelection: handleLassoSelection,
    onHoverChange: interaction.setHoveredId,
    onView3DChange: handleView3DChange,
  });

  const focusLayout = React.useCallback(() => {
    if (params.pinnedLayout || !resolvedLayoutKey || workspaceLayout.activeLayoutKey === resolvedLayoutKey) return;
    void commandClient.setActiveLayout(resolvedLayoutKey).catch((error) => {
      console.error("Failed to activate scatter layout:", error);
    });
  }, [commandClient, params.pinnedLayout, resolvedLayoutKey, workspaceLayout.activeLayoutKey]);

  const queryError = layoutsQuery.error ?? embeddingsQuery.error;
  const loadingLabel = queryError
    ? `Failed to load embeddings: ${queryError}`
    : resolvedLayoutKey
      ? "Loading embeddings..."
      : `No ${layoutDimension}D embeddings layout available`;

  return (
    <Panel className="h-full">
      <PanelToolbar items={toolbarItems} actions={toolbarActions} />
      <div className="flex min-h-0 flex-1">
        <div ref={scatter.containerRef} className="relative min-w-0 flex-1">
          <canvas
            ref={scatter.canvasRef}
            className="absolute inset-0"
            style={{ zIndex: 1 }}
            onPointerDown={(event) => {
              focusLayout();
              scatter.handlePointerDown(event);
            }}
            onPointerMove={scatter.handlePointerMove}
            onPointerUp={scatter.handlePointerUp}
            onPointerCancel={scatter.handlePointerUp}
            onPointerLeave={scatter.handlePointerLeave}
            onDoubleClick={scatter.handleDoubleClick}
            onPointerEnter={focusLayout}
          />
          <canvas
            ref={scatter.overlayCanvasRef}
            className="pointer-events-none absolute inset-0"
            style={{ zIndex: 20 }}
          />
          {scatter.rendererError ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/85 p-6">
              <div className="max-w-md text-center">
                <div className="mb-2 text-sm font-semibold text-foreground">Browser not supported</div>
                <div className="text-sm text-muted-foreground">{scatter.rendererError}</div>
              </div>
            </div>
          ) : !embeddings ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/80">
              <div className="text-muted-foreground">{loadingLabel}</div>
            </div>
          ) : null}
        </div>
      </div>
    </Panel>
  );
});

ScatterPanel.displayName = "ScatterPanel";
