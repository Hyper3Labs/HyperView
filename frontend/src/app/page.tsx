"use client";

import { useEffect, useCallback, useMemo, useRef, useState } from "react";
import { Header } from "@/components";
import { DockviewWorkspace, DockviewProvider } from "@/components/DockviewWorkspace";
import { useStore } from "@/store/useStore";
import type { Sample } from "@/types";
import {
  fetchDataset,
  fetchSamples,
  fetchSamplesBatch,
  fetchLassoSelection,
} from "@/lib/api";

const SAMPLES_PER_PAGE = 100;

export default function Home() {
  const {
    samples,
    totalSamples,
    samplesLoaded,
    setSamples,
    appendSamples,
    addSamplesIfMissing,
    setDatasetInfo,
    setIsLoading,
    isLoading,
    error,
    setError,
    selectedIds,
    isLassoSelection,
    selectionSource,
    lassoQuery,
    lassoSamples,
    lassoTotal,
    lassoIsLoading,
    setLassoResults,
    labelFilter,
  } = useStore();

  const [loadingMore, setLoadingMore] = useState(false);
  const labelFilterRef = useRef<string | null>(labelFilter ?? null);

  // Initial data load - runs once on mount
  // Store setters are stable and don't need to be in deps
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        // Fetch dataset info and samples in parallel
        const [datasetInfo, samplesRes] = await Promise.all([
          fetchDataset(),
          fetchSamples(0, SAMPLES_PER_PAGE),
        ]);

        setDatasetInfo(datasetInfo);
        setSamples(samplesRes.samples, samplesRes.total);
      } catch (err) {
        console.error("Failed to load data:", err);
        setError(err instanceof Error ? err.message : "Failed to load data");
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch selected samples that aren't already loaded
  useEffect(() => {
    const fetchSelectedSamples = async () => {
      if (isLassoSelection) return;
      if (selectedIds.size === 0) return;
      if (selectionSource === "label") return;

      // Find IDs that are selected but not in our samples array
      const loadedIds = new Set(samples.map((s) => s.id));
      const missingIds = Array.from(selectedIds).filter((id) => !loadedIds.has(id));

      if (missingIds.length === 0) return;

      try {
        const fetchedSamples = await fetchSamplesBatch(missingIds);
        addSamplesIfMissing(fetchedSamples);
      } catch (err) {
        console.error("Failed to fetch selected samples:", err);
      }
    };

    fetchSelectedSamples();
  }, [selectedIds, samples, addSamplesIfMissing, isLassoSelection, selectionSource]);

  // Refetch samples when label filter changes (non-lasso mode)
  useEffect(() => {
    if (labelFilterRef.current === labelFilter) return;
    if (isLassoSelection) return;

    labelFilterRef.current = labelFilter ?? null;

    let cancelled = false;
    const run = async () => {
      try {
        const res = await fetchSamples(0, SAMPLES_PER_PAGE, labelFilter ?? undefined);
        if (cancelled) return;
        setSamples(res.samples, res.total);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load filtered samples:", err);
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [isLassoSelection, labelFilter, setSamples]);

  // Fetch initial lasso selection page when a new lasso query begins.
  useEffect(() => {
    if (!isLassoSelection) return;
    if (!lassoQuery) return;
    if (!lassoIsLoading) return;

    const abort = new AbortController();

    const run = async () => {
      try {
        const res = await fetchLassoSelection({
          layoutKey: lassoQuery.layoutKey,
          polygon: lassoQuery.polygon,
          offset: 0,
          limit: SAMPLES_PER_PAGE,
          signal: abort.signal,
        });
        if (abort.signal.aborted) return;
        setLassoResults(res.samples, res.total, false);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        console.error("Failed to fetch lasso selection:", err);
        setLassoResults([], 0, false);
      }
    };

    run();

    return () => abort.abort();
  }, [isLassoSelection, lassoIsLoading, lassoQuery, setLassoResults]);

  // Load more samples
  const loadMore = useCallback(async () => {
    if (loadingMore) return;

    if (isLassoSelection) {
      if (!lassoQuery) return;
      if (lassoIsLoading) return;
      if (!lassoIsLoading && lassoSamples.length >= lassoTotal) return;

      setLoadingMore(true);
      try {
        const res = await fetchLassoSelection({
          layoutKey: lassoQuery.layoutKey,
          polygon: lassoQuery.polygon,
          offset: lassoSamples.length,
          limit: SAMPLES_PER_PAGE,
        });
        setLassoResults(res.samples, res.total, true);
      } catch (err) {
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
    loadingMore,
    appendSamples,
    isLassoSelection,
    lassoIsLoading,
    lassoQuery,
    lassoSamples.length,
    lassoTotal,
    samplesLoaded,
    totalSamples,
    setLassoResults,
    labelFilter,
  ]);

  const displayedSamples = useMemo(() => {
    if (isLassoSelection) return lassoSamples;

    // When a selection comes from the scatter plot, bring selected samples to the top
    // so the user immediately sees what they clicked.
    if (selectionSource === "scatter" && selectedIds.size > 0) {
      const byId = new Map<string, Sample>();
      for (const s of samples) byId.set(s.id, s);

      const pinned: Sample[] = [];
      for (const id of selectedIds) {
        const s = byId.get(id);
        if (s) pinned.push(s);
      }

      if (pinned.length > 0) {
        const rest = samples.filter((s) => !selectedIds.has(s.id));
        return [...pinned, ...rest];
      }
    }

    return samples;
  }, [isLassoSelection, lassoSamples, samples, selectedIds, selectionSource]);

  const displayedTotal = isLassoSelection ? lassoTotal : totalSamples;
  const displayedHasMore = isLassoSelection ? displayedSamples.length < displayedTotal : samplesLoaded < totalSamples;

  if (error) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-destructive text-lg mb-2">Error</div>
            <div className="text-muted-foreground">{error}</div>
            <p className="text-muted-foreground mt-4 text-sm">
              Make sure the HyperView backend is running on port 6262.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <div className="text-muted-foreground">Loading dataset...</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <DockviewProvider
      samples={displayedSamples}
      onLoadMore={loadMore}
      hasMore={displayedHasMore}
    >
      <div className="h-screen flex flex-col bg-background">
        <Header />

        {/* Main content - dockable panels */}
        <div className="flex-1 bg-background overflow-hidden">
          <DockviewWorkspace />
        </div>
      </div>
    </DockviewProvider>
  );
}
