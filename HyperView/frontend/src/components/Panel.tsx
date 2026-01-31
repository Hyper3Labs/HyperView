"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelProps {
  children: ReactNode;
  className?: string;
}

/**
 * Base panel container with consistent Rerun-style appearance.
 * No borders or rounded corners - panels should be flush against each other.
 */
export function Panel({ children, className }: PanelProps) {
  return (
    <div className={cn(
      "flex flex-col h-full bg-card overflow-hidden",
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
      "px-3 py-1 text-[11px] text-muted-foreground/70 border-t border-border bg-card font-mono",
      className
    )}>
      {children}
    </div>
  );
}
