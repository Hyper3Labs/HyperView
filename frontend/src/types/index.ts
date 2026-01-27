export interface Sample {
  id: string;
  filepath: string;
  filename: string;
  label: string | null;
  thumbnail: string | null;
  metadata: Record<string, unknown>;
  width: number | null;
  height: number | null;
}

export type Geometry = "euclidean" | "poincare";

export interface SpaceInfo {
  space_key: string;
  model_id: string;
  dim: number;
  count: number;
  provider: string;
  geometry: Geometry | string;
  config: Record<string, unknown> | null;
}

export interface LayoutInfo {
  layout_key: string;
  space_key: string;
  method: string;
  geometry: Geometry;
  count: number;
  params: Record<string, unknown> | null;
}

export interface DatasetInfo {
  name: string;
  num_samples: number;
  labels: string[];
  label_colors?: Record<string, string>;
  spaces: SpaceInfo[];
  layouts: LayoutInfo[];
}

export interface EmbeddingsData {
  layout_key: string;
  geometry: Geometry;
  ids: string[];
  labels: (string | null)[];
  coords: [number, number][];
  label_colors?: Record<string, string>;
}

export interface SamplesResponse {
  total: number;
  offset: number;
  limit: number;
  samples: Sample[];
}
