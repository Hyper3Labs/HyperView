"use client";

import React, { useCallback, useMemo } from "react";

import { useDockviewContext } from "@/components/DockviewContext";
import { Panel } from "@/components/Panel";
import { PanelHeader } from "@/components/PanelHeader";
import { usePanelInstance } from "@/components/PanelHostContext";
import {
  PanelToolbar,
  PanelToolbarButton,
  PanelToolbarIconButton,
} from "@/components/PanelToolbar";
import {
  apiRequest,
  apiUrl,
  fetchCollectionItems,
  fetchDataset,
  fetchEmbeddings,
  fetchLassoSelection,
  fetchRuntimeState,
  fetchSamplesBatch,
  fetchSimilarSamples,
  fetchStaticBundleManifest,
  getRuntimeClientId,
  isAbortError,
  isStaticBundle,
  listTools as listRuntimeTools,
  runControlCommand,
  runTool as runRuntimeTool,
  runtimeSnapshotFromCommandResult,
  SAMPLES_PANEL_ID,
  setLayoutView,
  updateStaticSelection,
  type ControlCommandResult,
  type CollectionItem,
  type OrbitView3DRequest,
  type ToolMetadata,
} from "@/lib/api";
import { RUNTIME_PANEL_PREFIX } from "@/lib/dockviewPanelPolicy";
import { useColorSettings } from "@/store/useColorSettings";
import { useStore } from "@/store/useStore";
import type {
  DatasetInfo,
  EmbeddingsData,
  LayoutInfo,
  RuntimeCollection,
  RuntimeSnapshot,
  Sample,
} from "@/types";

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
  setActiveLayout: (layoutKey: string | null) => Promise<RuntimeSnapshot>;
  setLayoutView: (
    layoutKey: string,
    camera3d: OrbitView3DRequest | null
  ) => Promise<RuntimeSnapshot>;
}

/** Whether natural-language text-query inference is available in this runtime. */
export function supportsTextSearch(dataset?: DatasetInfo | null): boolean {
  if (isStaticBundle()) return false;
  return Boolean(
    dataset?.indexes?.some((index) => index.query_modes.includes("text"))
  );
}

/** Hydration-safe reactive form of {@link supportsTextSearch}. */
export function useSupportsTextSearch(): boolean {
  const dataset = useStore((state) => state.datasetInfo);
  return supportsTextSearch(dataset);
}

/** Whether image-query similarity can be computed by this runtime. */
export function supportsSampleSimilarity(dataset?: DatasetInfo | null): boolean {
  return Boolean(
    dataset?.indexes?.some((index) => index.query_modes.includes("nearest"))
  );
}

/** Whether live or explicitly exported image-query similarity is available. */
export function useSupportsSampleSimilarity(): boolean {
  const dataset = useStore((state) => state.datasetInfo);
  const [supported, setSupported] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    if (!isStaticBundle()) {
      setSupported(supportsSampleSimilarity(dataset));
      return () => {
        cancelled = true;
      };
    }

    void fetchStaticBundleManifest()
      .then((manifest) => {
        if (!cancelled) {
          setSupported(manifest?.capabilities.sample_similarity === true);
        }
      })
      .catch(() => {
        if (!cancelled) setSupported(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dataset]);

  return supported;
}

/** Whether the current runtime can resolve a lasso for this layout dimension. */
export function supportsLassoSelection(layoutDimension: 2 | 3): boolean {
  return layoutDimension === 2 || !isStaticBundle();
}

/** Hydration-safe reactive form of {@link supportsLassoSelection}. */
export function useSupportsLassoSelection(layoutDimension: 2 | 3): boolean {
  const [supported, setSupported] = React.useState(true);
  React.useEffect(() => {
    setSupported(supportsLassoSelection(layoutDimension));
  }, [layoutDimension]);
  return supported;
}

/** Whether this panel can call Python-backed extension tools. */
export function useSupportsTools(): boolean {
  const [supported, setSupported] = React.useState(false);
  React.useEffect(() => {
    setSupported(!isStaticBundle());
  }, []);
  return supported;
}

export interface HyperViewToolClient {
  listTools: () => Promise<ToolMetadata[]>;
  runTool: <T = unknown>(
    tool: string,
    params?: Record<string, unknown>
  ) => Promise<T>;
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

/**
 * Address a collection command at a panel, or leave it workspace-scoped.
 *
 * Collection commands (`collection.filter.set`, `collection.selection.set`,
 * `collection.neighbors.create`) take an optional `panel_id`; omitting it
 * keeps the canonical Samples panel on both the live server and the static
 * bundle's command emulator.
 */
function collectionPanelTarget(panelId: string | null | undefined) {
  return panelId ? { panel_id: panelId } : undefined;
}

/**
 * The panel a collection command issued from this host should be addressed at.
 *
 * This is the write side of `usePanelInteractions`' read rule, and it has to
 * agree with it: a panel reads its own collection state once it owns a
 * collection, so that is exactly when it should write there too. A panel that
 * owns none -- the scatter panel, or an extension panel that only computes ids
 * for the shared sample view -- stays workspace-scoped, and the command lands
 * on the Samples panel as before. An explicit id always wins.
 */
function useCollectionOwnerPanelId(explicitPanelId?: string | null): string | null {
  const instance = usePanelInstance();
  const hostPanelId = instance.panelId ?? null;
  const hostOwnsCollection = useStore((state) => {
    if (!hostPanelId) return false;
    const collectionId = state.panelStates[hostPanelId]?.state?.collection_id;
    return typeof collectionId === "string" && collectionId.length > 0;
  });
  if (explicitPanelId) return explicitPanelId;
  return hostOwnsCollection ? hostPanelId : null;
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
        // The workspace is the client's to supply, so a panel addressing a
        // command at itself only has to pass `target: { panel_id }`.
        target: { ...workspaceTarget(workspaceId), ...(envelope?.target ?? {}) },
        args: envelope?.args ?? {},
      });
    },
    async setActiveLayout(layoutKey) {
      if (!workspaceId) throw new Error("No active workspace");
      if (isStaticBundle()) return fetchRuntimeState(workspaceId);
      const payload = await runControlCommand({
        command: "workspace.active-layout.set",
        target: { workspace_id: workspaceId },
        args: { layout_key: layoutKey, client_id: getRuntimeClientId() },
      });
      if (!payload.snapshot) throw new Error("Active layout command returned no snapshot");
      return payload.snapshot;
    },
    async setLayoutView(layoutKey, camera3d) {
      if (!workspaceId) throw new Error("No active workspace");
      const snapshot = await setLayoutView({ workspaceId, layoutKey, camera3d });
      return snapshot ?? fetchRuntimeState(workspaceId);
    },
  };
}

export function useCommandClient(): HyperViewCommandClient {
  const workspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const setActiveLayoutKey = useStore((state) => state.setActiveLayoutKey);
  const setLayoutViewCamera = useStore((state) => state.setLayoutViewCamera);

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
      setActiveLayout: async (layoutKey: string | null) => {
        setActiveLayoutKey(layoutKey);
        const snapshot = await client.setActiveLayout(layoutKey);
        if (!isStaticBundle()) applyRuntimeSnapshot(snapshot);
        return snapshot;
      },
      setLayoutView: async (layoutKey: string, camera3d: OrbitView3DRequest | null) => {
        setLayoutViewCamera(layoutKey, camera3d);
        const snapshot = await client.setLayoutView(layoutKey, camera3d);
        if (!isStaticBundle()) applyRuntimeSnapshot(snapshot);
        return snapshot;
      },
    };
  }, [applyRuntimeSnapshot, setActiveLayoutKey, setLayoutViewCamera, workspaceId]);
}

const STATIC_TOOLS_UNAVAILABLE =
  "Tools require the HyperView server and are unavailable in static exports.";

function assertToolsAvailable(): void {
  if (isStaticBundle()) {
    throw new Error(STATIC_TOOLS_UNAVAILABLE);
  }
}

export function useTool(): HyperViewToolClient {
  const workspaceId = useStore((state) => state.activeWorkspaceId);

  return useMemo(
    () => ({
      listTools: async () => {
        assertToolsAvailable();
        return listRuntimeTools();
      },
      runTool: async <T = unknown,>(
        tool: string,
        params?: Record<string, unknown>
      ): Promise<T> => {
        assertToolsAvailable();
        return runRuntimeTool<T>(tool, workspaceId ?? "default", params ?? {});
      },
    }),
    [workspaceId]
  );
}

export interface QueryResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export interface EmbeddingsQueryArgs {
  layoutKey?: string | null;
  layout_key?: string | null;
}

export type PanelQueryId = "embeddings" | "layouts";

export function useQuery(
  queryId: "embeddings",
  args?: EmbeddingsQueryArgs
): QueryResult<EmbeddingsData>;
export function useQuery(queryId: "layouts", args?: Record<string, never>): QueryResult<LayoutInfo[]>;
export function useQuery(
  queryId: PanelQueryId,
  args?: EmbeddingsQueryArgs | Record<string, never>
): QueryResult<EmbeddingsData | LayoutInfo[]> {
  const layoutKey =
    queryId === "embeddings"
      ? ((args as EmbeddingsQueryArgs | undefined)?.layoutKey ??
        (args as EmbeddingsQueryArgs | undefined)?.layout_key ??
        null)
      : null;
  const cachedDataset = useStore((state) => state.datasetInfo);
  const cachedEmbeddings = useStore((state) =>
    layoutKey ? state.embeddingsByLayoutKey[layoutKey] ?? null : null
  );
  const setDatasetInfo = useStore((state) => state.setDatasetInfo);
  const setEmbeddingsForLayout = useStore((state) => state.setEmbeddingsForLayout);
  const [revision, setRevision] = React.useState(0);
  const initialData =
    queryId === "layouts"
      ? cachedDataset?.layouts ?? null
      : cachedEmbeddings;
  const [remote, setRemote] = React.useState<{
    key: string;
    data: EmbeddingsData | LayoutInfo[] | null;
    loading: boolean;
    error: string | null;
  }>({ key: "", data: null, loading: initialData === null, error: null });
  const queryKey = `${queryId}:${layoutKey ?? "default"}:${revision}`;

  React.useEffect(() => {
    const abort = new AbortController();
    setRemote({ key: queryKey, data: null, loading: true, error: null });

    const pending =
      queryId === "layouts"
        ? fetchDataset(abort.signal).then((dataset) => {
            setDatasetInfo(dataset);
            return dataset.layouts;
          })
        : fetchEmbeddings(layoutKey ?? undefined).then((embeddings) => {
            setEmbeddingsForLayout(embeddings.layout_key, embeddings);
            return embeddings;
          });

    void pending
      .then((data) => {
        if (!abort.signal.aborted) {
          setRemote({ key: queryKey, data, loading: false, error: null });
        }
      })
      .catch((reason) => {
        if (abort.signal.aborted || isAbortError(reason)) return;
        setRemote({
          key: queryKey,
          data: null,
          loading: false,
          error: reason instanceof Error ? reason.message : `Failed to run ${queryId} query`,
        });
      });

    return () => abort.abort();
  }, [layoutKey, queryId, queryKey, setDatasetInfo, setEmbeddingsForLayout]);

  const data = remote.key === queryKey ? remote.data : initialData;
  const loading = remote.key === queryKey ? remote.loading : data === null;
  const error = remote.key === queryKey ? remote.error : null;
  const refetch = useCallback(() => setRevision((current) => current + 1), []);

  return useMemo(() => ({ data, loading, error, refetch }), [data, error, loading, refetch]);
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

export function usePanelActions() {
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);

  const focusPanel = useCallback(
    async (panelId: string) => {
      if (!activeWorkspaceId) throw new Error("No active workspace");
      const payload = await runControlCommand({
        command: "workspace.panel.focus",
        target: { workspace_id: activeWorkspaceId, panel_id: panelId },
        args: {},
      });
      const snapshot = runtimeSnapshotFromCommandResult(payload);
      applyRuntimeSnapshot(snapshot);
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot]
  );

  const updateProps = useCallback(
    async (panelId: string, props: Record<string, unknown>) => {
      if (!activeWorkspaceId) throw new Error("No active workspace");
      const payload = await runControlCommand({
        command: "workspace.panel.update-props",
        target: { workspace_id: activeWorkspaceId, panel_id: panelId },
        args: { props },
      });
      const snapshot = runtimeSnapshotFromCommandResult(payload);
      applyRuntimeSnapshot(snapshot);
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot]
  );

  return useMemo(() => ({ focusPanel, updateProps }), [focusPanel, updateProps]);
}

/**
 * Workspace selection, plus the lasso that presents one as a result set.
 *
 * `panelId` names the panel whose sample view a presented result set lands in;
 * by default it is the calling panel when that panel owns a collection, and the
 * Samples panel otherwise.
 */
export function useSelection(options?: { panelId?: string | null }) {
  const collectionPanelId = useCollectionOwnerPanelId(options?.panelId);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const selectedIds = useStore((state) => state.selectedIds);
  const selectionSource = useStore((state) => state.selectionSource);
  const clearLassoSelection = useStore((state) => state.clearLassoSelection);
  const setSelectedIds = useStore((state) => state.setSelectedIds);
  const [lassoLoading, setLassoLoading] = React.useState(false);
  const [lassoError, setLassoError] = React.useState<string | null>(null);

  const persistSelection = useCallback(
    async (ids: string[]) => {
      if (!activeWorkspaceId) {
        throw new Error("No active workspace");
      }
      const sampleIds = Array.from(new Set(ids));
      clearLassoSelection();
      if (isStaticBundle()) {
        setSelectedIds(new Set(sampleIds), "panel");
        return updateStaticSelection(sampleIds);
      }
      const payload = await runControlCommand({
        command: "workspace.selection.set",
        target: { workspace_id: activeWorkspaceId },
        args: { sample_ids: sampleIds, client_id: getRuntimeClientId() },
      });
      if (!payload.snapshot) throw new Error("Selection command returned no snapshot");
      const snapshot = payload.snapshot;
      applyRuntimeSnapshot(snapshot);
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot, clearLassoSelection, setSelectedIds]
  );

  const presentSelection = useCallback(
    async (ids: string[], source: string, panelId?: string | null) => {
      if (!activeWorkspaceId) throw new Error("No active workspace");
      const payload = await runControlCommand({
        command: "collection.selection.set",
        target: {
          workspace_id: activeWorkspaceId,
          ...collectionPanelTarget(panelId ?? collectionPanelId),
        },
        args: {
          sample_ids: Array.from(new Set(ids)),
          focus: true,
          source,
        },
      });
      const snapshot = runtimeSnapshotFromCommandResult(payload);
      applyRuntimeSnapshot(snapshot);
      clearLassoSelection();
      return snapshot;
    },
    [activeWorkspaceId, applyRuntimeSnapshot, clearLassoSelection, collectionPanelId]
  );

  const selectLasso = useCallback(
    async (query: {
      layoutKey: string;
      polygon: ArrayLike<number>;
      labelFilter?: string | null;
      view3d?: OrbitView3DRequest | null;
      viewportWidth?: number | null;
      viewportHeight?: number | null;
      panelId?: string | null;
    }) => {
      setLassoLoading(true);
      setLassoError(null);
      try {
        const pageSize = 2000;
        const ids: string[] = [];
        let offset = 0;
        let total = 0;
        do {
          const page = await fetchLassoSelection({
            ...query,
            labelFilter: query.labelFilter ?? undefined,
            offset,
            limit: pageSize,
          });
          ids.push(...page.sample_ids);
          total = page.total;
          offset += page.sample_ids.length;
          if (page.sample_ids.length === 0) break;
        } while (offset < total);
        await presentSelection(ids, "scatter-lasso", query.panelId ?? null);
        return ids;
      } catch (reason) {
        const message = reason instanceof Error ? reason.message : "Lasso selection failed";
        setLassoError(message);
        throw reason;
      } finally {
        setLassoLoading(false);
      }
    },
    [presentSelection]
  );

  return useMemo(
    () => ({
      selectedIds: Array.from(selectedIds),
      selectionSource,
      setSelection: persistSelection,
      clearSelection: () => persistSelection([]),
      selectLasso,
      lassoLoading,
      lassoError,
    }),
    [lassoError, lassoLoading, persistSelection, selectLasso, selectedIds, selectionSource]
  );
}

/**
 * Present an explicit result set in a collection-backed sample view.
 *
 * The default target is the canonical Samples panel, which is what an
 * extension panel usually wants: it computes ids and Samples shows them. A
 * panel that owns its own sample view passes its instance id -- either once
 * (`useSampleResults({ panelId })`) or per call -- and the results land in
 * that panel's state instead.
 */
export function useSampleResults(options?: { panelId?: string | null }) {
  const commandClient = useCommandClient();
  const defaultPanelId = options?.panelId ?? null;

  const showResults = useCallback(
    async (
      ids: string[],
      options?: { focus?: boolean; source?: string; panelId?: string | null }
    ) => {
      const sampleIds = Array.from(new Set(ids.map((id) => id.trim()).filter(Boolean)));
      if (sampleIds.length === 0) throw new Error("showResults requires at least one sample id");
      return commandClient.runCommand("collection.selection.set", {
        target: collectionPanelTarget(options?.panelId ?? defaultPanelId),
        args: {
          sample_ids: sampleIds,
          focus: options?.focus ?? true,
          source: options?.source ?? "panel",
        },
      });
    },
    [commandClient, defaultPanelId]
  );

  const resetResults = useCallback(
    (options?: { focus?: boolean; source?: string; panelId?: string | null }) =>
      commandClient.runCommand("collection.selection.set", {
        target: collectionPanelTarget(options?.panelId ?? defaultPanelId),
        args: {
          clear: true,
          focus: options?.focus ?? true,
          source: options?.source ?? "panel",
        },
      }),
    [commandClient, defaultPanelId]
  );

  return useMemo(
    () => ({ showResults, resetResults }),
    [resetResults, showResults]
  );
}

export function useActiveLayout() {
  const activeLayoutKey = useStore((state) => state.activeLayoutKey);
  const requestedLayoutKey = useStore((state) => state.requestedLayoutKey);
  const layoutViews = useStore((state) => state.layoutViews);
  const commandClient = useCommandClient();

  return useMemo(
    () => ({
      activeLayoutKey,
      requestedLayoutKey,
      layoutViews,
      setActiveLayout: commandClient.setActiveLayout,
      setLayoutView: commandClient.setLayoutView,
    }),
    [activeLayoutKey, commandClient.setActiveLayout, commandClient.setLayoutView, layoutViews, requestedLayoutKey]
  );
}

/**
 * Read the hover, highlight and focus signals a panel renders against.
 *
 * The signals live in the state of whichever panel owns the collection-backed
 * sample view. That is the Samples panel by default -- which is what the
 * scatter panel and every panel without a collection of its own follows. A
 * panel that owns one (because collection commands were addressed at it) reads
 * its own state instead, and `panelId` names one explicitly.
 */
export function usePanelInteractions(options?: { panelId?: string | null }) {
  const instance = usePanelInstance();
  const hoveredId = useStore((state) => state.hoveredId);
  const setHoveredId = useStore((state) => state.setHoveredId);
  const labelFilter = useStore((state) => state.labelFilter);
  const panelStates = useStore((state) => state.panelStates);
  const runtimeCollections = useStore((state) => state.runtimeCollections);
  const scatterLabelOverlayMode = useStore((state) => state.scatterLabelOverlayMode);
  const setScatterLabelOverlayMode = useStore((state) => state.setScatterLabelOverlayMode);
  const labelColorMapId = useColorSettings((state) => state.labelColorMapId);
  const requestedPanelId = options?.panelId ?? instance.panelId ?? null;
  const requestedPanelState =
    requestedPanelId === null ? undefined : panelStates[requestedPanelId]?.state;
  const ownsCollection =
    typeof requestedPanelState?.collection_id === "string" &&
    requestedPanelState.collection_id.length > 0;
  const collectionPanelState = ownsCollection
    ? (requestedPanelState as Record<string, unknown>)
    : panelStates[SAMPLES_PANEL_ID]?.state ?? {};
  const collectionId =
    typeof collectionPanelState.collection_id === "string"
      ? collectionPanelState.collection_id
      : null;
  const collection = runtimeCollections.find((item) => item.id === collectionId) ?? null;
  const highlightedCollectionId =
    collection?.kind === "neighbors" || collection?.kind === "search"
      ? collection.id
      : null;
  const highlightedSamples = useSamples(highlightedCollectionId, { pageSize: 100 });
  const highlightedIds = useMemo(
    () => new Set(highlightedSamples.samples.map((sample) => sample.id)),
    [highlightedSamples.samples]
  );
  const rawFocusRequest = collectionPanelState.focus_request;
  const focusRequest = useMemo(() => {
    if (!rawFocusRequest || typeof rawFocusRequest !== "object" || Array.isArray(rawFocusRequest)) {
      return null;
    }
    const request = rawFocusRequest as Record<string, unknown>;
    const kind = request.kind === "selection" || request.kind === "all" ? request.kind : null;
    const revision = typeof request.revision === "number" ? request.revision : null;
    if (!kind || revision === null) return null;
    return { kind, revision } as const;
  }, [rawFocusRequest]);

  return useMemo(
    () => ({
      hoveredId,
      setHoveredId,
      labelFilter,
      highlightedIds,
      focusRequest,
      labelColorMapId,
      scatterLabelOverlayMode,
      setScatterLabelOverlayMode,
    }),
    [
      highlightedIds,
      focusRequest,
      hoveredId,
      labelColorMapId,
      labelFilter,
      scatterLabelOverlayMode,
      setHoveredId,
      setScatterLabelOverlayMode,
    ]
  );
}

export function useCollection(collectionId?: string | null): RuntimeCollection | null {
  const runtimeCollections = useStore((state) => state.runtimeCollections);
  return useMemo(() => {
    if (!collectionId) return null;
    return runtimeCollections.find((collection) => collection.id === collectionId) ?? null;
  }, [collectionId, runtimeCollections]);
}

export interface SimilarSamplesQuery {
  anchorSampleId: string;
  layoutKey?: string;
  spaceKey?: string;
  k?: number;
}

export function useSimilarSamples(query?: SimilarSamplesQuery | null) {
  const anchorSampleId = query?.anchorSampleId ?? null;
  const layoutKey = query?.layoutKey;
  const spaceKey = query?.spaceKey;
  const k = Math.max(1, Math.floor(query?.k ?? 10));
  const queryKey = anchorSampleId
    ? `${anchorSampleId}:${layoutKey ?? spaceKey ?? "default"}:${k}`
    : null;
  const [remote, setRemote] = React.useState<{
    key: string | null;
    querySample: Sample | null;
    samples: Sample[];
    metric: string | null;
    spaceKey: string | null;
    loading: boolean;
    error: string | null;
  }>({
    key: null,
    querySample: null,
    samples: [],
    metric: null,
    spaceKey: null,
    loading: false,
    error: null,
  });

  React.useEffect(() => {
    if (!anchorSampleId || !queryKey) {
      setRemote({
        key: null,
        querySample: null,
        samples: [],
        metric: null,
        spaceKey: null,
        loading: false,
        error: null,
      });
      return;
    }
    let cancelled = false;
    setRemote({
      key: queryKey,
      querySample: null,
      samples: [],
      metric: null,
      spaceKey: null,
      loading: true,
      error: null,
    });
    void fetchSimilarSamples(anchorSampleId, {
      k,
      layoutKey,
      spaceKey,
      includeThumbnails: true,
    })
      .then((response) => {
        if (!cancelled) {
          setRemote({
            key: queryKey,
            querySample: response.query_sample,
            samples: response.results,
            metric: response.metric,
            spaceKey: response.space_key,
            loading: false,
            error: null,
          });
        }
      })
      .catch((error) => {
        if (cancelled || isAbortError(error)) return;
        setRemote({
          key: queryKey,
          querySample: null,
          samples: [],
          metric: null,
          spaceKey: null,
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load similar samples",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [anchorSampleId, k, layoutKey, queryKey, spaceKey]);

  return useMemo(
    () => ({
      querySample: remote.key === queryKey ? remote.querySample : null,
      samples: remote.key === queryKey ? remote.samples : [],
      total: remote.key === queryKey ? remote.samples.length : 0,
      metric: remote.key === queryKey ? remote.metric : null,
      spaceKey: remote.key === queryKey ? remote.spaceKey : null,
      loading: remote.key === queryKey ? remote.loading : Boolean(queryKey),
      error: remote.key === queryKey ? remote.error : null,
    }),
    [queryKey, remote]
  );
}

const DEFAULT_COLLECTION_PAGE_SIZE = 60;
const MAX_COLLECTION_API_PAGE_SIZE = 500;

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
        const items: CollectionItem[] = [];
        let nextOffset = offset;
        let total = 0;
        let hasMore = true;
        while (items.length < pageSize && hasMore) {
          const page = await fetchCollectionItems(collection.id, {
            workspaceId: activeWorkspaceId,
            offset: nextOffset,
            limit: Math.min(MAX_COLLECTION_API_PAGE_SIZE, pageSize - items.length),
            signal: abort.signal,
          });
          items.push(...page.items);
          total = page.total;
          hasMore = page.hasMore;
          nextOffset += page.items.length;
          if (page.items.length === 0) break;
        }
        if (abort.signal.aborted) return;
        setRemote((current) => {
          const scores: Record<string, number> = {
            ...(append && current.key === collectionKey ? current.scores : null),
          };
          let hasScores = Object.keys(scores).length > 0;
          for (const item of items) {
            if (item.score !== null) {
              scores[item.sample.id] = item.score;
              hasScores = true;
            }
          }
          const previous =
            append && current.key === collectionKey ? current.samples : [];
          return {
            key: collectionKey,
            samples: [...previous, ...items.map((item) => item.sample)],
            scores: hasScores ? scores : null,
            total,
            hasMore,
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

/** Load one sample by id through the same live/static data contract. */
export function useSample(sampleId?: string | null) {
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const [sample, setSample] = React.useState<Sample | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    if (!sampleId) {
      setSample(null);
      setLoading(false);
      setError(null);
      return () => { cancelled = true; };
    }
    // A sample belongs to the requested id, so never expose the previous
    // request's value while the next one is loading. Panels commonly switch
    // an anchor and its surrounding copy in the same render; retaining the
    // old sample here produces a briefly incorrect (and sometimes captured)
    // pairing rather than a neutral loading state.
    setSample(null);
    setLoading(true);
    setError(null);
    void fetchSamplesBatch([sampleId], {
      includeThumbnails: true,
      workspaceId: activeWorkspaceId,
    }).then(([result]) => {
      if (!cancelled) setSample(result ?? null);
    }).catch((reason) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : "Failed to load sample");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [activeWorkspaceId, sampleId]);

  return useMemo(() => ({ sample, loading, error }), [error, loading, sample]);
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
  /**
   * The panel chrome the built-in panels are made of. An extension panel is
   * free to render anything, but a panel that only wants to look like the rest
   * of the workspace should not have to hand-roll a header and a toolbar out of
   * inline CSS.
   */
  components: {
    Panel: typeof Panel;
    PanelHeader: typeof PanelHeader;
    PanelToolbar: typeof PanelToolbar;
    PanelToolbarButton: typeof PanelToolbarButton;
    PanelToolbarIconButton: typeof PanelToolbarIconButton;
  };
  /**
   * Ids and other literals a panel would otherwise hard-code. `SAMPLES_PANEL_ID`
   * is the panel that owns the workspace's default sample view, and the panel a
   * collection command lands on when it names no other.
   */
  constants: {
    SAMPLES_PANEL_ID: typeof SAMPLES_PANEL_ID;
  };
  hooks: {
    useCommandClient: typeof useCommandClient;
    useQuery: typeof useQuery;
    usePanelState: typeof usePanelState;
    useSelection: typeof useSelection;
    useSampleResults: typeof useSampleResults;
    useActiveLayout: typeof useActiveLayout;
    usePanelInteractions: typeof usePanelInteractions;
    usePanelActions: typeof usePanelActions;
    useCollection: typeof useCollection;
    useSamples: typeof useSamples;
    useSample: typeof useSample;
    useSimilarSamples: typeof useSimilarSamples;
    useDatasetInfo: typeof useDatasetInfo;
    useTool: typeof useTool;
    listTools: typeof listRuntimeTools;
    useHostAdapter: typeof useHostAdapter;
    useSupportsLassoSelection: typeof useSupportsLassoSelection;
    useSupportsSampleSimilarity: typeof useSupportsSampleSimilarity;
    useSupportsTextSearch: typeof useSupportsTextSearch;
    useSupportsTools: typeof useSupportsTools;
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
    components: {
      Panel,
      PanelHeader,
      PanelToolbar,
      PanelToolbarButton,
      PanelToolbarIconButton,
    },
    constants: {
      SAMPLES_PANEL_ID,
    },
    hooks: {
      useCommandClient,
      useQuery,
      usePanelState,
      useSelection,
      useSampleResults,
      useActiveLayout,
      usePanelInteractions,
      usePanelActions,
      useCollection,
      useSamples,
      useSample,
      useSimilarSamples,
      useDatasetInfo,
      useTool,
      listTools: listRuntimeTools,
      useHostAdapter,
      useSupportsLassoSelection,
      useSupportsSampleSimilarity,
      useSupportsTextSearch,
      useSupportsTools,
    },
    createClient: createHyperViewPanelClient,
  };
}
