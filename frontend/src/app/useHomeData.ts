"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchDataset, isAbortError } from "@/lib/api";
import { useStore } from "@/store/useStore";

import { useRuntimeSync } from "./useRuntimeSync";

export function useHomeData(): {
  error: string | null;
  isLoading: boolean;
  retry: () => void;
} {
  const setDatasetInfo = useStore((state) => state.setDatasetInfo);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [retryRevision, setRetryRevision] = useState(0);
  const hasLoadedDataset = useRef(false);
  const refreshDataset = useCallback(
    async (signal?: AbortSignal) => {
      if (!hasLoadedDataset.current) setIsLoading(true);
      setError(null);
      try {
        const dataset = await fetchDataset(signal);
        if (!signal?.aborted) {
          hasLoadedDataset.current = true;
          setDatasetInfo(dataset);
        }
      } catch (refreshError: unknown) {
        if (isAbortError(refreshError)) return;
        console.error("Failed to load dataset metadata:", refreshError);
        setError(
          refreshError instanceof Error
            ? refreshError.message
            : "Failed to load dataset metadata"
        );
      } finally {
        if (!signal?.aborted) setIsLoading(false);
      }
    },
    [setDatasetInfo]
  );

  const { runtimeReady, runtimeResetKey } = useRuntimeSync();

  useEffect(() => {
    if (!runtimeReady) return;
    const controller = new AbortController();
    void refreshDataset(controller.signal);
    return () => controller.abort();
  }, [refreshDataset, retryRevision, runtimeReady, runtimeResetKey]);

  return {
    error,
    isLoading,
    retry: () => setRetryRevision((revision) => revision + 1),
  };
}
