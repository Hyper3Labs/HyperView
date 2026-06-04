"use client";

import React, { useCallback, useMemo, useRef, useState } from "react";

import { useDockviewContext } from "@/components/DockviewContext";
import { Panel } from "@/components/Panel";
import { PanelHeader } from "@/components/PanelHeader";
import { PanelTitle } from "@/components/PanelTitle";
import {
  PanelToolbar,
  PanelToolbarButton,
  PanelToolbarMenu,
  type PanelToolbarItem,
} from "@/components/PanelToolbar";
import { apiUrl, getRuntimeClientId } from "@/lib/api";
import { getLayoutDimension } from "@/lib/layouts";
import { useHyperViewSamplesView } from "@/panels/runtime";
import { PANEL } from "@/panels/registry";
import { useStore, type OrbitView3DPayload } from "@/store/useStore";
import type {
  Geometry,
  LayoutInfo,
  RuntimePanel,
  RuntimeSnapshot,
  Sample,
  SimilarityQuery,
  SpaceInfo,
} from "@/types";

type SelectionUpdateSource = "scatter" | "grid" | "panel";
type BuiltinPanelRole = "samples" | "labels" | "explorer" | "scatter" | "euclidean" | "hyperbolic" | "spherical";

type PanelCommandPersistence = boolean | "background";
type PanelCommandPersistenceMode = "none" | "background" | "blocking";

interface PanelCommandOptions {
  persist?: PanelCommandPersistence;
}

interface SelectionCommandOptions extends PanelCommandOptions {
  source?: SelectionUpdateSource;
  clearLasso?: boolean;
}

interface LayoutCommandOptions extends PanelCommandOptions {}

interface SimilarityCommandOptions extends PanelCommandOptions {
  sampleId: string;
  layoutKey?: string | null;
  spaceKey?: string | null;
  k?: number;
  source?: string | null;
  focus?: BuiltinPanelRole | false;
}

interface RuntimeUiPatchSimilarity {
  sample_id: string;
  layout_key?: string | null;
  space_key?: string | null;
  k?: number;
  source?: string | null;
}

interface RuntimeUiPatch {
  set_active_layout?: boolean;
  active_layout_key?: string | null;
  set_selection?: boolean;
  selected_ids?: string[] | null;
  set_similarity_query?: boolean;
  similarity_query?: RuntimeUiPatchSimilarity | null;
}

interface LayoutFindQuery {
  layoutKey?: string | null;
  spaceKey?: string | null;
  geometry?: Geometry | string | null;
  modelId?: string | null;
  dimension?: 2 | 3 | number | null;
}

interface PanelInstanceContextValue {
  panel: RuntimePanel | null;
  panelId: string | null;
  props: Record<string, unknown>;
}

const PanelInstanceContext = React.createContext<PanelInstanceContextValue | null>(null);

export function PanelInstanceProvider({
  value,
  children,
}: {
  value: PanelInstanceContextValue;
  children: React.ReactNode;
}) {
  return React.createElement(PanelInstanceContext.Provider, { value }, children);
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
  const response = await fetch(path, {
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

function getPersistenceMode(
  persist: PanelCommandPersistence | undefined
): PanelCommandPersistenceMode {
  if (persist === false) return "none";
  if (persist === true) return "blocking";
  return "background";
}

export function createHyperViewPanelClient(workspaceId: string | null) {
  return {
    async getDatasetInfo() {
      return fetchJson(buildUrl(apiUrl("/dataset"), { workspace_id: workspaceId }));
    },
    async getRuntime() {
      return fetchJson(buildUrl(apiUrl("/runtime"), { workspace_id: workspaceId }));
    },
    async listSamples(args?: {
      offset?: number;
      limit?: number;
      includeThumbnails?: boolean;
    }) {
      return fetchJson(
        buildUrl(apiUrl("/samples"), {
          workspace_id: workspaceId,
          offset: args?.offset ?? 0,
          limit: args?.limit ?? 100,
          include_thumbnails: args?.includeThumbnails ?? true,
        })
      );
    },
    async querySamples(args?: {
      ids?: string[];
      labels?: Array<string | null>;
      metadata?: Record<string, unknown>;
      offset?: number;
      limit?: number;
      includeThumbnails?: boolean;
    }) {
      return fetchJson(apiUrl("/samples/query"), {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          ids: args?.ids ?? null,
          labels: args?.labels ?? null,
          metadata: args?.metadata ?? null,
          offset: args?.offset ?? 0,
          limit: args?.limit ?? 100,
          include_thumbnails: args?.includeThumbnails ?? true,
        }),
      });
    },
    async getSamplesByIds(
      ids: string[],
      args?: {
        includeThumbnails?: boolean;
      }
    ) {
      return fetchJson(apiUrl("/samples/query"), {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          ids,
          offset: 0,
          limit: Math.max(ids.length, 1),
          include_thumbnails: args?.includeThumbnails ?? true,
        }),
      });
    },
    async aggregateSamples(args?: {
      groupBy?: "label" | `metadata.${string}`;
      ids?: string[];
      labels?: Array<string | null>;
      metadata?: Record<string, unknown>;
    }) {
      return fetchJson(apiUrl("/samples/aggregate"), {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          group_by: args?.groupBy ?? "label",
          ids: args?.ids ?? null,
          labels: args?.labels ?? null,
          metadata: args?.metadata ?? null,
        }),
      });
    },
    async searchSimilar(
      sampleId: string,
      args?: {
        k?: number;
        spaceKey?: string | null;
        layoutKey?: string | null;
      }
    ) {
      return fetchJson(
        buildUrl(apiUrl(`/search/similar/${encodeURIComponent(sampleId)}`), {
          workspace_id: workspaceId,
          k: args?.k ?? 10,
          space_key: args?.spaceKey ?? undefined,
          layout_key: args?.layoutKey ?? undefined,
        })
      );
    },
    async setSimilarityQuery(args: {
      sampleId: string;
      layoutKey?: string | null;
      spaceKey?: string | null;
      k?: number;
      source?: string | null;
    }) {
      return fetchJson(apiUrl("/control/ui/similarity"), {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          sample_id: args.sampleId,
          layout_key: args.layoutKey ?? null,
          space_key: args.spaceKey ?? null,
          k: args.k ?? 18,
          source: args.source ?? "panel-client",
        }),
      });
    },
    async clearSimilarityQuery() {
      return fetchJson(apiUrl("/control/ui/similarity"), {
        method: "DELETE",
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
    },
    async getEmbeddings(layoutKey?: string | null) {
      return fetchJson(
        buildUrl(apiUrl("/embeddings"), {
          workspace_id: workspaceId,
          layout_key: layoutKey ?? undefined,
        })
      );
    },
    async setSelection(sampleIds: string[]) {
      return fetchJson(apiUrl("/control/ui/selection"), {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, sample_ids: sampleIds }),
      });
    },
    async selectSamples(args?: {
      ids?: string[];
      labels?: Array<string | null>;
      metadata?: Record<string, unknown>;
      limit?: number | null;
    }) {
      return fetchJson(apiUrl("/control/ui/selection/query"), {
        method: "POST",
        body: JSON.stringify({
          workspace_id: workspaceId,
          ids: args?.ids ?? null,
          labels: args?.labels ?? null,
          metadata: args?.metadata ?? null,
          limit: args?.limit ?? null,
        }),
      });
    },
    async setLayout(layoutKey: string | null) {
      return fetchJson(apiUrl("/control/ui/layout"), {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, layout_key: layoutKey }),
      });
    },
  };
}

export function usePanelClient() {
  const workspaceId = useStore((state) => state.activeWorkspaceId);
  return useMemo(() => createHyperViewPanelClient(workspaceId), [workspaceId]);
}

export function usePanelInstance() {
  return (
    React.useContext(PanelInstanceContext) ?? {
      panel: null,
      panelId: null,
      props: {},
    }
  );
}

export function usePanelProps() {
  return usePanelInstance().props;
}

export function usePanelSamplesView() {
  return useHyperViewSamplesView();
}

export function usePanelDatasetInfo() {
  return useStore((state) => state.datasetInfo);
}

export function usePanelSamples() {
  const samples = useStore((state) => state.samples);
  const totalSamples = useStore((state) => state.totalSamples);
  const samplesLoaded = useStore((state) => state.samplesLoaded);
  const isLoading = useStore((state) => state.isLoading);
  const error = useStore((state) => state.error);

  return useMemo(
    () => ({
      samples,
      totalSamples,
      samplesLoaded,
      isLoading,
      error,
    }),
    [error, isLoading, samples, samplesLoaded, totalSamples]
  );
}

export function usePanelSelectedSamples(args?: { includeThumbnails?: boolean }) {
  const selectedIds = useStore((state) => state.selectedIds);
  const loadedSamples = useStore((state) => state.samples);
  const addSamplesIfMissing = useStore((state) => state.addSamplesIfMissing);
  const client = usePanelClient();
  const includeThumbnails = args?.includeThumbnails ?? false;
  const selectedIdsList = useMemo(() => Array.from(selectedIds), [selectedIds]);
  const selectedKey = selectedIdsList.join("\u0000");
  const [fetchedSamples, setFetchedSamples] = useState<Sample[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  React.useEffect(() => {
    setFetchedSamples((current) =>
      current.filter((sample) => selectedIds.has(sample.id))
    );
  }, [selectedIds]);

  React.useEffect(() => {
    let cancelled = false;
    const loadedIds = new Set(loadedSamples.map((sample) => sample.id));
    const fetchedIds = new Set(fetchedSamples.map((sample) => sample.id));
    const missingIds = selectedIdsList.filter(
      (id) => !loadedIds.has(id) && !fetchedIds.has(id)
    );

    if (missingIds.length === 0) {
      setLoading(false);
      setError(null);
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    setError(null);

    client
      .getSamplesByIds(missingIds, { includeThumbnails })
      .then((payload) => {
        if (cancelled) return;
        const samples = ((payload as { samples?: Sample[] }).samples ?? []);
        setFetchedSamples((current) => {
          const nextById = new Map(current.map((sample) => [sample.id, sample]));
          for (const sample of samples) {
            nextById.set(sample.id, sample);
          }
          return Array.from(nextById.values());
        });
        addSamplesIfMissing(samples);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    addSamplesIfMissing,
    client,
    fetchedSamples,
    includeThumbnails,
    loadedSamples,
    selectedIdsList,
    selectedKey,
  ]);

  const samples = useMemo(() => {
    const samplesById = new Map<string, Sample>();
    for (const sample of loadedSamples) {
      samplesById.set(sample.id, sample);
    }
    for (const sample of fetchedSamples) {
      samplesById.set(sample.id, sample);
    }
    return selectedIdsList
      .map((id) => samplesById.get(id) ?? null)
      .filter((sample): sample is Sample => sample !== null);
  }, [fetchedSamples, loadedSamples, selectedIdsList]);

  return useMemo(
    () => ({
      selectedIds: selectedIdsList,
      samples,
      loading,
      error,
    }),
    [error, loading, samples, selectedIdsList]
  );
}

export function usePanelLayouts() {
  const datasetInfo = usePanelDatasetInfo();

  return useMemo(() => {
    const layouts = datasetInfo?.layouts ?? [];
    const spaces = datasetInfo?.spaces ?? [];
    const spaceByKey = new Map(spaces.map((space) => [space.space_key, space]));
    const layoutByKey = new Map(layouts.map((layout) => [layout.layout_key, layout]));

    const matches = (layout: LayoutInfo, query: LayoutFindQuery) => {
      if (query.layoutKey && layout.layout_key !== query.layoutKey) return false;
      if (query.spaceKey && layout.space_key !== query.spaceKey) return false;
      if (query.geometry && layout.geometry !== query.geometry) return false;
      if (query.dimension && getLayoutDimension(layout.layout_key) !== query.dimension) return false;
      if (query.modelId) {
        const space = spaceByKey.get(layout.space_key);
        if (space?.model_id !== query.modelId) return false;
      }
      return true;
    };

    return {
      layouts,
      spaces,
      get: (layoutKey: string | null | undefined): LayoutInfo | null =>
        layoutKey ? layoutByKey.get(layoutKey) ?? null : null,
      getSpace: (spaceKey: string | null | undefined): SpaceInfo | null =>
        spaceKey ? spaceByKey.get(spaceKey) ?? null : null,
      find: (query: LayoutFindQuery): LayoutInfo | null =>
        layouts.find((layout) => matches(layout, query)) ?? null,
      filter: (query: LayoutFindQuery): LayoutInfo[] =>
        layouts.filter((layout) => matches(layout, query)),
    };
  }, [datasetInfo]);
}

export function usePanelRuntimeState() {
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const runtimeDatasetName = useStore((state) => state.runtimeDatasetName);
  const activeLayoutKey = useStore((state) => state.activeLayoutKey);
  const activeSimilarityQuery = useStore((state) => state.activeSimilarityQuery);
  const requestedLayoutKey = useStore((state) => state.requestedLayoutKey);
  const workspaces = useStore((state) => state.workspaces);
  const customPanels = useStore((state) => state.customPanels);
  const viewRevision = useStore((state) => state.viewRevision);
  const layoutViews = useStore((state) => state.layoutViews);

  return useMemo(
    () => ({
      activeWorkspaceId,
      runtimeDatasetName,
      activeLayoutKey,
      activeSimilarityQuery,
      requestedLayoutKey,
      workspaces,
      customPanels,
      viewRevision,
      layoutViews,
    }),
    [
      activeLayoutKey,
      activeSimilarityQuery,
      activeWorkspaceId,
      customPanels,
      layoutViews,
      requestedLayoutKey,
      runtimeDatasetName,
      viewRevision,
      workspaces,
    ]
  );
}

export function usePanelSelection() {
  const selectedIds = useStore((state) => state.selectedIds);
  const selectionSource = useStore((state) => state.selectionSource);

  return useMemo(
    () => ({
      selectedIds: Array.from(selectedIds),
      selectionSource,
    }),
    [selectedIds, selectionSource]
  );
}

export function usePanelHover() {
  const hoveredId = useStore((state) => state.hoveredId);
  const setHoveredId = useStore((state) => state.setHoveredId);

  return useMemo(
    () => ({
      hoveredId,
      setHoveredId,
      clearHover: () => setHoveredId(null),
    }),
    [hoveredId, setHoveredId]
  );
}

export function usePanelLayoutView(layoutKey?: string | null) {
  const activeLayoutKey = useStore((state) => state.activeLayoutKey);
  const layoutViews = useStore((state) => state.layoutViews);
  const setLayoutViewCamera = useStore((state) => state.setLayoutViewCamera);
  const resolvedLayoutKey = layoutKey ?? activeLayoutKey;

  return useMemo(
    () => {
      const view = resolvedLayoutKey ? layoutViews[resolvedLayoutKey] ?? { camera_3d: null } : null;

      return {
        layoutKey: resolvedLayoutKey,
        view,
        camera3d: view?.camera_3d ?? null,
        setCamera3d: (camera3d: OrbitView3DPayload | null) => {
          if (!resolvedLayoutKey) return;
          setLayoutViewCamera(resolvedLayoutKey, camera3d);
        },
      };
    },
    [layoutViews, resolvedLayoutKey, setLayoutViewCamera]
  );
}

export function usePanelUiState() {
  const sampleGridSize = useStore((state) => state.sampleGridSize);
  const setSampleGridSize = useStore((state) => state.setSampleGridSize);
  const scatterLabelOverlayMode = useStore((state) => state.scatterLabelOverlayMode);
  const setScatterLabelOverlayMode = useStore((state) => state.setScatterLabelOverlayMode);

  return useMemo(
    () => ({
      sampleGridSize,
      setSampleGridSize,
      scatterLabelOverlayMode,
      setScatterLabelOverlayMode,
    }),
    [sampleGridSize, scatterLabelOverlayMode, setSampleGridSize, setScatterLabelOverlayMode]
  );
}

export function usePanelHostState() {
  const instance = usePanelInstance();
  const runtime = usePanelRuntimeState();
  const datasetInfo = usePanelDatasetInfo();
  const samples = usePanelSamples();
  const samplesView = usePanelSamplesView();
  const selection = usePanelSelection();
  const hover = usePanelHover();
  const ui = usePanelUiState();
  const labelFilter = useStore((state) => state.labelFilter);
  const isLassoSelection = useStore((state) => state.isLassoSelection);
  const lassoQuery = useStore((state) => state.lassoQuery);
  const lassoSamples = useStore((state) => state.lassoSamples);
  const lassoTotal = useStore((state) => state.lassoTotal);
  const lassoIsLoading = useStore((state) => state.lassoIsLoading);
  const neighborsResults = useStore((state) => state.neighborsResults);
  const neighborsMetric = useStore((state) => state.neighborsMetric);
  const neighborsLoading = useStore((state) => state.neighborsLoading);
  const neighborsError = useStore((state) => state.neighborsError);

  return useMemo(
    () => ({
      instance,
      runtime,
      datasetInfo,
      samples,
      samplesView,
      selection,
      hover,
      ui,
      filters: {
        label: labelFilter,
      },
      lasso: {
        isSelection: isLassoSelection,
        query: lassoQuery,
        samples: lassoSamples,
        total: lassoTotal,
        isLoading: lassoIsLoading,
      },
      neighbors: {
        results: neighborsResults,
        metric: neighborsMetric,
        loading: neighborsLoading,
        error: neighborsError,
      },
    }),
    [
      datasetInfo,
      hover,
      instance,
      isLassoSelection,
      labelFilter,
      lassoIsLoading,
      lassoQuery,
      lassoSamples,
      lassoTotal,
      neighborsError,
      neighborsLoading,
      neighborsMetric,
      neighborsResults,
      runtime,
      samples,
      samplesView,
      selection,
      ui,
    ]
  );
}

export interface ToolRunState<TResult = unknown> {
  loading: boolean;
  result: TResult | null;
  error: string | null;
}

export interface ToolHandle<TResult = unknown> extends ToolRunState<TResult> {
  run: (params?: Record<string, unknown>) => Promise<TResult | null>;
  reset: () => void;
}

export function useTool<TResult = unknown>(uri: string): ToolHandle<TResult> {
  const workspaceId = useStore((state) => state.activeWorkspaceId);
  const [state, setState] = useState<ToolRunState<TResult>>({
    loading: false,
    result: null,
    error: null,
  });
  const inflight = useRef(0);

  const run = useCallback(
    async (params?: Record<string, unknown>) => {
      if (!workspaceId) {
        const message = "No active workspace";
        setState({ loading: false, result: null, error: message });
        return null;
      }
      const ticket = inflight.current + 1;
      inflight.current = ticket;
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const response = await fetch(apiUrl("/tools/run"), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            tool: uri,
            workspace_id: workspaceId,
            params: params ?? {},
          }),
        });
        if (!response.ok) {
          const body = await response.text();
          throw new Error(`${response.status} ${response.statusText}: ${body}`);
        }
        const payload = (await response.json()) as {
          ok: boolean;
          result?: TResult;
          error?: string;
        };
        if (ticket !== inflight.current) return null;
        if (payload.ok === false) {
          setState({
            loading: false,
            result: null,
            error: payload.error ?? "Tool call failed",
          });
          return null;
        }
        const result = (payload.result ?? null) as TResult | null;
        setState({ loading: false, result, error: null });
        return result;
      } catch (err) {
        if (ticket !== inflight.current) return null;
        const message = err instanceof Error ? err.message : String(err);
        setState({ loading: false, result: null, error: message });
        return null;
      }
    },
    [uri, workspaceId]
  );

  const reset = useCallback(() => {
    inflight.current += 1;
    setState({ loading: false, result: null, error: null });
  }, []);

  return useMemo(
    () => ({ ...state, run, reset }),
    [reset, run, state]
  );
}

export function usePanelCommands() {
  const dockview = useDockviewContext();
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const setLabelFilter = useStore((state) => state.setLabelFilter);
  const setHoveredId = useStore((state) => state.setHoveredId);
  const clearLassoSelection = useStore((state) => state.clearLassoSelection);
  const setSelectedIds = useStore((state) => state.setSelectedIds);
  const setLayoutViewCamera = useStore((state) => state.setLayoutViewCamera);
  const setActiveLayoutKey = useStore((state) => state.setActiveLayoutKey);
  const setActiveSimilarityQuery = useStore((state) => state.setActiveSimilarityQuery);

  return useMemo(
    () => {
      const persistActiveLayout = async (
        layoutKey: string | null,
      ): Promise<RuntimeSnapshot> => {
        if (!activeWorkspaceId) {
          throw new Error("No active workspace");
        }
        await fetchJson(apiUrl("/control/ui/layout"), {
          method: "POST",
          body: JSON.stringify({
            workspace_id: activeWorkspaceId,
            layout_key: layoutKey,
          }),
        });
        const snapshot = await fetchJson<RuntimeSnapshot>(
          buildUrl(apiUrl("/runtime"), { workspace_id: activeWorkspaceId })
        );
        applyRuntimeSnapshot(snapshot);
        setActiveLayoutKey(layoutKey);
        return snapshot;
      };

      const persistSelection = async (
        ids: string[],
        source: SelectionUpdateSource
      ): Promise<RuntimeSnapshot> => {
        if (!activeWorkspaceId) {
          throw new Error("No active workspace");
        }
        const sampleIds = Array.from(new Set(ids));
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
        setSelectedIds(new Set(sampleIds), source);
        return snapshot;
      };

      const persistSimilarityQuery = async (
        options: SimilarityCommandOptions,
        source: string | null
      ): Promise<RuntimeSnapshot> => {
        if (!activeWorkspaceId) {
          throw new Error("No active workspace");
        }
        await fetchJson(apiUrl("/control/ui/similarity"), {
          method: "POST",
          body: JSON.stringify({
            workspace_id: activeWorkspaceId,
            sample_id: options.sampleId,
            layout_key: options.layoutKey ?? null,
            space_key: options.spaceKey ?? null,
            k: options.k ?? 18,
            source,
          }),
        });
        const snapshot = await fetchJson<RuntimeSnapshot>(
          buildUrl(apiUrl("/runtime"), { workspace_id: activeWorkspaceId })
        );
        applyRuntimeSnapshot(snapshot);
        return snapshot;
      };

      const persistRuntimeUiPatch = (patch: RuntimeUiPatch): void => {
        if (!activeWorkspaceId) {
          console.warn("Skipping background UI persistence: no active workspace");
          return;
        }

        void fetchJson(apiUrl("/control/ui/state"), {
          method: "PATCH",
          body: JSON.stringify({
            workspace_id: activeWorkspaceId,
            client_id: getRuntimeClientId(),
            ...patch,
          }),
        }).catch((error) => {
          console.error("Failed to persist runtime UI state:", error);
        });
      };

      const setSelection = async (
        ids: string[],
        options: SelectionCommandOptions = {},
      ): Promise<RuntimeSnapshot | null> => {
        const source = options.source ?? "panel";
        if (options.clearLasso ?? true) {
          clearLassoSelection();
        }
        const sampleIds = Array.from(new Set(ids));
        setSelectedIds(new Set(sampleIds), source);

        const persistenceMode = getPersistenceMode(options.persist);
        if (persistenceMode === "none") return null;
        if (persistenceMode === "background") {
          persistRuntimeUiPatch({
            set_selection: true,
            selected_ids: sampleIds,
          });
          return null;
        }

        return persistSelection(sampleIds, source);
      };

      const showSimilar = async (
        options: SimilarityCommandOptions,
      ): Promise<RuntimeSnapshot | null> => {
        const source = options.source ?? "panel";
        const sampleId = options.sampleId;
        if (!sampleId) {
          throw new Error("sampleId is required");
        }
        const query: SimilarityQuery = {
          anchor_sample_id: sampleId,
          layout_key: options.layoutKey ?? null,
          space_key: options.spaceKey ?? null,
          k: options.k ?? 18,
          source,
        };
        clearLassoSelection();
        setSelectedIds(new Set([sampleId]), "panel");
        setActiveSimilarityQuery(query);

        if (options.focus) {
          const panelId = getPanelIdForBuiltinRole(options.focus);
          if (panelId) focusDockPanel(dockview.api, panelId);
        }

        const persistenceMode = getPersistenceMode(options.persist);
        if (persistenceMode === "none") {
          return null;
        }

        if (persistenceMode === "background") {
          persistRuntimeUiPatch({
            set_selection: true,
            selected_ids: [sampleId],
            set_similarity_query: true,
            similarity_query: {
              sample_id: sampleId,
              layout_key: options.layoutKey ?? null,
              space_key: options.spaceKey ?? null,
              k: options.k ?? 18,
              source,
            },
          });
          return null;
        }

        return persistSimilarityQuery(options, source);
      };

      return {
        setLabelFilter,
        setHoveredId,
        clearLassoSelection,
        clearSelection: (options: SelectionCommandOptions = {}) =>
          setSelection([], options),
        setActiveLayout: async (layoutKey: string | null, options: LayoutCommandOptions = {}) => {
          setActiveLayoutKey(layoutKey);
          const persistenceMode = getPersistenceMode(options.persist);
          if (persistenceMode === "none") return null;
          if (persistenceMode === "background") {
            persistRuntimeUiPatch({
              set_active_layout: true,
              active_layout_key: layoutKey,
            });
            return null;
          }
          return persistActiveLayout(layoutKey);
        },
        setSelection,
        showSimilar,
        setLayoutViewCamera,
        setLayoutViewCameraPersisted: async (
          layoutKey: string,
          camera3d: OrbitView3DPayload | null
        ) => {
          setLayoutViewCamera(layoutKey, camera3d);
          if (!activeWorkspaceId) return null;
          await fetchJson(apiUrl("/control/ui/layout-view"), {
            method: "POST",
            body: JSON.stringify({
              workspace_id: activeWorkspaceId,
              layout_key: layoutKey,
              camera_3d: camera3d,
            }),
          });
          return null;
        },
        focusBuiltin: (role: BuiltinPanelRole) => {
          const panelId = getPanelIdForBuiltinRole(role);
          return panelId ? focusDockPanel(dockview.api, panelId) : false;
        },
        focusPanelByRole: (role: BuiltinPanelRole) => {
          const panelId = getPanelIdForBuiltinRole(role);
          return panelId ? focusDockPanel(dockview.api, panelId) : false;
        },
        focusPanel: (panelId: string) => {
          return focusDockPanel(dockview.api, panelId);
        },
        closePanel: (panelId: string) => {
          const api = dockview.api;
          if (!api) return false;

          const runtimePanelId = `runtime-panel:${panelId}`;
          const panel = api.getPanel(panelId) ?? api.getPanel(runtimePanelId);
          if (!panel) return false;

          panel.api.close();
          return true;
        },
      };
    },
    [
      activeWorkspaceId,
      applyRuntimeSnapshot,
      clearLassoSelection,
      dockview.api,
      setActiveLayoutKey,
      setActiveSimilarityQuery,
      setHoveredId,
      setLabelFilter,
      setSelectedIds,
      setLayoutViewCamera,
    ]
  );
}

function getPanelIdForBuiltinRole(role: BuiltinPanelRole): string | null {
  if (role === "samples") return PANEL.GRID;
  if (role === "labels" || role === "explorer") return PANEL.EXPLORER;
  if (role === "scatter") return PANEL.SCATTER_DEFAULT;
  if (role === "euclidean") return PANEL.SCATTER_EUCLIDEAN;
  if (role === "hyperbolic") return PANEL.SCATTER_POINCARE;
  if (role === "spherical") return PANEL.SCATTER_SPHERICAL;
  return null;
}

function focusDockPanel(
  api: ReturnType<typeof useDockviewContext>["api"],
  panelId: string
) {
  if (!api) return false;

  const runtimePanelId = `runtime-panel:${panelId}`;
  const panel = api.getPanel(panelId) ?? api.getPanel(runtimePanelId);
  if (!panel) return false;

  panel.api.setActive();
  panel.focus();
  return true;
}

export interface HyperViewPanelSdkGlobal {
  version: "1";
  React: typeof React;
  components: {
    Panel: typeof Panel;
    PanelHeader: typeof PanelHeader;
    PanelTitle: typeof PanelTitle;
    PanelToolbar: typeof PanelToolbar;
    PanelToolbarButton: typeof PanelToolbarButton;
    PanelToolbarMenu: typeof PanelToolbarMenu;
  };
  hooks: {
    usePanelClient: typeof usePanelClient;
    usePanelCommands: typeof usePanelCommands;
    usePanelDatasetInfo: typeof usePanelDatasetInfo;
    usePanelHostState: typeof usePanelHostState;
    usePanelHover: typeof usePanelHover;
    usePanelLayouts: typeof usePanelLayouts;
    usePanelRuntimeState: typeof usePanelRuntimeState;
    usePanelLayoutView: typeof usePanelLayoutView;
    usePanelInstance: typeof usePanelInstance;
    usePanelProps: typeof usePanelProps;
    usePanelSamples: typeof usePanelSamples;
    usePanelSamplesView: typeof usePanelSamplesView;
    usePanelSelectedSamples: typeof usePanelSelectedSamples;
    usePanelSelection: typeof usePanelSelection;
    usePanelUiState: typeof usePanelUiState;
    useTool: typeof useTool;
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
    version: "1",
    React,
    components: {
      Panel,
      PanelHeader,
      PanelTitle,
      PanelToolbar,
      PanelToolbarButton,
      PanelToolbarMenu,
    },
    hooks: {
      usePanelClient,
      usePanelCommands,
      usePanelDatasetInfo,
      usePanelHostState,
      usePanelHover,
      usePanelInstance,
      usePanelLayouts,
      usePanelLayoutView,
      usePanelProps,
      usePanelRuntimeState,
      usePanelSamples,
      usePanelSamplesView,
      usePanelSelectedSamples,
      usePanelSelection,
      usePanelUiState,
      useTool,
    },
    createClient: createHyperViewPanelClient,
  };
}

export {
  Panel,
  PanelHeader,
  PanelTitle,
  PanelToolbar,
  PanelToolbarButton,
  PanelToolbarMenu,
};

export type { PanelToolbarItem };
