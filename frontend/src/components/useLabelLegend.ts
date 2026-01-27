import { useMemo } from "react";

import type { DatasetInfo, EmbeddingsData } from "@/types";
import {
  MAX_DISTINCT_LABEL_COLORS,
  buildLabelColorMap,
  buildLabelCounts,
  buildLabelUniverse,
  buildLabelsInfo,
  buildLegendLabels,
  getDistinctLabelCount,
} from "@/lib/labelLegend";

interface UseLabelLegendArgs {
  datasetInfo: DatasetInfo | null;
  embeddings: EmbeddingsData | null;
  labelSearch?: string;
  labelFilter?: string | null;
}

export function useLabelLegend({
  datasetInfo,
  embeddings,
  labelSearch = "",
  labelFilter = null,
}: UseLabelLegendArgs) {
  const labelCounts = useMemo(() => buildLabelCounts(embeddings), [embeddings]);

  const labelUniverse = useMemo(
    () => buildLabelUniverse(datasetInfo?.labels ?? [], embeddings?.labels ?? null),
    [datasetInfo?.labels, embeddings?.labels]
  );

  const distinctLabelCount = useMemo(() => {
    const fromCounts = getDistinctLabelCount(labelCounts);
    if (fromCounts > 0) return fromCounts;
    let n = labelUniverse.length;
    if (labelUniverse.includes("undefined")) n -= 1;
    return n;
  }, [labelCounts, labelUniverse]);

  const distinctColoringDisabled = distinctLabelCount > MAX_DISTINCT_LABEL_COLORS;

  const labelsInfo = useMemo(
    () =>
      buildLabelsInfo({
        datasetLabels: datasetInfo?.labels ?? [],
        embeddings,
        distinctColoringDisabled,
        labelFilter,
      }),
    [datasetInfo?.labels, embeddings, distinctColoringDisabled, labelFilter]
  );

  const labelColorMap = useMemo(
    () =>
      buildLabelColorMap({
        labelsInfo,
        labelUniverse,
        distinctColoringDisabled,
        labelFilter,
      }),
    [labelsInfo, labelUniverse, distinctColoringDisabled, labelFilter]
  );

  const legendLabels = useMemo(
    () =>
      buildLegendLabels({
        labelUniverse,
        labelCounts,
        query: labelSearch,
      }),
    [labelUniverse, labelCounts, labelSearch]
  );

  return {
    labelCounts,
    labelUniverse,
    distinctLabelCount,
    distinctColoringDisabled,
    labelsInfo,
    labelColorMap,
    legendLabels,
  };
}
