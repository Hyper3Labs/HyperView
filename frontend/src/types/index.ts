export interface Sample {
  id: string;
  filepath: string;
  filename: string;
  label: string | null;
  thumbnail: string | null;
  media_url?: string | null;
  metadata: Record<string, unknown>;
  width: number | null;
  height: number | null;
}

export type Geometry = "euclidean" | "poincare" | "spherical";

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
  spaces: SpaceInfo[];
  layouts: LayoutInfo[];
}

export interface EmbeddingsData {
  layout_key: string;
  geometry: Geometry;
  ids: string[];
  labels: (string | null)[];
  coords: number[][];
}

export interface SamplesResponse {
  total: number;
  offset: number;
  limit: number;
  samples: Sample[];
}

export interface SimilarSample extends Sample {
  distance: number;
}

export interface SimilaritySearchResponse {
  query_id: string;
  query_sample: Sample | null;
  space_key: string | null;
  metric: string;
  k: number;
  results: SimilarSample[];
}

export interface RuntimePanelData {
  module_src: string | null;
}

export type RuntimePanelKind = "module" | "scatter";

export type RuntimePanelPosition = "center" | "right" | "bottom";

export type RuntimePanelDirection = "right" | "left" | "above" | "below" | "within";

export interface RuntimePanel {
  id: string;
  kind: RuntimePanelKind;
  title: string;
  position: RuntimePanelPosition;
  module_file: string | null;
  layout_key: string | null;
  geometry: Geometry | string | null;
  layout_dimension: number | null;
  reference_panel_id: string | null;
  direction: RuntimePanelDirection | null;
  data: RuntimePanelData;
}

export interface WorkspaceSummary {
  id: string;
  dataset_name: string | null;
}

export interface RuntimeWorkspaceState {
  id: string;
  dataset_name: string | null;
  ui: {
    active_layout_key: string | null;
    selected_ids: string[];
    layout_views: Record<
      string,
      {
        camera_3d: {
          yaw: number;
          pitch: number;
          distance: number;
          target_x: number;
          target_y: number;
          target_z: number;
          ortho_scale: number;
        } | null;
      }
    >;
    custom_panels: RuntimePanel[];
  };
}

export interface RuntimeSnapshot {
  runtime_id: string;
  version: number;
  active_workspace_id: string | null;
  workspaces: WorkspaceSummary[];
  workspace: RuntimeWorkspaceState;
}
