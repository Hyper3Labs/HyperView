import { create } from "zustand";
import type { DatasetInfo, EmbeddingsData, Geometry, Sample } from "@/types";

interface AppState {
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

  // Embeddings
  embeddings: EmbeddingsData | null;
  setEmbeddings: (data: EmbeddingsData) => void;

  // Current layout key (from embeddings)
  currentLayoutKey: string | null;

  // Geometry mode
  geometry: Geometry;
  setGeometry: (geometry: Geometry) => void;

  // Selection
  selectedIds: Set<string>;
  isLassoSelection: boolean;
  selectionSource: "scatter" | "grid" | "lasso" | null;
  setSelectedIds: (ids: Set<string>, source?: "scatter" | "grid") => void;
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
  embeddings: null,
  setEmbeddings: (data) => set({ embeddings: data, currentLayoutKey: data?.layout_key ?? null }),

  // Current layout key
  currentLayoutKey: null,

  // Geometry mode
  geometry: "euclidean",
  setGeometry: (geometry) => set({ geometry }),

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
