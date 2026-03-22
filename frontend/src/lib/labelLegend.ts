import type { EmbeddingsData } from "@/types";
import {
  FALLBACK_LABEL_COLOR,
  MISSING_LABEL_COLOR,
  normalizeLabel,
  type LabelColorMapId,
} from "@/lib/labelColors";
import { createCategoricalLabelTransferFunction } from "@/lib/colorTransfer";

export const UNSELECTED_LABEL_ALPHA = 0.12;

export interface ScatterLabelsInfo {
  uniqueLabels: string[];
  categories: Uint16Array;
  palette: string[];
}

function clamp01(v: number): number {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

function applyAlphaToHex(color: string, alpha: number): string {
  if (!color.startsWith("#")) return color;
  const hex = Math.round(clamp01(alpha) * 255)
    .toString(16)
    .padStart(2, "0");

  if (color.length === 7) {
    return `${color}${hex}`;
  }

  if (color.length === 9) {
    return `${color.slice(0, 7)}${hex}`;
  }

  return color;
}

function applyLabelFilterToPalette(params: {
  palette: string[];
  labels: string[];
  labelFilter: string | null;
  unselectedAlpha: number;
}): string[] {
  const { palette, labels, labelFilter, unselectedAlpha } = params;
  if (!labelFilter) return palette;
  if (!labels.includes(labelFilter)) return palette;

  return palette.map((color, idx) =>
    labels[idx] === labelFilter ? color : applyAlphaToHex(color, unselectedAlpha)
  );
}

export function buildLabelCounts(embeddings: EmbeddingsData | null): Map<string, number> {
  const counts = new Map<string, number>();
  if (!embeddings) return counts;
  for (const raw of embeddings.labels) {
    const l = normalizeLabel(raw);
    counts.set(l, (counts.get(l) ?? 0) + 1);
  }
  return counts;
}

export function buildLabelUniverse(
  datasetLabels: string[],
  embeddingsLabels: (string | null)[] | null
): string[] {
  const universe: string[] = [];
  const seen = new Set<string>();
  let hasMissing = false;

  const baseLabels = datasetLabels.map((l) => normalizeLabel(l));
  for (const l of baseLabels) {
    if (l === "undefined") {
      hasMissing = true;
      continue;
    }
    if (seen.has(l)) continue;
    seen.add(l);
    universe.push(l);
  }

  if (embeddingsLabels) {
    const extras = new Set<string>();
    for (const raw of embeddingsLabels) {
      const l = normalizeLabel(raw);
      if (l === "undefined") {
        hasMissing = true;
        continue;
      }
      if (!seen.has(l)) extras.add(l);
    }

    if (extras.size > 0) {
      const extraSorted = Array.from(extras).sort((a, b) => a.localeCompare(b));
      for (const l of extraSorted) {
        seen.add(l);
        universe.push(l);
      }
    }
  }

  if (hasMissing) universe.push("undefined");
  return universe;
}

export function buildLabelsInfo(params: {
  datasetLabels: string[];
  embeddings: EmbeddingsData | null;
  labelColorMapId: LabelColorMapId;
}): ScatterLabelsInfo | null {
  const {
    datasetLabels,
    embeddings,
    labelColorMapId,
  } = params;
  if (!embeddings) return null;

  const universe = buildLabelUniverse(datasetLabels, embeddings.labels);

  // Guard: hyper-scatter categories are Uint16.
  if (universe.length > 65535) {
    console.warn(
      `Too many labels (${universe.length}) for uint16 categories; collapsing to a single color.`
    );
    return {
      uniqueLabels: ["undefined"],
      categories: new Uint16Array(embeddings.labels.length),
      palette: [FALLBACK_LABEL_COLOR],
    };
  }

  const labelToCategory: Record<string, number> = {};
  for (let i = 0; i < universe.length; i++) {
    labelToCategory[universe[i]] = i;
  }

  const undefinedIndex = labelToCategory["undefined"] ?? 0;
  const categories = new Uint16Array(embeddings.labels.length);
  for (let i = 0; i < embeddings.labels.length; i++) {
    const key = normalizeLabel(embeddings.labels[i]);
    categories[i] = labelToCategory[key] ?? undefinedIndex;
  }

  const transfer = createCategoricalLabelTransferFunction({
    labels: universe,
    paletteId: labelColorMapId,
  });
  const palette = universe.map((l) => transfer.colorFor(l));

  return { uniqueLabels: universe, categories, palette };
}

export function buildLabelColorMap(params: {
  labelsInfo: ScatterLabelsInfo | null;
  labelUniverse: string[];
  labelColorMapId: LabelColorMapId;
  labelFilter?: string | null;
  unselectedAlpha?: number;
}): Record<string, string> {
  const {
    labelsInfo,
    labelUniverse,
    labelColorMapId,
    labelFilter = null,
    unselectedAlpha = UNSELECTED_LABEL_ALPHA,
  } = params;
  const map: Record<string, string> = {};

  if (labelsInfo) {
    const filteredPalette = applyLabelFilterToPalette({
      palette: labelsInfo.palette,
      labels: labelsInfo.uniqueLabels,
      labelFilter,
      unselectedAlpha,
    });

    for (let i = 0; i < labelsInfo.uniqueLabels.length; i++) {
      map[labelsInfo.uniqueLabels[i]] = filteredPalette[i] ?? FALLBACK_LABEL_COLOR;
    }
  } else {
    if (labelUniverse.length === 0) return map;

    const transfer = createCategoricalLabelTransferFunction({
      labels: labelUniverse,
      paletteId: labelColorMapId,
    });
    for (const label of labelUniverse) {
      map[label] = transfer.colorFor(label);
    }

    if (!labelFilter || !labelUniverse.includes(labelFilter)) return map;

    for (const label of labelUniverse) {
      if (label !== labelFilter) {
        map[label] = applyAlphaToHex(map[label], unselectedAlpha);
      }
    }
  }

  return map;
}

export function buildLegendLabels(params: {
  labelUniverse: string[];
  labelCounts: Map<string, number>;
  query: string;
}): string[] {
  const { labelUniverse, labelCounts, query } = params;
  const all = labelUniverse.length > 0 ? [...labelUniverse] : Array.from(labelCounts.keys());
  const q = query.trim().toLowerCase();
  const filtered = q ? all.filter((l) => l.toLowerCase().includes(q)) : all;
  const hasCounts = labelCounts.size > 0;

  return filtered.sort((a, b) => {
    if (a === "undefined" && b !== "undefined") return 1;
    if (b === "undefined" && a !== "undefined") return -1;

    if (hasCounts) {
      const ca = labelCounts.get(a) ?? 0;
      const cb = labelCounts.get(b) ?? 0;
      if (cb !== ca) return cb - ca;
    }

    return a.localeCompare(b);
  });
}
