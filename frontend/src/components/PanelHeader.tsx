"use client";

import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface PanelHeaderProps {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  children?: ReactNode; // Toolbar actions slot
  className?: string;
}

/**
 * Rerun-style panel header with icon, title, and optional toolbar.
 */
export function PanelHeader({ icon, title, subtitle, children, className }: PanelHeaderProps) {
  return (
    <div className={cn(
      "h-9 min-h-[36px] flex items-center justify-between px-2 border-b border-border bg-secondary select-none",
      className
    )}>
      <div className="flex items-center gap-2 min-w-0">
        {icon && (
          <span className="flex-shrink-0 w-4 h-4 text-muted-foreground">{icon}</span>
        )}
        <span className="text-sm font-medium text-foreground truncate">{title}</span>
        {subtitle && (
          <span className="text-xs text-muted-foreground truncate">{subtitle}</span>
        )}
      </div>
      {children && (
        <div className="flex items-center gap-1">{children}</div>
      )}
    </div>
  );
}
