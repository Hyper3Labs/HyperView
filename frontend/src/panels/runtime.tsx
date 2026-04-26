"use client";

import { useDockviewContext } from "@/components/DockviewContext";
import type { SamplesViewModel } from "@/lib/sampleCollections";

export function useHyperViewSamplesView(): SamplesViewModel {
  return useDockviewContext().samplesView;
}