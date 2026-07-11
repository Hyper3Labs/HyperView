"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import { getDistanceMetricLabel } from "@/lib/similarity";
import { cn } from "@/lib/utils";
import { useStore } from "@/store/useStore";
import type { Sample } from "@/types";

import { SampleGridView } from "./SampleGridView";
import { SampleTile } from "./SampleTile";
import { getSampleAspectRatio } from "./tiles/sampleTileKind";

interface SampleDerivedSpaceProps {
  selectionSamples: Sample[];
  neighborSamples: Sample[];
  neighborsMetric: string | null;
  neighborsSourceLabel: string | null;
  neighborsLoading: boolean;
  hasMoreNeighbors: boolean;
  loadMoreNeighbors?: () => void;
  neighborsError: string | null;
  neighborsScrollResetKey: string;
  neighborsTitle?: string;
}

const ANCHOR_TILE_HEIGHT = 180;
const ANCHOR_TILE_MIN_WIDTH = 180;
const ANCHOR_TILE_MAX_WIDTH = 500;

function getAnchorTileWidth(sample: Sample): number {
  const width = Math.round(getSampleAspectRatio(sample) * ANCHOR_TILE_HEIGHT);
  return Math.max(ANCHOR_TILE_MIN_WIDTH, Math.min(ANCHOR_TILE_MAX_WIDTH, width));
}

export function SampleDerivedSpace({
  selectionSamples,
  neighborSamples,
  neighborsMetric,
  neighborsSourceLabel,
  neighborsLoading,
  hasMoreNeighbors,
  loadMoreNeighbors,
  neighborsError,
  neighborsScrollResetKey,
  neighborsTitle = "Nearest neighbors",
}: SampleDerivedSpaceProps) {
  const { hoveredId, selectedIds, setHoveredId } = useStore();

  const showNeighbors =
    neighborSamples.length > 0 || neighborsLoading || neighborsError !== null;
  const distanceMetricLabel = getDistanceMetricLabel(neighborsMetric);
  const neighborsLabel = [
    neighborsTitle,
    distanceMetricLabel,
    neighborsSourceLabel,
  ].filter(Boolean).join(" · ");

  if (selectionSamples.length > 1 && !showNeighbors) {
    return (
      <div className="flex min-h-0 flex-1">
        <SampleGridView
          samples={selectionSamples}
          scrollResetKey={neighborsScrollResetKey}
          className="w-full"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="shrink-0">
        <div className="flex flex-wrap gap-0.5">
          {selectionSamples.map((sample) => (
            <button
              key={sample.id}
              type="button"
              className="shrink-0"
              style={{ width: getAnchorTileWidth(sample), maxWidth: "100%" }}
              onClick={() => useStore.getState().setSelectedIds(new Set([sample.id]), "grid")}
            >
              <SampleTile
                sample={sample}
                selected={selectedIds.has(sample.id)}
                hovered={hoveredId === sample.id}
                className="h-[180px] w-full transition-shadow duration-150"
                onMouseEnter={() => setHoveredId(sample.id)}
                onMouseLeave={() => setHoveredId(null)}
              />
            </button>
          ))}
        </div>
      </div>

      {showNeighbors && (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex h-6 min-h-[24px] min-w-0 items-center overflow-hidden border-y border-border bg-secondary/20 px-2">
            <span className="min-w-0 truncate text-[11px] leading-4 text-muted-foreground" title={neighborsLabel}>
              {neighborsLabel}
            </span>
          </div>
          <div className="flex min-h-0 flex-1 w-full overflow-hidden">
            {neighborSamples.length > 0 ? (
              <SampleGridView
                samples={neighborSamples}
                onLoadMore={loadMoreNeighbors}
                hasMore={hasMoreNeighbors}
                scrollResetKey={neighborsScrollResetKey}
                className="w-full"
                showRankSimilarityBadge
                distanceMetric={neighborsMetric}
              />
            ) : neighborsLoading ? (
              <div className="flex flex-1 items-center justify-center text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center gap-2 px-2 text-sm text-muted-foreground">
                <AlertCircle className="h-4 w-4" />
                <span className={cn("truncate")}>{neighborsError ?? "Nearest samples unavailable"}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
