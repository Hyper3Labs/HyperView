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
