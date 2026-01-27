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
      "h-6 min-h-[24px] flex items-center justify-between px-3 border-b border-border bg-secondary select-none",
      className
    )}>
      <div className="flex items-center gap-1 min-w-0">
        {icon && (
          // 14px icon (3.5 tailwind units) with 4px gap to text
          <span className="flex-shrink-0 w-3.5 h-3.5 text-muted-foreground">{icon}</span>
        )}
        {/* 12px font, medium weight, tight tracking */}
        <span className="text-[12px] leading-[16px] font-medium tracking-[-0.15px] text-foreground truncate">{title}</span>
        {subtitle && (
          <span className="text-[11px] leading-4 text-muted-foreground truncate">{subtitle}</span>
        )}
      </div>
      {children && (
        <div className="flex items-center gap-1">{children}</div>
      )}
    </div>
  );
}
