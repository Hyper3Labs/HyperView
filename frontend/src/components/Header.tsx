"use client";

import { useStore } from "@/store/useStore";
import { Button } from "@/components/ui/button";
import { HyperViewLogo } from "./icons";

export function Header() {
  const { datasetInfo, selectedIds, clearSelection } = useStore();

  return (
    <header className="h-10 min-h-[40px] bg-secondary border-b border-border flex items-center justify-between px-3">
      {/* Logo and title */}
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded flex items-center justify-center text-primary">
          <HyperViewLogo />
        </div>
        <div className="flex items-center gap-2">
          <h1 className="text-sm font-semibold text-foreground">HyperView</h1>
          {datasetInfo && (
            <span className="text-xs text-muted-foreground/70 font-mono">
              {datasetInfo.name}
            </span>
          )}
        </div>
      </div>

      {/* Dataset info and actions */}
      <div className="flex items-center gap-3">
        {datasetInfo && (
          <div className="flex items-center gap-3 text-[11px] font-mono">
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground/70">samples</span>
              <span className="text-muted-foreground">{datasetInfo.num_samples.toLocaleString()}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-muted-foreground/70">labels</span>
              <span className="text-muted-foreground">{datasetInfo.labels.length}</span>
            </div>
          </div>
        )}

        {selectedIds.size > 0 && (
          <Button
            variant="secondary"
            size="sm"
            onClick={clearSelection}
            className="h-6 text-[11px]"
          >
            Clear ({selectedIds.size})
          </Button>
        )}
      </div>
    </header>
  );
}
