export function formatDistanceValue(distance: number, significantDigits = 3): string | null {
  if (!Number.isFinite(distance)) return null;
  if (distance === 0) return "0";

  const absoluteDistance = Math.abs(distance);
  const formatted =
    absoluteDistance >= 1000 || absoluteDistance < 0.001
      ? distance.toExponential(Math.max(0, significantDigits - 1))
      : distance.toPrecision(significantDigits);

  return formatted
    .replace(/(\.\d*?[1-9])0+(e|$)/, "$1$2")
    .replace(/\.0+(e|$)/, "$1");
}

export function getDistanceMetricLabel(metric: string | null | undefined): string | null {
  if (!metric) return null;
  if (metric === "hyperboloid" || metric === "hyperbolic") return "hyperbolic distance";
  if (metric === "cosine") return "cosine distance";
  if (metric === "l2" || metric === "euclidean") return "Euclidean distance";
  return `${metric} distance`;
}
