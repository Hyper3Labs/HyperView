const MISSING_LABEL_SENTINEL = "undefined";

export const MISSING_LABEL_COLOR = "#39d3cc"; // matches --accent-cyan
export const FALLBACK_LABEL_COLOR = "#8b949e"; // matches --muted-foreground

export const LABEL_COLOR_MAP_IDS = ["auto", "classic20", "tab10", "tab20", "wong"] as const;
export type LabelColorMapId = (typeof LABEL_COLOR_MAP_IDS)[number];

const AUTO_DEFAULT_PALETTE_ID: LabelColorMapId = "tab20";
const OVERFLOW_HUE_STEP_DEGREES = 137.508;

export function isLabelColorMapId(value: string): value is LabelColorMapId {
  return LABEL_COLOR_MAP_IDS.includes(value as LabelColorMapId);
}

const CLASSIC_20_LABEL_PALETTE = [
  "#e6194b",
  "#3cb44b",
  "#ffe119",
  "#4363d8",
  "#f58231",
  "#911eb4",
  "#46f0f0",
  "#f032e6",
  "#bcf60c",
  "#fabebe",
  "#008080",
  "#e6beff",
  "#9a6324",
  "#fffac8",
  "#800000",
  "#aaffc3",
  "#808000",
  "#ffd8b1",
  "#000075",
  "#808080",
];

const TAB_10_LABEL_PALETTE = [
  "#4e79a7",
  "#f28e2b",
  "#e15759",
  "#76b7b2",
  "#59a14f",
  "#edc948",
  "#b07aa1",
  "#ff9da7",
  "#9c755f",
  "#bab0ab",
];

const TAB_20_LABEL_PALETTE = [
  "#1f77b4",
  "#aec7e8",
  "#ff7f0e",
  "#ffbb78",
  "#2ca02c",
  "#98df8a",
  "#d62728",
  "#ff9896",
  "#9467bd",
  "#c5b0d5",
  "#8c564b",
  "#c49c94",
  "#e377c2",
  "#f7b6d2",
  "#7f7f7f",
  "#c7c7c7",
  "#bcbd22",
  "#dbdb8d",
  "#17becf",
  "#9edae5",
];

const WONG_LABEL_PALETTE = [
  "#e69f00",
  "#56b4e9",
  "#009e73",
  "#f0e442",
  "#0072b2",
  "#d55e00",
  "#cc79a7",
];

function clamp01(v: number): number {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

function hslToHex(hDegrees: number, saturation: number, lightness: number): string {
  const h = ((((hDegrees % 360) + 360) % 360) / 360) % 1;
  const s = clamp01(saturation);
  const l = clamp01(lightness);

  let r = l;
  let g = l;
  let b = l;

  if (s > 0) {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;

    const hueToChannel = (tIn: number): number => {
      let t = tIn;
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };

    r = hueToChannel(h + 1 / 3);
    g = hueToChannel(h);
    b = hueToChannel(h - 1 / 3);
  }

  const toHex = (x: number) => {
    const n = Math.round(clamp01(x) * 255);
    return n.toString(16).padStart(2, "0");
  };

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function createOverflowColor(index: number, seedPrefix: LabelColorMapId): string {
  const paletteSeedShift =
    seedPrefix === "tab10"
      ? 17
      : seedPrefix === "tab20"
        ? 43
        : seedPrefix === "wong"
          ? 71
          : seedPrefix === "classic20"
            ? 101
            : 131;

  const hue = (paletteSeedShift + index * OVERFLOW_HUE_STEP_DEGREES) % 360;
  const saturationBands = [0.72, 0.64, 0.78];
  const lightnessBands = [0.46, 0.54, 0.38, 0.62];

  const saturation = saturationBands[index % saturationBands.length];
  const lightness =
    lightnessBands[Math.floor(index / saturationBands.length) % lightnessBands.length];

  return hslToHex(hue, saturation, lightness);
}

function stableLabelSort(a: string, b: string): number {
  if (a === MISSING_LABEL_SENTINEL && b !== MISSING_LABEL_SENTINEL) return 1;
  if (b === MISSING_LABEL_SENTINEL && a !== MISSING_LABEL_SENTINEL) return -1;
  return a.localeCompare(b);
}

function createAutoLabelColorMap(unique: string[]): Record<string, string> {
  return createPaletteLabelColorMap(unique, TAB_20_LABEL_PALETTE, AUTO_DEFAULT_PALETTE_ID);
}

function createPaletteLabelColorMap(
  unique: string[],
  palette: string[],
  seedPrefix: LabelColorMapId
): Record<string, string> {
  const colors: Record<string, string> = {};
  const used = new Set<string>();
  let nonMissingIndex = 0;
  let overflowIndex = 0;

  for (const label of unique) {
    if (label === MISSING_LABEL_SENTINEL) {
      colors[label] = MISSING_LABEL_COLOR;
      used.add(MISSING_LABEL_COLOR.toLowerCase());
      continue;
    }

    let candidate =
      nonMissingIndex < palette.length
        ? (palette[nonMissingIndex] ?? FALLBACK_LABEL_COLOR)
        : createOverflowColor(overflowIndex, seedPrefix);

    let safety = 0;
    while (used.has(candidate.toLowerCase()) && safety < 2048) {
      overflowIndex += 1;
      candidate = createOverflowColor(overflowIndex, seedPrefix);
      safety += 1;
    }

    if (nonMissingIndex >= palette.length) {
      overflowIndex += 1;
    }

    if (used.has(candidate.toLowerCase())) {
      candidate = FALLBACK_LABEL_COLOR;
    }

    colors[label] = candidate;
    used.add(candidate.toLowerCase());
    nonMissingIndex += 1;
  }

  return colors;
}

/**
 * Builds a deterministic label → color mapping for the given label universe.
 *
 * Notes:
 * - `auto` mode uses `tab20` as the default categorical palette.
 * - `classic20`, `tab10`, `tab20`, and `wong` use fixed categorical palettes
 *   first, then deterministic overflow colors for additional labels.
 */
export function createLabelColorMap(
  labels: string[],
  options?: { paletteId?: LabelColorMapId }
): Record<string, string> {
  const unique = Array.from(new Set(labels.map((l) => normalizeLabel(l)))).sort(stableLabelSort);
  const paletteId = options?.paletteId ?? "auto";

  if (paletteId === "classic20") {
    return createPaletteLabelColorMap(unique, CLASSIC_20_LABEL_PALETTE, "classic20");
  }

  if (paletteId === "tab10") {
    return createPaletteLabelColorMap(unique, TAB_10_LABEL_PALETTE, "tab10");
  }

  if (paletteId === "tab20") {
    return createPaletteLabelColorMap(unique, TAB_20_LABEL_PALETTE, "tab20");
  }

  if (paletteId === "wong") {
    return createPaletteLabelColorMap(unique, WONG_LABEL_PALETTE, "wong");
  }

  return createAutoLabelColorMap(unique);
}

export function normalizeLabel(label: string | null | undefined): string {
  return label && label.length > 0 ? label : MISSING_LABEL_SENTINEL;
}
