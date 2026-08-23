"use client";

import { useEffect, useRef, useState } from "react";

import { fetchRuntimeState, getRuntimeEventsUrl, isStaticBundle } from "@/lib/api";
import { useStore } from "@/store/useStore";
import type { RuntimeSnapshot } from "@/types";

export function useRuntimeSync(
  onRuntimeRefresh?: (snapshot: RuntimeSnapshot) => Promise<void> | void
): { runtimeResetKey: string; runtimeReady: boolean; runtimeVersion: number } {
  const applyRuntimeSnapshot = useStore((state) => state.applyRuntimeSnapshot);
  const activeWorkspaceId = useStore((state) => state.activeWorkspaceId);
  const runtimeDatasetName = useStore((state) => state.runtimeDatasetName);
  const refreshRef = useRef(onRuntimeRefresh);
  const lastAppliedRuntimeIdRef = useRef<string | null>(null);
  const lastAppliedVersionRef = useRef(-1);
  const [runtimeReady, setRuntimeReady] = useState(false);
  const [runtimeVersion, setRuntimeVersion] = useState(-1);

  useEffect(() => {
    refreshRef.current = onRuntimeRefresh;
  }, [onRuntimeRefresh]);

  useEffect(() => {
    let cancelled = false;

    const handleSnapshot = async (snapshot: RuntimeSnapshot) => {
      if (cancelled) return;

      if (snapshot.runtime_id !== lastAppliedRuntimeIdRef.current) {
        lastAppliedRuntimeIdRef.current = snapshot.runtime_id;
        lastAppliedVersionRef.current = -1;
      }

      if (snapshot.version <= lastAppliedVersionRef.current) return;

      lastAppliedVersionRef.current = snapshot.version;
      applyRuntimeSnapshot(snapshot);
      setRuntimeVersion(snapshot.version);
      setRuntimeReady(true);
      if (refreshRef.current) {
        await refreshRef.current(snapshot);
      }
    };

    const bootstrap = async () => {
      try {
        const snapshot = await fetchRuntimeState();
        await handleSnapshot(snapshot);
      } catch (err) {
        console.error("Failed to bootstrap runtime state:", err);
        setRuntimeReady(true);
      }
    };

    void bootstrap();

    if (isStaticBundle()) {
      return () => {
        cancelled = true;
      };
    }

    const events = new EventSource(getRuntimeEventsUrl());
    events.onmessage = (event) => {
      try {
        const snapshot = JSON.parse(event.data) as RuntimeSnapshot;
        void handleSnapshot(snapshot);
      } catch (err) {
        console.error("Failed to parse runtime event:", err);
      }
    };
    events.onerror = () => {
      console.error("Runtime event stream disconnected");
    };

    return () => {
      cancelled = true;
      events.close();
    };
  }, [applyRuntimeSnapshot]);

  return {
    runtimeResetKey: `${activeWorkspaceId ?? "none"}:${runtimeDatasetName ?? "none"}`,
    runtimeReady,
    runtimeVersion,
  };
}
