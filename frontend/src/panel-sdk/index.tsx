"use client";

import React, { useCallback, useMemo } from "react";

import { useDockviewContext } from "@/components/DockviewContext";
import { usePanelInstance } from "@/components/PanelHostContext";
import {
  apiRequest,
  apiUrl,
  fetchCollectionItems,
  fetchDataset,
  fetchRuntimeState,
  getRuntimeClientId,
  isAbortError,
  isStaticBundle,
  runControlCommand,
  runtimeSnapshotFromCommandResult,
  type ControlCommandResult,
} from "@/lib/api";
import { RUNTIME_PANEL_PREFIX } from "@/lib/dockviewPanelPolicy";
import { useStore } from "@/store/useStore";
import type { DatasetInfo, RuntimeCollection, RuntimeSnapshot, Sample } from "@/types";

interface CommandEnvelope {
  target?: Record<string, unknown>;
  args?: Record<string, unknown>;
}

export interface CommandMetadata {
  id: string;
  owner: string;
  summary: string;
  target_schema: Record<string, unknown>;
  args_schema: Record<string, unknown>;
}

export interface HyperViewCommandClient {
  listCommands: () => Promise<CommandMetadata[]>;
  runCommand: (
    command: string,
    envelope?: CommandEnvelope
  ) => Promise<ControlCommandResult>;
}

export interface PanelResizeOptions {
  width?: number | null;
  height?: number | null;
  minWidth?: number | null;
  minHeight?: number | null;
  maxWidth?: number | null;
  maxHeight?: number | null;
}

function buildUrl(path: string, params?: Record<string, string | number | boolean | null | undefined>) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === null || value === undefined || value === "") continue;
    url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiRequest(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  return (await response.json()) as T;
}

export interface DatasetInfoResult {
  dataset: DatasetInfo | null;
  name: string | null;
  labels: string[];
  numSamples: number;
  labelCounts: Map<string, number>;
  loading: boolean;
  error: string | null;
}

export function useDatasetInfo(): DatasetInfoResult {
  const cachedDataset = useStore((state) => state.datasetInfo);
  const setDatasetInfo = useStore((state) => state.setDatasetInfo);
  const embeddingsByLayoutKey = useStore((state) => state.embeddingsByLayoutKey);
  const activeLayoutKey = useStore((state) => state.activeLayoutKey);
  const [loading, setLoading] = React.useState(cachedDataset === null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (cachedDataset) {
      setLoading(false);
      return;
    }

    const abort = new AbortController();
    setLoading(true);
    setError(null);
    void fetchDataset(abort.signal)
      .then(setDatasetInfo)
      .catch((reason) => {
        if (abort.signal.aborted || isAbortError(reason)) return;
        setError(reason instanceof Error ? reason.message : "Failed to load dataset information");
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false);
      });
    return () => abort.abort();
  }, [cachedDataset, setDatasetInfo]);

  const resolvedLayoutKey = activeLayoutKey ?? cachedDataset?.layouts?.[0]?.layout_key ?? null;
  const embeddingLabels = resolvedLayoutKey
    ? embeddingsByLayoutKey[resolvedLayoutKey]?.labels ?? null
    : null;
  const labelCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const label of embeddingLabels ?? []) {
      const key = label ?? "undefined";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return counts;
  }, [embeddingLabels]);

  return useMemo(
    () => ({
      dataset: cachedDataset,
      name: cachedDataset?.name ?? null,
      labels: cachedDataset?.labels ?? [],
      numSamples: cachedDataset?.num_samples ?? 0,
      labelCounts,
      loading,
      error,
    }),
    [cachedDataset, error, labelCounts, loading]
  );
}

function workspaceTarget(workspaceId: string | null) {
  return { workspace_id: workspaceId ?? "default" };
}

function panelLayoutPatch(options: PanelResizeOptions): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  if ("width" in options) patch.width = options.width ?? null;
  if ("height" in options) patch.height = options.height ?? null;
  if ("minWidth" in options) patch.min_width = options.minWidth ?? null;
  if ("minHeight" in options) patch.min_height = options.minHeight ?? null;
  if ("maxWidth" in options) patch.max_width = options.maxWidth ?? null;
  if ("maxHeight" in options) patch.max_height = options.maxHeight ?? null;
  return patch;
}

export function createHyperViewPanelClient(workspaceId: string | null): HyperViewCommandClient {
  return {
    async listCommands() {
      const payload = await fetchJson<{ commands: CommandMetadata[] }>(
        buildUrl(apiUrl("/control/commands"), { workspace_id: workspaceId })
      );
      return payload.commands;
    },
    async runCommand(command, envelope) {
      return runControlCommand({
        command,
        target: envelope?.target ?? workspaceTarget(workspaceId),
        args: envelope?.args ?? {},
      });
    },
  };
}

export function useCommandClient(): HyperViewCommandClient {
  const workspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);

  return useMemo(() => {
    const client = createHyperViewPanelClient(workspaceId);
    return {
      listCommands: client.listCommands,
      runCommand: async (command: string, envelope?: CommandEnvelope) => {
        const payload = await client.runCommand(command, envelope);
        if (payload.snapshot) {
          applyRuntimeSnapshot(payload.snapshot);
        }
        return payload;
      },
    };
  }, [applyRuntimeSnapshot, workspaceId]);
}

export function usePanelState(panelIdOverride?: string) {
  const instance = usePanelInstance();
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const fallbackState = useStore((state) =>
    panelIdOverride ? state.panelStates[panelIdOverride] : undefined
  );
  const resolvedPanelId = instance.panelId ?? panelIdOverride ?? null;
  const resolvedState = instance.panelId ? instance.state : fallbackState?.state ?? instance.state;
  const resolvedStateRevision = instance.panelId
    ? instance.stateRevision
    : fallbackState?.state_revision ?? instance.stateRevision;

  const patchState = useCallback(
    async (
      statePatch: Record<string, unknown>,
      args?: {
        replaceState?: boolean;
        expectedRevision?: number | null;
      }
    ) => {
      if (!activeWorkspaceId || !resolvedPanelId) {
        throw new Error("No active panel instance");
      }
      const payload = await runControlCommand({
        command: "workspace.panel.state.patch",
        target: {
          workspace_id: activeWorkspaceId,
          panel_id: resolvedPanelId,
        },
        args: {
          state: statePatch,
          replace_state: args?.replaceState ?? false,
          expected_revision: args?.expectedRevision ?? null,
          client_id: getRuntimeClientId(),
        },
      });
      const snapshot = runtimeSnapshotFromCommandResult(payload);
      applyRuntimeSnapshot(snapshot);
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot, resolvedPanelId]
  );

  return useMemo(
    () => ({
      panel: instance.panel,
      panelId: resolvedPanelId,
      props: instance.props,
      state: resolvedState,
      stateRevision: resolvedStateRevision,
      patchState,
    }),
    [
      instance.panel,
      resolvedPanelId,
      instance.props,
      resolvedState,
      resolvedStateRevision,
      patchState,
    ]
  );
}

export function useSelection() {
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const selectedIds = useStore((state) => state.selectedIds);
  const selectionSource = useStore((state) => state.selectionSource);
  const clearLassoSelection = useStore((state) => state.clearLassoSelection);
  const setSelectedIds = useStore((state) => state.setSelectedIds);

  const persistSelection = useCallback(
    async (ids: string[]) => {
      if (!activeWorkspaceId) {
        throw new Error("No active workspace");
      }
      const sampleIds = Array.from(new Set(ids));
      clearLassoSelection();
      if (isStaticBundle()) {
        setSelectedIds(new Set(sampleIds), "panel");
        return fetchRuntimeState(activeWorkspaceId);
      }
      await fetchJson(apiUrl("/control/ui/selection"), {
        method: "POST",
        body: JSON.stringify({
          workspace_id: activeWorkspaceId,
          sample_ids: sampleIds,
        }),
      });
      const snapshot = await fetchJson<RuntimeSnapshot>(
        buildUrl(apiUrl("/runtime"), { workspace_id: activeWorkspaceId })
      );
      applyRuntimeSnapshot(snapshot);
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot, clearLassoSelection, setSelectedIds]
  );

  return useMemo(
    () => ({
      selectedIds: Array.from(selectedIds),
      selectionSource,
      setSelection: persistSelection,
      clearSelection: () => persistSelection([]),
    }),
    [persistSelection, selectedIds, selectionSource]
  );
}

export function useCollection(collectionId?: string | null): RuntimeCollection | null {
  const runtimeCollections = useStore((state) => state.runtimeCollections);
  return useMemo(() => {
    if (!collectionId) return null;
    return runtimeCollections.find((collection) => collection.id === collectionId) ?? null;
  }, [collectionId, runtimeCollections]);
}

const DEFAULT_COLLECTION_PAGE_SIZE = 60;

interface CollectionSamplesState {
  key: string | null;
  samples: Sample[];
  scores: Record<string, number> | null;
  total: number;
  hasMore: boolean;
}

const EMPTY_COLLECTION_SAMPLES: CollectionSamplesState = {
  key: null,
  samples: [],
  scores: null,
  total: 0,
  hasMore: false,
};

export function useSamples(
  collectionId?: string | null,
  options?: { pageSize?: number }
) {
  const collection = useCollection(collectionId);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);

  const pageSize = Math.max(1, options?.pageSize ?? DEFAULT_COLLECTION_PAGE_SIZE);
  const materialized = collection !== null;
  // created_at is part of the identity: replacing a collection under the same
  // id (e.g. a new search) must invalidate the loaded pages.
  const collectionKey = collection
    ? `${collection.id}:${collection.created_at}`
    : null;

  const [remote, setRemote] = React.useState<CollectionSamplesState>(
    EMPTY_COLLECTION_SAMPLES
  );
  const [remoteLoading, setRemoteLoading] = React.useState(false);
  const [remoteError, setRemoteError] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  const fetchPage = React.useCallback(
    async (offset: number, append: boolean) => {
      if (!materialized || !collection || !collectionKey) return;
      abortRef.current?.abort();
      const abort = new AbortController();
      abortRef.current = abort;
      setRemoteLoading(true);
      setRemoteError(null);
      try {
        const page = await fetchCollectionItems(collection.id, {
          workspaceId: activeWorkspaceId,
          offset,
          limit: pageSize,
          signal: abort.signal,
        });
        if (abort.signal.aborted) return;
        setRemote((current) => {
          const scores: Record<string, number> = {
            ...(append && current.key === collectionKey ? current.scores : null),
          };
          let hasScores = Object.keys(scores).length > 0;
          for (const item of page.items) {
            if (item.score !== null) {
              scores[item.sample.id] = item.score;
              hasScores = true;
            }
          }
          const previous =
            append && current.key === collectionKey ? current.samples : [];
          return {
            key: collectionKey,
            samples: [...previous, ...page.items.map((item) => item.sample)],
            scores: hasScores ? scores : null,
            total: page.total,
            hasMore: page.hasMore,
          };
        });
      } catch (error) {
        if (abort.signal.aborted || isAbortError(error)) return;
        setRemoteError(
          error instanceof Error ? error.message : "Failed to load collection items"
        );
      } finally {
        if (!abort.signal.aborted) {
          setRemoteLoading(false);
        }
      }
    },
    [activeWorkspaceId, collection, collectionKey, materialized, pageSize]
  );

  React.useEffect(() => {
    if (!materialized) {
      abortRef.current?.abort();
      setRemote(EMPTY_COLLECTION_SAMPLES);
      setRemoteLoading(false);
      setRemoteError(null);
      return;
    }
    void fetchPage(0, false);
    return () => {
      abortRef.current?.abort();
    };
  }, [fetchPage, materialized]);

  const loadMore = React.useCallback(() => {
    if (!materialized || remoteLoading || !remote.hasMore) return;
    void fetchPage(remote.samples.length, true);
  }, [fetchPage, materialized, remote.hasMore, remote.samples.length, remoteLoading]);

  return useMemo(() => {
    if (materialized) {
      return {
        collection,
        samples: remote.key === collectionKey ? remote.samples : [],
        scores: remote.key === collectionKey ? remote.scores : null,
        total: remote.key === collectionKey ? remote.total : 0,
        loading: remoteLoading,
        error: remoteError,
        hasMore: remote.key === collectionKey ? remote.hasMore : false,
        loadMore,
      };
    }

    return {
      collection,
      samples: [],
      scores: null,
      total: 0,
      loading: false,
      error: collectionId ? `Collection ${collectionId} is not available` : null,
      hasMore: false,
      loadMore: () => {},
    };
  }, [
    collection,
    collectionKey,
    loadMore,
    materialized,
    remote,
    remoteError,
    remoteLoading,
    collectionId,
  ]);
}

export function useHostAdapter() {
  const dockview = useDockviewContext();
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);

  const focusPanel = useCallback(
    (panelId: string) => {
      const api = dockview.api;
      if (!api) return false;

      const runtimePanelId = `${RUNTIME_PANEL_PREFIX}${panelId}`;
      const panel = api.getPanel(panelId) ?? api.getPanel(runtimePanelId);
      if (!panel) return false;

      panel.api.setActive();
      panel.focus();
      return true;
    },
    [dockview.api]
  );

  const resizePanel = useCallback(
    async (panelId: string, options: PanelResizeOptions): Promise<RuntimeSnapshot> => {
      if (!activeWorkspaceId) {
        throw new Error("No active workspace");
      }
      const payload = await runControlCommand({
        command: "workspace.panel.resize",
        target: {
          workspace_id: activeWorkspaceId,
          panel_id: panelId,
        },
        args: panelLayoutPatch(options),
      });
      const snapshot = runtimeSnapshotFromCommandResult(payload);
      applyRuntimeSnapshot(snapshot);
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot]
  );

  return useMemo(
    () => ({
      focusPanel,
      resizePanel,
    }),
    [focusPanel, resizePanel]
  );
}

export interface HyperViewPanelSdkGlobal {
  version: "2";
  React: typeof React;
  hooks: {
    useCommandClient: typeof useCommandClient;
    usePanelState: typeof usePanelState;
    useSelection: typeof useSelection;
    useCollection: typeof useCollection;
    useSamples: typeof useSamples;
    useDatasetInfo: typeof useDatasetInfo;
    useHostAdapter: typeof useHostAdapter;
  };
  createClient: typeof createHyperViewPanelClient;
}

declare global {
  interface Window {
    HyperViewPanelSDK?: HyperViewPanelSdkGlobal;
  }
}

export function installHyperViewPanelSdkGlobal() {
  if (typeof window === "undefined") return;

  window.HyperViewPanelSDK = {
    version: "2",
    React,
    hooks: {
      useCommandClient,
      usePanelState,
      useSelection,
      useCollection,
      useSamples,
      useDatasetInfo,
      useHostAdapter,
    },
    createClient: createHyperViewPanelClient,
  };
}
