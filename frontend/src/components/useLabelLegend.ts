import { useMemo } from "react";

import type { DatasetInfo, EmbeddingsData } from "@/types";
import {
  buildLabelColorMap,
  buildLabelCounts,
  buildLabelUniverse,
  buildLabelsInfo,
  buildLegendLabels,
} from "@/lib/labelLegend";
import { useColorSettings } from "@/store/useColorSettings";

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
  const labelColorMapId = useColorSettings((state) => state.labelColorMapId);

  const labelCounts = useMemo(() => buildLabelCounts(embeddings), [embeddings]);

  const labelUniverse = useMemo(
    () => buildLabelUniverse(datasetInfo?.labels ?? [], embeddings?.labels ?? null),
    [datasetInfo?.labels, embeddings?.labels]
  );

  const labelsInfo = useMemo(
    () =>
      buildLabelsInfo({
        datasetLabels: datasetInfo?.labels ?? [],
        embeddings,
        labelColorMapId,
        labelFilter,
      }),
    [datasetInfo?.labels, embeddings, labelColorMapId, labelFilter]
  );

  const labelColorMap = useMemo(
    () =>
      buildLabelColorMap({
        labelsInfo,
        labelUniverse,
        labelColorMapId,
        labelFilter,
      }),
    [labelsInfo, labelUniverse, labelColorMapId, labelFilter]
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
    labelsInfo,
    labelColorMap,
    legendLabels,
  };
}
