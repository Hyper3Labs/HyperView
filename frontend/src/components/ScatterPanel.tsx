"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Settings2 } from "lucide-react";
import { useStore } from "@/store/useStore";
import { Panel } from "./Panel";
import {
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  PanelToolbar,
  PanelToolbarMenu,
  type PanelToolbarItem,
  type PanelToolbarOption,
} from "./PanelToolbar";
import { useHyperScatter } from "./useHyperScatter";
import { useLabelLegend } from "./useLabelLegend";
import type { Geometry } from "@/types";
import {
  findLayoutByGeometry,
  getLayoutDimension,
  listAvailableGeometries,
} from "@/lib/layouts";
import {
  fetchDataset,
  fetchEmbeddings,
  isLayoutNotFoundError,
} from "@/lib/api";

interface ScatterPanelProps {
  className?: string;
  layoutKey?: string;
  geometry?: Geometry;
  layoutDimension?: 2 | 3;
  pinnedLayout?: boolean;
}

export function ScatterPanel({
  className = "",
  layoutKey,
  geometry,
  layoutDimension = 2,
  pinnedLayout = false,
}: ScatterPanelProps) {
  const {
    datasetInfo,
    embeddingsByLayoutKey,
    neighborsResults,
    setEmbeddingsForLayout,
    selectedIds,
    setSelectedIds,
    beginLassoSelection,
    hoveredId,
    setHoveredId,
    setActiveLayoutKey,
    setDatasetInfo,
    labelFilter,
    requestedLayoutKey,
    scatterLabelOverlayMode,
    setScatterLabelOverlayMode,
  } = useStore();

  const highlightedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const sample of neighborsResults) {
      ids.add(sample.id);
    }
    return ids;
  }, [neighborsResults]);

  const [localGeometry, setLocalGeometry] = useState<Geometry>("euclidean");
  const [localLayoutKey, setLocalLayoutKey] = useState<string | null>(null);

  const renderableLayouts = useMemo(() => {
    return (datasetInfo?.layouts ?? []).filter(
      (layout) => getLayoutDimension(layout.layout_key) === layoutDimension
    );
  }, [datasetInfo?.layouts, layoutDimension]);

  // Check which geometries are available
  const availableGeometries = useMemo(() => {
    return listAvailableGeometries(renderableLayouts, layoutDimension);
  }, [layoutDimension, renderableLayouts]);

  useEffect(() => {
    if (geometry) return;
    if (availableGeometries.length === 0) return;
    if (!availableGeometries.includes(localGeometry)) {
      setLocalGeometry(availableGeometries[0]);
    }
  }, [availableGeometries, geometry, localGeometry]);

  const resolvedGeometry = geometry ?? localGeometry;

  useEffect(() => {
    if (pinnedLayout) return;
    if (!requestedLayoutKey) return;

    const requestedLayout = renderableLayouts.find(
      (layout) => layout.layout_key === requestedLayoutKey
    );
    if (!requestedLayout) return;

    if (requestedLayout.geometry !== resolvedGeometry) return;

    setLocalLayoutKey(requestedLayout.layout_key);
  }, [pinnedLayout, renderableLayouts, requestedLayoutKey, resolvedGeometry]);

  const resolvedLayoutKey = useMemo(() => {
    if (!datasetInfo) return localLayoutKey ?? layoutKey ?? null;

    if (localLayoutKey) {
      const exists = renderableLayouts.some((layout) => layout.layout_key === localLayoutKey);
      if (exists) return localLayoutKey;
    }

    if (layoutKey) {
      const exists = renderableLayouts.some((layout) => layout.layout_key === layoutKey);
      if (exists) return layoutKey;
    }

    const layout = findLayoutByGeometry(renderableLayouts, resolvedGeometry, layoutDimension);
    if (geometry) {
      return layout?.layout_key ?? null;
    }

    return layout?.layout_key ?? renderableLayouts[0]?.layout_key ?? null;
  }, [datasetInfo, geometry, layoutDimension, layoutKey, localLayoutKey, renderableLayouts, resolvedGeometry]);

  useEffect(() => {
    if (!datasetInfo || !localLayoutKey) return;
    const exists = renderableLayouts.some((layout) => layout.layout_key === localLayoutKey);
    if (!exists) {
      setLocalLayoutKey(null);
    }
  }, [datasetInfo, localLayoutKey, renderableLayouts]);

  const resolvedLayout = useMemo(() => {
    if (!datasetInfo || !resolvedLayoutKey) return null;
    return renderableLayouts.find((layout) => layout.layout_key === resolvedLayoutKey) ?? null;
  }, [datasetInfo, renderableLayouts, resolvedLayoutKey]);

  const resolvedSpace = useMemo(() => {
    if (!datasetInfo || !resolvedLayout) return null;
    return datasetInfo.spaces.find((space) => space.space_key === resolvedLayout.space_key) ?? null;
  }, [datasetInfo, resolvedLayout]);

  const geometryLayouts = useMemo(() => {
    return renderableLayouts.filter((layout) => layout.geometry === resolvedGeometry);
  }, [renderableLayouts, resolvedGeometry]);

  const modelOptions = useMemo<PanelToolbarOption[]>(() => {
    if (!datasetInfo || geometryLayouts.length === 0) return [];

    const seenSpaceKeys = new Set<string>();

    return geometryLayouts.flatMap((layout) => {
      if (seenSpaceKeys.has(layout.space_key)) return [];
      seenSpaceKeys.add(layout.space_key);

      const space = datasetInfo.spaces.find((candidate) => candidate.space_key === layout.space_key);

      return [
        {
          value: layout.space_key,
          label: space?.model_id ?? layout.space_key,
          group: space?.provider,
        },
      ];
    });
  }, [datasetInfo, geometryLayouts]);

  const selectedSpaceKey = resolvedLayout?.space_key ?? modelOptions[0]?.value ?? "";

  const selectedProjectionMethod = resolvedLayout?.method ?? "";

  const selectedModelLabel =
    modelOptions.find((option) => option.value === selectedSpaceKey)?.label ??
    resolvedSpace?.model_id ??
    "";

  const projectionMethodOptions = useMemo(() => {
    const methodsForSelectedModel = geometryLayouts
      .filter((layout) => layout.space_key === selectedSpaceKey)
      .map((layout) => layout.method);

    const sourceMethods =
      methodsForSelectedModel.length > 0
        ? methodsForSelectedModel
        : geometryLayouts.map((layout) => layout.method);

    return Array.from(new Set(sourceMethods)).sort();
  }, [geometryLayouts, selectedSpaceKey]);

  const handleModelChange = useCallback(
    (nextSpaceKey: string) => {
      if (!nextSpaceKey || geometryLayouts.length === 0) return;

      const targetLayout =
        geometryLayouts.find(
          (layout) =>
            layout.space_key === nextSpaceKey && layout.method === selectedProjectionMethod
        ) ?? geometryLayouts.find((layout) => layout.space_key === nextSpaceKey);

      if (targetLayout) {
        setLocalLayoutKey(targetLayout.layout_key);
      }
    },
    [geometryLayouts, selectedProjectionMethod]
  );

  const handleProjectionMethodChange = useCallback(
    (nextMethod: string) => {
      if (!nextMethod || geometryLayouts.length === 0) return;

      const targetLayout =
        geometryLayouts.find(
          (layout) =>
            layout.method === nextMethod &&
            layout.space_key === selectedSpaceKey
        ) ?? geometryLayouts.find((layout) => layout.method === nextMethod);

      if (targetLayout) {
        setLocalLayoutKey(targetLayout.layout_key);
      }
    },
    [geometryLayouts, selectedSpaceKey]
  );

  const toolbarItems = useMemo<PanelToolbarItem[]>(() => {
    return [
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
    ];
  }, [handleModelChange, modelOptions, selectedModelLabel, selectedSpaceKey]);

  const toolbarActions = useMemo(
    () => (
      <PanelToolbarMenu
        icon={<Settings2 className="h-3.5 w-3.5" />}
        label="Scatter settings"
        title={
          selectedProjectionMethod
            ? `Projection method: ${selectedProjectionMethod}`
            : "Scatter settings"
        }
        disabled={false}
        contentClassName="min-w-[220px]"
      >
          <DropdownMenuLabel>
            Projection method
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          {projectionMethodOptions.length > 0 ? (
            <DropdownMenuRadioGroup
              value={selectedProjectionMethod}
              onValueChange={handleProjectionMethodChange}
            >
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
          {layoutDimension === 2 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>
                Topic labels
              </DropdownMenuLabel>
              <DropdownMenuRadioGroup
                value={scatterLabelOverlayMode}
                onValueChange={(value) =>
                  setScatterLabelOverlayMode(value as "off" | "auto" | "coarse" | "fine")
                }
              >
                <DropdownMenuRadioItem value="off">
                  <span className="truncate">Hidden</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="auto">
                  <span className="truncate">Auto</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="coarse">
                  <span className="truncate">Coarse</span>
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="fine">
                  <span className="truncate">Fine</span>
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </>
          )}
      </PanelToolbarMenu>
    ),
    [
      handleProjectionMethodChange,
      layoutDimension,
      projectionMethodOptions,
      scatterLabelOverlayMode,
      setScatterLabelOverlayMode,
      selectedProjectionMethod,
    ]
  );

  const embeddings = resolvedLayoutKey ? embeddingsByLayoutKey[resolvedLayoutKey] ?? null : null;

  useEffect(() => {
    if (!resolvedLayoutKey) return;
    setActiveLayoutKey(resolvedLayoutKey);
  }, [resolvedLayoutKey, setActiveLayoutKey]);

  useEffect(() => {
    if (!resolvedLayoutKey) return;
    if (embeddingsByLayoutKey[resolvedLayoutKey]) return;

    let cancelled = false;

    fetchEmbeddings(resolvedLayoutKey)
      .then((data) => {
        if (cancelled) return;
        setEmbeddingsForLayout(resolvedLayoutKey, data);
      })
      .catch(async (err) => {
        if (cancelled) return;

        if (isLayoutNotFoundError(err)) {
          // The dock layout can reference stale layout keys after backend/session changes.
          // Refresh metadata and let resolvedLayoutKey fall back to currently available layouts.
          if (localLayoutKey === resolvedLayoutKey) {
            setLocalLayoutKey(null);
          }
          setActiveLayoutKey(null);

          try {
            const dataset = await fetchDataset();
            if (cancelled) return;
            setDatasetInfo(dataset);
          } catch (refreshErr) {
            if (cancelled) return;
            console.error("Failed to refresh dataset metadata after stale layout key:", refreshErr);
          }
          return;
        }

        console.error("Failed to load embeddings:", err);
      })

    return () => {
      cancelled = true;
    };
  }, [
    embeddingsByLayoutKey,
    localLayoutKey,
    resolvedLayoutKey,
    setActiveLayoutKey,
    setDatasetInfo,
    setEmbeddingsForLayout,
  ]);

  const { labelsInfo } = useLabelLegend({ datasetInfo, embeddings });

  const {
    canvasRef,
    overlayCanvasRef,
    containerRef,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerLeave,
    handleDoubleClick,
    rendererError,
  } = useHyperScatter({
    embeddings,
    labelsInfo,
    labelFilter,
    semanticLabelDisplayMode: scatterLabelOverlayMode,
    selectedIds,
    highlightedIds,
    hoveredId,
    setSelectedIds,
    beginLassoSelection,
    setHoveredId,
  });

  const focusLayout = useCallback(() => {
    if (!resolvedLayoutKey) return;
    setActiveLayoutKey(resolvedLayoutKey);
  }, [resolvedLayoutKey, setActiveLayoutKey]);

  const loadingLabel = resolvedLayoutKey
    ? "Loading embeddings..."
    : `No ${layoutDimension}D embeddings layout available`;

  return (
    <Panel className={className}>
      <PanelToolbar items={toolbarItems} actions={toolbarActions} />

      {/* Main content area - min-h-0 prevents flex overflow */}
      <div className="flex-1 flex min-h-0">
        {/* Canvas container */}
        <div ref={containerRef} className="flex-1 relative min-w-0">
          <canvas
            ref={canvasRef}
            className="absolute inset-0"
            style={{ zIndex: 1 }}
            onPointerDown={(e) => {
              focusLayout();
              handlePointerDown(e);
            }}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onPointerLeave={handlePointerLeave}
            onDoubleClick={handleDoubleClick}
            onPointerEnter={focusLayout}
          />

          <canvas
            ref={overlayCanvasRef}
            className="absolute inset-0 pointer-events-none"
            style={{ zIndex: 20 }}
          />

          {/* Loading overlay */}
          {rendererError ? (
            <div className="absolute inset-0 flex items-center justify-center bg-card/85 z-10 p-6">
              <div className="max-w-md text-center">
                <div className="text-sm font-semibold text-foreground mb-2">Browser not supported</div>
                <div className="text-sm text-muted-foreground">{rendererError}</div>
              </div>
            </div>
          ) : (
            !embeddings && (
              <div className="absolute inset-0 flex items-center justify-center bg-card/80 z-10">
                <div className="text-muted-foreground">{loadingLabel}</div>
              </div>
            )
          )}
        </div>

      </div>
    </Panel>
  );
}
