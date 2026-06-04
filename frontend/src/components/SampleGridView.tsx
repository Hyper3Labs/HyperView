"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import justifiedLayout from "justified-layout";

import { formatDistanceValue, getDistanceMetricLabel } from "@/lib/similarity";
import { cn } from "@/lib/utils";
import { useStore } from "@/store/useStore";
import type { Sample } from "@/types";

import { SampleTile } from "./SampleTile";

interface SampleGridViewProps {
  samples: Sample[];
  onLoadMore?: () => void;
  hasMore?: boolean;
  scrollResetKey?: string;
  className?: string;
  showRankSimilarityBadge?: boolean;
  distanceMetric?: string | null;
}

const BOX_SPACING = 2;
const DEFAULT_ASPECT_RATIO = 1;
const MIN_LAYOUT_ASPECT_RATIO = 0.25;
const MAX_LAYOUT_ASPECT_RATIO = 4;

function getTargetRowHeight(size: "small" | "medium" | "large"): number {
  if (size === "small") return 100;
  if (size === "large") return 260;
  return 180;
}

function getLayoutAspectRatio(sample: Sample): number {
  if (sample.width && sample.height && sample.height > 0) {
    const aspectRatio = sample.width / sample.height;
    return Math.min(MAX_LAYOUT_ASPECT_RATIO, Math.max(MIN_LAYOUT_ASPECT_RATIO, aspectRatio));
  }
  return DEFAULT_ASPECT_RATIO;
}

function computeLayout(
  samples: Sample[],
  containerWidth: number,
  targetRowHeight: number
): { boxes: Array<{ width: number; height: number; top: number; left: number }>; containerHeight: number } {
  if (samples.length === 0 || containerWidth <= 0) {
    return { boxes: [], containerHeight: 0 };
  }

  const aspectRatios = samples.map(getLayoutAspectRatio);

  const geometry = justifiedLayout(aspectRatios, {
    containerWidth,
    containerPadding: 0,
    boxSpacing: BOX_SPACING,
    targetRowHeight,
    targetRowHeightTolerance: 0.25,
    showWidows: true,
  });

  return {
    boxes: geometry.boxes,
    containerHeight: geometry.containerHeight,
  };
}

interface RowData {
  startIndex: number;
  endIndex: number;
  top: number;
  height: number;
}

function groupIntoRows(
  boxes: Array<{ width: number; height: number; top: number; left: number }>
): RowData[] {
  if (boxes.length === 0) return [];

  const rows: RowData[] = [];
  let currentRowTop = boxes[0].top;
  let currentRowStart = 0;
  let currentRowHeight = boxes[0].height;

  for (let i = 1; i < boxes.length; i++) {
    const box = boxes[i];
    if (Math.abs(box.top - currentRowTop) > 1) {
      rows.push({
        startIndex: currentRowStart,
        endIndex: i,
        top: currentRowTop,
        height: currentRowHeight,
      });
      currentRowStart = i;
      currentRowTop = box.top;
      currentRowHeight = box.height;
    } else {
      currentRowHeight = Math.max(currentRowHeight, box.height);
    }
  }

  rows.push({
    startIndex: currentRowStart,
    endIndex: boxes.length,
    top: currentRowTop,
    height: currentRowHeight,
  });

  return rows;
}

export function SampleGridView({
  samples,
  onLoadMore,
  hasMore,
  scrollResetKey,
  className,
  showRankSimilarityBadge = false,
  distanceMetric = null,
}: SampleGridViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  const {
    selectedIds,
    isLassoSelection,
    selectionSource,
    toggleSelection,
    addToSelection,
    setHoveredId,
    hoveredId,
    sampleGridSize,
  } = useStore();

  const targetRowHeight = useMemo(() => getTargetRowHeight(sampleGridSize), [sampleGridSize]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const updateWidth = () => {
      const width = container.clientWidth;
      if (width > 0 && width !== containerWidth) {
        setContainerWidth(width);
      }
    };

    updateWidth();

    const resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(updateWidth);
    });
    resizeObserver.observe(container);

    return () => resizeObserver.disconnect();
  }, [containerWidth]);

  const { boxes, containerHeight } = useMemo(
    () => computeLayout(samples, containerWidth, targetRowHeight),
    [samples, containerWidth, targetRowHeight]
  );

  const rows = useMemo(() => groupIntoRows(boxes), [boxes]);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: (index) => rows[index]?.height ?? targetRowHeight,
    overscan: 3,
    getItemKey: (index) => {
      const row = rows[index];
      if (!row) return `row-${index}`;
      return samples.slice(row.startIndex, row.endIndex).map((sample) => sample.id).join("-") || `row-${index}`;
    },
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !onLoadMore || !hasMore) return;

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = container;
      if (scrollHeight - scrollTop - clientHeight < 500) {
        onLoadMore();
      }
    };

    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, [onLoadMore, hasMore]);

  useEffect(() => {
    if (!scrollResetKey) return;
    containerRef.current?.scrollTo({ top: 0 });
  }, [scrollResetKey]);

  useEffect(() => {
    if (isLassoSelection) return;
    if (selectionSource !== "scatter") return;
    if (selectedIds.size === 0) return;

    try {
      virtualizer.scrollToIndex(0, { align: "start" });
    } catch {
      containerRef.current?.scrollTo({ top: 0 });
    }
  }, [isLassoSelection, selectedIds, selectionSource, virtualizer]);

  const handleClick = useCallback(
    (sample: Sample, event: React.MouseEvent) => {
      if (event.metaKey || event.ctrlKey) {
        toggleSelection(sample.id);
      } else if (event.shiftKey && selectedIds.size > 0) {
        const selectedArray = Array.from(selectedIds);
        const lastSelected = selectedArray[selectedArray.length - 1];
        const lastIndex = samples.findIndex((candidate) => candidate.id === lastSelected);
        const currentIndex = samples.findIndex((candidate) => candidate.id === sample.id);

        if (lastIndex !== -1 && currentIndex !== -1) {
          const start = Math.min(lastIndex, currentIndex);
          const end = Math.max(lastIndex, currentIndex);
          const rangeIds = samples.slice(start, end + 1).map((candidate) => candidate.id);
          addToSelection(rangeIds);
        }
      } else {
        useStore.getState().setSelectedIds(new Set([sample.id]), "grid");
      }
    },
    [addToSelection, samples, selectedIds, toggleSelection]
  );

  const virtualRows = virtualizer.getVirtualItems();

  return (
    <div
      className={cn("flex-1 min-h-0 min-w-0 w-full overflow-hidden", className)}
      data-testid="sample-grid-view"
    >
      <div ref={containerRef} className="panel-scroll h-full min-h-0 overflow-auto">
        <div
          style={{
            height: containerHeight || "100%",
            width: "100%",
            position: "relative",
          }}
        >
          {virtualRows.map((virtualRow) => {
            const row = rows[virtualRow.index];
            if (!row) return null;

            const rowSamples = samples.slice(row.startIndex, row.endIndex);
            const rowBoxes = boxes.slice(row.startIndex, row.endIndex);

            return (
              <div
                key={virtualRow.key}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: row.height,
                  transform: `translateY(${row.top}px)`,
                }}
              >
                {rowSamples.map((sample, index) => {
                  const box = rowBoxes[index];
                  if (!box) return null;

                  const isSelected = isLassoSelection ? true : selectedIds.has(sample.id);
                  const isHovered = hoveredId === sample.id;
                  const sampleIndex = row.startIndex + index;
                  const distance = (sample as { distance?: number }).distance;
                  const distanceLabel =
                    typeof distance === "number" ? formatDistanceValue(distance) : null;
                  const preciseDistanceLabel =
                    typeof distance === "number" ? formatDistanceValue(distance, 6) : null;
                  const distanceMetricLabel = getDistanceMetricLabel(distanceMetric) ?? "distance";
                  const metricBadge =
                    showRankSimilarityBadge && distanceLabel !== null
                      ? `#${sampleIndex + 1} · d ${distanceLabel}`
                      : null;
                  const metricBadgeTitle =
                    showRankSimilarityBadge && preciseDistanceLabel !== null
                      ? `Rank ${sampleIndex + 1}, ${distanceMetricLabel} ${preciseDistanceLabel}. Lower is closer.`
                      : undefined;

                  return (
                    <div
                      key={sample.id}
                      style={{
                        position: "absolute",
                        left: box.left,
                        top: 0,
                        width: box.width,
                        height: box.height,
                      }}
                    >
                      <SampleTile
                        sample={sample}
                        selected={isSelected}
                        hovered={isHovered}
                        metricBadge={metricBadge}
                        metricBadgeTitle={metricBadgeTitle}
                        className="h-full w-full cursor-pointer transition-shadow duration-150 ease-out"
                        onClick={(event) => handleClick(sample, event)}
                        onMouseEnter={() => setHoveredId(sample.id)}
                        onMouseLeave={() => setHoveredId(null)}
                      />
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
