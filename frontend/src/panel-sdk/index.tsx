"use client";

import React, { useCallback, useMemo } from "react";

import { useDockviewContext } from "@/components/DockviewContext";
import { usePanelInstance } from "@/components/PanelHostContext";
import {
  apiUrl,
  getRuntimeClientId,
  runControlCommand,
  runtimeSnapshotFromCommandResult,
  type ControlCommandResult,
} from "@/lib/api";
import { RUNTIME_PANEL_PREFIX } from "@/lib/dockviewPanelPolicy";
import { useStore } from "@/store/useStore";
import type { RuntimeCollection, RuntimeSnapshot, Sample } from "@/types";

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

export function usePanelState() {
  const instance = usePanelInstance();
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);

  const patchState = useCallback(
    async (
      statePatch: Record<string, unknown>,
      args?: {
        replaceState?: boolean;
        expectedRevision?: number | null;
      }
    ) => {
      if (!activeWorkspaceId || !instance.panelId) {
        throw new Error("No active panel instance");
      }
      const payload = await runControlCommand({
        command: "workspace.panel.state.patch",
        target: {
          workspace_id: activeWorkspaceId,
          panel_id: instance.panelId,
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
    [activeWorkspaceId, applyRuntimeSnapshot, instance.panelId]
  );

  return useMemo(
    () => ({
      panel: instance.panel,
      panelId: instance.panelId,
      props: instance.props,
      state: instance.state,
      stateRevision: instance.stateRevision,
      patchState,
    }),
    [
      instance.panel,
      instance.panelId,
      instance.props,
      instance.state,
      instance.stateRevision,
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

  const persistSelection = useCallback(
    async (ids: string[]) => {
      if (!activeWorkspaceId) {
        throw new Error("No active workspace");
      }
      const sampleIds = Array.from(new Set(ids));
      clearLassoSelection();
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
    [activeWorkspaceId, applyRuntimeSnapshot, clearLassoSelection]
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

function sampleMatchesCollection(sample: Sample, collection: RuntimeCollection | null) {
  if (!collection || collection.kind === "all") return true;
  if (collection.kind === "selection") return true;
  if (collection.kind !== "filter") return false;

  const { field, op, value } = collection.query;
  if (field !== "label" || op !== "eq") return false;
  return sample.label === (typeof value === "string" ? value : null);
}

export function useSamples(collectionId?: string | null) {
  const collection = useCollection(collectionId);
  const samples = useStore((state) => state.samples);
  const totalSamples = useStore((state) => state.totalSamples);
  const isLoading = useStore((state) => state.isLoading);
  const error = useStore((state) => state.error);

  return useMemo(() => {
    const filteredSamples = samples.filter((sample) =>
      sampleMatchesCollection(sample, collection)
    );
    return {
      collection,
      samples: filteredSamples,
      total: collection ? filteredSamples.length : totalSamples,
      loading: isLoading,
      error,
    };
  }, [collection, error, isLoading, samples, totalSamples]);
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
      useHostAdapter,
    },
    createClient: createHyperViewPanelClient,
  };
}
