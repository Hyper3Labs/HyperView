"use client";

import React from "react";
import { Panel } from "./Panel";
import { PanelHeader } from "./PanelHeader";
import { Search, Tag } from "lucide-react";
import { cn } from "@/lib/utils";
import { FALLBACK_LABEL_COLOR, MISSING_LABEL_COLOR, normalizeLabel } from "@/lib/labelColors";
import { useLabelLegend } from "./useLabelLegend";
import {
  useCollection,
  useCommandClient,
  useDatasetInfo,
  usePanelState,
} from "@/panel-sdk";

interface ExplorerPanelProps {
  className?: string;
}

export function ExplorerPanel({ className }: ExplorerPanelProps) {
  const dataset = useDatasetInfo();
  const commandClient = useCommandClient();
  const { state } = usePanelState("samples");
  const collectionId = typeof state.collection_id === "string" ? state.collection_id : null;
  const collection = useCollection(collectionId);
  const [labelSearch, setLabelSearch] = React.useState("");
  const [isSearchOpen, setIsSearchOpen] = React.useState(false);
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  const labelFilter = React.useMemo(() => {
    if (collection?.kind !== "filter") return null;
    const { field, op, value } = collection.query;
    if (field !== "label" || op !== "eq") return null;
    return normalizeLabel(typeof value === "string" ? value : null);
  }, [collection]);

  const {
    labelCounts,
    labelColorMap,
    legendLabels,
  } = useLabelLegend({
    datasetInfo: dataset.dataset,
    embeddings: null,
    labelSearch,
    labelFilter,
    labelCountsOverride: dataset.labelCounts,
  });

  const hasCounts = labelCounts.size > 0;

  const activeLabel = labelFilter ? normalizeLabel(labelFilter) : null;

  // Focus search input when opened
  React.useEffect(() => {
    if (isSearchOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isSearchOpen]);

  const handleSearchToggle = () => {
    setIsSearchOpen(!isSearchOpen);
    if (isSearchOpen) {
      setLabelSearch("");
    }
  };

  const applyLabelFilter = React.useCallback(
    (nextLabel: string | null) => {
      void commandClient
        .runCommand("collection.filter.set", {
          args: {
            field: "label",
            ...(nextLabel === null
              ? { clear: true }
              : { value: nextLabel === "undefined" ? null : nextLabel }),
            source: "explorer",
          },
        })
        .catch((err) => {
          console.error("Failed to persist label filter:", err);
        });
    },
    [commandClient]
  );

  return (
    <Panel className={cn("h-full flex flex-col", className)}>
      <PanelHeader title="Labels" icon={<Tag className="h-3.5 w-3.5" />}>
        {/* Search toggle button in header toolbar */}
        <button
          onClick={handleSearchToggle}
          className={cn(
            "h-6 w-6 flex items-center justify-center rounded text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted/50 transition-colors",
            isSearchOpen && "text-muted-foreground bg-muted/50"
          )}
          title="Filter labels"
        >
          <Search className="h-3 w-3" />
        </button>
      </PanelHeader>

      {/* Search input - shown when search is toggled */}
      {isSearchOpen && (
        <div className="px-2 py-1 border-b border-border">
          <input
            ref={searchInputRef}
            value={labelSearch}
            onChange={(e) => setLabelSearch(e.target.value)}
            placeholder="Filter labels..."
            className="w-full h-6 px-2 rounded bg-background border border-border text-[12px] leading-[16px] text-foreground placeholder:text-muted-foreground/50 outline-none focus:ring-1 focus:ring-ring focus:border-ring"
          />
        </div>
      )}

      {/* Scrollable labels list */}
      <div className="flex-1 min-h-0 overflow-auto panel-scroll">
        {legendLabels.length === 0 ? (
          <div className="px-2 py-2 text-[11px] text-muted-foreground/50">
            No labels available
          </div>
        ) : (
          <div className="py-1 space-y-px">
            {legendLabels.map((label) => {
              const color =
                label === "undefined"
                  ? MISSING_LABEL_COLOR
                  : labelColorMap[label] ?? FALLBACK_LABEL_COLOR;
              const normalized = normalizeLabel(label);
              const isActive = activeLabel === normalized;
              const isDimmed = activeLabel && !isActive;

              return (
                <button
                  key={label}
                  type="button"
                  onClick={() => applyLabelFilter(isActive ? null : normalized)}
                  className={cn(
                    "flex items-center gap-2 w-full h-6 px-2 text-[12px] leading-[16px] text-left text-muted-foreground hover:text-foreground",
                    "hover:bg-muted/40 transition-colors",
                    isActive && "bg-muted/60 text-foreground",
                    isDimmed && "opacity-40"
                  )}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: color }}
                  />
                  <span className="truncate flex-1" title={label}>
                    {label}
                  </span>
                  {hasCounts && (
                    <span className="text-[10px] text-muted-foreground/50 font-mono tabular-nums flex-shrink-0">
                      {labelCounts.get(label) ?? 0}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </Panel>
  );
}
