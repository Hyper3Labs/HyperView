"use client";

import { startTransition, useEffect, useState } from "react";

import { normalizeLabel } from "@/lib/labelColors";
import type { EmbeddingsData } from "@/types";
import {
  buildSemanticLabelModel,
  type SemanticLabelDisplayMode,
  type SemanticLabelModel,
} from "hyper-scatter";

interface UseScatterSemanticLabelsArgs {
  embeddings: EmbeddingsData | null;
  layoutDimension: 2 | 3;
  labelFilter: string | null;
  displayMode: "off" | SemanticLabelDisplayMode;
}

function toGeometryMode(geometry: EmbeddingsData["geometry"]): "euclidean" | "poincare" {
  return geometry === "poincare" ? "poincare" : "euclidean";
}

export function useScatterSemanticLabels({
  embeddings,
  layoutDimension,
  labelFilter,
  displayMode,
}: UseScatterSemanticLabelsArgs) {
  const [model, setModel] = useState<SemanticLabelModel | null>(null);

  useEffect(() => {
    if (!embeddings || layoutDimension !== 2 || displayMode === "off") {
      setModel(null);
      return;
    }

    let cancelled = false;
    const run = () => {
      const coords = embeddings.coords;
      if (coords.length === 0) {
        if (!cancelled) setModel(null);
        return;
      }

      let pointCount = 0;
      for (let index = 0; index < coords.length; index++) {
        const label = normalizeLabel(embeddings.labels[index]);
        if (labelFilter && label !== labelFilter) continue;
        const point = coords[index];
        if (!point || point.length < 2) continue;
        pointCount += 1;
      }

      if (pointCount < 8) {
        if (!cancelled) setModel(null);
        return;
      }

      const positions = new Float32Array(pointCount * 2);
      const terms = new Array<string>(pointCount);
      let cursor = 0;

      for (let index = 0; index < coords.length; index++) {
        const point = coords[index];
        if (!point || point.length < 2) continue;

        const normalizedLabel = normalizeLabel(embeddings.labels[index]);
        if (labelFilter && normalizedLabel !== labelFilter) continue;

        positions[cursor * 2] = point[0];
        positions[cursor * 2 + 1] = point[1];
        terms[cursor] = normalizedLabel === "undefined" ? "" : String(embeddings.labels[index] ?? "");
        cursor += 1;
      }

      if (cursor < 8 || !terms.some((term) => term.trim().length > 0)) {
        if (!cancelled) setModel(null);
        return;
      }

      const nextModel = buildSemanticLabelModel({
        positions,
        terms,
        geometry: toGeometryMode(embeddings.geometry),
        engine: "candidate",
      });

      if (cancelled) return;
      startTransition(() => {
        if (!cancelled) {
          setModel(nextModel);
        }
      });
    };

    const idleCallback = window.requestIdleCallback?.(() => run(), { timeout: 120 }) ?? null;
    const timeoutHandle = idleCallback === null ? window.setTimeout(run, 0) : null;

    return () => {
      cancelled = true;
      if (idleCallback !== null) {
        window.cancelIdleCallback?.(idleCallback);
      }
      if (timeoutHandle !== null) {
        window.clearTimeout(timeoutHandle);
      }
    };
  }, [displayMode, embeddings, labelFilter, layoutDimension]);

  return { semanticLabelModel: model };
}