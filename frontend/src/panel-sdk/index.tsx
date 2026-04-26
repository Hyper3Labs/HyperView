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
import { useHyperViewSamplesView } from "@/panels/runtime";
import { useStore } from "@/store/useStore";

type SelectionUpdateSource = "scatter" | "grid";

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

export function createHyperViewPanelClient(workspaceId: string | null) {
  return {
    async getDatasetInfo() {
      return fetchJson(buildUrl("/api/dataset", { workspace_id: workspaceId }));
    },
    async getRuntime() {
      return fetchJson(buildUrl("/api/runtime", { workspace_id: workspaceId }));
    },
    async listSamples(args?: {
      offset?: number;
      limit?: number;
      includeThumbnails?: boolean;
    }) {
      return fetchJson(
        buildUrl("/api/samples", {
          workspace_id: workspaceId,
          offset: args?.offset ?? 0,
          limit: args?.limit ?? 100,
          include_thumbnails: args?.includeThumbnails ?? true,
        })
      );
    },
    async getEmbeddings(layoutKey?: string | null) {
      return fetchJson(
        buildUrl("/api/embeddings", {
          workspace_id: workspaceId,
          layout_key: layoutKey ?? undefined,
        })
      );
    },
    async setSelection(sampleIds: string[]) {
      return fetchJson("/api/control/ui/selection", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, sample_ids: sampleIds }),
      });
    },
    async setLayout(layoutKey: string | null) {
      return fetchJson("/api/control/ui/layout", {
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

export function usePanelRuntimeState() {
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const runtimeDatasetName = useStore((state) => state.runtimeDatasetName);
  const activeLayoutKey = useStore((state) => state.activeLayoutKey);
  const requestedLayoutKey = useStore((state) => state.requestedLayoutKey);
  const workspaces = useStore((state) => state.workspaces);
  const customPanels = useStore((state) => state.customPanels);

  return useMemo(
    () => ({
      activeWorkspaceId,
      runtimeDatasetName,
      activeLayoutKey,
      requestedLayoutKey,
      workspaces,
      customPanels,
    }),
    [
      activeLayoutKey,
      activeWorkspaceId,
      customPanels,
      requestedLayoutKey,
      runtimeDatasetName,
      workspaces,
    ]
  );
}

export function usePanelSelection() {
  const selectedIds = useStore((state) => state.selectedIds);
  const selectionSource = useStore((state) => state.selectionSource);
  const setSelectedIds = useStore((state) => state.setSelectedIds);
  const clearSelection = useStore((state) => state.clearSelection);

  return useMemo(
    () => ({
      selectedIds: Array.from(selectedIds),
      selectionSource,
      setSelection: (ids: string[], source: SelectionUpdateSource = "grid") => {
        setSelectedIds(new Set(ids), source);
      },
      clearSelection,
    }),
    [clearSelection, selectedIds, selectionSource, setSelectedIds]
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
        const response = await fetch("/api/tools/run", {
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
  const setLabelFilter = useStore((state) => state.setLabelFilter);
  const setHoveredId = useStore((state) => state.setHoveredId);
  const clearLassoSelection = useStore((state) => state.clearLassoSelection);
  const clearSelection = useStore((state) => state.clearSelection);
  const setSelectedIds = useStore((state) => state.setSelectedIds);

  return useMemo(
    () => ({
      setLabelFilter,
      setHoveredId,
      clearLassoSelection,
      clearSelection,
      setSelection: (ids: string[], source: SelectionUpdateSource = "grid") => {
        setSelectedIds(new Set(ids), source);
      },
      focusPanel: (panelId: string) => {
        const api = dockview.api;
        if (!api) return false;

        const runtimePanelId = `runtime-panel:${panelId}`;
        const panel = api.getPanel(panelId) ?? api.getPanel(runtimePanelId);
        if (!panel) return false;

        panel.focus();
        return true;
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
    }),
    [clearLassoSelection, clearSelection, dockview.api, setHoveredId, setLabelFilter, setSelectedIds]
  );
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
    usePanelRuntimeState: typeof usePanelRuntimeState;
    usePanelSamples: typeof usePanelSamples;
    usePanelSamplesView: typeof usePanelSamplesView;
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
      usePanelRuntimeState,
      usePanelSamples,
      usePanelSamplesView,
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