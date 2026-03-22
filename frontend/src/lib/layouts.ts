import type { Geometry, LayoutInfo } from "@/types";

const LAYOUT_DIMENSION_PATTERN = /__(2|3)d(?:_[0-9a-f]{8})?$/;

export function getLayoutDimension(layoutKey: string): 2 | 3 {
  const match = layoutKey.match(LAYOUT_DIMENSION_PATTERN);
  if (!match) {
    throw new Error(
      `Invalid layout key '${layoutKey}': expected a '__2d' or '__3d' suffix.`
    );
  }
  return Number(match[1]) as 2 | 3;
}

export function listAvailableGeometries(
  layouts: LayoutInfo[],
  layoutDimension?: 2 | 3
): Geometry[] {
  const geometries = new Set<Geometry>();
  for (const layout of layouts) {
    if (
      typeof layoutDimension === "number" &&
      getLayoutDimension(layout.layout_key) !== layoutDimension
    ) {
      continue;
    }
    geometries.add(layout.geometry);
  }
  return Array.from(geometries);
}

export function findLayoutByGeometry(
  layouts: LayoutInfo[],
  geometry: Geometry,
  layoutDimension?: 2 | 3
): LayoutInfo | undefined {
  return layouts.find(
    (l) =>
      l.geometry === geometry &&
      (typeof layoutDimension !== "number" || getLayoutDimension(l.layout_key) === layoutDimension)
  );
}

export function findLayoutByKey(layouts: LayoutInfo[], layoutKey: string): LayoutInfo | undefined {
  return layouts.find((l) => l.layout_key === layoutKey);
}
