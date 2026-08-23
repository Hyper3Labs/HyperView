"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";
import type { DockviewApi, EdgeGroupPosition } from "dockview-react";

const EMPTY_PANEL_SIGNATURE = "";
const PANEL_SIGNATURE_SEPARATOR = "\u0000";
const EMPTY_EDGE_SIGNATURE = "";
const EDGE_SIGNATURE_SEPARATOR = "\u0000";

type DockviewEdgeZone = Extract<EdgeGroupPosition, "left" | "right" | "bottom">;

function getOpenPanelSignature(api: DockviewApi | null, panelIds: readonly string[]) {
  if (!api || panelIds.length === 0) {
    return EMPTY_PANEL_SIGNATURE;
  }

  return panelIds.filter((panelId) => Boolean(api.getPanel(panelId))).join(PANEL_SIGNATURE_SEPARATOR);
}

function isEdgeZoneOpen(api: DockviewApi | null, zone: DockviewEdgeZone) {
  if (!api) return false;
  const group = api.getEdgeGroup(zone);
  return Boolean(group && api.isEdgeGroupVisible(zone) && !group.isCollapsed());
}

function getOpenEdgeZoneSignature(
  api: DockviewApi | null,
  zones: readonly DockviewEdgeZone[]
) {
  if (!api || zones.length === 0) {
    return EMPTY_EDGE_SIGNATURE;
  }

  return zones
    .filter((zone) => isEdgeZoneOpen(api, zone))
    .join(EDGE_SIGNATURE_SEPARATOR);
}

export interface DockviewContextValue {
  api: DockviewApi | null;
  setApi: (api: DockviewApi) => void;
  edgeStateRevision: number;
  notifyEdgeStateChange: () => void;
}

export const DockviewContext = createContext<DockviewContextValue | null>(null);

export function useDockviewContext() {
  const ctx = useContext(DockviewContext);
  if (!ctx) {
    throw new Error("useDockviewContext must be used within DockviewProvider");
  }
  return ctx;
}

export function useDockviewOpenPanelIds(panelIds: readonly string[]): ReadonlySet<string> {
  const ctx = useContext(DockviewContext);
  const api = ctx?.api ?? null;

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (!api) {
        return () => {};
      }

      const disposables = [
        api.onDidAddPanel(() => onStoreChange()),
        api.onDidRemovePanel(() => onStoreChange()),
        api.onDidLayoutChange(() => onStoreChange()),
      ];

      return () => {
        for (const disposable of disposables) {
          disposable.dispose();
        }
      };
    },
    [api]
  );

  const getSnapshot = useCallback(
    () => getOpenPanelSignature(api, panelIds),
    [api, panelIds]
  );

  const signature = useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_PANEL_SIGNATURE);

  return useMemo(
    () => new Set(signature ? signature.split(PANEL_SIGNATURE_SEPARATOR) : []),
    [signature]
  );
}

export function useDockviewOpenEdgeZones(
  zones: readonly DockviewEdgeZone[]
): ReadonlySet<DockviewEdgeZone> {
  const ctx = useContext(DockviewContext);
  const api = ctx?.api ?? null;
  const edgeStateRevision = ctx?.edgeStateRevision ?? 0;

  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (!api) {
        return () => {};
      }

      const disposables = [
        api.onDidAddGroup(() => onStoreChange()),
        api.onDidRemoveGroup(() => onStoreChange()),
        api.onDidAddPanel(() => onStoreChange()),
        api.onDidRemovePanel(() => onStoreChange()),
        api.onDidMovePanel(() => onStoreChange()),
        api.onDidLayoutFromJSON(() => onStoreChange()),
        api.onDidLayoutChange(() => onStoreChange()),
      ];

      return () => {
        for (const disposable of disposables) {
          disposable.dispose();
        }
      };
    },
    [api]
  );

  const getSnapshot = useCallback(
    () => `${edgeStateRevision}:${getOpenEdgeZoneSignature(api, zones)}`,
    [api, edgeStateRevision, zones]
  );

  const signature = useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_EDGE_SIGNATURE);
  const openZoneSignature = signature.includes(":")
    ? signature.slice(signature.indexOf(":") + 1)
    : signature;

  return useMemo(
    () =>
      new Set(
        openZoneSignature
          ? (openZoneSignature.split(EDGE_SIGNATURE_SEPARATOR) as DockviewEdgeZone[])
          : []
      ),
    [openZoneSignature]
  );
}
