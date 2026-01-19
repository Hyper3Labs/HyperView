import type { Geometry } from "@/types";

export function getLayoutSpaceKey(layoutKey: string): string {
  return layoutKey.split("__")[0] || layoutKey;
}

export function getLayoutGeometry(layoutKey: string): Geometry | null {
  const parts = layoutKey.split("__");
  if (parts.length < 2) {
    const legacy = layoutKey.toLowerCase();
    if (legacy === "poincare" || legacy === "hyperbolic") return "poincare";
    if (legacy === "euclidean") return "euclidean";
    return null;
  }

  const token = parts[1]?.split("_")[0]?.toLowerCase();
  if (token === "poincare" || token === "hyperbolic") return "poincare";
  if (token === "euclidean") return "euclidean";
  return null;
}

export function listAvailableGeometries(layouts: string[]): Geometry[] {
  const geometries = new Set<Geometry>();
  for (const layoutKey of layouts) {
    const geometry = getLayoutGeometry(layoutKey);
    if (geometry) geometries.add(geometry);
  }
  return Array.from(geometries);
}
