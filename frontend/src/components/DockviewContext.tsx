"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
} from "react";
import type { DockviewApi } from "dockview";

import type { SamplesViewModel } from "@/lib/sampleCollections";

const EMPTY_PANEL_SIGNATURE = "";
const PANEL_SIGNATURE_SEPARATOR = "\u0000";

function getOpenPanelSignature(api: DockviewApi | null, panelIds: readonly string[]) {
  if (!api || panelIds.length === 0) {
    return EMPTY_PANEL_SIGNATURE;
  }

  return panelIds.filter((panelId) => Boolean(api.getPanel(panelId))).join(PANEL_SIGNATURE_SEPARATOR);
}

export interface DockviewContextValue {
  api: DockviewApi | null;
  setApi: (api: DockviewApi) => void;
  samplesView: SamplesViewModel;
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