import type { Geometry, LayoutInfo } from "@/types";

export function listAvailableGeometries(layouts: LayoutInfo[]): Geometry[] {
  const geometries = new Set<Geometry>();
  for (const layout of layouts) {
    geometries.add(layout.geometry);
  }
  return Array.from(geometries);
}

export function findLayoutByGeometry(layouts: LayoutInfo[], geometry: Geometry): LayoutInfo | undefined {
  return layouts.find((l) => l.geometry === geometry);
}

export function findLayoutByKey(layouts: LayoutInfo[], layoutKey: string): LayoutInfo | undefined {
  return layouts.find((l) => l.layout_key === layoutKey);
}
