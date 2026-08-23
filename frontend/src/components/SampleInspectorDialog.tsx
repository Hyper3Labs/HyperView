"use client";

import { Search } from "lucide-react";

import { backendUrl } from "@/lib/api";
import type { Sample } from "@/types";

import { Dialog, DialogContent } from "./ui/dialog";
import * as DialogPrimitive from "@radix-ui/react-dialog";

export function SampleInspectorDialog({
  sample,
  onOpenChange,
  onFindSimilar,
  findingSimilar = false,
  similarityError = null,
}: {
  sample: Sample | null;
  onOpenChange: (open: boolean) => void;
  onFindSimilar?: (sample: Sample) => void;
  findingSimilar?: boolean;
  similarityError?: string | null;
}) {
  const mediaUrl = backendUrl(sample?.media_url);
  const title = sample?.label || sample?.text || sample?.filename || sample?.id || "Sample";
  const metadata = sample
    ? Object.entries(sample.metadata ?? {})
        .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
        .slice(0, 10)
    : [];

  return (
    <Dialog open={sample !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(88vh,900px)] w-[min(92vw,1100px)] max-w-none flex-col gap-0 overflow-hidden p-0">
        <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
        <DialogPrimitive.Description className="sr-only">
          Full-resolution sample preview, metadata, and similarity actions.
        </DialogPrimitive.Description>
        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
          <div className="flex min-h-[280px] min-w-0 flex-1 items-center justify-center bg-black/90 p-3">
            {sample && mediaUrl ? (
              // Full-resolution inspection intentionally uses /content rather
              // than the grid thumbnail endpoint.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={mediaUrl}
                alt={sample.filename || sample.id}
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <span className="text-sm text-white/60">No media preview</span>
            )}
          </div>
          <aside className="w-full shrink-0 overflow-y-auto border-t border-border bg-card p-4 md:w-[320px] md:border-l md:border-t-0">
            <p className="pr-8 text-sm font-semibold leading-5 text-foreground">{title}</p>
            {sample ? (
              <p className="mt-1 break-all font-mono text-[10px] leading-4 text-muted-foreground">
                {sample.id}
              </p>
            ) : null}
            {sample?.text ? (
              <p className="mt-3 text-xs leading-5 text-muted-foreground">{sample.text}</p>
            ) : null}
            {sample && onFindSimilar ? (
              <button
                type="button"
                disabled={findingSimilar}
                onClick={() => onFindSimilar(sample)}
                className="mt-4 flex h-8 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground disabled:opacity-50"
              >
                <Search className="h-3.5 w-3.5" />
                {findingSimilar ? "Finding neighbours…" : "Find similar"}
              </button>
            ) : null}
            {similarityError ? (
              <p className="mt-2 text-xs leading-4 text-destructive">{similarityError}</p>
            ) : null}
            {metadata.length > 0 ? (
              <dl className="mt-5 space-y-2 border-t border-border pt-4">
                {metadata.map(([key, value]) => (
                  <div key={key} className="grid grid-cols-[90px_1fr] gap-2 text-[11px] leading-4">
                    <dt className="truncate text-muted-foreground" title={key}>{key}</dt>
                    <dd className="break-words text-foreground/80">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
          </aside>
        </div>
      </DialogContent>
    </Dialog>
  );
}
