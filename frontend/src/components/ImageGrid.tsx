"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import justifiedLayout from "justified-layout";
import { useStore } from "@/store/useStore";
import { Panel } from "./Panel";
import { CheckIcon } from "./icons";
import type { Sample } from "@/types";

interface ImageGridProps {
  samples: Sample[];
  onLoadMore?: () => void;
  hasMore?: boolean;
}

// Justified layout config
const BOX_SPACING = 2; // Tight spacing between images
const TARGET_ROW_HEIGHT = 180; // Target height for rows
const DEFAULT_ASPECT_RATIO = 1; // Fallback for samples without dimensions

/**
 * Get aspect ratio from sample, with fallback
 */
function getAspectRatio(sample: Sample): number {
  if (sample.width && sample.height && sample.height > 0) {
    return sample.width / sample.height;
  }
  return DEFAULT_ASPECT_RATIO;
}

/**
 * Compute justified layout geometry for samples
 */
function computeLayout(
  samples: Sample[],
  containerWidth: number
): { boxes: Array<{ width: number; height: number; top: number; left: number }>; containerHeight: number } {
  if (samples.length === 0 || containerWidth <= 0) {
    return { boxes: [], containerHeight: 0 };
  }

  const aspectRatios = samples.map(getAspectRatio);

  const geometry = justifiedLayout(aspectRatios, {
    containerWidth,
    containerPadding: 0,
    boxSpacing: BOX_SPACING,
    targetRowHeight: TARGET_ROW_HEIGHT,
    targetRowHeightTolerance: 0.25,
    showWidows: true, // Always show last row even if incomplete
  });

  return {
    boxes: geometry.boxes,
    containerHeight: geometry.containerHeight,
  };
}

/**
 * Group boxes into rows for virtualization
 */
interface RowData {
  startIndex: number;
  endIndex: number; // exclusive
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
    // New row if top position changes significantly
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
      // Same row - take max height in case of slight variations
      currentRowHeight = Math.max(currentRowHeight, box.height);
    }
  }

  // Push final row
  rows.push({
    startIndex: currentRowStart,
    endIndex: boxes.length,
    top: currentRowTop,
    height: currentRowHeight,
  });

  return rows;
}

export function ImageGrid({ samples, onLoadMore, hasMore }: ImageGridProps) {
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
    labelFilter,
  } = useStore();

  // Track container width for layout computation
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

  // Compute justified layout
  const { boxes, containerHeight } = useMemo(
    () => computeLayout(samples, containerWidth),
    [samples, containerWidth]
  );

  // Group into rows for virtualization
  const rows = useMemo(() => groupIntoRows(boxes), [boxes]);

  // Virtualizer for rows
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => containerRef.current,
    estimateSize: (index) => rows[index]?.height ?? TARGET_ROW_HEIGHT,
    overscan: 3,
    getItemKey: (index) => {
      const row = rows[index];
      if (!row) return `row-${index}`;
      // Create stable key from sample IDs in this row
      const rowSamples = samples.slice(row.startIndex, row.endIndex);
      return rowSamples.map((s) => s.id).join("-") || `row-${index}`;
    },
  });

  // Load more when scrolling near bottom
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

  // Reset scroll on filter change
  useEffect(() => {
    containerRef.current?.scrollTo({ top: 0 });
  }, [labelFilter]);

  // Scroll to top when scatter selection made
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

  // Handle click with selection logic
  const handleClick = useCallback(
    (sample: Sample, event: React.MouseEvent) => {
      if (event.metaKey || event.ctrlKey) {
        toggleSelection(sample.id);
      } else if (event.shiftKey && selectedIds.size > 0) {
        const selectedArray = Array.from(selectedIds);
        const lastSelected = selectedArray[selectedArray.length - 1];
        const lastIndex = samples.findIndex((s) => s.id === lastSelected);
        const currentIndex = samples.findIndex((s) => s.id === sample.id);

        if (lastIndex !== -1 && currentIndex !== -1) {
          const start = Math.min(lastIndex, currentIndex);
          const end = Math.max(lastIndex, currentIndex);
          const rangeIds = samples.slice(start, end + 1).map((s) => s.id);
          addToSelection(rangeIds);
        }
      } else {
        const newSet = new Set<string>();
        newSet.add(sample.id);
        useStore.getState().setSelectedIds(newSet, "grid");
      }
    },
    [samples, selectedIds, toggleSelection, addToSelection]
  );

  const virtualRows = virtualizer.getVirtualItems();

  return (
    <Panel>
      <div className="flex-1 min-h-0 overflow-hidden">
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
                  {rowSamples.map((sample, i) => {
                    const box = rowBoxes[i];
                    if (!box) return null;

                    const isSelected = isLassoSelection ? true : selectedIds.has(sample.id);
                    const isHovered = hoveredId === sample.id;

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
                        className={`
                          overflow-hidden cursor-pointer
                          transition-shadow duration-150 ease-out
                          ${isSelected ? "ring-2 ring-inset ring-primary" : ""}
                          ${isHovered && !isSelected ? "ring-2 ring-inset ring-primary/50" : ""}
                        `}
                        onClick={(e) => handleClick(sample, e)}
                        onMouseEnter={() => setHoveredId(sample.id)}
                        onMouseLeave={() => setHoveredId(null)}
                      >
                        {/* Image container - justified layout sizes tile to preserve aspect ratio */}
                        {/* Future: overlays (segmentations, bboxes) will be absolutely positioned here */}
                        {sample.thumbnail ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={`data:image/jpeg;base64,${sample.thumbnail}`}
                            alt={sample.filename}
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <div className="w-full h-full bg-muted flex items-center justify-center">
                            <span className="text-muted-foreground text-xs">No image</span>
                          </div>
                        )}

                        {/* Label badge */}
                        {sample.label && (
                          <div className="absolute bottom-0.5 left-0.5 right-0.5">
                            <span
                              className="inline-block px-1 py-0.5 text-[10px] leading-tight truncate max-w-full"
                              style={{
                                backgroundColor: "rgba(0,0,0,0.7)",
                                color: "#fff",
                              }}
                            >
                              {sample.label}
                            </span>
                          </div>
                        )}

                        {/* Selection indicator */}
                        {isSelected && (
                          <div className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-primary flex items-center justify-center">
                            <CheckIcon />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Panel>
  );
}
