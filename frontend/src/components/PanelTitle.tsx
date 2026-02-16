"use client";

import { ReactNode } from "react";

import { cn } from "@/lib/utils";

interface PanelTitleProps {
  title?: string;
  icon?: ReactNode;
  className?: string;
  titleClassName?: string;
  iconClassName?: string;
  fullHeight?: boolean;
}

export function PanelTitle({
  title,
  icon,
  className,
  titleClassName,
  iconClassName,
  fullHeight = false,
}: PanelTitleProps) {
  return (
    <div
      className={cn(
        "min-w-0 flex items-center gap-1 text-[12px] leading-[16px] font-medium tracking-[-0.15px]",
        fullHeight && "h-full",
        className
      )}
    >
      {icon && (
        <span className={cn("flex-shrink-0 w-3.5 h-3.5 text-muted-foreground", iconClassName)}>
          {icon}
        </span>
      )}
      <span className={cn("truncate text-foreground", titleClassName)}>{title ?? ""}</span>
    </div>
  );
}
