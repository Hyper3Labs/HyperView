"use client";

import { useEffect, useMemo, useState, type HTMLAttributes } from "react";

import { backendUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Sample } from "@/types";

import { CheckIcon } from "./icons";
import { ImageTileContent } from "./tiles/ImageTileContent";
import { MetadataTileContent } from "./tiles/MetadataTileContent";
import { getSampleTileKind } from "./tiles/sampleTileKind";
import { TextTileContent } from "./tiles/TextTileContent";
import { VideoTileContent } from "./tiles/VideoTileContent";

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
  const tileKind = getSampleTileKind(sample);
  const thumbnailSrc = useMemo(() => {
    if (sample.thumbnail) return `data:image/jpeg;base64,${sample.thumbnail}`;
    if (sample.thumbnail_url) return backendUrl(sample.thumbnail_url);
    return null;
  }, [sample.thumbnail, sample.thumbnail_url]);
  const imageSrc = thumbnailSrc ?? backendUrl(sample.media_url);
  const rendererSrc = tileKind === "video" ? thumbnailSrc : imageSrc;
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [rendererSrc, tileKind]);

  const durationBadge = formatDuration(sample.duration_s);

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
      {tileKind === "image" ? (
        <ImageTileContent
          src={imageSrc}
          alt={sample.filename}
          failed={imageFailed}
          onError={() => setImageFailed(true)}
        />
      ) : tileKind === "text" ? (
        <TextTileContent text={sample.text} />
      ) : tileKind === "video" ? (
        <VideoTileContent
          posterSrc={thumbnailSrc}
          filename={sample.filename}
          id={sample.id}
          failed={imageFailed}
          onError={() => setImageFailed(true)}
        />
      ) : (
        <MetadataTileContent
          filename={sample.filename}
          id={sample.id}
          kind={sample.media_type || sample.modality}
        />
      )}

      {tileKind === "video" && durationBadge ? (
        <div className="absolute left-1 top-1 z-[1] rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] font-medium tabular-nums text-white backdrop-blur-sm">
          {durationBadge}
        </div>
      ) : null}

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

      {showLabel && (sample.label || sample.text) && (
        <div className="absolute bottom-0.5 left-0.5 right-0.5 space-y-0.5">
          {sample.label ? (
            <span
              className="inline-block max-w-full truncate px-1 py-0.5 text-[10px] leading-tight text-white"
              style={{ backgroundColor: "rgba(0,0,0,0.72)" }}
            >
              {sample.label}
            </span>
          ) : null}
          {sample.text && tileKind !== "text" ? (
            <span
              className="block max-w-full truncate px-1 py-0.5 text-[10px] leading-tight text-white"
              style={{ backgroundColor: "rgba(0,0,0,0.72)" }}
              title={sample.text}
            >
              {sample.text}
            </span>
          ) : null}
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

function formatDuration(durationSeconds: number | null | undefined): string | null {
  if (
    typeof durationSeconds !== "number" ||
    !Number.isFinite(durationSeconds) ||
    durationSeconds < 0
  ) {
    return null;
  }

  const totalSeconds = Math.floor(durationSeconds);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
