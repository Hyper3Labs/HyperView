import type { Sample } from "@/types";

export type SampleTileKind = "image" | "text" | "video" | "metadata";

export const FIXED_TILE_ASPECT_RATIO = 4 / 3;

export function getSampleTileKind(sample: Sample): SampleTileKind {
  const mediaType = sample.media_type?.trim().toLowerCase() ?? "";

  if (mediaType.startsWith("image/")) return "image";
  if (mediaType.startsWith("text/")) return "text";
  if (mediaType.startsWith("video/")) return "video";

  const modality = sample.modality?.trim().toLowerCase() ?? "";
  if (modality === "image") return "image";
  if (modality === "text") return "text";
  if (modality === "video") return "video";

  return "metadata";
}

export function getSampleAspectRatio(sample: Sample): number {
  const width = sample.width;
  const height = sample.height;

  if (
    typeof width !== "number" ||
    typeof height !== "number" ||
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return FIXED_TILE_ASPECT_RATIO;
  }

  return width / height;
}
