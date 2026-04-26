"use client";

import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";
import type { Sample } from "@/types";

import { CheckIcon } from "./icons";

interface SampleTileProps extends HTMLAttributes<HTMLDivElement> {
  sample: Sample;
  selected?: boolean;
  hovered?: boolean;
  related?: boolean;
  showLabel?: boolean;
  showSelectionBadge?: boolean;
  metricBadge?: string | null;
  metricBadgeTitle?: string;
}

export function SampleTile({
  sample,
  selected = false,
  hovered = false,
  related = false,
  showLabel = true,
  showSelectionBadge = true,
  metricBadge = null,
  metricBadgeTitle,
  className,
  ...props
}: SampleTileProps) {
  return (
    <div
      data-sample-id={sample.id}
      className={cn(
        "group relative overflow-hidden bg-muted/30",
        selected && "ring-2 ring-inset ring-primary",
        hovered && !selected && "ring-2 ring-inset ring-primary/60",
        related && !selected && !hovered && "ring-1 ring-inset ring-primary/35",
        className
      )}
      {...props}
    >
      {sample.thumbnail ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`data:image/jpeg;base64,${sample.thumbnail}`}
          alt={sample.filename}
          className="h-full w-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-muted">
          <span className="text-xs text-muted-foreground">No image</span>
        </div>
      )}

      {metricBadge && (
        <div
          className="absolute right-1 top-1 z-[1] rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm"
          title={metricBadgeTitle ?? metricBadge}
        >
          {metricBadge}
        </div>
      )}

      {showLabel && sample.label && (
        <div className="absolute bottom-0.5 left-0.5 right-0.5">
          <span
            className="inline-block max-w-full truncate px-1 py-0.5 text-[10px] leading-tight text-white"
            style={{ backgroundColor: "rgba(0,0,0,0.72)" }}
          >
            {sample.label}
          </span>
        </div>
      )}

      {showSelectionBadge && selected && (
        <div className="absolute right-1 top-1 z-[1] flex h-4 w-4 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <CheckIcon />
        </div>
      )}
    </div>
  );
}