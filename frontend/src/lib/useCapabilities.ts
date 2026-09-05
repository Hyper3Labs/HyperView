"use client";

import { useSyncExternalStore } from "react";

import {
  getCapabilities,
  getServerCapabilities,
  subscribeToCapabilities,
  type Capabilities,
} from "@/lib/api";

/**
 * What this host lets the viewer do.
 *
 * One table defines it (src/hyperview/capabilities.py). A Static Space reports
 * it in the bundle manifest, a live server at `GET /api/capabilities`, and the
 * generated table stands in until whichever of those answers -- so a component
 * asks "can I do this here" instead of "am I a static bundle".
 *
 * The first render returns what the hosting mode permits; the object is
 * replaced once, when the host's own answer arrives.
 */
export function useCapabilities(): Capabilities {
  return useSyncExternalStore(
    subscribeToCapabilities,
    getCapabilities,
    getServerCapabilities
  );
}

/** One capability, for the common case of a single boolean gate. */
export function useCapability<K extends keyof Capabilities>(key: K): Capabilities[K] {
  return useCapabilities()[key];
}
