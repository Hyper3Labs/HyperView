"use client";

import { useMemo } from "react";
import { useStore } from "@/store/useStore";
import { Panel, PanelFooter } from "./Panel";
import { PanelHeader } from "./PanelHeader";
import { ScatterIcon } from "./icons";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type ScatterLabelsInfo, useHyperScatter } from "./useHyperScatter";

interface ScatterPanelProps {
  className?: string;
}

export function ScatterPanel({ className = "" }: ScatterPanelProps) {
  const {
    embeddings,
    viewMode,
    setViewMode,
    selectedIds,
    setSelectedIds,
    beginLassoSelection,
    hoveredId,
    setHoveredId,
  } = useStore();

  const labelsInfo = useMemo<ScatterLabelsInfo | null>(() => {
    if (!embeddings) return null;

    // Stable label order for palette and legend.
    const uniqueLabels = [...new Set(embeddings.labels.map((l) => l || "undefined"))];

    const labelToCategory: Record<string, number> = {};
    for (let i = 0; i < uniqueLabels.length; i++) {
      labelToCategory[uniqueLabels[i]] = i;
    }

    const categories = new Uint16Array(embeddings.labels.length);
    for (let i = 0; i < embeddings.labels.length; i++) {
      const key = embeddings.labels[i] || "undefined";
      categories[i] = labelToCategory[key] ?? 0;
    }

    const palette = uniqueLabels.map((label) => {
      if (label === "undefined") return "#008080";
      return embeddings.label_colors[label] || "#808080";
    });

    return { uniqueLabels, categories, palette };
  }, [embeddings]);

  const {
    canvasRef,
    overlayCanvasRef,
    containerRef,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    handlePointerLeave,
    handleDoubleClick,
  } = useHyperScatter({
    embeddings,
    viewMode,
    labelsInfo,
    selectedIds,
    hoveredId,
    setSelectedIds,
    beginLassoSelection,
    setHoveredId,
  });

  const uniqueLabels = labelsInfo?.uniqueLabels ?? [];

  return (
    <Panel className={className}>
      <PanelHeader
        icon={<ScatterIcon />}
        title="Embeddings"
        subtitle={embeddings ? `${embeddings.ids.length} points` : "Loading..."}
      >
        {/* View mode toggle using shadcn ToggleGroup */}
        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(val) => val && setViewMode(val as "euclidean" | "hyperbolic")}
          variant="outline"
          size="sm"
          className="h-6"
        >
          <ToggleGroupItem value="euclidean" className="text-[11px] px-2.5 h-6">
            Euclidean
          </ToggleGroupItem>
          <ToggleGroupItem value="hyperbolic" className="text-[11px] px-2.5 h-6">
            Hyperbolic
          </ToggleGroupItem>
        </ToggleGroup>
      </PanelHeader>

      {/* Main content area */}
      <div className="flex-1 flex">
        {/* Canvas container */}
        <div ref={containerRef} className="flex-1 relative">
          <canvas
            ref={canvasRef}
            className="absolute inset-0"
            style={{ zIndex: 1 }}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onPointerLeave={handlePointerLeave}
            onDoubleClick={handleDoubleClick}
          />

          {/* Lasso overlay (screen-space) */}
          <canvas
            ref={overlayCanvasRef}
            className="absolute inset-0 pointer-events-none"
            style={{ zIndex: 20 }}
          />

          {/* Loading overlay */}
          {!embeddings && (
            <div className="absolute inset-0 flex items-center justify-center bg-card/80 z-10">
              <div className="text-muted-foreground">Loading embeddings...</div>
            </div>
          )}
        </div>

        {/* Legend */}
        {uniqueLabels.length > 0 && (
          <div className="w-36 border-l border-border bg-card p-2 overflow-y-auto">
            <div className="text-[11px] font-medium mb-2 text-muted-foreground uppercase tracking-wide">Labels</div>
            <div className="space-y-1">
              {uniqueLabels.slice(0, 20).map((label) => (
                <div key={label} className="flex items-center gap-2">
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{
                      backgroundColor: label === "undefined" ? "hsl(var(--accent-cyan))" : (embeddings?.label_colors[label] || "hsl(var(--muted-foreground))"),
                    }}
                  />
                  <span className="text-[11px] text-muted-foreground truncate font-mono" title={label}>
                    {label}
                  </span>
                </div>
              ))}
              {uniqueLabels.length > 20 && (
                <div className="text-[11px] text-muted-foreground/70">+{uniqueLabels.length - 20} more</div>
              )}
            </div>
          </div>
        )}
      </div>

      <PanelFooter>
        <span>⇧+drag lasso • scroll zoom • drag pan</span>
      </PanelFooter>
    </Panel>
  );
}
