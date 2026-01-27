"use client";

import React from "react";
import { HyperViewLogo } from "./icons";
import { Panel } from "./Panel";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface PlaceholderPanelProps {
  className?: string;
  onClose?: () => void;
}

/**
 * Empty placeholder panel with centered HyperView logo and a close button.
 * Used for right and bottom zones that are reserved for future features.
 * The close button is always visible in the top-right corner of the panel content.
 */
export function PlaceholderPanel({ className, onClose }: PlaceholderPanelProps) {
  return (
    <Panel className={cn("h-full w-full relative", className)}>
      {/* Close button always visible in top right */}
      {onClose && (
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1.5 rounded-md text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted/60 transition-colors z-10"
          aria-label="Close panel"
        >
          <X className="h-4 w-4" />
        </button>
      )}
      <div className="flex-1 flex items-center justify-center">
        <div className="text-muted-foreground/20">
          <HyperViewLogo className="w-12 h-12" />
        </div>
      </div>
    </Panel>
  );
}
