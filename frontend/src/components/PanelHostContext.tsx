"use client";

import React from "react";

import type { RuntimePanel } from "@/types";

interface PanelInstanceContextValue {
  panel: RuntimePanel | null;
  panelId: string | null;
  props: Record<string, unknown>;
  state: Record<string, unknown>;
  stateRevision: number;
}

const PanelInstanceContext = React.createContext<PanelInstanceContextValue | null>(null);

export function PanelInstanceProvider({
  value,
  children,
}: {
  value: PanelInstanceContextValue;
  children: React.ReactNode;
}) {
  return (
    <PanelInstanceContext.Provider value={value}>
      {children}
    </PanelInstanceContext.Provider>
  );
}

export function usePanelInstance() {
  return (
    React.useContext(PanelInstanceContext) ?? {
      panel: null,
      panelId: null,
      props: {},
      state: {},
      stateRevision: 0,
    }
  );
}
