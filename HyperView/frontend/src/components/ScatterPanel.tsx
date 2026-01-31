"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useStore } from "@/store/useStore";
import { Panel } from "./Panel";
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
    if (!datasetInfo) return layoutKey ?? null;

    if (layoutKey) {
      const exists = datasetInfo.layouts.some((layout) => layout.layout_key === layoutKey);
      if (exists) return layoutKey;
    }

    const layout = findLayoutByGeometry(datasetInfo.layouts, resolvedGeometry);
    return layout?.layout_key ?? datasetInfo.layouts[0]?.layout_key ?? null;
  }, [datasetInfo, layoutKey, resolvedGeometry]);

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
