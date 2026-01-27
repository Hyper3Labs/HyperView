"use client";

import React from "react";
import { useStore } from "@/store/useStore";
import { Panel } from "./Panel";
import { PanelHeader } from "./PanelHeader";
import { Tag, Search, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { FALLBACK_LABEL_COLOR, MISSING_LABEL_COLOR, normalizeLabel } from "@/lib/labelColors";
import { useLabelLegend } from "./useLabelLegend";

interface ExplorerPanelProps {
  className?: string;
}

export function ExplorerPanel({ className }: ExplorerPanelProps) {
  const {
    datasetInfo,
    embeddingsByLayoutKey,
    activeLayoutKey,
    labelFilter,
    setLabelFilter,
  } = useStore();
  const [labelSearch, setLabelSearch] = React.useState("");
  const [isSearchOpen, setIsSearchOpen] = React.useState(false);
  const [isLabelsExpanded, setIsLabelsExpanded] = React.useState(true);
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  const resolvedLayoutKey =
    activeLayoutKey ?? datasetInfo?.layouts?.[0]?.layout_key ?? null;
  const embeddings = resolvedLayoutKey
    ? embeddingsByLayoutKey[resolvedLayoutKey] ?? null
    : null;

  const {
    labelCounts,
    labelUniverse,
    distinctLabelCount,
    distinctColoringDisabled,
    labelColorMap,
    legendLabels,
  } = useLabelLegend({ datasetInfo, embeddings, labelSearch, labelFilter });

  const hasCounts = labelCounts.size > 0;
  const baseLabelCount = labelUniverse.length > 0
    ? labelUniverse.filter((label) => label !== "undefined").length
    : distinctLabelCount;
  const displayCount = labelSearch.trim().length > 0
    ? legendLabels.length
    : baseLabelCount;

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

  return (
    <Panel className={cn("h-full flex flex-col", className)}>
      <PanelHeader title="Explorer" />
      
      {/* Scrollable content area */}
      <div className="flex-1 min-h-0 overflow-auto panel-scroll">
        {/* Labels section */}
        <div className="border-b border-border">
          {/* Section header - collapsible with search icon */}
          <div className="flex items-center h-6 px-2 bg-secondary/50">
            <button
              onClick={() => setIsLabelsExpanded(!isLabelsExpanded)}
              className="flex items-center gap-1.5 flex-1 min-w-0 text-left hover:bg-muted/30 rounded px-1 -ml-1"
            >
              {isLabelsExpanded ? (
                <ChevronDown className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              )}
              <Tag className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
              <span className="text-xs text-muted-foreground truncate">
                Labels
              </span>
              <span className="ml-auto text-xs text-muted-foreground/50 tabular-nums">
                {displayCount}
              </span>
            </button>
            
            {/* Search toggle button */}
            <button
              onClick={handleSearchToggle}
              className={cn(
                "h-5 w-5 flex items-center justify-center rounded text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted/50 transition-colors ml-1",
                isSearchOpen && "text-muted-foreground bg-muted/50"
              )}
              title="Search labels"
            >
              <Search className="h-3 w-3" />
            </button>
          </div>

          {/* Search input - shown when search is toggled */}
          {isSearchOpen && (
            <div className="px-2 py-1.5 bg-secondary/30 border-b border-border/50">
              <input
                ref={searchInputRef}
                value={labelSearch}
                onChange={(e) => setLabelSearch(e.target.value)}
                placeholder="Filter labels..."
                className="w-full h-6 px-2 rounded bg-background border border-border text-[12px] leading-[16px] text-foreground placeholder:text-muted-foreground/50 outline-none focus:ring-1 focus:ring-ring focus:border-ring"
              />
            </div>
          )}

          {/* Labels list - collapsible */}
          {isLabelsExpanded && (
            <div className="py-1">
              {distinctColoringDisabled && (
                <div className="px-3 py-1 text-[10px] text-muted-foreground/60">
                  Too many labels ({distinctLabelCount}) to color distinctly; using one color.
                </div>
              )}

              {legendLabels.length === 0 ? (
                <div className="px-3 py-2 text-[11px] text-muted-foreground/50">
                  No labels available
                </div>
              ) : (
                <div className="space-y-px">
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
                        onClick={() => setLabelFilter(isActive ? null : normalized)}
                        className={cn(
                          "flex items-center gap-2 w-full h-6 px-3 text-[12px] leading-[16px] text-left text-muted-foreground hover:text-foreground",
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
          )}
        </div>
      </div>
    </Panel>
  );
}
