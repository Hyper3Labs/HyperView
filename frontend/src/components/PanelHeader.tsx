"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { PanelTitle } from "./PanelTitle";

interface PanelHeaderProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  children?: ReactNode; // Toolbar actions slot
  className?: string;
}

/**
 * Rerun-style panel header with icon, title, and optional toolbar.
 * 
 * Design tokens (from Rerun):
 * - Title bar height: 24px
 * - Icon size: 14px (3.5 tailwind units)
 * - Icon-to-text gap: 4px (gap-1)
 * - Font size: 12px with -0.15px tracking
 * - Section header font: 11px uppercase
 */
export function PanelHeader({ icon, title, subtitle, children, className }: PanelHeaderProps) {
  return (
    <div className={cn(
      // 24px height matches Rerun's title_bar_height()
      "h-6 min-h-[24px] flex items-center justify-between px-2 border-b border-border bg-secondary select-none",
      className
    )}>
      <div className="flex items-center min-w-0">
        <PanelTitle title={title} icon={icon} />
        {subtitle && (
          <span className="ml-1 text-[11px] leading-4 text-muted-foreground truncate">{subtitle}</span>
        )}
      </div>
      {children && (
        <div className="flex items-center gap-1">{children}</div>
      )}
    </div>
  );
}
