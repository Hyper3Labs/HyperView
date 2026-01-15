"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps {
  children: ReactNode;
  className?: string;
}

/**
 * Base panel container with consistent Rerun-style appearance.
 */
export function Panel({ children, className }: PanelProps) {
  return (
    <div className={cn(
      "flex flex-col h-full bg-card rounded-sm overflow-hidden border border-border",
      className
    )}>
      {children}
    </div>
  );
}

interface PanelFooterProps {
  children: ReactNode;
  className?: string;
}

/**
 * Panel footer for keyboard shortcuts/hints.
 */
export function PanelFooter({ children, className }: PanelFooterProps) {
  return (
    <div className={cn(
      "px-2 py-1.5 text-[11px] text-muted-foreground/70 border-t border-border bg-card font-mono",
      className
    )}>
      {children}
    </div>
  );
}
