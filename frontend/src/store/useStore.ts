import { create } from "zustand";
import type { DatasetInfo, EmbeddingsData, Sample } from "@/types";
import { normalizeLabel } from "@/lib/labelColors";

function computeLabelSelection(embeddings: EmbeddingsData, label: string): Set<string> {
  const target = normalizeLabel(label);
  const ids = new Set<string>();
  for (let i = 0; i < embeddings.labels.length; i++) {
    if (normalizeLabel(embeddings.labels[i]) === target) {
      ids.add(embeddings.ids[i]);
    }
  }
  return ids;
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
  selectionSource: "scatter" | "grid" | "lasso" | "label" | null;
  setSelectedIds: (ids: Set<string>, source?: "scatter" | "grid" | "label") => void;
  toggleSelection: (id: string) => void;
  addToSelection: (ids: string[]) => void;
  clearSelection: () => void;

  // Lasso selection (server-driven)
  lassoQuery: { layoutKey: string; polygon: number[] } | null;
  lassoSamples: Sample[];
  lassoTotal: number;
  lassoIsLoading: boolean;
  beginLassoSelection: (query: { layoutKey: string; polygon: number[] }) => void;
  setLassoResults: (samples: Sample[], total: number, append?: boolean) => void;
  clearLassoSelection: () => void;

  // Hover state
  hoveredId: string | null;
  setHoveredId: (id: string | null) => void;

  // Loading states
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;

  // Error state
  error: string | null;
  setError: (error: string | null) => void;
}

export const useStore = create<AppState>((set, get) => ({
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
    set((state) => {
      const selectionUpdate =
        state.labelFilter &&
        state.selectionSource === "label" &&
        state.activeLayoutKey === layoutKey
          ? {
              selectedIds: computeLabelSelection(data, state.labelFilter),
              selectionSource: "label" as const,
            }
          : {};

      return {
        embeddingsByLayoutKey: { ...state.embeddingsByLayoutKey, [layoutKey]: data },
        ...selectionUpdate,
      };
    }),

  // Active layout
  activeLayoutKey: null,
  setActiveLayoutKey: (layoutKey) =>
    set((state) => {
      if (!layoutKey) return { activeLayoutKey: null };
      if (!state.labelFilter || state.selectionSource !== "label") {
        return { activeLayoutKey: layoutKey };
      }

      const embeddings = state.embeddingsByLayoutKey[layoutKey];
      if (!embeddings) {
        return {
          activeLayoutKey: layoutKey,
          selectedIds: new Set<string>(),
          selectionSource: "label",
        };
      }

      return {
        activeLayoutKey: layoutKey,
        selectedIds: computeLabelSelection(embeddings, state.labelFilter),
        selectionSource: "label",
      };
    }),

  // Label filter
  labelFilter: null,
  setLabelFilter: (label) =>
    set((state) => {
      const nextLabel = label ? normalizeLabel(label) : null;
      const nextState: Partial<AppState> = { labelFilter: nextLabel };

      if (nextLabel) {
        const layoutKey = state.activeLayoutKey;
        const embeddings = layoutKey ? state.embeddingsByLayoutKey[layoutKey] : null;
        nextState.selectedIds = embeddings ? computeLabelSelection(embeddings, nextLabel) : new Set<string>();
        nextState.selectionSource = "label";
        nextState.isLassoSelection = false;
        nextState.lassoQuery = null;
        nextState.lassoSamples = [];
        nextState.lassoTotal = 0;
        nextState.lassoIsLoading = false;
      } else if (state.selectionSource === "label") {
        nextState.selectedIds = new Set<string>();
        nextState.selectionSource = null;
      }

      return nextState;
    }),

  // Selection
  selectedIds: new Set<string>(),
  isLassoSelection: false,
  selectionSource: null,
  setSelectedIds: (ids, source = "grid") =>
    set({
      selectedIds: ids,
      selectionSource: ids.size > 0 ? source : null,
      isLassoSelection: false,
      lassoQuery: null,
      lassoSamples: [],
      lassoTotal: 0,
      lassoIsLoading: false,
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
        isLassoSelection: false,
        lassoQuery: null,
        lassoSamples: [],
        lassoTotal: 0,
        lassoIsLoading: false,
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
        isLassoSelection: false,
        lassoQuery: null,
        lassoSamples: [],
        lassoTotal: 0,
        lassoIsLoading: false,
      };
    }),
  clearSelection: () =>
    set({
      selectedIds: new Set<string>(),
      selectionSource: null,
      isLassoSelection: false,
      lassoQuery: null,
      lassoSamples: [],
      lassoTotal: 0,
      lassoIsLoading: false,
    }),

  // Lasso selection (server-driven)
  lassoQuery: null,
  lassoSamples: [],
  lassoTotal: 0,
  lassoIsLoading: false,
  beginLassoSelection: (query) =>
    set({
      isLassoSelection: true,
      selectedIds: new Set<string>(),
      selectionSource: "lasso",
      lassoQuery: query,
      lassoSamples: [],
      lassoTotal: 0,
      lassoIsLoading: true,
    }),
  setLassoResults: (samples, total, append = false) =>
    set((state) => ({
      lassoSamples: append ? [...state.lassoSamples, ...samples] : samples,
      lassoTotal: total,
      lassoIsLoading: false,
    })),
  clearLassoSelection: () =>
    set({
      isLassoSelection: false,
      selectionSource: null,
      lassoQuery: null,
      lassoSamples: [],
      lassoTotal: 0,
      lassoIsLoading: false,
    }),

  // Hover
  hoveredId: null,
  setHoveredId: (id) => set({ hoveredId: id }),

  // Loading
  isLoading: false,
  setIsLoading: (loading) => set({ isLoading: loading }),

  // Error
  error: null,
  setError: (error) => set({ error }),
}));
