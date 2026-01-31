const MISSING_LABEL_SENTINEL = "undefined";

export const MISSING_LABEL_COLOR = "#39d3cc"; // matches --accent-cyan
export const FALLBACK_LABEL_COLOR = "#8b949e"; // matches --muted-foreground

// Rerun-style auto colors: distribute hues by golden ratio conjugate.
// See: context/repos/rerun/crates/viewer/re_viewer_context/src/utils/color.rs
const GOLDEN_RATIO_CONJUGATE = (Math.sqrt(5) - 1) / 2; // ~0.61803398875

function fnv1a32(input: string): number {
  // 32-bit FNV-1a hash
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function clamp01(v: number): number {
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

function hsvToHex(h: number, s: number, v: number): string {
  // h/s/v in [0, 1]
  const hh = ((h % 1) + 1) % 1;
  const ss = clamp01(s);
  const vv = clamp01(v);

  const x = hh * 6;
  const i = Math.floor(x);
  const f = x - i;

  const p = vv * (1 - ss);
  const q = vv * (1 - ss * f);
  const t = vv * (1 - ss * (1 - f));

  let r = 0;
  let g = 0;
  let b = 0;

  switch (i % 6) {
    case 0:
      r = vv;
      g = t;
      b = p;
      break;
    case 1:
      r = q;
      g = vv;
      b = p;
      break;
    case 2:
      r = p;
      g = vv;
      b = t;
      break;
    case 3:
      r = p;
      g = q;
      b = vv;
      break;
    case 4:
      r = t;
      g = p;
      b = vv;
      break;
    case 5:
      r = vv;
      g = p;
      b = q;
      break;
  }

  const toHex = (x: number) => {
    const n = Math.round(clamp01(x) * 255);
    return n.toString(16).padStart(2, "0");
  };

  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

export function labelToColor(label: string): string {
  if (!label) return FALLBACK_LABEL_COLOR;
  if (label === MISSING_LABEL_SENTINEL) return MISSING_LABEL_COLOR;

  return colorForKey(label);
}

function colorForKey(key: string): string {
  const seed = fnv1a32(key);
  const val = seed & 0xffff; // map to u16
  const h = (val * GOLDEN_RATIO_CONJUGATE) % 1;

  // Match Rerun's defaults: saturation 0.85, value 0.5
  return hsvToHex(h, 0.85, 0.5);
}

function stableLabelSort(a: string, b: string): number {
  if (a === MISSING_LABEL_SENTINEL && b !== MISSING_LABEL_SENTINEL) return 1;
  if (b === MISSING_LABEL_SENTINEL && a !== MISSING_LABEL_SENTINEL) return -1;
  return a.localeCompare(b);
}

/**
 * Builds a deterministic, collision-free label → color mapping for the given
 * label universe.
 *
 * Notes:
 * - No modulo/cycling: if there are N labels, we produce N colors.
 * - Deterministic: same input set yields same mapping.
 * - Collision-free within the provided set via deterministic rehashing.
 */
export function createLabelColorMap(labels: string[]): Record<string, string> {
  const unique = Array.from(new Set(labels.map((l) => normalizeLabel(l)))).sort(stableLabelSort);

  const colors: Record<string, string> = {};
  const used = new Set<string>();

  for (const label of unique) {
    if (label === MISSING_LABEL_SENTINEL) {
      colors[label] = MISSING_LABEL_COLOR;
      used.add(MISSING_LABEL_COLOR.toLowerCase());
      continue;
    }

    let attempt = 0;
    // Deterministic collision resolution (should be extremely rare).
    while (attempt < 32) {
      const candidate = colorForKey(attempt === 0 ? label : `${label}#${attempt}`);
      const normalized = candidate.toLowerCase();
      if (!used.has(normalized)) {
        colors[label] = candidate;
        used.add(normalized);
        break;
      }
      attempt++;
    }

    if (!colors[label]) {
      // Should never happen, but keep UI resilient.
      colors[label] = FALLBACK_LABEL_COLOR;
    }
  }

  return colors;
}

export function normalizeLabel(label: string | null | undefined): string {
  return label && label.length > 0 ? label : MISSING_LABEL_SENTINEL;
}
