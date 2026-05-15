import type { Sample } from "@/types";

interface SampleCollectionBase {
  title: string;
  samples: Sample[];
  total: number;
  loading: boolean;
  hasMore: boolean;
  loadMore?: () => void;
  error?: string | null;
  emptyTitle: string;
  emptyDescription: string;
}

export interface SamplesCollection extends SampleCollectionBase {
  kind: "samples";
  meta: {
    source: "dataset" | "lasso";
    labelFilter: string | null;
    scrollResetKey: string;
  };
}

export interface DerivedSamplesSpace {
  visible: boolean;
  selectionSamples: Sample[];
  neighborSamples: Sample[];
  neighborsMetric: string | null;
  neighborsLoading: boolean;
  hasMoreNeighbors: boolean;
  loadMoreNeighbors?: () => void;
  neighborsError: string | null;
  neighborsScrollResetKey: string;
}

export interface SamplesViewModel {
  collection: SamplesCollection;
  derivedSpace: DerivedSamplesSpace;
}
