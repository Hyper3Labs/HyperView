"use client";

import { AlertCircle, Boxes, Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

type SampleCollectionTone = "empty" | "loading" | "error";

interface SampleCollectionStateProps {
  title: string;
  description: string;
  tone?: SampleCollectionTone;
  className?: string;
}

const toneIcon = {
  empty: Boxes,
  loading: Loader2,
  error: AlertCircle,
} as const;

export function SampleCollectionState({
  title,
  description,
  tone = "empty",
  className,
}: SampleCollectionStateProps) {
  const Icon = toneIcon[tone];

  return (
    <div
      className={cn(
        "flex h-full min-h-0 items-center justify-center px-6 py-10",
        className
      )}
    >
      <div className="max-w-sm text-center">
        <div className="mx-auto mb-4 flex h-10 w-10 items-center justify-center rounded-full border border-border bg-secondary/30 text-muted-foreground">
          <Icon className={cn("h-4 w-4", tone === "loading" && "animate-spin")} />
        </div>
        <div className="text-sm font-medium text-foreground">{title}</div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}