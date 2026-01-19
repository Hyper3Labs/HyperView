export interface Sample {
  id: string;
  filepath: string;
  filename: string;
  label: string | null;
  thumbnail: string | null;
  metadata: Record<string, unknown>;
}

export type Geometry = "euclidean" | "poincare";

export interface SpaceInfo {
  space_key: string;
  model_id: string;
  dim: number;
  count: number;
}

export interface DatasetInfo {
  name: string;
  num_samples: number;
  labels: string[];
  label_colors: Record<string, string>;
  spaces: SpaceInfo[];
  layouts: string[];
}

export interface EmbeddingsData {
  layout_key: string;
  ids: string[];
  labels: (string | null)[];
  coords: [number, number][];
  label_colors: Record<string, string>;
}

export interface SamplesResponse {
  total: number;
  offset: number;
  limit: number;
  samples: Sample[];
}
