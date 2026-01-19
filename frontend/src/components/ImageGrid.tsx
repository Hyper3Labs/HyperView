"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useStore } from "@/store/useStore";
import { Panel, PanelFooter } from "./Panel";
import { PanelHeader } from "./PanelHeader";
import { GridIcon, CheckIcon } from "./icons";
import type { Sample } from "@/types";

interface ImageGridProps {
  samples: Sample[];
  onLoadMore?: () => void;
  hasMore?: boolean;
}

const GAP = 8;
const ITEM_HEIGHT = 200;
const MIN_ITEM_WIDTH = 200; // Minimum width for each image

export function ImageGrid({ samples, onLoadMore, hasMore }: ImageGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const {
    selectedIds,
    isLassoSelection,
    selectionSource,
    lassoTotal,
    toggleSelection,
    addToSelection,
    setHoveredId,
    hoveredId,
  } = useStore();
  const [columnCount, setColumnCount] = useState(4);

  // Calculate column count based on container width
  useEffect(() => {
    const updateColumnCount = () => {
      if (!containerRef.current) return;
      const containerWidth = containerRef.current.clientWidth;
      const padding = 16; // Total horizontal padding (8px each side)
      const availableWidth = containerWidth - padding;

      // Calculate how many columns can fit
      const columns = Math.max(1, Math.floor((availableWidth + GAP) / (MIN_ITEM_WIDTH + GAP)));
      setColumnCount(columns);
    };

    updateColumnCount();

    const resizeObserver = new ResizeObserver(updateColumnCount);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, []);

  // In lasso mode, `samples` is already the selected-page list.
  const rowCount = Math.ceil(samples.length / columnCount);

  // Create stable row keys based on the sample IDs in each row
  const getRowKey = useCallback(
    (index: number) => {
      const startIndex = index * columnCount;
      const rowSamples = samples.slice(startIndex, startIndex + columnCount);
      return rowSamples.map((s) => s.id).join("-") || `row-${index}`;
    },
    [samples, columnCount]
  );

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => containerRef.current,
    estimateSize: () => ITEM_HEIGHT + GAP,
    overscan: 5,
    getItemKey: getRowKey,
  });

  // Load more when scrolling near the bottom
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

  // Reset virtualizer measurements when selection or filter mode changes
  useEffect(() => {
    virtualizer.measure();
  }, [selectedIds, isLassoSelection, virtualizer]);

  // If a selection was made in the scatter plot, jump the image grid to the top
  // so the selected sample(s) are immediately visible.
  useEffect(() => {
    if (isLassoSelection) return;
    if (selectionSource !== "scatter") return;
    if (selectedIds.size === 0) return;

    try {
      virtualizer.scrollToIndex(0, { align: "start" });
    } catch {
      // Fallback if the virtualizer isn't ready yet.
      containerRef.current?.scrollTo({ top: 0 });
    }
  }, [isLassoSelection, selectedIds, selectionSource, virtualizer]);

  const handleClick = useCallback(
    (sample: Sample, event: React.MouseEvent) => {
      if (event.metaKey || event.ctrlKey) {
        // Multi-select with Cmd/Ctrl
        toggleSelection(sample.id);
      } else if (event.shiftKey && selectedIds.size > 0) {
        // Range select with Shift - use original samples array, not filtered
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
        // Single select
        const newSet = new Set<string>();
        newSet.add(sample.id);
        useStore.getState().setSelectedIds(newSet, "grid");
      }
    },
    [samples, selectedIds, toggleSelection, addToSelection]
  );

  const items = virtualizer.getVirtualItems();

  return (
    <Panel>
      <PanelHeader
        icon={<GridIcon />}
        title="Samples"
        subtitle={
          isLassoSelection
            ? `${lassoTotal} selected`
            : selectedIds.size > 0
              ? `${selectedIds.size} selected`
              : `${samples.length} items`
        }
      />

      {/* Grid Container */}
      <div ref={containerRef} className="flex-1 overflow-auto p-2">
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: "100%",
            position: "relative",
          }}
        >
          {items.map((virtualRow) => {
            const rowIndex = virtualRow.index;
            const startIndex = rowIndex * columnCount;
            const rowSamples = samples.slice(startIndex, startIndex + columnCount);

            return (
              <div
                key={virtualRow.key}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: `${ITEM_HEIGHT}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
                className="flex gap-2 px-1"
              >
                {rowSamples.map((sample) => {
                  const isSelected = isLassoSelection ? true : selectedIds.has(sample.id);
                  const isHovered = hoveredId === sample.id;

                  return (
                    <div
                      key={sample.id}
                      className={`
                        relative flex-1 rounded-md overflow-hidden cursor-pointer
                        transition-all duration-150 ease-out
                        ${isSelected ? "ring-2 ring-primary" : ""}
                        ${isHovered ? "ring-2 ring-primary/50" : ""}
                      `}
                      onClick={(e) => handleClick(sample, e)}
                      onMouseEnter={() => setHoveredId(sample.id)}
                      onMouseLeave={() => setHoveredId(null)}
                    >
                      {/* Image - using native img for base64 data (Next Image doesn't support this) */}
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
                        <div className="absolute bottom-1 left-1 right-1">
                          <span
                            className="inline-block px-1.5 py-0.5 text-xs rounded truncate max-w-full"
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
                        <div className="absolute top-1 right-1 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                          <CheckIcon />
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* Fill empty cells */}
                {Array.from({ length: columnCount - rowSamples.length }).map((_, i) => (
                  <div key={`empty-${i}`} className="flex-1" />
                ))}
              </div>
            );
          })}
        </div>
      </div>

      <PanelFooter>
        <span>Click • ⌘+click multi • ⇧+click range</span>
      </PanelFooter>
    </Panel>
  );
}
