"use client";

import { useEffect, useMemo, useState, type HTMLAttributes } from "react";

import { backendUrl } from "@/lib/api";
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
  const mediaSrc = useMemo(() => {
    if (sample.thumbnail) return `data:image/jpeg;base64,${sample.thumbnail}`;
    return backendUrl(sample.media_url);
  }, [sample.media_url, sample.thumbnail]);
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = Boolean(mediaSrc) && !imageFailed;

  useEffect(() => {
    setImageFailed(false);
  }, [mediaSrc]);

  return (
    <div
      data-sample-id={sample.id}
      className={cn(
        "group relative overflow-hidden bg-muted/30",
        hovered && !selected && "ring-2 ring-inset ring-primary/60",
        related && !selected && !hovered && "ring-1 ring-inset ring-primary/35",
        className
      )}
      {...props}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mediaSrc ?? undefined}
          alt={sample.filename}
          className="block h-full w-full object-contain"
          loading="lazy"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center bg-muted">
          <span className="text-xs text-muted-foreground">No image</span>
        </div>
      )}

      {metricBadge && (
        <div
          className={cn(
            "absolute right-1 z-[1] rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm",
            selected && showSelectionBadge ? "top-7" : "top-1"
          )}
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
        <div className="absolute right-1 top-1 z-[2] flex h-5 w-5 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm ring-1 ring-background/70">
          <CheckIcon />
        </div>
      )}
    </div>
  );
}
