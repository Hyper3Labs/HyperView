export interface Sample {
  id: string;
  filepath: string;
  filename: string;
  label: string | null;
  text?: string | null;
  modality?: string | null;
  media_type?: string | null;
  duration_s?: number | null;
  thumbnail: string | null;
  media_url?: string | null;
  thumbnail_url?: string | null;
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

export interface RepresentationInfo {
  id: string;
  entity_set_id: string;
  field_path: string;
  kind: string;
  shape: number[];
  model_id: string;
  provider: string;
  modality: string;
  geometry: Geometry | string;
  count: number;
}

export interface IndexInfo {
  id: string;
  representation_id: string;
  query_modes: string[];
  scorer: string;
}

export interface DatasetInfo {
  name: string;
  num_samples: number;
  labels: string[];
  fields?: Record<string, {
    type: "scalar" | "text" | "media" | "label" | "vector_ref";
    nullable: boolean;
    source: string;
  }>;
  spaces: SpaceInfo[];
  representations?: RepresentationInfo[];
  indexes?: IndexInfo[];
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
  query_id?: string | null;
  query_text?: string | null;
  query_sample: Sample | null;
  space_key: string | null;
  metric: string;
  k: number;
  results: SimilarSample[];
}

export interface SimilarityQuery {
  anchor_sample_id?: string | null;
  query_text?: string | null;
  layout_key: string | null;
  space_key: string | null;
  k: number;
  source: string | null;
}

export type CollectionKind =
  | "all"
  | "filter"
  | "selection"
  | "neighbors"
  | "lasso"
  | "search"
  | "tool_result"
  | "extension";

export interface RuntimeCollection {
  id: string;
  dataset_id: string;
  entity_set_id: string;
  kind: CollectionKind;
  query: Record<string, unknown>;
  scores: Record<string, number> | null;
  created_at: number;
}

export interface RuntimePanelStateEntry {
  state: Record<string, unknown>;
  state_revision: number;
}

export interface RuntimePanelData {
  module_src: string | null;
  static_compatible?: boolean;
  static_reason?: string | null;
}

export interface RuntimePanelDefinition {
  panel_type: string;
  label: string;
  title: string;
  source: string;
  renderer: string;
  extension: string | null;
  extension_panel: string | null;
  default_props: Record<string, unknown>;
  default_state: Record<string, unknown>;
  props_schema: Record<string, unknown> | null;
  state_schema: Record<string, unknown> | null;
  commands: string[];
  queries: string[];
  data_capabilities: string[];
  default_layout: Record<string, unknown>;
  allow_multiple: boolean;
  icon: string | null;
  category: string | null;
  static_compatible: boolean;
  static_reason: string | null;
}

export type RuntimePanelKind = "module" | "builtin";

export type RuntimePanelPosition = "center" | "right" | "bottom";

export type RuntimePanelDirection = "right" | "left" | "above" | "below" | "within";

export interface RuntimePanelLayout {
  position: RuntimePanelPosition;
  reference_panel_id: string | null;
  direction: RuntimePanelDirection | null;
  width: number | null;
  height: number | null;
  min_width: number | null;
  min_height: number | null;
  max_width: number | null;
  max_height: number | null;
}

export interface RuntimePanel {
  id: string;
  kind: RuntimePanelKind;
  panel_type: string;
  source: string;
  renderer: string;
  title: string;
  position: RuntimePanelPosition;
  builtin_panel: "samples" | string | null;
  extension: string | null;
  extension_panel: string | null;
  layout_key: string | null;
  geometry: Geometry | string | null;
  layout_dimension: number | null;
  reference_panel_id: string | null;
  direction: RuntimePanelDirection | null;
  width: number | null;
  height: number | null;
  min_width: number | null;
  min_height: number | null;
  max_width: number | null;
  max_height: number | null;
  visible: boolean;
  active: boolean;
  props: Record<string, unknown>;
  state_revision: number;
  layout: RuntimePanelLayout;
  data: RuntimePanelData;
}

export interface WorkspaceSummary {
  id: string;
  dataset_name: string | null;
}

export interface RuntimeWorkspaceState {
  id: string;
  dataset_name: string | null;
  collections: RuntimeCollection[];
  ui: {
    active_layout_key: string | null;
    selected_ids: string[];
    layout: Record<string, unknown> | null;
    layout_revision: number;
    panels: Record<string, RuntimePanelStateEntry>;
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
    has_explicit_view: boolean;
    active_panel_id: string | null;
    view_revision: number;
  };
}

export interface RuntimeSnapshot {
  runtime_id: string;
  version: number;
  active_workspace_id: string | null;
  panel_definitions: RuntimePanelDefinition[];
  workspaces: WorkspaceSummary[];
  workspace: RuntimeWorkspaceState;
}
