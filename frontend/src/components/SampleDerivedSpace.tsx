"use client";

import { AlertCircle, Loader2 } from "lucide-react";

import { getDistanceMetricLabel } from "@/lib/similarity";
import { cn } from "@/lib/utils";
import { useStore } from "@/store/useStore";
import type { Sample } from "@/types";

import { SampleGridView } from "./SampleGridView";
import { SampleTile } from "./SampleTile";

interface SampleDerivedSpaceProps {
  selectionSamples: Sample[];
  neighborSamples: Sample[];
  neighborsMetric: string | null;
  neighborsLoading: boolean;
  hasMoreNeighbors: boolean;
  loadMoreNeighbors?: () => void;
  neighborsError: string | null;
  neighborsScrollResetKey: string;
}

const ANCHOR_TILE_HEIGHT = 180;
const ANCHOR_TILE_MIN_WIDTH = 180;
const ANCHOR_TILE_MAX_WIDTH = 500;

function getAnchorTileWidth(sample: Sample): number {
  if (!sample.width || !sample.height || sample.height <= 0) {
    return ANCHOR_TILE_HEIGHT;
  }

  const width = Math.round((sample.width / sample.height) * ANCHOR_TILE_HEIGHT);
  return Math.max(ANCHOR_TILE_MIN_WIDTH, Math.min(ANCHOR_TILE_MAX_WIDTH, width));
}

export function SampleDerivedSpace({
  selectionSamples,
  neighborSamples,
  neighborsMetric,
  neighborsLoading,
  hasMoreNeighbors,
  loadMoreNeighbors,
  neighborsError,
  neighborsScrollResetKey,
}: SampleDerivedSpaceProps) {
  const { hoveredId, selectedIds, setHoveredId } = useStore();

  const showNeighbors =
    neighborSamples.length > 0 || neighborsLoading || neighborsError !== null;
  const distanceMetricLabel = getDistanceMetricLabel(neighborsMetric);

  return (
    <div className="flex flex-1 min-h-0 flex-col">
      <div className="shrink-0">
        <div className="flex flex-wrap gap-0.5">
          {selectionSamples.map((sample) => (
            <button
              key={sample.id}
              type="button"
              className="shrink-0"
              style={{ width: getAnchorTileWidth(sample) }}
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
          <div className="h-6 min-h-[24px] border-y border-border bg-secondary/20 px-2 flex items-center">
            <span className="text-[11px] leading-4 text-muted-foreground">
              Nearest neighbors{distanceMetricLabel ? ` · ${distanceMetricLabel}` : ""}
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
