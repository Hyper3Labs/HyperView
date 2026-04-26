import { create } from "zustand";
import type {
  DatasetInfo,
  EmbeddingsData,
  RuntimePanel,
  RuntimeSnapshot,
  Sample,
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
    activeLayoutKey: null as string | null,
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
  // Panel visibility (for header toggles)
  leftPanelOpen: boolean;
  rightPanelOpen: boolean;
  bottomPanelOpen: boolean;
  setLeftPanelOpen: (open: boolean) => void;
  setRightPanelOpen: (open: boolean) => void;
  setBottomPanelOpen: (open: boolean) => void;

  // Dataset info
  datasetInfo: DatasetInfo | null;
  setDatasetInfo: (info: DatasetInfo) => void;

  // Runtime / workspace state
  activeWorkspaceId: string | null;
  workspaces: WorkspaceSummary[];
  runtimeDatasetName: string | null;
  customPanels: RuntimePanel[];
  requestedLayoutKey: string | null;
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

  // Label filter (sidebar-driven)
  labelFilter: string | null;
  setLabelFilter: (label: string | null) => void;

  // Selection
  selectedIds: Set<string>;
  isLassoSelection: boolean;
  selectionSource: "scatter" | "grid" | "lasso" | null;
  setSelectedIds: (ids: Set<string>, source?: "scatter" | "grid") => void;
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
  neighborsLoading: boolean;
  neighborsError: string | null;
  beginNeighborsQuery: (resetResults?: boolean) => void;
  setNeighborsResults: (samples: SimilarSample[]) => void;
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
  // Panel visibility (for header toggles)
  leftPanelOpen: false,
  rightPanelOpen: false,
  bottomPanelOpen: false,
  setLeftPanelOpen: (open) => set({ leftPanelOpen: open }),
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
  setBottomPanelOpen: (open) => set({ bottomPanelOpen: open }),

  // Dataset info
  datasetInfo: null,
  setDatasetInfo: (info) => set({ datasetInfo: info }),

  // Runtime / workspace state
  activeWorkspaceId: null,
  workspaces: [],
  runtimeDatasetName: null,
  customPanels: [],
  requestedLayoutKey: null,
  applyRuntimeSnapshot: (snapshot) =>
    set((state) => {
      const nextWorkspaceId = snapshot.active_workspace_id;
      const nextDatasetName = snapshot.workspace.dataset_name;
      const runtimeScopeChanged =
        state.activeWorkspaceId !== nextWorkspaceId ||
        state.runtimeDatasetName !== nextDatasetName;

      return {
        activeWorkspaceId: nextWorkspaceId,
        workspaces: snapshot.workspaces,
        runtimeDatasetName: nextDatasetName,
        customPanels: snapshot.workspace.ui.custom_panels,
        requestedLayoutKey: snapshot.workspace.ui.active_layout_key,
        selectedIds: new Set(snapshot.workspace.ui.selected_ids),
        selectionSource:
          snapshot.workspace.ui.selected_ids.length > 0 ? "scatter" : null,
        ...(runtimeScopeChanged ? createClearedDatasetScopedState() : {}),
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

  // Label filter
  labelFilter: null,
  setLabelFilter: (label) => {
    const nextLabel = label ? normalizeLabel(label) : null;
    set({
      labelFilter: nextLabel,
      selectedIds: new Set<string>(),
      selectionSource: null,
      ...createClearedLassoState(),
      ...createClearedNeighborsState(),
    });
  },

  // Selection
  selectedIds: new Set<string>(),
  isLassoSelection: false,
  selectionSource: null,
  setSelectedIds: (ids, source = "grid") =>
    set((state) => {
      const nextSelectionSource = ids.size > 0 ? source : null;

      if (!state.isLassoSelection && areSetsEqual(state.selectedIds, ids)) {
        if (state.selectionSource === nextSelectionSource) {
          return state;
        }

        return {
          selectionSource: nextSelectionSource,
        };
      }

      return {
        selectedIds: ids,
        selectionSource: nextSelectionSource,
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
        ...createClearedLassoState(),
        ...createClearedNeighborsState(),
      };
    }),
  clearSelection: () =>
    set({
      selectedIds: new Set<string>(),
      selectionSource: null,
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
      neighborsLoading: true,
      neighborsError: null,
    })),
  setNeighborsResults: (samples) =>
    set({
      neighborsResults: samples,
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
