"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchDataset,
  fetchLassoSelection,
  fetchSamples,
  fetchSamplesBatch,
  fetchSimilarSamples,
  isAbortError,
  isLayoutNotFoundError,
} from "@/lib/api";
import { findLayoutByKey } from "@/lib/layouts";
import type { SamplesCollection, SamplesViewModel } from "@/lib/sampleCollections";
import { useStore } from "@/store/useStore";
import type { DatasetInfo, Sample, SimilarityQuery } from "@/types";

import { useRuntimeSync } from "./useRuntimeSync";

const SAMPLES_PER_PAGE = 100;
const INITIAL_NEIGHBORS_LIMIT = 18;
const NEIGHBORS_PAGE_INCREMENT = 12;
const MAX_NEIGHBORS = 96;

function useRefreshDatasetMetadata() {
  const setDatasetInfo = useStore((state) => state.setDatasetInfo);

  return useCallback(async (signal?: AbortSignal) => {
    try {
      const dataset = await fetchDataset(signal);
      if (signal?.aborted) return;
      setDatasetInfo(dataset);
    } catch (refreshErr) {
      if (isAbortError(refreshErr)) return;
      console.error("Failed to refresh dataset metadata:", refreshErr);
    }
  }, [setDatasetInfo]);
}

function useSamplesDataFlow(
  refreshDatasetMetadata: (signal?: AbortSignal) => Promise<void>,
  runtimeResetKey: string
) {
  const datasetInfo = useStore((state) => state.datasetInfo);
  const samples = useStore((state) => state.samples);
  const totalSamples = useStore((state) => state.totalSamples);
  const samplesLoaded = useStore((state) => state.samplesLoaded);
  const setSamples = useStore((state) => state.setSamples);
  const appendSamples = useStore((state) => state.appendSamples);
  const addSamplesIfMissing = useStore((state) => state.addSamplesIfMissing);
  const setDatasetInfo = useStore((state) => state.setDatasetInfo);
  const setIsLoading = useStore((state) => state.setIsLoading);
  const isLoading = useStore((state) => state.isLoading);
  const error = useStore((state) => state.error);
  const setError = useStore((state) => state.setError);
  const selectedIds = useStore((state) => state.selectedIds);
  const isLassoSelection = useStore((state) => state.isLassoSelection);
  const selectionSource = useStore((state) => state.selectionSource);
  const lassoQuery = useStore((state) => state.lassoQuery);
  const lassoSamples = useStore((state) => state.lassoSamples);
  const lassoTotal = useStore((state) => state.lassoTotal);
  const lassoIsLoading = useStore((state) => state.lassoIsLoading);
  const setLassoResults = useStore((state) => state.setLassoResults);
  const clearLassoSelection = useStore((state) => state.clearLassoSelection);
  const labelFilter = useStore((state) => state.labelFilter);
  const activeLayoutKey = useStore((state) => state.activeLayoutKey);

  const [loadingMore, setLoadingMore] = useState(false);
  const [collectionLoading, setCollectionLoading] = useState(false);
  const labelFilterRef = useRef<string | null>(labelFilter ?? null);

  const selectedIdsList = useMemo(() => Array.from(selectedIds), [selectedIds]);
  const selectedAnchorId = selectedIdsList.length === 1 ? selectedIdsList[0] : null;

  const loadInitialData = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);

    try {
      const [nextDatasetInfo, samplesRes] = await Promise.all([
        fetchDataset(signal),
        fetchSamples(0, SAMPLES_PER_PAGE, undefined, signal),
      ]);
      if (signal?.aborted) return;

      setDatasetInfo(nextDatasetInfo);
      setSamples(samplesRes.samples, samplesRes.total);
    } catch (err) {
      if (isAbortError(err)) return;
      console.error("Failed to load data:", err);
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      if (signal?.aborted) return;
      setIsLoading(false);
    }
  }, [setDatasetInfo, setError, setIsLoading, setSamples]);

  useEffect(() => {
    const controller = new AbortController();
    void loadInitialData(controller.signal);

    return () => {
      controller.abort();
    };
  }, [loadInitialData, runtimeResetKey]);

  const retryInitialLoad = useCallback(() => {
    void loadInitialData();
  }, [loadInitialData]);

  useEffect(() => {
    const fetchSelectedSamples = async () => {
      if (isLassoSelection || selectedIds.size === 0) return;

      const loadedIds = new Set(samples.map((sample) => sample.id));
      const missingIds = Array.from(selectedIds).filter((id) => !loadedIds.has(id));

      if (missingIds.length === 0) return;

      try {
        const fetchedSamples = await fetchSamplesBatch(missingIds);
        addSamplesIfMissing(fetchedSamples);
      } catch (err) {
        console.error("Failed to fetch selected samples:", err);
      }
    };

    void fetchSelectedSamples();
  }, [addSamplesIfMissing, isLassoSelection, samples, selectedIds]);

  useEffect(() => {
    if (isLassoSelection) {
      setCollectionLoading(false);
      return;
    }

    if (labelFilterRef.current === labelFilter) return;

    labelFilterRef.current = labelFilter ?? null;

    let cancelled = false;
    setCollectionLoading(true);
    setSamples([], 0);

    const run = async () => {
      try {
        const res = await fetchSamples(0, SAMPLES_PER_PAGE, labelFilter ?? undefined);
        if (cancelled) return;
        setSamples(res.samples, res.total);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load filtered samples:", err);
      } finally {
        if (cancelled) return;
        setCollectionLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
      setCollectionLoading(false);
    };
  }, [isLassoSelection, labelFilter, setSamples]);

  useEffect(() => {
    if (!isLassoSelection || !lassoQuery || !lassoIsLoading) return;

    const abort = new AbortController();

    const run = async () => {
      try {
        const res = await fetchLassoSelection({
          layoutKey: lassoQuery.layoutKey,
          polygon: lassoQuery.polygon,
          labelFilter: lassoQuery.labelFilter ?? undefined,
          view3d: lassoQuery.view3d,
          viewportWidth: lassoQuery.viewportWidth,
          viewportHeight: lassoQuery.viewportHeight,
          offset: 0,
          limit: SAMPLES_PER_PAGE,
          signal: abort.signal,
        });

        if (abort.signal.aborted) return;
        setLassoResults(res.samples, res.total, false);
      } catch (err) {
        if (isAbortError(err)) return;

        if (isLayoutNotFoundError(err)) {
          clearLassoSelection();
          void refreshDatasetMetadata();
          return;
        }

        console.error("Failed to fetch lasso selection:", err);
        setLassoResults([], 0, false);
      }
    };

    void run();
    return () => abort.abort();
  }, [
    clearLassoSelection,
    isLassoSelection,
    lassoIsLoading,
    lassoQuery,
    refreshDatasetMetadata,
    setLassoResults,
  ]);

  const loadMore = useCallback(async () => {
    if (loadingMore || collectionLoading) return;

    if (isLassoSelection) {
      if (!lassoQuery || lassoIsLoading || lassoSamples.length >= lassoTotal) return;

      setLoadingMore(true);
      try {
        const res = await fetchLassoSelection({
          layoutKey: lassoQuery.layoutKey,
          polygon: lassoQuery.polygon,
          labelFilter: lassoQuery.labelFilter ?? undefined,
          view3d: lassoQuery.view3d,
          viewportWidth: lassoQuery.viewportWidth,
          viewportHeight: lassoQuery.viewportHeight,
          offset: lassoSamples.length,
          limit: SAMPLES_PER_PAGE,
        });
        setLassoResults(res.samples, res.total, true);
      } catch (err) {
        if (isLayoutNotFoundError(err)) {
          clearLassoSelection();
          void refreshDatasetMetadata();
          return;
        }

        console.error("Failed to load more lasso samples:", err);
      } finally {
        setLoadingMore(false);
      }
      return;
    }

    if (samplesLoaded >= totalSamples) return;

    setLoadingMore(true);
    try {
      const res = await fetchSamples(samplesLoaded, SAMPLES_PER_PAGE, labelFilter ?? undefined);
      appendSamples(res.samples);
    } catch (err) {
      console.error("Failed to load more samples:", err);
    } finally {
      setLoadingMore(false);
    }
  }, [
    appendSamples,
    clearLassoSelection,
    isLassoSelection,
    labelFilter,
    lassoIsLoading,
    lassoQuery,
    lassoSamples.length,
    lassoTotal,
    loadingMore,
    refreshDatasetMetadata,
    samplesLoaded,
    setLassoResults,
    collectionLoading,
    totalSamples,
  ]);

  return {
    activeLayoutKey,
    collectionLoading,
    datasetInfo,
    error,
    isLassoSelection,
    isLoading,
    labelFilter,
    lassoIsLoading,
    lassoQuery,
    lassoSamples,
    lassoTotal,
    loadMore,
    retryInitialLoad,
    samples,
    samplesLoaded,
    selectedAnchorId,
    selectedIds,
    selectedIdsList,
    selectionSource,
    totalSamples,
  };
}

function useNeighborsDataFlow(args: {
  activeLayoutKey: string | null;
  activeSimilarityQuery: SimilarityQuery | null;
  datasetInfo: DatasetInfo | null;
  isLassoSelection: boolean;
  selectedAnchorId: string | null;
  selectedCount: number;
}) {
  const {
    activeLayoutKey,
    activeSimilarityQuery,
    datasetInfo,
    isLassoSelection,
    selectedAnchorId,
    selectedCount,
  } = args;

  const neighborsResults = useStore((state) => state.neighborsResults);
  const neighborsMetric = useStore((state) => state.neighborsMetric);
  const neighborsLoading = useStore((state) => state.neighborsLoading);
  const neighborsError = useStore((state) => state.neighborsError);
  const beginNeighborsQuery = useStore((state) => state.beginNeighborsQuery);
  const setNeighborsResults = useStore((state) => state.setNeighborsResults);
  const setNeighborsError = useStore((state) => state.setNeighborsError);
  const clearNeighbors = useStore((state) => state.clearNeighbors);

  const [neighborsLimit, setNeighborsLimit] = useState(INITIAL_NEIGHBORS_LIMIT);
  const lastQueryKeyRef = useRef<string | null>(null);

  const resolvedNeighborLayout = useMemo(() => {
    if (!datasetInfo || datasetInfo.layouts.length === 0) return null;
    if (activeSimilarityQuery?.layout_key) {
      return findLayoutByKey(datasetInfo.layouts, activeSimilarityQuery.layout_key) ?? null;
    }
    if (activeSimilarityQuery?.space_key) {
      return (
        datasetInfo.layouts.find((layout) => layout.space_key === activeSimilarityQuery.space_key) ??
        null
      );
    }
    if (!activeLayoutKey) return datasetInfo.layouts[0] ?? null;
    return findLayoutByKey(datasetInfo.layouts, activeLayoutKey) ?? datasetInfo.layouts[0] ?? null;
  }, [activeLayoutKey, activeSimilarityQuery, datasetInfo]);

  const resolvedNeighborSpace = useMemo(() => {
    if (!datasetInfo) return null;
    if (activeSimilarityQuery?.space_key) {
      return (
        datasetInfo.spaces.find((space) => space.space_key === activeSimilarityQuery.space_key) ??
        null
      );
    }
    if (!resolvedNeighborLayout) return null;
    return (
      datasetInfo.spaces.find((space) => space.space_key === resolvedNeighborLayout.space_key) ??
      null
    );
  }, [activeSimilarityQuery, datasetInfo, resolvedNeighborLayout]);

  const resolvedNeighborAnchorId = activeSimilarityQuery?.anchor_sample_id ?? selectedAnchorId;
  const requestedNeighborsLimit = activeSimilarityQuery?.k ?? INITIAL_NEIGHBORS_LIMIT;

  useEffect(() => {
    setNeighborsLimit(requestedNeighborsLimit);
  }, [
    activeSimilarityQuery?.layout_key,
    activeSimilarityQuery?.space_key,
    requestedNeighborsLimit,
    resolvedNeighborAnchorId,
  ]);

  useEffect(() => {
    const hasExplicitSimilarityQuery = activeSimilarityQuery !== null;
    if (
      isLassoSelection ||
      (!hasExplicitSimilarityQuery && selectedCount !== 1) ||
      !resolvedNeighborAnchorId ||
      !resolvedNeighborSpace
    ) {
      lastQueryKeyRef.current = null;
      clearNeighbors();
      return;
    }

    const queryKey = [
      resolvedNeighborAnchorId,
      resolvedNeighborSpace.space_key,
      resolvedNeighborLayout?.layout_key ?? "none",
      activeSimilarityQuery?.source ?? "selection",
    ].join(":");
    const resetResults = lastQueryKeyRef.current !== queryKey;
    lastQueryKeyRef.current = queryKey;

    const abort = new AbortController();

    beginNeighborsQuery(resetResults);

    const run = async () => {
      try {
        const response = await fetchSimilarSamples(resolvedNeighborAnchorId, {
          k: neighborsLimit,
          spaceKey: activeSimilarityQuery?.layout_key ? undefined : resolvedNeighborSpace.space_key,
          layoutKey: activeSimilarityQuery?.layout_key ?? undefined,
          signal: abort.signal,
        });

        if (abort.signal.aborted) return;

        setNeighborsResults(response.results, response.metric);
      } catch (err) {
        if (isAbortError(err)) return;
        console.error("Failed to fetch neighbors:", err);
        setNeighborsError(err instanceof Error ? err.message : "Failed to fetch neighbors");
      }
    };

    void run();
    return () => abort.abort();
  }, [
    activeSimilarityQuery,
    beginNeighborsQuery,
    clearNeighbors,
    isLassoSelection,
    neighborsLimit,
    resolvedNeighborLayout?.layout_key,
    resolvedNeighborSpace,
    resolvedNeighborAnchorId,
    selectedCount,
    setNeighborsError,
    setNeighborsResults,
  ]);

  const loadMoreNeighbors = useCallback(() => {
    setNeighborsLimit((current) => Math.min(MAX_NEIGHBORS, current + NEIGHBORS_PAGE_INCREMENT));
  }, []);

  const hasMoreNeighbors = useMemo(() => {
    const hasExplicitSimilarityQuery = activeSimilarityQuery !== null;
    if (
      isLassoSelection ||
      (!hasExplicitSimilarityQuery && selectedCount !== 1) ||
      !resolvedNeighborAnchorId ||
      !resolvedNeighborSpace
    ) {
      return false;
    }
    return neighborsResults.length >= neighborsLimit && neighborsLimit < MAX_NEIGHBORS;
  }, [
    activeSimilarityQuery,
    isLassoSelection,
    neighborsLimit,
    neighborsResults.length,
    resolvedNeighborAnchorId,
    resolvedNeighborSpace,
    selectedCount,
  ]);

  return {
    neighborsError,
    neighborsLoading,
    neighborsMetric,
    neighborsResults,
    hasMoreNeighbors,
    loadMoreNeighbors,
    resolvedNeighborLayout,
    resolvedNeighborSpace,
  };
}

export function useHomeData(): {
  samplesView: SamplesViewModel;
  error: string | null;
  isLoading: boolean;
  retry: () => void;
} {
  const refreshDatasetMetadata = useRefreshDatasetMetadata();
  const runtimeResetKey = useRuntimeSync(async () => {
    await refreshDatasetMetadata();
  });
  const samplesFlow = useSamplesDataFlow(refreshDatasetMetadata, runtimeResetKey);
  const activeSimilarityQuery = useStore((state) => state.activeSimilarityQuery);
  const neighborsFlow = useNeighborsDataFlow({
    activeLayoutKey: samplesFlow.activeLayoutKey,
    activeSimilarityQuery,
    datasetInfo: samplesFlow.datasetInfo,
    isLassoSelection: samplesFlow.isLassoSelection,
    selectedAnchorId: samplesFlow.selectedAnchorId,
    selectedCount: samplesFlow.selectedIdsList.length,
  });

  const samplesById = useMemo(() => {
    const map = new Map<string, Sample>();
    for (const sample of samplesFlow.samples) {
      map.set(sample.id, sample);
    }
    return map;
  }, [samplesFlow.samples]);

  const selectedSamples = useMemo(() => {
    return samplesFlow.selectedIdsList
      .map((id) => samplesById.get(id) ?? null)
      .filter((sample): sample is Sample => sample !== null);
  }, [samplesById, samplesFlow.selectedIdsList]);

  const derivedNeighborSamples = useMemo(() => {
    if (samplesFlow.selectedIdsList.length !== 1) {
      return [] as Sample[];
    }

    return neighborsFlow.neighborsResults.filter(
      (sample) => !samplesFlow.selectedIds.has(sample.id)
    );
  }, [neighborsFlow.neighborsResults, samplesFlow.selectedIds, samplesFlow.selectedIdsList.length]);

  const neighborsSourceLabel = useMemo(() => {
    const space = neighborsFlow.resolvedNeighborSpace;
    if (!space) return null;
    const geometry = space.geometry ? ` · ${space.geometry}` : "";
    const layout = neighborsFlow.resolvedNeighborLayout?.method
      ? ` · ${neighborsFlow.resolvedNeighborLayout.method}`
      : "";
    return `${space.model_id}${geometry}${layout}`;
  }, [neighborsFlow.resolvedNeighborLayout, neighborsFlow.resolvedNeighborSpace]);

  const samplesCollection = useMemo<SamplesCollection>(() => {
    if (samplesFlow.isLassoSelection) {
      return {
        kind: "samples",
        title: "Samples",
        samples: samplesFlow.lassoSamples,
        total: samplesFlow.lassoTotal,
        loading: samplesFlow.lassoIsLoading,
        hasMore: samplesFlow.lassoSamples.length < samplesFlow.lassoTotal,
        loadMore: samplesFlow.loadMore,
        error: null,
        emptyTitle: "No samples in lasso",
        emptyDescription: "The current lasso did not return any samples.",
        meta: {
          source: "lasso",
          labelFilter: samplesFlow.labelFilter,
          scrollResetKey: `lasso:${samplesFlow.lassoQuery?.layoutKey ?? "none"}:${samplesFlow.lassoTotal}`,
        },
      };
    }

    return {
      kind: "samples",
      title: "Samples",
      samples: samplesFlow.samples,
      total: samplesFlow.totalSamples,
      loading: samplesFlow.collectionLoading,
      hasMore: samplesFlow.samplesLoaded < samplesFlow.totalSamples,
      loadMore: samplesFlow.loadMore,
      error: null,
      emptyTitle: samplesFlow.labelFilter ? "No samples match this filter" : "No samples available",
      emptyDescription: samplesFlow.labelFilter
        ? "Clear the current label filter to return to the full dataset."
        : "The dataset has no samples to display.",
      meta: {
        source: "dataset",
        labelFilter: samplesFlow.labelFilter,
        scrollResetKey: `dataset:${samplesFlow.labelFilter ?? "all"}`,
      },
    };
  }, [
    samplesFlow.collectionLoading,
    samplesFlow.samples,
    samplesFlow.isLassoSelection,
    samplesFlow.labelFilter,
    samplesFlow.lassoIsLoading,
    samplesFlow.lassoQuery?.layoutKey,
    samplesFlow.lassoSamples,
    samplesFlow.lassoTotal,
    samplesFlow.loadMore,
    samplesFlow.samplesLoaded,
    samplesFlow.totalSamples,
  ]);

  const samplesView = useMemo<SamplesViewModel>(
    () => ({
      collection: samplesCollection,
      derivedSpace: {
        visible: !samplesFlow.isLassoSelection && selectedSamples.length > 0,
        selectionSamples: selectedSamples,
        neighborSamples:
          samplesFlow.selectedIdsList.length === 1 ? derivedNeighborSamples : [],
        neighborsMetric:
          samplesFlow.selectedIdsList.length === 1 ? neighborsFlow.neighborsMetric : null,
        neighborsSourceLabel:
          samplesFlow.selectedIdsList.length === 1 ? neighborsSourceLabel : null,
        neighborsLoading:
          samplesFlow.selectedIdsList.length === 1 ? neighborsFlow.neighborsLoading : false,
        hasMoreNeighbors:
          samplesFlow.selectedIdsList.length === 1 ? neighborsFlow.hasMoreNeighbors : false,
        loadMoreNeighbors:
          samplesFlow.selectedIdsList.length === 1 ? neighborsFlow.loadMoreNeighbors : undefined,
        neighborsError:
          samplesFlow.selectedIdsList.length === 1 ? neighborsFlow.neighborsError : null,
        neighborsScrollResetKey: samplesFlow.selectedAnchorId
          ? `neighbors:${samplesFlow.selectedAnchorId}`
          : `selection:${samplesFlow.selectedIdsList.join(",")}`,
      },
    }),
    [
      derivedNeighborSamples,
      neighborsFlow.hasMoreNeighbors,
      neighborsFlow.loadMoreNeighbors,
      neighborsFlow.neighborsError,
      neighborsFlow.neighborsLoading,
      neighborsFlow.neighborsMetric,
      neighborsSourceLabel,
      samplesCollection,
      samplesFlow.isLassoSelection,
      samplesFlow.selectedAnchorId,
      samplesFlow.selectedIdsList,
      selectedSamples,
    ]
  );

  return {
    samplesView,
    error: samplesFlow.error,
    isLoading: samplesFlow.isLoading,
    retry: samplesFlow.retryInitialLoad,
  };
}
