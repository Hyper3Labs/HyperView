"use client";

import React from "react";
import { Focus, Settings2 } from "lucide-react";

import { Panel } from "@/components/Panel";
import {
  PanelToolbar,
  PanelToolbarIconButton,
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
  useSupportsLassoSelection,
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

export const ScatterPanel = React.memo(function ScatterPanel() {
  const panelState = usePanelState();
  const params = panelState.props as ScatterPanelParams;
  const datasetInfo = useDatasetInfo();
  const layoutsQuery = useQuery("layouts");
  const selection = useSelection();
  const interaction = usePanelInteractions();
  const workspaceLayout = useActiveLayout();
  const commandClient = useCommandClient();

  const layoutDimension = params.layoutDimension === 3 ? 3 : 2;
  const lassoEnabled = useSupportsLassoSelection(layoutDimension);
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
    () => {
      const candidates = layouts.filter(
        (layout) => getLayoutDimension(layout.layout_key) === layoutDimension
      );
      if (!params.pinnedLayout || !params.layoutKey) return candidates;
      return candidates.filter((layout) => layout.layout_key === params.layoutKey);
    },
    [layoutDimension, layouts, params.layoutKey, params.pinnedLayout]
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
      // Detached renderer adapters have no runtime panel state to persist.
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
        disabled: params.pinnedLayout || modelOptions.length === 0,
      },
    ],
    [handleModelChange, modelOptions, params.pinnedLayout, selectedModelLabel, selectedSpaceKey]
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
  const hoveredSample = React.useMemo(() => {
    if (!embeddings || !interaction.hoveredId) return null;
    const index = embeddings.ids.indexOf(interaction.hoveredId);
    if (index < 0) return null;
    return {
      id: interaction.hoveredId,
      label: embeddings.labels[index] ?? "Unlabelled",
    };
  }, [embeddings, interaction.hoveredId]);
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
    lassoEnabled,
    focusRequest: interaction.focusRequest,
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

  const { rendererError, resetView } = scatter;
  const scatterControlsDisabled = !embeddings || !!rendererError;

  const toolbarActions = React.useMemo(
    () => (
      <div className="flex items-center gap-0.5">
        <PanelToolbarIconButton
          title="Fit / reset view"
          aria-label="Fit and reset view"
          disabled={scatterControlsDisabled}
          onClick={resetView}
        >
          <Focus className="h-3.5 w-3.5" />
        </PanelToolbarIconButton>
        <div className="mx-0.5 h-4 w-px bg-border" aria-hidden />
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
          {labelsInfo && labelsInfo.uniqueLabels.length > 0 ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Label legend</DropdownMenuLabel>
              <div className="max-h-48 space-y-1 overflow-y-auto px-2 pb-1">
                {labelsInfo.uniqueLabels.map((label, index) => (
                  <div key={label} className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: labelsInfo.palette[index] }}
                      aria-hidden="true"
                    />
                    <span className="truncate" title={label}>{label}</span>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </PanelToolbarMenu>
      </div>
    ),
    [
      handleProjectionMethodChange,
      interaction,
      labelsInfo,
      labelOverlayMode,
      layoutDimension,
      patchRuntimePanelState,
      projectionMethodOptions,
      resetView,
      scatterControlsDisabled,
      selectedProjectionMethod,
    ]
  );

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
            style={{
              zIndex: 1,
              cursor: "grab",
            }}
            aria-label="Embedding scatter plot. Drag to pan, scroll to zoom, and Shift-drag to lasso select."
            title="Drag to pan · Scroll to zoom · Shift-drag to select"
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
            aria-hidden="true"
            style={{ zIndex: 20, pointerEvents: "none" }}
          />
          {selectedIds.size > 0 ? (
            <div className="pointer-events-none absolute right-2 top-2 z-30 rounded border border-border bg-card/90 px-2 py-1 text-[10px] font-medium text-foreground shadow-sm backdrop-blur-sm">
              {selectedIds.size.toLocaleString()} selected
            </div>
          ) : null}
          {hoveredSample ? (
            <div className="pointer-events-none absolute bottom-2 left-2 z-30 max-w-[min(360px,calc(100%-1rem))] rounded border border-border bg-card/90 px-2 py-1 shadow-sm backdrop-blur-sm">
              <div className="truncate text-[11px] font-medium text-foreground">{hoveredSample.label}</div>
              <div className="truncate font-mono text-[9px] text-muted-foreground">{hoveredSample.id}</div>
            </div>
          ) : null}
          {rendererError ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-card/85 p-6">
              <div className="max-w-md text-center">
                <div className="mb-2 text-sm font-semibold text-foreground">Browser not supported</div>
                <div className="text-sm text-muted-foreground">{rendererError}</div>
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
