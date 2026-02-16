"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Settings2 } from "lucide-react";
import { useStore } from "@/store/useStore";
import { Panel } from "./Panel";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  PanelContextBar,
  type PanelContextItem,
  type PanelContextOption,
} from "./PanelContextBar";
import { useHyperScatter } from "./useHyperScatter";
import { useLabelLegend } from "./useLabelLegend";
import type { Geometry } from "@/types";
import { findLayoutByGeometry, listAvailableGeometries } from "@/lib/layouts";
import { fetchEmbeddings } from "@/lib/api";

interface ScatterPanelProps {
  className?: string;
  layoutKey?: string;
  geometry?: Geometry;
}

export function ScatterPanel({
  className = "",
  layoutKey,
  geometry,
}: ScatterPanelProps) {
  const {
    datasetInfo,
    embeddingsByLayoutKey,
    setEmbeddingsForLayout,
    selectedIds,
    setSelectedIds,
    beginLassoSelection,
    hoveredId,
    setHoveredId,
    setActiveLayoutKey,
    labelFilter,
  } = useStore();

  const [localGeometry, setLocalGeometry] = useState<Geometry>("euclidean");
  const [localLayoutKey, setLocalLayoutKey] = useState<string | null>(null);

  // Check which geometries are available
  const availableGeometries = useMemo(() => {
    return listAvailableGeometries(datasetInfo?.layouts ?? []);
  }, [datasetInfo?.layouts]);

  useEffect(() => {
    if (geometry) return;
    if (availableGeometries.length === 0) return;
    if (!availableGeometries.includes(localGeometry)) {
      setLocalGeometry(availableGeometries[0]);
    }
  }, [availableGeometries, geometry, localGeometry]);

  const resolvedGeometry = geometry ?? localGeometry;

  const resolvedLayoutKey = useMemo(() => {
    if (!datasetInfo) return localLayoutKey ?? layoutKey ?? null;

    if (localLayoutKey) {
      const exists = datasetInfo.layouts.some((layout) => layout.layout_key === localLayoutKey);
      if (exists) return localLayoutKey;
    }

    if (layoutKey) {
      const exists = datasetInfo.layouts.some((layout) => layout.layout_key === layoutKey);
      if (exists) return layoutKey;
    }

    const layout = findLayoutByGeometry(datasetInfo.layouts, resolvedGeometry);
    return layout?.layout_key ?? datasetInfo.layouts[0]?.layout_key ?? null;
  }, [datasetInfo, layoutKey, localLayoutKey, resolvedGeometry]);

  useEffect(() => {
    if (!datasetInfo || !localLayoutKey) return;
    const exists = datasetInfo.layouts.some((layout) => layout.layout_key === localLayoutKey);
    if (!exists) {
      setLocalLayoutKey(null);
    }
  }, [datasetInfo, localLayoutKey]);

  const resolvedLayout = useMemo(() => {
    if (!datasetInfo || !resolvedLayoutKey) return null;
    return datasetInfo.layouts.find((layout) => layout.layout_key === resolvedLayoutKey) ?? null;
  }, [datasetInfo, resolvedLayoutKey]);

  const resolvedSpace = useMemo(() => {
    if (!datasetInfo || !resolvedLayout) return null;
    return datasetInfo.spaces.find((space) => space.space_key === resolvedLayout.space_key) ?? null;
  }, [datasetInfo, resolvedLayout]);

  const geometryLayouts = useMemo(() => {
    if (!datasetInfo) return [];
    return datasetInfo.layouts.filter((layout) => layout.geometry === resolvedGeometry);
  }, [datasetInfo, resolvedGeometry]);

  const modelOptions = useMemo<PanelContextOption[]>(() => {
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

  const contextItems = useMemo<PanelContextItem[]>(() => {
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

  const projectionSettings = useMemo(
    () => (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            disabled={projectionMethodOptions.length === 0}
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground hover:bg-muted/40"
            title={
              selectedProjectionMethod
                ? `Projection method: ${selectedProjectionMethod}`
                : "Projection method"
            }
            aria-label="Projection method settings"
          >
            <Settings2 className="h-3.5 w-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[220px]">
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
        </DropdownMenuContent>
      </DropdownMenu>
    ),
    [
      handleProjectionMethodChange,
      projectionMethodOptions,
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
      .catch((err) => {
        if (cancelled) return;
        console.error("Failed to load embeddings:", err);
      })

    return () => {
      cancelled = true;
    };
  }, [embeddingsByLayoutKey, resolvedLayoutKey, setEmbeddingsForLayout]);

  const { labelsInfo } = useLabelLegend({ datasetInfo, embeddings, labelFilter });

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
    selectedIds,
    hoveredId,
    setSelectedIds,
    beginLassoSelection,
    setHoveredId,
    hoverEnabled: !labelFilter,
  });

  const focusLayout = useCallback(() => {
    if (!resolvedLayoutKey) return;
    setActiveLayoutKey(resolvedLayoutKey);
  }, [resolvedLayoutKey, setActiveLayoutKey]);

  const loadingLabel = resolvedLayoutKey
    ? "Loading embeddings..."
    : "No embeddings layout available";

  return (
    <Panel className={className}>
      <PanelContextBar items={contextItems} rightContent={projectionSettings} />

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

          {/* Lasso overlay (screen-space) */}
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
