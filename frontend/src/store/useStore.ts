import { create } from "zustand";
import type { DatasetInfo, EmbeddingsData, Sample, ViewMode } from "@/types";

interface AppState {
  // Dataset info
  datasetInfo: DatasetInfo | null;
  setDatasetInfo: (info: DatasetInfo) => void;

  // Samples
  samples: Sample[];
  totalSamples: number;
  setSamples: (samples: Sample[], total: number) => void;
  appendSamples: (samples: Sample[]) => void;
  addSamplesIfMissing: (samples: Sample[]) => void;

  // Embeddings
  embeddings: EmbeddingsData | null;
  setEmbeddings: (data: EmbeddingsData) => void;

  // View mode (euclidean or hyperbolic)
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;

  // Selection
  selectedIds: Set<string>;
  isLassoSelection: boolean;
  setSelectedIds: (ids: Set<string>) => void;
  toggleSelection: (id: string) => void;
  addToSelection: (ids: string[]) => void;
  clearSelection: () => void;

  // Lasso selection (server-driven)
  lassoQuery: { viewMode: ViewMode; polygon: number[] } | null;
  lassoSamples: Sample[];
  lassoTotal: number;
  lassoIsLoading: boolean;
  beginLassoSelection: (query: { viewMode: ViewMode; polygon: number[] }) => void;
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
  // Dataset info
  datasetInfo: null,
  setDatasetInfo: (info) => set({ datasetInfo: info }),

  // Samples
  samples: [],
  totalSamples: 0,
  setSamples: (samples, total) => set({ samples, totalSamples: total }),
  appendSamples: (newSamples) =>
    set((state) => ({
      samples: [...state.samples, ...newSamples],
    })),
  addSamplesIfMissing: (newSamples) =>
    set((state) => {
      const existingIds = new Set(state.samples.map((s) => s.id));
      const toAdd = newSamples.filter((s) => !existingIds.has(s.id));
      if (toAdd.length === 0) return state;
      return { samples: [...state.samples, ...toAdd] };
    }),

  // Embeddings
  embeddings: null,
  setEmbeddings: (data) => set({ embeddings: data }),

  // View mode
  viewMode: "hyperbolic",
  setViewMode: (mode) => set({ viewMode: mode }),

  // Selection
  selectedIds: new Set<string>(),
  isLassoSelection: false,
  setSelectedIds: (ids) =>
    set({
      selectedIds: ids,
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
