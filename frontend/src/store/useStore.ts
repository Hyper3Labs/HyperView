import { create } from "zustand";
import type {
  DatasetInfo,
  EmbeddingsData,
  RuntimeCollection,
  RuntimePanel,
  RuntimePanelDefinition,
  RuntimePanelStateEntry,
  RuntimeSnapshot,
  Sample,
  SimilarityQuery,
  SimilarSample,
  WorkspaceSummary,
} from "@/types";
import { normalizeLabel } from "@/lib/labelColors";

function createClearedLassoState() {
  return {
    isLassoSelection: false,
    lassoQuery: null,
    lassoSamples: [] as Sample[],
    lassoTotal: 0,
    lassoIsLoading: false,
  };
}

function createClearedNeighborsState() {
  return {
    neighborsResults: [] as SimilarSample[],
    neighborsMetric: null as string | null,
    neighborsLoading: false,
    neighborsError: null,
  };
}

function createClearedDatasetScopedState() {
  return {
    datasetInfo: null as DatasetInfo | null,
    samples: [] as Sample[],
    totalSamples: 0,
    samplesLoaded: 0,
    embeddingsByLayoutKey: {} as Record<string, EmbeddingsData>,
    runtimeCollections: [] as RuntimeCollection[],
    panelStates: {} as Record<string, RuntimePanelStateEntry>,
    activeLayoutKey: null as string | null,
    activeSimilarityQuery: null as SimilarityQuery | null,
    selectionLayoutKey: null as string | null,
    labelFilter: null as string | null,
    hoveredId: null as string | null,
    isLoading: false,
    error: null as string | null,
  };
}

function areSetsEqual<T>(left: Set<T>, right: Set<T>) {
  if (left.size !== right.size) return false;
  for (const value of left) {
    if (!right.has(value)) return false;
  }
  return true;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function coerceSimilarityQuery(value: unknown): SimilarityQuery | null {
  if (!isRecord(value)) return null;
  const anchorSampleId =
    typeof value.anchor_sample_id === "string" && value.anchor_sample_id.length > 0
      ? value.anchor_sample_id
      : null;
  const queryText =
    typeof value.query_text === "string" && value.query_text.length > 0
      ? value.query_text
      : null;
  if (!anchorSampleId && !queryText) return null;
  const k = typeof value.k === "number" ? value.k : Number(value.k ?? 18);
  return {
    anchor_sample_id: anchorSampleId,
    query_text: queryText,
    layout_key: typeof value.layout_key === "string" ? value.layout_key : null,
    space_key: typeof value.space_key === "string" ? value.space_key : null,
    k: Number.isFinite(k) ? Math.max(1, Math.min(k, 100)) : 18,
    source: typeof value.source === "string" ? value.source : null,
  };
}

function labelFilterFromSamplesPanelState(state: Record<string, unknown>): string | null {
  if (state.mode !== "collection" || !isRecord(state.collection)) return null;
  const collection = state.collection;
  if (collection.kind !== "filter" || !isRecord(collection.query)) return null;
  const { field, op, value } = collection.query;
  if (field !== "label" || op !== "eq") return null;
  return normalizeLabel(typeof value === "string" ? value : null);
}

type SelectionSource = "scatter" | "grid" | "panel";

export interface OrbitView3DPayload {
  yaw: number;
  pitch: number;
  distance: number;
  target_x: number;
  target_y: number;
  target_z: number;
  ortho_scale: number;
}

export interface LassoQueryPayload {
  layoutKey: string;
  polygon: number[];
  labelFilter: string | null;
  view3d: OrbitView3DPayload | null;
  viewportWidth: number | null;
  viewportHeight: number | null;
}

interface AppState {
  // Dataset info
  datasetInfo: DatasetInfo | null;
  setDatasetInfo: (info: DatasetInfo) => void;

  // Runtime / workspace state
  activeWorkspaceId: string | null;
  workspaces: WorkspaceSummary[];
  runtimeDatasetName: string | null;
  customPanels: RuntimePanel[];
  panelDefinitions: RuntimePanelDefinition[];
  runtimeCollections: RuntimeCollection[];
  panelStates: Record<string, RuntimePanelStateEntry>;
  workspaceLayout: Record<string, unknown> | null;
  workspaceLayoutRevision: number;
  setWorkspaceLayoutLocal: (layout: Record<string, unknown> | null) => void;
  hasExplicitView: boolean;
  activePanelId: string | null;
  viewRevision: number;
  requestedLayoutKey: string | null;
  layoutViews: Record<string, { camera_3d: OrbitView3DPayload | null }>;
  setLayoutViewCamera: (layoutKey: string, camera3d: OrbitView3DPayload | null) => void;
  applyRuntimeSnapshot: (snapshot: RuntimeSnapshot) => void;

  // Samples
  samples: Sample[];
  totalSamples: number;
  // Number of samples loaded via offset/limit pagination (excludes ad-hoc fetched samples)
  samplesLoaded: number;
  setSamples: (samples: Sample[], total: number) => void;
  appendSamples: (samples: Sample[]) => void;
  addSamplesIfMissing: (samples: Sample[]) => void;

  // Embeddings (cached per layout key)
  embeddingsByLayoutKey: Record<string, EmbeddingsData>;
  setEmbeddingsForLayout: (layoutKey: string, data: EmbeddingsData) => void;

  // Active layout (for sidebar context)
  activeLayoutKey: string | null;
  setActiveLayoutKey: (layoutKey: string | null) => void;
  activeSimilarityQuery: SimilarityQuery | null;

  // Label filter (sidebar-driven)
  labelFilter: string | null;
  setLabelFilter: (label: string | null) => void;

  // Selection
  selectedIds: Set<string>;
  isLassoSelection: boolean;
  selectionSource: SelectionSource | "lasso" | null;
  selectionLayoutKey: string | null;
  setSelectedIds: (
    ids: Set<string>,
    source?: SelectionSource,
    layoutKey?: string | null
  ) => void;
  toggleSelection: (id: string) => void;
  addToSelection: (ids: string[]) => void;
  clearSelection: () => void;

  // Lasso selection (server-driven)
  lassoQuery: LassoQueryPayload | null;
  lassoSamples: Sample[];
  lassoTotal: number;
  lassoIsLoading: boolean;
  beginLassoSelection: (query: LassoQueryPayload) => void;
  setLassoResults: (samples: Sample[], total: number, append?: boolean) => void;
  clearLassoSelection: () => void;

  // Neighbors / KNN state
  neighborsResults: SimilarSample[];
  neighborsMetric: string | null;
  neighborsLoading: boolean;
  neighborsError: string | null;
  beginNeighborsQuery: (resetResults?: boolean) => void;
  setNeighborsResults: (samples: SimilarSample[], metric: string | null) => void;
  setNeighborsError: (error: string) => void;
  clearNeighbors: () => void;

  // Hover state
  hoveredId: string | null;
  setHoveredId: (id: string | null) => void;

  // Loading states
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  // Error state
  error: string | null;
  setError: (error: string | null) => void;

  // UI state
  sampleGridSize: "small" | "medium" | "large";
  setSampleGridSize: (size: "small" | "medium" | "large") => void;
  scatterLabelOverlayMode: "off" | "auto" | "coarse" | "fine";
  setScatterLabelOverlayMode: (mode: "off" | "auto" | "coarse" | "fine") => void;
}

export const useStore = create<AppState>((set) => ({
  // Dataset info
  datasetInfo: null,
  setDatasetInfo: (info) => set({ datasetInfo: info }),

  // Runtime / workspace state
  activeWorkspaceId: null,
  workspaces: [],
  runtimeDatasetName: null,
  customPanels: [],
  panelDefinitions: [],
  runtimeCollections: [],
  panelStates: {},
  workspaceLayout: null,
  workspaceLayoutRevision: 0,
  setWorkspaceLayoutLocal: (workspaceLayout) => set({ workspaceLayout }),
  hasExplicitView: false,
  activePanelId: null,
  viewRevision: 0,
  requestedLayoutKey: null,
  layoutViews: {},
  setLayoutViewCamera: (layoutKey, camera3d) =>
    set((state) => ({
      layoutViews: {
        ...state.layoutViews,
        [layoutKey]: {
          ...(state.layoutViews[layoutKey] ?? {}),
          camera_3d: camera3d,
        },
      },
    })),
  applyRuntimeSnapshot: (snapshot) =>
    set((state) => {
      const nextWorkspaceId = snapshot.active_workspace_id;
      const nextDatasetName = snapshot.workspace.dataset_name;
      const runtimeScopeChanged =
        state.activeWorkspaceId !== nextWorkspaceId ||
        state.runtimeDatasetName !== nextDatasetName;

      const samplesPanelState = snapshot.workspace.ui.panels?.samples?.state ?? {};
      const activeSimilarityQuery = coerceSimilarityQuery(samplesPanelState.retrieval);
      const selectedIds = activeSimilarityQuery
        ? []
        : snapshot.workspace.ui.selected_ids;
      const labelFilter = labelFilterFromSamplesPanelState(samplesPanelState);

      return {
        ...(runtimeScopeChanged ? createClearedDatasetScopedState() : {}),
        activeWorkspaceId: nextWorkspaceId,
        workspaces: snapshot.workspaces,
        runtimeDatasetName: nextDatasetName,
        customPanels: snapshot.workspace.ui.custom_panels,
        panelDefinitions: snapshot.panel_definitions ?? [],
        runtimeCollections: snapshot.workspace.collections ?? [],
        panelStates: snapshot.workspace.ui.panels ?? {},
        workspaceLayout: snapshot.workspace.ui.layout ?? null,
        workspaceLayoutRevision: snapshot.workspace.ui.layout_revision ?? 0,
        hasExplicitView: snapshot.workspace.ui.has_explicit_view,
        activePanelId: snapshot.workspace.ui.active_panel_id,
        viewRevision: snapshot.workspace.ui.view_revision ?? 0,
        requestedLayoutKey: snapshot.workspace.ui.active_layout_key,
        layoutViews: snapshot.workspace.ui.layout_views ?? {},
        selectedIds: new Set(selectedIds),
        selectionSource: selectedIds.length > 0 ? "scatter" : null,
        selectionLayoutKey: null,
        activeSimilarityQuery,
        labelFilter,
        ...createClearedLassoState(),
        ...createClearedNeighborsState(),
      };
    }),

  // Samples
  samples: [],
  totalSamples: 0,
  samplesLoaded: 0,
  setSamples: (samples, total) => set({ samples, totalSamples: total, samplesLoaded: samples.length }),
  appendSamples: (newSamples) =>
    set((state) => {
      const existingIds = new Set(state.samples.map((s) => s.id));
      const toAdd = newSamples.filter((s) => !existingIds.has(s.id));

      // Advance pagination cursor by what the API returned (even if some IDs were prefetched).
      const samplesLoaded = state.samplesLoaded + newSamples.length;

      if (toAdd.length === 0) return { samplesLoaded };
      return { samples: [...state.samples, ...toAdd], samplesLoaded };
    }),
  addSamplesIfMissing: (newSamples) =>
    set((state) => {
      const existingIds = new Set(state.samples.map((s) => s.id));
      const toAdd = newSamples.filter((s) => !existingIds.has(s.id));
      if (toAdd.length === 0) return state;
      return { samples: [...state.samples, ...toAdd] };
    }),

  // Embeddings
  embeddingsByLayoutKey: {},
  setEmbeddingsForLayout: (layoutKey, data) =>
    set((state) => ({
      embeddingsByLayoutKey: { ...state.embeddingsByLayoutKey, [layoutKey]: data },
    })),

  // Active layout
  activeLayoutKey: null,
  setActiveLayoutKey: (layoutKey) => set({ activeLayoutKey: layoutKey }),
  activeSimilarityQuery: null,

  // Label filter
  labelFilter: null,
  setLabelFilter: (label) => {
    const nextLabel = label ? normalizeLabel(label) : null;
    set({
      labelFilter: nextLabel,
      selectedIds: new Set<string>(),
      selectionSource: null,
      selectionLayoutKey: null,
      activeSimilarityQuery: null,
      ...createClearedLassoState(),
      ...createClearedNeighborsState(),
    });
  },

  // Selection
  selectedIds: new Set<string>(),
  isLassoSelection: false,
  selectionSource: null,
  selectionLayoutKey: null,
  setSelectedIds: (ids, source = "grid", layoutKey = null) =>
    set((state) => {
      const nextSelectionSource = ids.size > 0 ? source : null;
      const nextSelectionLayoutKey =
        nextSelectionSource === "scatter" ? layoutKey : null;

      if (!state.isLassoSelection && areSetsEqual(state.selectedIds, ids)) {
        if (
          state.selectionSource === nextSelectionSource &&
          state.selectionLayoutKey === nextSelectionLayoutKey
        ) {
          return state;
        }

        return {
          selectionSource: nextSelectionSource,
          selectionLayoutKey: nextSelectionLayoutKey,
        };
      }

      return {
        selectedIds: ids,
        selectionSource: nextSelectionSource,
        selectionLayoutKey: nextSelectionLayoutKey,
        activeSimilarityQuery:
          state.activeSimilarityQuery?.anchor_sample_id &&
          ids.has(state.activeSimilarityQuery.anchor_sample_id)
            ? state.activeSimilarityQuery
            : null,
        ...createClearedLassoState(),
        ...createClearedNeighborsState(),
      };
    }),
  toggleSelection: (id) =>
    set((state) => {
      const newSet = new Set(state.selectedIds);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      // Manual selection from image grid, not lasso
      return {
        selectedIds: newSet,
        selectionSource: newSet.size > 0 ? "grid" : null,
        selectionLayoutKey: null,
        activeSimilarityQuery:
          state.activeSimilarityQuery?.anchor_sample_id &&
          newSet.has(state.activeSimilarityQuery.anchor_sample_id)
            ? state.activeSimilarityQuery
            : null,
        ...createClearedLassoState(),
        ...createClearedNeighborsState(),
      };
    }),
  addToSelection: (ids) =>
    set((state) => {
      const newSet = new Set(state.selectedIds);
      ids.forEach((id) => newSet.add(id));
      // Manual selection from image grid, not lasso
      return {
        selectedIds: newSet,
        selectionSource: newSet.size > 0 ? "grid" : null,
        selectionLayoutKey: null,
        activeSimilarityQuery:
          state.activeSimilarityQuery?.anchor_sample_id &&
          newSet.has(state.activeSimilarityQuery.anchor_sample_id)
            ? state.activeSimilarityQuery
            : null,
        ...createClearedLassoState(),
        ...createClearedNeighborsState(),
      };
    }),
  clearSelection: () =>
    set({
      selectedIds: new Set<string>(),
      selectionSource: null,
      selectionLayoutKey: null,
      activeSimilarityQuery: null,
      ...createClearedLassoState(),
      ...createClearedNeighborsState(),
    }),

  // Lasso selection (server-driven)
  lassoQuery: null,
  lassoSamples: [],
  lassoTotal: 0,
  lassoIsLoading: false,
  beginLassoSelection: (query) =>
    set({
      selectedIds: new Set<string>(),
      selectionSource: "lasso",
      selectionLayoutKey: null,
      activeSimilarityQuery: null,
      isLassoSelection: true,
      lassoQuery: query,
      lassoSamples: [],
      lassoTotal: 0,
      lassoIsLoading: true,
      ...createClearedNeighborsState(),
    }),
  setLassoResults: (samples, total, append = false) =>
    set((state) => ({
      lassoSamples: append ? [...state.lassoSamples, ...samples] : samples,
      lassoTotal: total,
      lassoIsLoading: false,
    })),
  clearLassoSelection: () =>
    set({
      selectionSource: null,
      ...createClearedLassoState(),
    }),

  // Neighbors
  ...createClearedNeighborsState(),
  beginNeighborsQuery: (resetResults = true) =>
    set((state) => ({
      neighborsResults: resetResults ? [] : state.neighborsResults,
      neighborsMetric: resetResults ? null : state.neighborsMetric,
      neighborsLoading: true,
      neighborsError: null,
    })),
  setNeighborsResults: (samples, metric) =>
    set({
      neighborsResults: samples,
      neighborsMetric: metric,
      neighborsLoading: false,
      neighborsError: null,
    }),
  setNeighborsError: (error) =>
    set({
      neighborsLoading: false,
      neighborsError: error,
    }),
  clearNeighbors: () => set(createClearedNeighborsState()),

  // Hover
  hoveredId: null,
  setHoveredId: (id) => set({ hoveredId: id }),

  // Loading
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),

  // Error
  error: null,
  setError: (error) => set({ error }),

  // UI state
  sampleGridSize: "medium",
  setSampleGridSize: (size) => set({ sampleGridSize: size }),
  scatterLabelOverlayMode: "off",
  setScatterLabelOverlayMode: (mode) => set({ scatterLabelOverlayMode: mode }),
}));
